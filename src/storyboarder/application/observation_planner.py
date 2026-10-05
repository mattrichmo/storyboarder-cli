"""Exact, request-scoped observation coverage and atomic shot planning.

This planner reports authored relationships and declarations only. It never
infers a source anchor from imported screenplay content or evaluates prose,
images, cameras, or rendered frames.
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from storyboarder.application.documents import page_bounds
from storyboarder.application.observation_contracts import (
    ObservationContractError,
    ObservationContracts,
    _validate_body,
)
from storyboarder.application.provenance import Provenance
from storyboarder.domain.documents import content_hash
from storyboarder.domain.errors import Conflict, StoryboardError
from storyboarder.domain.models import dumps, now, text, title, validate_fields

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COVERAGE_SCHEMA = "storyboarder.observation-coverage/v1"


class ObservationPlannerError(ObservationContractError):
    """Stable planner errors for callers that do not use an interface adapter."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


def _canonical_uuid(value: str) -> str:
    if not UUID_RE.fullmatch(value) or str(uuid.UUID(value)) != value:
        raise ValueError("Use a lowercase canonical UUID.")
    return value


class ExactAnchor(_StrictModel):
    document_id: str
    version_id: str
    node_id: str
    source_sha256: str
    priority: Literal["must", "prefer", "unknown"]
    basis: Literal["direct", "interpreted", "unknown"]

    @field_validator("document_id", "version_id", "node_id")
    @classmethod
    def canonical_ids(cls, value):
        return _canonical_uuid(value)

    @field_validator("source_sha256")
    @classmethod
    def canonical_digest(cls, value):
        if not SHA256_RE.fullmatch(value):
            raise ValueError("Use a lowercase SHA-256 digest.")
        return value


class ExactVisualizesEdge(_StrictModel):
    edge_id: str
    document_id: str
    version_id: str
    node_id: str
    source_sha256: str
    source_scope: Literal["direct-element", "scene-context"]

    @field_validator("edge_id", "document_id", "version_id", "node_id")
    @classmethod
    def canonical_ids(cls, value):
        return _canonical_uuid(value)

    @field_validator("source_sha256")
    @classmethod
    def canonical_digest(cls, value):
        if not SHA256_RE.fullmatch(value):
            raise ValueError("Use a lowercase SHA-256 digest.")
        return value


class GroupItem(_StrictModel):
    shot_id: str
    contract_id: str
    scene_id: str
    expected_scene_revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=240)
    description: str = ""
    fields: dict = Field(default_factory=dict)
    source_edges: list[ExactVisualizesEdge] = Field(min_length=1, max_length=128)
    contract: dict

    @field_validator("shot_id", "contract_id", "scene_id")
    @classmethod
    def canonical_ids(cls, value):
        return _canonical_uuid(value)


def _validated_model(model, value, label):
    try:
        return model.model_validate(value)
    except ValidationError as exc:
        issues = [{"path": "/".join(map(str, error["loc"])), "message": error["msg"], "type": error["type"]}
                  for error in exc.errors()[:100]]
        raise ObservationPlannerError("observation_plan_invalid", f"{label} is invalid.", {"issues": issues}) from exc


class ObservationPlanner:
    """Project-scoped exact anchor reporting and atomic grouped authoring."""

    def __init__(self, service):
        self.service, self.repo = service, service.repo
        self.contracts = ObservationContracts(service)
        self.provenance = Provenance(service)

    @staticmethod
    def _coverage_kind(node_type, target_kind):
        if target_kind == "scene":
            return "scene-context"
        if target_kind == "shot" and node_type == "scene":
            return "direct-scene-link"
        if target_kind == "shot":
            return "direct-element-link"
        return "unsupported-target"

    def _authored_links(self, conn, limit, offset):
        where = "e.relation='visualizes' AND e.source_type='node' AND e.target_type='entity' AND d.kind='screenplay' AND target.kind IN ('scene','shot')"
        total = conn.execute(f"""SELECT count(*) FROM provenance_edges e
          JOIN document_nodes n ON n.id=e.source_id
          JOIN document_versions v ON v.id=n.version_id
          JOIN documents d ON d.id=v.document_id
          JOIN entities target ON target.id=e.target_id
          WHERE {where}""").fetchone()[0]
        rows = conn.execute(f"""SELECT e.*,n.node_type,n.identity,n.logical_id,n.content_sha256 AS source_sha256,
                 n.version_id,v.document_id,v.content_sha256 AS document_sha256,d.current_version_id,d.archived AS document_archived,
                 target.kind AS target_kind,target.archived AS target_archived
          FROM provenance_edges e
          JOIN document_nodes n ON n.id=e.source_id
          JOIN document_versions v ON v.id=n.version_id
          JOIN documents d ON d.id=v.document_id
          JOIN entities target ON target.id=e.target_id
          WHERE {where}
          ORDER BY e.id LIMIT ? OFFSET ?""", (limit, offset)).fetchall()
        items = []
        for raw in rows:
            row = dict(raw)
            inherited = []
            if row["target_kind"] == "scene":
                inherited = [item[0] for item in conn.execute(
                    "SELECT id FROM entities WHERE kind='shot' AND parent_id=? ORDER BY id", (row["target_id"],))]
            snapshot_state = "exact"
            try:
                source_snapshot = json.loads(row["source_snapshot"])
                target_snapshot = json.loads(row["target_snapshot"])
                if (source_snapshot.get("id") != row["source_id"]
                        or source_snapshot.get("version_id") != row["version_id"]
                        or source_snapshot.get("document_id") != row["document_id"]
                        or source_snapshot.get("document_kind") != "screenplay"
                        or source_snapshot.get("node_type") != row["node_type"]
                        or source_snapshot.get("logical_id") != row["logical_id"]
                        or source_snapshot.get("identity") != row["identity"]
                        or source_snapshot.get("content_sha256") != row["source_sha256"]
                        or target_snapshot.get("id") != row["target_id"]
                        or target_snapshot.get("kind") != row["target_kind"]):
                    snapshot_state = "mismatch"
            except (TypeError, ValueError):
                snapshot_state = "invalid"
            items.append({
                "edge_id": row["id"], "relation": row["relation"], "retired": bool(row["retired"]),
                "revision": row["revision"],
                "coverage_kind": self._coverage_kind(row["node_type"], row["target_kind"]),
                "target_id": row["target_id"], "target_kind": row["target_kind"],
                "target_archived": bool(row["target_archived"]),
                "inherited_shot_ids": inherited,
                "source": {"document_id": row["document_id"], "version_id": row["version_id"],
                           "current_version_id": row["current_version_id"], "version_current": row["version_id"] == row["current_version_id"],
                           "document_archived": bool(row["document_archived"]), "node_id": row["source_id"],
                           "logical_id": row["logical_id"], "node_type": row["node_type"],
                           "identity": row["identity"], "source_sha256": row["source_sha256"]},
                "snapshot_state": snapshot_state,
            })
        return {"items": items, "total": total, "limit": limit, "offset": offset,
                "next_offset": offset + len(items) if offset + len(items) < total else None}

    def _contract_declarations(self, conn, limit, offset):
        total = conn.execute("SELECT count(*) FROM observation_contracts").fetchone()[0]
        rows = conn.execute("""SELECT * FROM observation_contracts ORDER BY shot_id,id LIMIT ? OFFSET ?""",
                            (limit, offset)).fetchall()
        items = []
        for raw in rows:
            header = dict(raw)
            if not header["current_version_id"]:
                items.append({"contract_id": header["id"], "shot_id": header["shot_id"],
                              "contract_revision": header["revision"], "version_id": None,
                              "state": "unresolved", "requirements": [], "source_pins": []})
                continue
            try:
                _, version = self.contracts._version(conn, header["id"])
                validation = self.contracts._validate(conn, header, version)
                items.append({"contract_id": header["id"], "shot_id": header["shot_id"],
                              "contract_revision": header["revision"], "version_id": version["id"],
                              "state": validation["status"],
                              "source_pins": validation["source_pins"],
                              "requirements": [{**requirement,
                                                "source_node_types": sorted({mapping.get("source_node_type") for mapping in requirement["source_mappings"]
                                                                             if mapping.get("source_node_type")}),
                                                "coverage_kinds": sorted({mapping.get("coverage_kind") for mapping in requirement["source_mappings"]
                                                                          if mapping.get("coverage_kind")})}
                                               for requirement in validation["requirements"]],
                              "validation_findings": validation["findings"]})
            except (ObservationContractError, TypeError, ValueError) as exc:
                items.append({"contract_id": header["id"], "shot_id": header["shot_id"],
                              "contract_revision": header["revision"], "version_id": header["current_version_id"],
                              "state": "conflict", "requirements": [], "source_pins": [],
                              "validation_findings": [{"code": "contract_unavailable", "message": str(exc)}]})
        return {"items": items, "total": total, "limit": limit, "offset": offset,
                "next_offset": offset + len(items) if offset + len(items) < total else None}

    def _exact_anchor(self, conn, anchor):
        row = conn.execute("""SELECT n.*,v.document_id,v.content_sha256 AS document_sha256,v.source_artifact_id,
                 d.kind AS document_kind,d.current_version_id,d.archived AS document_archived
          FROM document_nodes n JOIN document_versions v ON v.id=n.version_id
          JOIN documents d ON d.id=v.document_id WHERE n.id=? AND n.version_id=?""",
                           (anchor.node_id, anchor.version_id)).fetchone()
        if row is None:
            raise ObservationPlannerError("observation_anchor_not_found", "The exact screenplay node and version are not in this project.",
                                          {"document_id": anchor.document_id, "version_id": anchor.version_id,
                                           "node_id": anchor.node_id}, 404)
        row = dict(row)
        if row["document_id"] != anchor.document_id or row["document_kind"] != "screenplay":
            raise ObservationPlannerError("observation_anchor_identity_mismatch", "The exact node does not belong to the supplied screenplay document and version.",
                                          {"document_id": anchor.document_id, "version_id": anchor.version_id,
                                           "node_id": anchor.node_id})
        if row["node_type"] == "screenplay" or row["identity"] != "explicit":
            raise ObservationPlannerError("observation_anchor_identity_not_exact", "Coverage anchors require an explicitly identified screenplay scene or element.",
                                          {"node_id": row["id"], "identity": row["identity"], "node_type": row["node_type"]})
        try:
            payload = json.loads(row["payload"])
            actual = content_hash(payload)
        except (TypeError, ValueError) as exc:
            raise ObservationPlannerError("observation_anchor_hash_mismatch", "The exact screenplay node payload is malformed.",
                                          {"node_id": row["id"]}) from exc
        if actual != row["content_sha256"] or actual != anchor.source_sha256:
            raise ObservationPlannerError("observation_anchor_hash_mismatch", "The supplied source hash does not match the exact screenplay node.",
                                          {"node_id": row["id"], "expected": row["content_sha256"], "actual": actual})
        version = {"id": row["version_id"], "source_artifact_id": row["source_artifact_id"],
                   "content_sha256": row["document_sha256"]}
        artifact = self.contracts._artifact_check(conn, version)
        out_of_date_reasons = []
        if row["document_archived"]:
            out_of_date_reasons.append("document_archived")
        if row["current_version_id"] != row["version_id"]:
            out_of_date_reasons.append("source_version_not_current")
        if artifact is None:
            out_of_date_reasons.append("source_artifact_unavailable_or_changed")
        return {**row, "artifact_current": artifact is not None,
                "version_current": row["current_version_id"] == row["version_id"],
                "out_of_date_reasons": out_of_date_reasons}

    def _anchor_links(self, conn, source):
        rows = conn.execute("""SELECT e.*,target.kind AS target_kind,target.archived AS target_archived
          FROM provenance_edges e JOIN entities target ON target.id=e.target_id
          WHERE e.source_type='node' AND e.source_id=? AND e.target_type='entity' AND e.relation='visualizes'
            AND target.kind IN ('scene','shot') ORDER BY e.target_type,e.target_id,e.id""", (source["id"],)).fetchall()
        links = []
        for raw in rows:
            edge = dict(raw)
            kind = self._coverage_kind(source["node_type"], edge["target_kind"])
            snapshot_state = "exact"
            try:
                source_snapshot = json.loads(edge["source_snapshot"])
                target_snapshot = json.loads(edge["target_snapshot"])
                if (source_snapshot.get("id") != source["id"]
                        or source_snapshot.get("version_id") != source["version_id"]
                        or source_snapshot.get("document_id") != source["document_id"]
                        or source_snapshot.get("document_kind") != "screenplay"
                        or source_snapshot.get("node_type") != source["node_type"]
                        or source_snapshot.get("logical_id") != source["logical_id"]
                        or source_snapshot.get("identity") != "explicit"
                        or source_snapshot.get("content_sha256") != source["content_sha256"]
                        or target_snapshot.get("id") != edge["target_id"]
                        or target_snapshot.get("kind") != edge["target_kind"]):
                    snapshot_state = "mismatch"
            except (TypeError, ValueError):
                snapshot_state = "invalid"
            links.append({"edge_id": edge["id"], "target_id": edge["target_id"], "target_kind": edge["target_kind"],
                          "target_archived": bool(edge["target_archived"]), "retired": bool(edge["retired"]),
                          "coverage_kind": kind, "snapshot_state": snapshot_state})
        return links

    @staticmethod
    def _anchor_state(anchor, source, links):
        direct = [link for link in links if link["coverage_kind"] == "direct-element-link"]
        direct_scene = [link for link in links if link["coverage_kind"] == "direct-scene-link"]
        contexts = [link for link in links if link["coverage_kind"] == "scene-context"]
        fresh_direct = [link for link in direct if not link["retired"] and not link["target_archived"]
                        and link["snapshot_state"] == "exact"]
        reasons = list(source["out_of_date_reasons"])
        if any(link["retired"] for link in links):
            reasons.append("matching_link_retired")
        if any(link["target_archived"] for link in links):
            reasons.append("matching_target_archived")
        if any(link["snapshot_state"] != "exact" for link in links):
            reasons.append("matching_link_snapshot_invalid")
        if anchor.basis == "unknown":
            reasons.append("anchor_basis_unknown")
        if anchor.priority == "unknown":
            state = "open-question"
        elif source["out_of_date_reasons"] or anchor.basis == "unknown" or not fresh_direct:
            state = "unresolved" if anchor.priority == "must" else "warning"
        else:
            state = "direct-link"
        if not links:
            reasons.append("missing_visualizes_link")
        if not fresh_direct and contexts:
            reasons.append("scene_context_does_not_satisfy_direct_anchor")
        if not fresh_direct and direct_scene:
            reasons.append("direct_scene_link_is_not_beat_coverage")
        return {"document_id": source["document_id"], "version_id": source["version_id"],
                "node_id": source["id"], "logical_id": source["logical_id"],
                "node_type": source["node_type"], "source_sha256": source["content_sha256"],
                "current_version_id": source["current_version_id"], "version_current": source["version_current"],
                "priority": anchor.priority, "basis": anchor.basis, "state": state,
                "out_of_date": bool(source["out_of_date_reasons"] or any(
                    link["retired"] or link["target_archived"] or link["snapshot_state"] != "exact" for link in links)),
                "out_of_date_reasons": sorted(set(reasons)),
                "direct_shot_links": direct, "direct_scene_links": direct_scene,
                "scene_context_links": contexts,
                "method": "Exact IDs, hashes, and authored visualizes edges only; a direct link does not establish image or semantic satisfaction."}

    def coverage(self, anchors=None, *, limit=500, offset=0):
        """Report authored links/declarations and optional exact request anchors.

        No unlinked imported screenplay nodes are enumerated. Callers may pass
        only the anchors they want evaluated, each pinned to exact IDs/hash.
        """
        page_bounds(limit, offset)
        if anchors is None:
            anchors = []
        if not isinstance(anchors, list) or len(anchors) > 100:
            raise ObservationPlannerError("observation_plan_invalid", "Provide at most 100 request-scoped exact anchors as a JSON array.")
        parsed = [_validated_model(ExactAnchor, value, f"anchors[{index}]") for index, value in enumerate(anchors)]
        identities = [(item.document_id, item.version_id, item.node_id) for item in parsed]
        if len(identities) != len(set(identities)):
            raise ObservationPlannerError("observation_anchor_duplicate", "A request cannot repeat the same exact document/version/node anchor.")
        with self.repo.transaction(False) as conn:
            authored_links = self._authored_links(conn, limit, offset)
            declarations = self._contract_declarations(conn, limit, offset)
            request_anchors = []
            for anchor in parsed:
                source = self._exact_anchor(conn, anchor)
                links = self._anchor_links(conn, source)
                request_anchors.append(self._anchor_state(anchor, source, links))
            return {"schema": COVERAGE_SCHEMA,
                    "method": "Project reporting includes authored screenplay visualizes edges and current contract declarations only. Request anchors are exact and caller supplied; no unlinked import scan, title/order inference, percentages, or semantic/image checks are performed.",
                    "authored_links": authored_links,
                    "contract_declarations": declarations,
                    "request_anchors": request_anchors}

    def _validate_exact_source(self, conn, edge_input):
        row = conn.execute("""SELECT n.*,v.document_id,v.content_sha256 AS document_sha256,v.source_artifact_id,
                 d.kind AS document_kind,d.archived AS document_archived
          FROM document_nodes n JOIN document_versions v ON v.id=n.version_id
          JOIN documents d ON d.id=v.document_id WHERE n.id=? AND n.version_id=?""",
                           (edge_input.node_id, edge_input.version_id)).fetchone()
        if row is None:
            raise ObservationPlannerError("observation_source_exact_not_found", "The requested exact screenplay node and version are not in this project.",
                                          {"document_id": edge_input.document_id, "version_id": edge_input.version_id,
                                           "node_id": edge_input.node_id}, 404)
        row = dict(row)
        if row["document_id"] != edge_input.document_id or row["document_kind"] != "screenplay":
            raise ObservationPlannerError("observation_source_identity_mismatch", "The exact source node does not belong to the supplied screenplay document and version.",
                                          {"document_id": edge_input.document_id, "version_id": edge_input.version_id,
                                           "node_id": edge_input.node_id})
        if row["node_type"] == "screenplay" or row["identity"] != "explicit":
            raise ObservationPlannerError("observation_source_identity_inferred", "New visualizes edges require an explicitly identified screenplay scene or element.",
                                          {"node_id": row["id"], "identity": row["identity"], "node_type": row["node_type"]})
        try:
            actual = content_hash(json.loads(row["payload"]))
        except (TypeError, ValueError) as exc:
            raise ObservationPlannerError("observation_source_hash_mismatch", "The exact screenplay node payload is malformed.",
                                          {"node_id": row["id"]}) from exc
        if actual != row["content_sha256"] or actual != edge_input.source_sha256:
            raise ObservationPlannerError("observation_source_hash_mismatch", "The supplied source hash does not match the exact screenplay node.",
                                          {"node_id": row["id"], "expected": row["content_sha256"], "actual": actual})
        if row["document_archived"]:
            raise ObservationPlannerError("observation_source_archived", "Restore the screenplay before creating a new source edge.",
                                          {"document_id": row["document_id"]})
        artifact = self.contracts._artifact_check(conn, {
            "id": row["version_id"], "source_artifact_id": row["source_artifact_id"],
            "content_sha256": row["document_sha256"],
        })
        if artifact is None:
            raise ObservationPlannerError("observation_source_artifact_unavailable",
                                          "The exact screenplay artifact or version hash is unavailable or changed.",
                                          {"document_id": row["document_id"], "version_id": row["version_id"]})
        return row

    @staticmethod
    def _raise_group_validation(exc):
        if isinstance(exc, ObservationContractError):
            raise exc
        if isinstance(exc, Conflict):
            raise exc
        if isinstance(exc, StoryboardError):
            raise ObservationPlannerError("observation_group_invalid", str(exc), getattr(exc, "details", {})) from exc
        raise exc

    def create_group(self, items):
        """Atomically create shots, exact visualizes edges, and first contracts.

        ``shot_id``, ``contract_id``, and every ``edge_id`` are caller supplied.
        Source document/version/node/hash values are always explicit; the batch
        never resolves an implicit or latest source version.
        """
        if not isinstance(items, list) or not 1 <= len(items) <= 50:
            raise ObservationPlannerError("observation_plan_invalid", "A grouped plan must contain 1 to 50 items.")
        parsed = [_validated_model(GroupItem, value, f"items[{index}]") for index, value in enumerate(items)]
        shot_ids = [item.shot_id for item in parsed]
        contract_ids = [item.contract_id for item in parsed]
        edge_ids = [edge.edge_id for item in parsed for edge in item.source_edges]
        if len(set(shot_ids)) != len(shot_ids) or len(set(contract_ids)) != len(contract_ids) or len(set(edge_ids)) != len(edge_ids):
            raise ObservationPlannerError("observation_plan_duplicate_id", "Shot, contract, and edge UUIDs must be unique within the group.")
        if set(shot_ids) & set(contract_ids) or set(shot_ids) & set(edge_ids) or set(contract_ids) & set(edge_ids):
            raise ObservationPlannerError("observation_plan_duplicate_id", "A caller UUID cannot identify more than one planned record.")
        prepared = []
        for item in parsed:
            body = _validate_body(item.contract)
            requested = {pin["edge_id"]: pin["source_scope"] for pin in body["source_pins"]}
            expected = {edge.edge_id: edge.source_scope for edge in item.source_edges}
            if requested != expected:
                raise ObservationPlannerError("observation_group_pin_set_mismatch", "Each first contract version must pin exactly the visualizes edges created for its shot.",
                                              {"shot_id": item.shot_id, "provided_edge_ids": sorted(requested),
                                               "planned_edge_ids": sorted(expected)})
            try:
                field_values = validate_fields("shot", item.fields)
                shot_title = title(item.title)
                description = text(item.description)
            except StoryboardError as exc:
                raise ObservationPlannerError("observation_group_invalid", str(exc), getattr(exc, "details", {})) from exc
            prepared.append((item, body, field_values, shot_title, description))

        scene_revisions = {}
        for item in parsed:
            previous = scene_revisions.setdefault(item.scene_id, item.expected_scene_revision)
            if previous != item.expected_scene_revision:
                raise ObservationPlannerError("observation_plan_scene_revision_mismatch", "Items for one parent scene must share one expected revision.",
                                              {"scene_id": item.scene_id, "expected_revisions": sorted({previous, item.expected_scene_revision})})

        try:
            with self.repo.transaction() as conn:
                for scene_id, revision in scene_revisions.items():
                    scene = self.service.entity(conn, scene_id, "scene")
                    self.repo.check(scene, revision)
                # Validate the exact source endpoints before writing any rows.
                for item, _, _, _, _ in prepared:
                    for edge in item.source_edges:
                        self._validate_exact_source(conn, edge)

                created = []
                for item, body, field_values, shot_title, description in prepared:
                    self.service._validate_location(conn, field_values)
                    position = conn.execute("SELECT coalesce(max(position),-1)+1 FROM entities WHERE kind='shot' AND parent_id=?",
                                            (item.scene_id,)).fetchone()[0]
                    stamp = now()
                    shot = self.repo.insert(conn, "entities", {
                        "id": item.shot_id, "kind": "shot", "parent_id": item.scene_id,
                        "position": position, "title": shot_title, "description": description,
                        "fields": field_values, "created_at": stamp, "updated_at": stamp,
                    })
                    self.repo.event(conn, "shot.created", shot["id"])
                    edge_rows = []
                    for edge_input in item.source_edges:
                        source = self.provenance._endpoint(conn, "node", edge_input.node_id)
                        target_id = item.shot_id if edge_input.source_scope == "direct-element" else item.scene_id
                        target = self.provenance._endpoint(conn, "entity", target_id)
                        try:
                            self.provenance._semantics(source, target, "visualizes")
                        except StoryboardError as exc:
                            raise ObservationPlannerError("observation_group_source_edge_invalid", str(exc),
                                                          {"edge_id": edge_input.edge_id, "node_id": edge_input.node_id,
                                                           "target_id": target_id}) from exc
                        edge_row = {"id": edge_input.edge_id, "source_type": "node", "source_id": edge_input.node_id,
                                    "target_type": "entity", "target_id": target_id, "relation": "visualizes",
                                    "source_snapshot": dumps(source), "target_snapshot": dumps(target),
                                    "notes": "", "retired": 0, "revision": 1, "created_at": now()}
                        conn.execute("""INSERT INTO provenance_edges
                          (id,source_type,source_id,target_type,target_id,relation,source_snapshot,target_snapshot,notes,retired,revision,created_at)
                          VALUES(:id,:source_type,:source_id,:target_type,:target_id,:relation,:source_snapshot,:target_snapshot,
                                 :notes,:retired,:revision,:created_at)""", edge_row)
                        self.repo.event(conn, "provenance.linked", edge_row["id"],
                                        {"source": f"node:{edge_input.node_id}", "target": f"entity:{target_id}", "relation": "visualizes"})
                        edge_rows.append(edge_row)

                    stamp = now()
                    header = {"id": item.contract_id, "shot_id": item.shot_id, "current_version_id": None,
                              "revision": 1, "created_at": stamp, "updated_at": stamp}
                    conn.execute("""INSERT INTO observation_contracts
                      (id,shot_id,current_version_id,revision,created_at,updated_at) VALUES(?,?,NULL,1,?,?)""",
                                 (item.contract_id, item.shot_id, stamp, stamp))
                    version = self.contracts._insert_version(conn, header, body, "create")
                    conn.execute("UPDATE observation_contracts SET current_version_id=? WHERE id=?",
                                 (version["id"], item.contract_id))
                    self.repo.event(conn, "observation_contract.created", item.contract_id,
                                    {"shot_id": item.shot_id, "version_id": version["id"]})
                    shown = self.contracts._show(conn, item.contract_id, version["id"])
                    created.append({"shot_id": item.shot_id, "shot_revision": shot["revision"],
                                    "scene_id": item.scene_id, "expected_scene_revision": item.expected_scene_revision,
                                    "contract_id": item.contract_id, "contract_revision": 1,
                                    "version_id": version["id"], "edge_ids": [row["id"] for row in edge_rows],
                                    "contract": shown})
                self.repo.event(conn, "observation_group.created", None,
                                {"shot_ids": shot_ids, "contract_ids": contract_ids,
                                 "edge_ids": edge_ids})
                return {"items": created, "count": len(created)}
        except StoryboardError as exc:
            self._raise_group_validation(exc)
