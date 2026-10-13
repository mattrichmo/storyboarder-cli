"""Opt-in observation-v2 review envelope. Existing v1 code and hashes are untouched."""
from __future__ import annotations

import json
from storyboarder.domain.errors import Conflict, NotFound, StoryboardError
from storyboarder.domain.models import now, uid
from storyboarder.domain.spatial import SpatialReview, checked, sha, SpatialError, EVALUATOR
from .spatial_plans import SpatialPlans, unpack, raw_hash, bounds, page


def planning_context(service,conn,shot_id):
    """Same ancestor order and append/replace/exclude semantics, only two keys."""
    chain=[];item=service.entity(conn,shot_id,active=False);seen=set()
    while item:
        if item["id"] in seen:raise SpatialError("Story ancestry cycle.",code="spatial_integrity")
        seen.add(item["id"]);chain.append(item)
        item=service.entity(conn,item["parent_id"],active=False) if item.get("parent_id") else None
    result={"light":[],"blocking":[]}
    for item in reversed(chain):
        for key in result:
            if item["fields"].get(key):result[key].append({"owner_id":item["id"],"text":item["fields"][key]})
        for row in conn.execute("SELECT key,operation,text,id FROM context_blocks WHERE owner_id=? AND key IN ('light','blocking') ORDER BY key,id",(item["id"],)):
            if row["operation"] in ("replace","exclude"):result[row["key"]]=[]
            if row["operation"]!="exclude" and row["text"]:result[row["key"]].append({"owner_id":item["id"],"block_id":row["id"],"text":row["text"]})
    return result


class SpatialReviews:
    def __init__(self,service):
        self.service,self.repo=service,service.repo
        self.plans=SpatialPlans(service)

    def _basis(self,conn,shot_id,body,*,historical=False):
        # Connection-bound v1 helpers are read without changing v1 constants,
        # validation, schema, published heads or source semantics.
        from .observation_contracts import ObservationContracts
        obs=ObservationContracts(self.service)
        row=conn.execute("SELECT v.*,c.shot_id FROM observation_contract_versions v JOIN observation_contracts c ON c.id=v.contract_id WHERE v.id=? AND v.sealed=1",(body["observation_version_id"],)).fetchone()
        if not row or row["shot_id"]!=shot_id:raise SpatialError("Review needs a v1 observation for this same shot.",code="spatial_scope_mismatch")
        header,version=obs._version(conn,row["contract_id"],row["id"])
        validation=obs._validate(conn,header,version)
        if validation["status"]=="conflict":raise SpatialError("The exact v1 observation has an integrity conflict.",{"findings":validation["findings"][:50]},"spatial_integrity")
        binding=self.plans._binding_version(conn,body["binding_version_id"])
        bh=self.plans._binding_header(conn,binding_id=binding["binding_id"])
        if bh["shot_id"]!=shot_id:raise SpatialError("Review needs a binding for the same shot.",code="spatial_scope_mismatch")
        if not historical and (binding["binding_json"]["status"]!="active" or bh["current_version_id"]!=binding["id"]):
            raise SpatialError("Review the current active binding. Historical envelopes remain readable.")
        setup=self.plans._version(conn,binding["setup_version_id"])
        pins=self.plans._preserved(conn,setup)
        reference_status=[]
        for p in pins["asset"]:
            asset,current=self.plans._asset(conn,p["asset_id"],False)
            reference_status.append({"asset_id":p["asset_id"],"pinned":p["semantic_sha256"],"current":sha(current),"archived":bool(asset["archived"])})
        v1_live=obs._basis(conn,shot_id,json.loads(version["contract_json"]))
        basis={"schema":"storyboarder.observation-spatial-basis/v1","project_id":self.plans.project_id,"shot_id":shot_id,
               "observation_version_id":version["id"],"observation_content_sha256":version["content_sha256"],"observation_basis_sha256":version["basis_sha256"],"current_v1_basis_sha256":sha(v1_live),
               "binding_version_id":binding["id"],"binding_sha256":binding["content_sha256"],"setup_version_id":setup["id"],"setup_content_sha256":setup["content_sha256"],"physical_sha256":setup["basis_json"]["physical_sha256"],
               "camera_plan_id":binding["binding_json"]["camera_plan_id"],"sample":binding["binding_json"]["sample"],"time_mapping":binding["binding_json"]["time_mapping"],
               "evaluator":EVALUATOR,"lighting_model":"authored-cone-and-area-envelope/v1","planning_context":planning_context(self.service,conn,shot_id),
               "reference_status":reference_status,"source_status":validation["source_pins"],"scale":setup["payload_json"]["scale"],"floor_plans":setup["payload_json"]["floor_plans"]}
        return basis,validation,header,bh,setup

    def _candidate(self,conn,shot_id,expected_previous_number,review):
        self.plans._entity(conn,shot_id,"shot")
        if type(expected_previous_number) is not int or expected_previous_number<0:raise SpatialError("Previous review number must be a nonnegative integer.")
        previous=unpack(conn.execute("SELECT * FROM observation_spatial_reviews WHERE shot_id=? ORDER BY number DESC LIMIT 1",(shot_id,)).fetchone())
        current=previous["number"] if previous else 0
        if current!=expected_previous_number:raise Conflict("Another spatial review was saved. Your review is still local.",{"current_number":current,"expected":expected_previous_number})
        basis,validation,*_=self._basis(conn,shot_id,review)
        token=sha({"schema":"storyboarder.spatial-review-publication/v1","project_id":self.plans.project_id,"shot_id":shot_id,"previous_number":current,"review":review,"basis":basis})
        return previous,basis,validation,token

    def preview(self,shot_id,expected_previous_number,review):
        review=checked(review,SpatialReview)
        with self.repo.transaction(False) as conn:
            previous,basis,validation,token=self._candidate(conn,shot_id,expected_previous_number,review)
            return {"expected_basis_sha256":token,"review":review,"basis":basis,"v1_validation":validation,"label":"Spatial plan reviewed (authored review, not physical verification)"}

    def apply(self,shot_id,expected_previous_number,review,expected_basis_sha256):
        review=checked(review,SpatialReview)
        with self.repo.transaction() as conn:
            previous,basis,validation,token=self._candidate(conn,shot_id,expected_previous_number,review)
            self.plans._expect(expected_basis_sha256,token)
            row={"id":uid(),"shot_id":shot_id,"parent_review_id":previous["id"] if previous else None,"number":expected_previous_number+1,"schema_version":2,
                 "observation_version_id":review["observation_version_id"],"binding_version_id":review["binding_version_id"],"review_json":review,"content_sha256":sha(review),"basis_json":basis,"basis_sha256":sha(basis),"created_at":now()}
            self.plans._insert(conn,"observation_spatial_reviews",row)
            self.repo.event(conn,"spatial.review",shot_id,{"review_id":row["id"],"number":row["number"],"binding_version_id":row["binding_version_id"]})
            return row|{"label":"Spatial plan reviewed"}

    def _row(self,conn,shot_id=None,review_id=None):
        if (shot_id is None)==(review_id is None):raise SpatialError("Choose exactly one shot or review ID.")
        row=conn.execute("SELECT * FROM observation_spatial_reviews WHERE "+("id=?" if review_id else "shot_id=? ORDER BY number DESC LIMIT 1"),(review_id or shot_id,)).fetchone()
        if not row:raise NotFound("No spatial review exists for this selection.")
        if raw_hash(row["review_json"])!=row["content_sha256"] or raw_hash(row["basis_json"])!=row["basis_sha256"]:raise SpatialError("Spatial review hash mismatch.",code="spatial_integrity")
        return unpack(row)

    def show(self,shot_id=None,review_id=None):
        with self.repo.transaction(False) as conn:
            row=self._row(conn,shot_id,review_id)
            return row|{"validation":self._status(conn,row),"label":"Spatial plan reviewed"}

    def _status(self,conn,row):
        reasons=[]
        try:
            live,v1,oh,bh,setup=self._basis(conn,row["shot_id"],row["review_json"],historical=True)
            saved=row["basis_json"]
            if bh["current_version_id"]!=row["binding_version_id"] or self.plans._binding_version(conn,bh["current_version_id"])["binding_json"]["status"]!="active":reasons.append({"code":"binding_changed"})
            if oh["current_version_id"]!=row["observation_version_id"] or not v1["basis_current"] or live["current_v1_basis_sha256"]!=saved["current_v1_basis_sha256"]:reasons.append({"code":"observation_changed"})
            if live["planning_context"]!=saved["planning_context"] or live["source_status"]!=saved["source_status"]:reasons.append({"code":"source_basis_changed"})
            if live["reference_status"]!=saved["reference_status"] or any(x["pinned"]!=x["current"] or x["archived"] for x in live["reference_status"]):reasons.append({"code":"reference_semantics_changed"})
            head=self.plans._header(conn,setup["setup_id"])
            if head["current_version_id"]!=setup["id"]:
                latest=self.plans._version(conn,head["current_version_id"])
                reasons.append({"code":"new_setup_version_available","physical_changed":latest["basis_json"]["physical_sha256"]!=setup["basis_json"]["physical_sha256"],"pinned_version_unchanged":True})
        except StoryboardError as exc:
            reasons.append({"code":"integrity_failure","message":str(exc)})
        actionable=[x for x in reasons if x["code"]!="new_setup_version_available" or x["physical_changed"]]
        return {"status":"attention" if actionable else "reviewed-pinned-version","reasons":reasons,"authored_review_only":True,"frame_verified":False}

    def history(self,shot_id,limit=100,offset=0):
        bounds(limit,offset)
        with self.repo.transaction(False) as conn:
            total=conn.execute("SELECT count(*) FROM observation_spatial_reviews WHERE shot_id=?",(shot_id,)).fetchone()[0]
            rows=[dict(r) for r in conn.execute("SELECT id,number,parent_review_id,observation_version_id,binding_version_id,content_sha256,basis_sha256,created_at FROM observation_spatial_reviews WHERE shot_id=? ORDER BY number DESC LIMIT ? OFFSET ?",(shot_id,limit,offset))]
            return page(rows,total,limit,offset)
