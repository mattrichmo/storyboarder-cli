"""Transaction-owned immutable setups and exact shot bindings.

Reads are bounded and stay out of the generic project snapshot. Publication
resolves dependencies server-side on the same SQLite connection as the write.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

from storyboarder.domain.errors import Conflict, NotFound, StoryboardError
from storyboarder.domain.models import now, uid
from storyboarder.domain.documents import content_hash
from storyboarder.domain.spatial import SpatialError, SpatialPayload, checked, canonical, canonical_uuid, physical, sha, validate_binding, EVALUATOR
from storyboarder.domain.spatial_evaluation import evaluate
from storyboarder.media.files import safe_path

JSON_FIELDS = {"payload_json", "binding_json", "review_json", "basis_json", "snapshot_json", "producer_json", "mapping_json", "imported_records_json", "details"}


def unpack(row):
    if row is None:
        return None
    result = dict(row)
    for key in JSON_FIELDS & result.keys():
        result[key] = json.loads(result[key])
    return result


def bounds(limit=100, offset=0):
    if type(limit) is not int or not 1 <= limit <= 500 or type(offset) is not int or offset < 0:
        raise SpatialError("Use page size 1–500 and a nonnegative integer offset.")
    return limit, offset


def page(items, total, limit, offset):
    return {"items": items, "total": total, "limit": limit, "offset": offset, "next_offset": offset+len(items) if offset+len(items)<total else None}


def identity(value):
    try:
        return canonical_uuid(value)
    except ValueError as exc:
        raise SpatialError(str(exc)) from exc


def raw_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def differences(a, b, path="", limit=300):
    """Stable-ID comparison, with an explicit truncated flag at the boundary."""
    found=[]
    def walk(x,y,p):
        if len(found)>=limit:return
        if isinstance(x,dict) and isinstance(y,dict):
            for k in sorted(set(x)|set(y)):
                walk(x.get(k),y.get(k),p+"/"+k)
        elif isinstance(x,list) and isinstance(y,list) and all(isinstance(v,dict) and "id" in v for v in x+y):
            walk({v["id"]:v for v in x},{v["id"]:v for v in y},p)
        elif x!=y:
            def small(v):
                s=canonical(v)
                return v if len(s)<=1200 else {"summary":s[:1200],"truncated":True}
            found.append({"path":p,"before":small(x),"after":small(y)})
    walk(a,b,path)
    return {"changes":found,"truncated":len(found)>=limit}


class SpatialPlans:
    def __init__(self, service):
        self.service, self.repo, self.root = service, service.repo, service.root
        self.project_id = service.project.id

    def _entity(self, conn, item_id, kind=None, active=True):
        try:
            row=self.service.entity(conn,item_id,kind,active)
        except StoryboardError as exc:
            raise SpatialError(str(exc), {"id":item_id}, "spatial_reference_missing") from exc
        if row["kind"] in ("scene","shot","sequence"):
            current,seen=row,set()
            while current["kind"]!="project":
                if current["id"] in seen or not current.get("parent_id"):
                    raise SpatialError("Invalid story ancestry.",code="spatial_scope_mismatch")
                seen.add(current["id"])
                current=self.service.entity(conn,current["parent_id"],active=active)
            if current["id"]!=self.project_id:
                raise SpatialError("Spatial references belong to a different project.",code="spatial_scope_mismatch")
        return row

    def _header(self,conn,setup_id,active=False):
        row=unpack(conn.execute("SELECT * FROM spatial_setups WHERE id=? AND project_id=?",(setup_id,self.project_id)).fetchone())
        if not row:raise NotFound("Spatial setup was not found in this project.")
        if active and row["archived"]:raise SpatialError("Unarchive this setup before revising or binding it.")
        return row

    def _version(self,conn,version_id):
        raw=conn.execute("SELECT v.* FROM spatial_setup_versions v JOIN spatial_setups s ON s.id=v.setup_id WHERE v.id=? AND s.project_id=?",(version_id,self.project_id)).fetchone()
        if not raw or not raw["sealed"]:raise NotFound("Exact sealed spatial version was not found.")
        if raw_hash(raw["payload_json"])!=raw["content_sha256"] or raw_hash(raw["basis_json"])!=raw["basis_sha256"]:
            raise SpatialError("Stored spatial bytes do not match their hashes.",{"version_id":version_id},"spatial_integrity")
        return unpack(raw)

    def _pins(self,conn,version_id):
        return {kind:[unpack(r) for r in conn.execute(f"SELECT * FROM spatial_version_{kind}_pins WHERE version_id=? ORDER BY 1,2",(version_id,))]
                for kind in ("scene","asset","media","source")}

    def _file(self, path, expected):
        f=safe_path(self.root,path,must_exist=True)
        digest=hashlib.sha256()
        with f.open("rb") as handle:
            for chunk in iter(lambda:handle.read(1024*1024),b""):digest.update(chunk)
        if digest.hexdigest()!=expected:
            raise SpatialError("Pinned file changed or is corrupt.",{"path":path},"spatial_integrity")
        return f

    def _asset(self,conn,item_id,active=True):
        row=self._entity(conn,item_id,"asset",active)
        media=[dict(r) for r in conn.execute("SELECT am.media_id,am.is_primary,m.sha256 FROM asset_media am JOIN media m ON m.id=am.media_id WHERE am.asset_id=? ORDER BY am.media_id",(item_id,))]
        semantic={"id":row["id"],"fields":row["fields"],"description":row["description"],"tags":row["tags"],"aliases":row["aliases"],"media":media}
        return row,semantic

    def _source(self,conn,pin,scene_ids,active=True):
        if pin["kind"]=="document-node":
            node=conn.execute("SELECT * FROM document_nodes WHERE id=? AND version_id=?",(pin["node_id"],pin["document_version_id"])).fetchone()
            version=conn.execute("SELECT * FROM document_versions WHERE id=? AND document_id=?",(pin["document_version_id"],pin["document_id"])).fetchone()
            doc=conn.execute("SELECT * FROM documents WHERE id=?",(pin["document_id"],)).fetchone()
            if not node or not version or not doc or (active and doc["archived"]):
                raise SpatialError("Source node/version/document is missing, archived, or outside its declared scope.",code="spatial_reference_missing")
            if node["identity"]!="explicit":raise SpatialError("Inferred source identities cannot become exact spatial pins.")
            body=json.loads(node["payload"])
            if content_hash(body)!=node["content_sha256"] or pin["expected_source_sha256"]!=node["content_sha256"] or pin["expected_document_sha256"]!=version["content_sha256"]:
                raise SpatialError("Source hashes no longer match the reviewed document.",code="spatial_integrity")
            artifact=conn.execute("SELECT * FROM source_artifacts WHERE id=?",(version["source_artifact_id"],)).fetchone()
            if not artifact:raise SpatialError("Source artifact is missing.",code="spatial_integrity")
            self._file(artifact["path"],artifact["sha256"])
            snapshot={"document_id":doc["id"],"document_version_id":version["id"],"node_id":node["id"],"logical_id":node["logical_id"],"source_sha256":node["content_sha256"],"document_sha256":version["content_sha256"],"artifact_sha256":artifact["sha256"],"payload":body}
            row={"pin_id":pin["id"],"source_kind":pin["kind"],"document_id":doc["id"],"document_version_id":version["id"],"node_id":node["id"],"observation_version_id":None}
        else:
            raw=conn.execute("SELECT v.*,c.shot_id FROM observation_contract_versions v JOIN observation_contracts c ON c.id=v.contract_id WHERE v.id=? AND v.sealed=1",(pin["observation_version_id"],)).fetchone()
            if not raw:raise SpatialError("The v1 observation source does not exist.",code="spatial_reference_missing")
            shot=self._entity(conn,raw["shot_id"],"shot",active)
            if active and shot["parent_id"] not in scene_ids:raise SpatialError("Observation source shot is outside the setup scenes.",code="spatial_scope_mismatch")
            if raw_hash(raw["contract_json"])!=raw["content_sha256"] or raw_hash(raw["basis_json"])!=raw["basis_sha256"] or pin["expected_content_sha256"]!=raw["content_sha256"] or pin["expected_basis_sha256"]!=raw["basis_sha256"]:
                raise SpatialError("V1 observation source hashes do not match.",code="spatial_integrity")
            snapshot={"observation_version_id":raw["id"],"shot_id":raw["shot_id"],"content_sha256":raw["content_sha256"],"basis_sha256":raw["basis_sha256"],"contract":json.loads(raw["contract_json"]),"basis":json.loads(raw["basis_json"])}
            row={"pin_id":pin["id"],"source_kind":pin["kind"],"document_id":None,"document_version_id":None,"node_id":None,"observation_version_id":raw["id"]}
        return row|{"semantic_sha256":sha(snapshot),"snapshot_json":snapshot}

    def _dependencies(self,conn,payload):
        pins={"scene":[],"asset":[],"media":[],"source":[]}
        for scene_id in payload["scene_ids"]:
            self._entity(conn,scene_id,"scene")
            pins["scene"].append({"scene_id":scene_id})
        references=[]
        if payload["location_asset_id"]:references.append(("location",self.project_id,payload["location_asset_id"]))
        for group in ("instances","resources","cameras","lights","modifiers"):
            for item in payload[group]:
                if item.get("asset_id"):references.append(("identity",item["id"],item["asset_id"]))
                if item.get("reference_asset_id"):references.append(("reference",item["id"],item["reference_asset_id"]))
        for role,owner_id,asset_id in sorted(set(references)):
            row,semantic=self._asset(conn,asset_id)
            if role=="location" and row["fields"]["type"]!="location":raise SpatialError("Choose a location asset.")
            pins["asset"].append({"owner_id":owner_id,"role":role,"asset_id":asset_id,"asset_revision":row["revision"],"semantic_sha256":sha(semantic),"snapshot_json":{"title":row["title"],"semantic":semantic}})
        for floor in payload["floor_plans"]:
            media=conn.execute("SELECT * FROM media WHERE id=?",(floor["media_id"],)).fetchone()
            if not media or media["sha256"]!=floor["media_sha256"]:raise SpatialError("Floor-plan media hash changed; recalibration is required.",code="spatial_integrity")
            self._file(media["path"],media["sha256"])
            cal=floor["calibration"]
            if cal["status"]=="measured":
                if any(p[0]>media["width"] or p[1]>media["height"] for p in (cal["pixel_a"],cal["pixel_b"])):
                    raise SpatialError("Calibration points must lie inside the exact source image.")
            pins["media"].append({"owner_id":floor["id"],"media_id":media["id"],"media_sha256":media["sha256"]})
        pins["source"]=[self._source(conn,p,payload["scene_ids"]) for p in payload["source_pins"]]
        return pins

    def _preserved(self,conn,version):
        pins=self._pins(conn,version["id"])
        for p in pins["scene"]:self._entity(conn,p["scene_id"],"scene",False)
        for p in pins["asset"]:
            self._entity(conn,p["asset_id"],"asset",False)
            if sha(p["snapshot_json"]["semantic"])!=p["semantic_sha256"]:raise SpatialError("Historical asset pin hash is inconsistent.",code="spatial_integrity")
        for p in pins["media"]:
            media=conn.execute("SELECT * FROM media WHERE id=?",(p["media_id"],)).fetchone()
            if not media or media["sha256"]!=p["media_sha256"]:raise SpatialError("Historical media pin is missing or changed.",code="spatial_integrity")
            self._file(media["path"],p["media_sha256"])
        inputs={p["id"]:p for p in version["payload_json"]["source_pins"]}
        for p in pins["source"]:
            resolved=self._source(conn,inputs[p["pin_id"]],version["payload_json"]["scene_ids"],False)
            if resolved["semantic_sha256"]!=p["semantic_sha256"] or resolved["snapshot_json"]!=p["snapshot_json"]:
                raise SpatialError("Historical source pin cannot be reproduced.",code="spatial_integrity")
        return {k:[{a:b for a,b in p.items() if a!="version_id"} for p in values] for k,values in pins.items()}

    def _basis(self,payload,pins):
        pins={k:sorted(values,key=canonical) for k,values in pins.items()}
        semantics={"scene_ids":payload["scene_ids"],"assets":[{k:p[k] for k in ("owner_id","role","asset_id","semantic_sha256")} for p in pins["asset"]],"media":pins["media"],"sources":[{"pin_id":p["pin_id"],"semantic_sha256":p["semantic_sha256"]} for p in pins["source"]]}
        return {"schema":"storyboarder.spatial-basis/v1","project_id":self.project_id,"evaluator":EVALUATOR,"physical_sha256":sha({"payload":physical(payload),"dependencies":semantics}),"dependencies":pins}

    def _token(self,operation,header,payload,basis,extra=None):
        return sha({"schema":"storyboarder.spatial-review-token/v1","project_id":self.project_id,"operation":operation,"head":header.get("current_version_id"),"revision":header["revision"],"id":header["id"],"candidate_sha256":sha(payload),"physical_sha256":basis["physical_sha256"],"extra":extra})

    @staticmethod
    def _expect(expected,actual):
        if expected!=actual:raise SpatialError("Reviewed dependencies changed. Preview again; your draft has not been applied.",{"expected_basis_sha256":expected,"current_basis_sha256":actual},"spatial_review_stale",409)

    def _insert(self,conn,table,row):
        columns=list(row)
        values=[canonical(v) if k in JSON_FIELDS and not isinstance(v,str) else v for k,v in row.items()]
        conn.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",values)

    def _publish(self,conn,header,payload,pins,operation,operation_id=None,request_hash=None):
        version_id,stamp=uid(),now()
        prior=self._version(conn,header["current_version_id"]) if header.get("current_version_id") else None
        basis=self._basis(payload,pins)
        self._insert(conn,"spatial_setup_versions",{"id":version_id,"setup_id":header["id"],"parent_version_id":prior["id"] if prior else None,"number":prior["number"]+1 if prior else 1,"schema_version":1,"payload_json":payload,"content_sha256":sha(payload),"basis_json":basis,"basis_sha256":sha(basis),"operation":operation,"sealed":0,"created_at":stamp})
        for kind,values in pins.items():
            for p in values:self._insert(conn,f"spatial_version_{kind}_pins",p|{"version_id":version_id})
        conn.execute("UPDATE spatial_setup_versions SET sealed=1 WHERE id=?",(version_id,))
        revision=header["revision"]+(1 if prior else 0)
        archived=1 if operation=="archive" else 0 if operation=="unarchive" else header["archived"]
        conn.execute("UPDATE spatial_setups SET current_version_id=?,revision=?,title=?,archived=?,updated_at=? WHERE id=?",(version_id,revision,payload["setup_label"],archived,stamp,header["id"]))
        details={"setup_id":header["id"],"version_id":version_id,"previous_version_id":prior["id"] if prior else None,"content_sha256":sha(payload),"physical_sha256":basis["physical_sha256"]}
        if operation_id:details.update(operation_id=identity(operation_id),request_sha256=request_hash)
        self.repo.event(conn,"spatial."+operation,header["id"],details)
        return self._show(conn,header["id"],version_id)

    def _replay(self,conn,operation_id,request):
        if not operation_id:return None
        identity(operation_id)
        row=unpack(conn.execute("SELECT * FROM events WHERE action GLOB 'spatial.*' AND json_extract(details,'$.operation_id')=?",(operation_id,)).fetchone())
        if not row:return None
        details=row["details"]
        if details.get("request_sha256")!=sha(request):raise Conflict("Operation ID was already used for different content.")
        if details.get("setup_id"):return self._show(conn,details["setup_id"],details["version_id"])|{"idempotent":True}
        return self._binding_show(conn,binding_id=details["binding_id"],version_id=details["version_id"])|{"idempotent":True}

    def create_preview(self,setup_id,expected_project_revision,payload):
        payload=checked(payload);identity(setup_id)
        with self.repo.transaction(False) as conn:
            project=self._entity(conn,self.project_id,"project");self.repo.check(project,expected_project_revision)
            if conn.execute("SELECT 1 FROM spatial_setups WHERE id=?",(setup_id,)).fetchone():raise Conflict("Setup ID already exists.")
            header={"id":setup_id,"revision":expected_project_revision,"current_version_id":None}
            pins=self._dependencies(conn,payload);basis=self._basis(payload,pins)
            return {"expected_basis_sha256":self._token("create",header,payload,basis),"payload":payload,"physical_sha256":basis["physical_sha256"],"warnings":self.warnings(payload)}

    def create(self,setup_id,expected_project_revision,payload,expected_basis_sha256,operation_id=None):
        payload=checked(payload);identity(setup_id)
        request={"setup_id":setup_id,"payload":payload,"operation":"create"}
        with self.repo.transaction() as conn:
            replay=self._replay(conn,operation_id,request)
            if replay:return replay
            project=self._entity(conn,self.project_id,"project");self.repo.check(project,expected_project_revision)
            if conn.execute("SELECT 1 FROM spatial_setups WHERE id=?",(setup_id,)).fetchone():raise Conflict("Setup ID already exists; read it before retrying.")
            pins=self._dependencies(conn,payload);basis=self._basis(payload,pins)
            self._expect(expected_basis_sha256,self._token("create",{"id":setup_id,"revision":expected_project_revision},payload,basis))
            stamp=now();header={"id":setup_id,"project_id":self.project_id,"current_version_id":None,"revision":1,"title":payload["setup_label"],"archived":0,"created_at":stamp,"updated_at":stamp}
            self._insert(conn,"spatial_setups",header)
            return self._publish(conn,header,payload,pins,"create",operation_id,sha(request))

    @staticmethod
    def warnings(payload):
        return [{"code":"schematic_lighting","message":"Lighting coverage is planned, not photometric or safety-certified."}]+([] if payload["scale"]["status"]=="measured" else [{"code":"scale_"+payload["scale"]["status"],"message":"Scale is not a verified measurement."}])

    def validate(self,payload,setup_id=None):
        try:
            payload=checked(payload)
            with self.repo.transaction(False) as conn:
                if setup_id:self._header(conn,setup_id)
                pins=self._dependencies(conn,payload)
                basis=self._basis(payload,pins)
            return {"valid":True,"payload":payload,"content_sha256":sha(payload),"physical_sha256":basis["physical_sha256"],"errors":[],"warnings":self.warnings(payload)}
        except StoryboardError as exc:
            return {"valid":False,"errors":[exc.as_dict()],"warnings":[]}

    def list(self,scene_id=None,include_archived=False,limit=100,offset=0):
        bounds(limit,offset)
        if type(include_archived) is not bool:raise SpatialError("include_archived must be boolean.")
        clauses,args=["s.project_id=?"],[self.project_id]
        if not include_archived:clauses.append("s.archived=0")
        if scene_id:clauses.append("EXISTS(SELECT 1 FROM spatial_version_scene_pins p WHERE p.version_id=s.current_version_id AND p.scene_id=?)");args.append(scene_id)
        where=" AND ".join(clauses)
        with self.repo.transaction(False) as conn:
            total=conn.execute("SELECT count(*) FROM spatial_setups s WHERE "+where,args).fetchone()[0]
            rows=[dict(r) for r in conn.execute("SELECT s.*,v.number,v.content_sha256,v.basis_sha256 FROM spatial_setups s JOIN spatial_setup_versions v ON v.id=s.current_version_id WHERE "+where+" ORDER BY s.title,s.id LIMIT ? OFFSET ?",(*args,limit,offset))]
            return page(rows,total,limit,offset)

    def _show(self,conn,setup_id,version_id=None):
        header=self._header(conn,setup_id);version=self._version(conn,version_id or header["current_version_id"])
        if version["setup_id"]!=setup_id:raise SpatialError("Version belongs to another setup.",code="spatial_scope_mismatch")
        return {"header":header,"version":version,"pins":self._pins(conn,version["id"]),"newer_setup_available":header["current_version_id"]!=version["id"],"warnings":self.warnings(version["payload_json"])}

    def show(self,setup_id,version_id=None):
        with self.repo.transaction(False) as conn:return self._show(conn,setup_id,version_id)

    def history(self,setup_id,limit=100,offset=0):
        bounds(limit,offset)
        with self.repo.transaction(False) as conn:
            self._header(conn,setup_id)
            total=conn.execute("SELECT count(*) FROM spatial_setup_versions WHERE setup_id=?",(setup_id,)).fetchone()[0]
            items=[dict(r) for r in conn.execute("SELECT id,setup_id,parent_version_id,number,content_sha256,basis_sha256,operation,created_at FROM spatial_setup_versions WHERE setup_id=? ORDER BY number DESC LIMIT ? OFFSET ?",(setup_id,limit,offset))]
            return page(items,total,limit,offset)

    def revise_preview(self,setup_id,revision,payload):
        payload=checked(payload)
        with self.repo.transaction(False) as conn:
            header=self._header(conn,setup_id,True);self.repo.check(header,revision)
            previous=self._version(conn,header["current_version_id"])
            pins=self._dependencies(conn,payload);basis=self._basis(payload,pins)
            return {"expected_basis_sha256":self._token("revise",header,payload,basis),"diff":differences(previous["payload_json"],payload),"physical_changed":previous["basis_json"]["physical_sha256"]!=basis["physical_sha256"],"impact":self._impact(conn,setup_id=setup_id),"payload":payload}

    def revise(self,setup_id,revision,payload,expected_basis_sha256,operation_id=None):
        payload=checked(payload);request={"operation":"revise","setup_id":setup_id,"revision":revision,"payload":payload}
        with self.repo.transaction() as conn:
            replay=self._replay(conn,operation_id,request)
            if replay:return replay
            header=self._header(conn,setup_id,True);self.repo.check(header,revision)
            pins=self._dependencies(conn,payload);basis=self._basis(payload,pins)
            self._expect(expected_basis_sha256,self._token("revise",header,payload,basis))
            return self._publish(conn,header,payload,pins,"revise",operation_id,sha(request))

    def diff(self,setup_id,from_version_id,to_version_id):
        with self.repo.transaction(False) as conn:
            a=self._show(conn,setup_id,from_version_id)["version"];b=self._show(conn,setup_id,to_version_id)["version"]
            return differences(a["payload_json"],b["payload_json"])|{"physical_changed":a["basis_json"]["physical_sha256"]!=b["basis_json"]["physical_sha256"]}

    def restore_preview(self,setup_id,revision,version_id):
        with self.repo.transaction(False) as conn:
            header=self._header(conn,setup_id);self.repo.check(header,revision)
            source=self._show(conn,setup_id,version_id)["version"];pins=self._preserved(conn,source)
            return {"expected_basis_sha256":self._token("restore",header,source["payload_json"],self._basis(source["payload_json"],pins),version_id),"diff":differences(self._version(conn,header["current_version_id"])["payload_json"],source["payload_json"]),"retains_exact_historical_dependencies":True}

    def restore(self,setup_id,revision,version_id,expected_basis_sha256):
        with self.repo.transaction() as conn:
            header=self._header(conn,setup_id);self.repo.check(header,revision)
            source=self._show(conn,setup_id,version_id)["version"];pins=self._preserved(conn,source)
            self._expect(expected_basis_sha256,self._token("restore",header,source["payload_json"],self._basis(source["payload_json"],pins),version_id))
            return self._publish(conn,header,source["payload_json"],pins,"restore")

    def archive(self,setup_id,revision,unarchive=False):
        with self.repo.transaction() as conn:
            header=self._header(conn,setup_id);self.repo.check(header,revision)
            source=self._version(conn,header["current_version_id"])
            return self._publish(conn,header,source["payload_json"],self._preserved(conn,source),"unarchive" if unarchive else "archive")

    def duplicate_preview(self,setup_id,version_id,new_setup_id,title):
        identity(new_setup_id)
        with self.repo.transaction(False) as conn:
            source=self._show(conn,setup_id,version_id)["version"];payload=deepcopy(source["payload_json"])
            payload.update(setup_label=title,origin={"setup_id":setup_id,"version_id":source["id"]});payload=checked(payload)
            pins=self._preserved(conn,source)
            header={"id":new_setup_id,"revision":1}
            return {"expected_basis_sha256":self._token("duplicate",header,payload,self._basis(payload,pins),source["id"]),"payload":payload}

    def duplicate(self,setup_id,version_id,new_setup_id,title,expected_basis_sha256):
        identity(new_setup_id)
        with self.repo.transaction() as conn:
            source=self._show(conn,setup_id,version_id)["version"];payload=deepcopy(source["payload_json"])
            payload.update(setup_label=title,origin={"setup_id":setup_id,"version_id":source["id"]});payload=checked(payload)
            pins=self._preserved(conn,source)
            header={"id":new_setup_id,"project_id":self.project_id,"revision":1,"current_version_id":None,"archived":0,"title":title,"created_at":now(),"updated_at":now()}
            self._expect(expected_basis_sha256,self._token("duplicate",header,payload,self._basis(payload,pins),source["id"]))
            if conn.execute("SELECT 1 FROM spatial_setups WHERE id=?",(new_setup_id,)).fetchone():raise Conflict("Duplicate destination ID already exists.")
            self._insert(conn,"spatial_setups",header)
            return self._publish(conn,header,payload,pins,"duplicate")

    def evaluate(self,version_id,times_us,target_plane_z_m=0.0,view_bounds=None):
        if not isinstance(times_us,list) or not 1<=len(times_us)<=1000:raise SpatialError("Request 1–1000 sample times.",code="spatial_limit_exceeded")
        with self.repo.transaction(False) as conn:v=self._version(conn,version_id)
        payload=checked(v["payload_json"])
        return {"version_id":v["id"],"content_sha256":v["content_sha256"],"samples":[evaluate(payload,t,target_plane_z_m,view_bounds) for t in times_us]}

    def _binding_header(self,conn,binding_id=None,shot_id=None):
        if (binding_id is None)==(shot_id is None):raise SpatialError("Choose exactly one binding ID or shot ID.")
        row=unpack(conn.execute("SELECT * FROM shot_spatial_bindings WHERE "+("id=?" if binding_id else "shot_id=?"),(binding_id or shot_id,)).fetchone())
        if not row:raise NotFound("This shot has no spatial binding.")
        self._entity(conn,row["shot_id"],"shot",False)
        return row

    def _binding_version(self,conn,version_id):
        row=conn.execute("SELECT * FROM shot_spatial_binding_versions WHERE id=? AND sealed=1",(version_id,)).fetchone()
        if not row:raise NotFound("Exact binding version was not found.")
        if raw_hash(row["binding_json"])!=row["content_sha256"] or raw_hash(row["basis_json"])!=row["basis_sha256"]:
            raise SpatialError("Binding hash is inconsistent.",code="spatial_integrity")
        return unpack(row)

    def _binding_show(self,conn,binding_id=None,shot_id=None,version_id=None):
        header=self._binding_header(conn,binding_id,shot_id);version=self._binding_version(conn,version_id or header["current_version_id"])
        if version["binding_id"]!=header["id"]:raise SpatialError("Binding version belongs to another shot.",code="spatial_scope_mismatch")
        setup=self._version(conn,version["setup_version_id"])
        setup_header=self._header(conn,setup["setup_id"])
        shot=self._entity(conn,header["shot_id"],"shot",False)
        return {"header":header,"version":version,"setup":self._show(conn,setup["setup_id"],setup["id"]),"historical_scope":shot["parent_id"]!=version["basis_json"]["parent_scene_id"],"newer_setup_available":setup_header["current_version_id"]!=setup["id"]}

    def binding_show(self,binding_id=None,shot_id=None,version_id=None):
        with self.repo.transaction(False) as conn:return self._binding_show(conn,binding_id,shot_id,version_id)

    def binding_history(self,binding_id,limit=100,offset=0):
        bounds(limit,offset)
        with self.repo.transaction(False) as conn:
            self._binding_header(conn,binding_id)
            total=conn.execute("SELECT count(*) FROM shot_spatial_binding_versions WHERE binding_id=?",(binding_id,)).fetchone()[0]
            rows=[dict(r) for r in conn.execute("SELECT id,number,parent_version_id,setup_version_id,content_sha256,operation,created_at FROM shot_spatial_binding_versions WHERE binding_id=? ORDER BY number DESC LIMIT ? OFFSET ?",(binding_id,limit,offset))]
            return page(rows,total,limit,offset)

    def _binding_candidate(self,conn,shot_id,expected_shot_revision,binding,binding_id,revision=None,detaching=False):
        shot=self._entity(conn,shot_id,"shot");self.repo.check(shot,expected_shot_revision)
        from storyboarder.domain.spatial import SpatialBinding
        binding=checked(binding,SpatialBinding)
        version=self._version(conn,binding["setup_version_id"])
        if not detaching:self._header(conn,version["setup_id"],True)
        if detaching:
            from storyboarder.domain.spatial import SpatialBinding
            body=checked(binding,SpatialBinding)
        else:body=validate_binding(binding,version["payload_json"],shot["parent_id"],shot["fields"].get("duration"))
        header={"id":binding_id,"revision":1,"current_version_id":None}
        if revision is not None:
            header=self._binding_header(conn,binding_id);self.repo.check(header,revision)
            if header["shot_id"]!=shot_id:raise SpatialError("Binding belongs to another shot.",code="spatial_scope_mismatch")
        elif conn.execute("SELECT 1 FROM shot_spatial_bindings WHERE shot_id=? OR id=?",(shot_id,binding_id)).fetchone():raise Conflict("This shot already has a binding; rebind it explicitly.")
        from storyboarder.rendering.composer import context
        # Resolve only the current ancestor records and context rows, not a second snapshot.
        chain=[];current=shot
        while current:
            chain.append(current);current=self._entity(conn,current["parent_id"],active=False) if current.get("parent_id") else None
        blocks=[dict(r) for r in conn.execute("SELECT * FROM context_blocks WHERE owner_id IN ("+','.join('?' for _ in chain)+")",[e["id"] for e in chain])]
        ctx=context({"entities":chain,"context_blocks":blocks},shot_id)
        basis={"schema":"storyboarder.spatial-binding-basis/v1","project_id":self.project_id,"parent_scene_id":shot["parent_id"],"shot_id":shot_id,"shot_revision":shot["revision"],"shot_fields":shot["fields"],"context":ctx,"setup_version_id":version["id"],"setup_content_sha256":version["content_sha256"],"physical_sha256":version["basis_json"]["physical_sha256"]}
        token=sha({"schema":"storyboarder.spatial-bind-review/v1","project_id":self.project_id,"header":header,"body":body,"basis":basis})
        return header,body,basis,token

    def bind_preview(self,shot_id,expected_shot_revision,binding_id,binding,revision=None):
        identity(binding_id)
        with self.repo.transaction(False) as conn:
            header,body,basis,token=self._binding_candidate(conn,shot_id,expected_shot_revision,binding,binding_id,revision)
            previous=self._binding_version(conn,header["current_version_id"])["binding_json"] if header.get("current_version_id") else None
            return {"expected_basis_sha256":token,"binding":body,"diff":differences(previous,body),"basis":basis}

    def _publish_binding(self,conn,header,shot_id,body,basis,operation,operation_id=None,request_hash=None):
        stamp=now();new_id=uid();prior=self._binding_version(conn,header["current_version_id"]) if header.get("current_version_id") else None
        if prior is None:self._insert(conn,"shot_spatial_bindings",{"id":header["id"],"shot_id":shot_id,"current_version_id":None,"revision":1,"created_at":stamp,"updated_at":stamp})
        row={"id":new_id,"binding_id":header["id"],"parent_version_id":prior["id"] if prior else None,"number":prior["number"]+1 if prior else 1,"setup_version_id":body["setup_version_id"],"schema_version":1,"binding_json":body,"content_sha256":sha(body),"basis_json":basis,"basis_sha256":sha(basis),"operation":operation,"sealed":0,"created_at":stamp}
        self._insert(conn,"shot_spatial_binding_versions",row)
        conn.execute("UPDATE shot_spatial_binding_versions SET sealed=1 WHERE id=?",(new_id,))
        conn.execute("UPDATE shot_spatial_bindings SET current_version_id=?,revision=?,updated_at=? WHERE id=?",(new_id,header["revision"]+(1 if prior else 0),stamp,header["id"]))
        details={"binding_id":header["id"],"version_id":new_id,"setup_version_id":body["setup_version_id"],"shot_id":shot_id}
        if operation_id:details.update(operation_id=identity(operation_id),request_sha256=request_hash)
        self.repo.event(conn,"spatial."+operation,shot_id,details)
        return self._binding_show(conn,binding_id=header["id"])

    def bind(self,shot_id,expected_shot_revision,binding_id,binding,expected_basis_sha256,revision=None,operation_id=None):
        identity(binding_id)
        request={"shot_id":shot_id,"binding_id":binding_id,"binding":binding,"revision":revision,"operation":"bind"}
        with self.repo.transaction() as conn:
            replay=self._replay(conn,operation_id,request)
            if replay:return replay
            header,body,basis,token=self._binding_candidate(conn,shot_id,expected_shot_revision,binding,binding_id,revision)
            if body["status"]!="active":raise SpatialError("Use detach to append a detached binding.")
            self._expect(expected_basis_sha256,token)
            return self._publish_binding(conn,header,shot_id,body,basis,"rebind" if revision is not None else "create",operation_id,sha(request))

    def detach(self,binding_id,revision,expected_shot_revision):
        with self.repo.transaction() as conn:
            header=self._binding_header(conn,binding_id);self.repo.check(header,revision)
            shot=self._entity(conn,header["shot_id"],"shot");self.repo.check(shot,expected_shot_revision)
            old=self._binding_version(conn,header["current_version_id"])
            body=deepcopy(old["binding_json"]);body["status"]="detached"
            return self._publish_binding(conn,header,shot["id"],body,old["basis_json"],"detach")

    def _impact(self,conn,setup_id=None,dependency_id=None,limit=100,offset=0):
        bounds(limit,offset)
        conditions,args=[],[]
        if setup_id:conditions.append("v.setup_id=?");args.append(setup_id)
        if dependency_id:
            conditions.append("(EXISTS(SELECT 1 FROM spatial_version_asset_pins p WHERE p.version_id=v.id AND p.asset_id=?) OR EXISTS(SELECT 1 FROM spatial_version_scene_pins p WHERE p.version_id=v.id AND p.scene_id=?) OR EXISTS(SELECT 1 FROM spatial_version_media_pins p WHERE p.version_id=v.id AND p.media_id=?) OR EXISTS(SELECT 1 FROM spatial_version_source_pins p WHERE p.version_id=v.id AND (p.node_id=? OR p.observation_version_id=?)))")
            args.extend([dependency_id]*5)
        where=" AND ".join(conditions) or "1=1"
        query=" FROM shot_spatial_binding_versions bv JOIN shot_spatial_bindings b ON b.id=bv.binding_id JOIN spatial_setup_versions v ON v.id=bv.setup_version_id WHERE "+where
        total=conn.execute("SELECT count(*)"+query,args).fetchone()[0]
        rows=[dict(r) for r in conn.execute("SELECT b.shot_id,b.id AS binding_id,bv.id AS binding_version_id,v.setup_id,v.id AS setup_version_id,(b.current_version_id=bv.id) AS is_current,json_extract(bv.binding_json,'$.status') AS status"+query+" ORDER BY b.shot_id,bv.number DESC LIMIT ? OFFSET ?",(*args,limit,offset))]
        return page(rows,total,limit,offset)

    def impact(self,setup_id=None,dependency_id=None,limit=100,offset=0):
        with self.repo.transaction(False) as conn:return self._impact(conn,setup_id,dependency_id,limit,offset)

    def operation_show(self,operation_id):
        identity(operation_id)
        with self.repo.transaction(False) as conn:
            row=unpack(conn.execute("SELECT * FROM events WHERE action GLOB 'spatial.*' AND json_extract(details,'$.operation_id')=?",(operation_id,)).fetchone())
            return {"found":bool(row),"event":row}


def usage(conn,record_id):
    """Retained identity usage, included by authoring preflight and SQL FKs."""
    queries={"spatial_scenes":("SELECT version_id FROM spatial_version_scene_pins WHERE scene_id=?",(record_id,)),
             "spatial_assets":("SELECT version_id FROM spatial_version_asset_pins WHERE asset_id=?",(record_id,)),
             "spatial_media":("SELECT version_id FROM spatial_version_media_pins WHERE media_id=?",(record_id,)),
             "spatial_sources":("SELECT version_id FROM spatial_version_source_pins WHERE node_id=? OR document_id=? OR document_version_id=? OR observation_version_id=?",(record_id,)*4),
             "spatial_bindings":("SELECT id FROM shot_spatial_bindings WHERE shot_id=?",(record_id,))}
    return {k:[r[0] for r in conn.execute(sql,args)] for k,(sql,args) in queries.items()}


def check_shot_move(conn,shot_id,new_scene_id):
    current=conn.execute("SELECT v.binding_json,s.payload_json FROM shot_spatial_bindings b JOIN shot_spatial_binding_versions v ON v.id=b.current_version_id JOIN spatial_setup_versions s ON s.id=v.setup_version_id WHERE b.shot_id=?",(shot_id,)).fetchone()
    if current and json.loads(current["binding_json"])["status"]=="active" and new_scene_id not in json.loads(current["payload_json"])["scene_ids"]:
        raise SpatialError("Detach this shot's spatial binding before moving it to an unlisted scene.",{"shot_id":shot_id,"scene_id":new_scene_id},"spatial_scope_mismatch",409)
