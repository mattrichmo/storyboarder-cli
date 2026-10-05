"""Immutable, exact-source observation contracts for storyboard shots.

This module deliberately treats prose as authored data. Validation checks
identities, pins, hashes, and the documented basis; it never interprets a
statement as proof that a frame communicates it.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from storyboarder.domain.documents import content_hash
from storyboarder.domain.errors import NotFound, StoryboardError
from storyboarder.domain.models import dumps, now, uid
from storyboarder.formats import parse
from storyboarder.media.files import safe_path
from .documents import page_bounds

CONTRACT_SCHEMA = "storyboarder.observation-contract/v1"
BASIS_SCHEMA = "storyboarder.observation-basis/v1"
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
SCALAR_CONTEXT = ("location_id", "time", "framing", "camera")
DIRECTION_CONTEXT = ("premise", "visual_style", "constraints", "arc", "tone", "summary", "continuity")
SHOT_BASIS_FIELDS = ("action", "dialogue", "framing", "camera", "duration", "continuity", "constraints")


class ObservationContractError(StoryboardError):
    """Expected contract error with a stable cross-interface machine code."""

    def __init__(self, code: str, message: str, details=None, status: int = 422):
        super().__init__(message, details)
        self.code = code
        self.status = status


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False, populate_by_name=True)


def _uuid(value: str) -> str:
    if not UUID_RE.fullmatch(value) or str(uuid.UUID(value)) != value:
        raise ValueError("Use a lowercase canonical UUID.")
    return value


class SourcePin(StrictModel):
    edge_id: str
    source_scope: Literal["direct-element", "scene-context"]

    @field_validator("edge_id")
    @classmethod
    def canonical_edge_id(cls, value):
        return _uuid(value)


class ScriptIntent(StrictModel):
    id: str
    source_edge_id: str
    source_scope: Literal["direct-element", "scene-context"]
    purpose: str = Field(min_length=1, max_length=120)
    communication: str = Field(min_length=1, max_length=4000)
    basis: Literal["direct", "interpreted", "unknown"]

    @field_validator("id", "source_edge_id")
    @classmethod
    def canonical_ids(cls, value):
        return _uuid(value)


class Requirement(StrictModel):
    id: str
    priority: Literal["must", "prefer", "unknown"]
    basis: Literal["direct", "interpreted", "unknown"]
    source_edge_ids: list[str] = Field(default_factory=list, max_length=64)
    statement: str | None = Field(default=None, min_length=1, max_length=4000)
    topic: str | None = Field(default=None, min_length=1, max_length=1000)

    @field_validator("id")
    @classmethod
    def canonical_id(cls, value):
        return _uuid(value)

    @field_validator("source_edge_ids")
    @classmethod
    def canonical_source_ids(cls, values):
        return [_uuid(value) for value in values]

    @model_validator(mode="after")
    def check_body(self):
        if len(self.source_edge_ids) != len(set(self.source_edge_ids)):
            raise ValueError("source_edge_ids cannot contain duplicates.")
        if self.priority == "unknown":
            if self.topic is None or self.statement is not None:
                raise ValueError("Unknown requirements need topic and cannot contain statement.")
        elif self.statement is None or self.topic is not None:
            raise ValueError("Must/prefer requirements need statement and cannot contain topic.")
        return self


class Continuity(StrictModel):
    id: str
    related_shot_ids: list[str] = Field(min_length=1, max_length=64)
    statement: str = Field(min_length=1, max_length=4000)

    @field_validator("id")
    @classmethod
    def canonical_id(cls, value):
        return _uuid(value)

    @field_validator("related_shot_ids")
    @classmethod
    def canonical_related_ids(cls, values):
        return [_uuid(value) for value in values]

    @model_validator(mode="after")
    def unique_related_ids(self):
        if len(self.related_shot_ids) != len(set(self.related_shot_ids)):
            raise ValueError("related_shot_ids cannot contain duplicates.")
        return self


class ContractBody(StrictModel):
    schema_version: Literal[CONTRACT_SCHEMA] = Field(alias="schema")
    source_pins: list[SourcePin] = Field(max_length=128)
    script_intents: list[ScriptIntent] = Field(default_factory=list, max_length=128)
    requirements: list[Requirement] = Field(default_factory=list, max_length=256)
    references: list[str] = Field(default_factory=list, max_length=64)
    continuity: list[Continuity] = Field(default_factory=list, max_length=128)
    notes: str = Field(default="", max_length=4000)

    @field_validator("references")
    @classmethod
    def canonical_reference_ids(cls, values):
        return [_uuid(value) for value in values]

    @model_validator(mode="after")
    def unique_and_exact_references(self):
        pin_ids = [pin.edge_id for pin in self.source_pins]
        if len(pin_ids) != len(set(pin_ids)):
            raise ValueError("source_pins cannot repeat a provenance edge.")
        if len(self.references) != len(set(self.references)):
            raise ValueError("references cannot contain duplicate asset IDs.")
        stable_ids = [item.id for item in (*self.script_intents, *self.requirements, *self.continuity)]
        if len(stable_ids) != len(set(stable_ids)):
            raise ValueError("Stable IDs must be unique across intents, requirements, and continuity notes.")
        scopes = {pin.edge_id: pin.source_scope for pin in self.source_pins}
        for intent in self.script_intents:
            if scopes.get(intent.source_edge_id) != intent.source_scope:
                raise ValueError("Each script intent must name a declared source pin with the same scope.")
        for requirement in self.requirements:
            if any(edge_id not in scopes for edge_id in requirement.source_edge_ids):
                raise ValueError("Each requirement source edge must be declared in source_pins.")
        return self


def _validate_body(value):
    try:
        model = ContractBody.model_validate(value)
    except ValidationError as exc:
        issues = [{"path": "/".join(map(str, error["loc"])), "message": error["msg"], "type": error["type"]}
                  for error in exc.errors()[:100]]
        raise ObservationContractError("contract_invalid", "Observation contract content is invalid.", {"issues": issues}) from exc
    return model.model_dump(mode="json", by_alias=True)


def _parse_json(raw):
    def unique_pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON property: {key}")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique_pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"Invalid number: {value}")))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ObservationContractError("contract_invalid", f"Observation contract JSON is invalid: {exc}") from exc


def _row_dict(row):
    return dict(row) if row is not None else None


class ObservationContracts:
    def __init__(self, service):
        self.service, self.repo = service, service.repo

    def _header(self, conn, contract_id):
        row = conn.execute("SELECT * FROM observation_contracts WHERE id=?", (contract_id,)).fetchone()
        if row is None:
            raise ObservationContractError("contract_not_found", "Observation contract is not in this project.",
                                           {"contract_id": contract_id}, 404)
        return dict(row)

    def _version(self, conn, contract_id, version_id=None):
        header = self._header(conn, contract_id)
        selected = version_id or header["current_version_id"]
        row = conn.execute("SELECT * FROM observation_contract_versions WHERE id=? AND contract_id=?",
                           (selected, contract_id)).fetchone() if selected else None
        if row is None:
            raise ObservationContractError("contract_version_not_found", "Observation contract version is not in this contract.",
                                           {"contract_id": contract_id, "version_id": selected}, 404)
        return header, dict(row)

    @staticmethod
    def _safe_json(raw, *, code="contract_integrity_error", label="saved contract"):
        try:
            value = _parse_json(raw)
            if dumps(value) != raw:
                raise ValueError("JSON is not stored in canonical form.")
            return value
        except (ObservationContractError, TypeError, ValueError) as exc:
            if isinstance(exc, ObservationContractError):
                message = str(exc)
            else:
                message = str(exc)
            raise ObservationContractError(code, f"The {label} cannot be read safely.", {"reason": message}) from exc

    def _shot(self, conn, shot_id, *, active=True):
        try:
            row = self.service.entity(conn, shot_id, "shot", active=active)
        except NotFound as exc:
            raise ObservationContractError("contract_shot_not_found", "Choose a storyboard shot in this project.",
                                           {"shot_id": shot_id}, 404) from exc
        except StoryboardError as exc:
            if "archived" in str(exc).lower():
                raise ObservationContractError("contract_shot_archived", "Restore the shot before creating a contract version.",
                                               {"shot_id": shot_id}) from exc
            raise ObservationContractError("contract_shot_invalid", "The selected contract owner is not a storyboard shot.",
                                           {"shot_id": shot_id}) from exc
        return row

    def _artifact_check(self, conn, version, artifact_cache=None):
        artifact_cache = artifact_cache if artifact_cache is not None else {}
        artifact_id = version["source_artifact_id"]
        if artifact_id in artifact_cache:
            cached = artifact_cache[artifact_id]
            return cached if cached is not None and cached["content_sha256"] == version["content_sha256"] else None
        artifact = conn.execute("""SELECT a.path,a.sha256,a.size FROM source_artifacts a
          WHERE a.id=?""", (artifact_id,)).fetchone()
        if artifact is None:
            artifact_cache[artifact_id] = None
            return None
        try:
            path = safe_path(self.service.root, artifact["path"], must_exist=True)
            raw = path.read_bytes()
        except (OSError, StoryboardError):
            artifact_cache[artifact_id] = None
            return None
        digest = hashlib.sha256(raw).hexdigest()
        if len(raw) != artifact["size"] or digest != artifact["sha256"]:
            artifact_cache[artifact_id] = None
            return None
        try:
            parsed = parse(raw, "screenjson")
        except StoryboardError:
            artifact_cache[artifact_id] = None
            return None
        if parsed.kind != "screenplay":
            artifact_cache[artifact_id] = None
            return None
        artifact_cache[artifact_id] = {"sha256": digest, "path": artifact["path"], "size": artifact["size"],
                                       "content_sha256": content_hash(parsed.payload)}
        cached = artifact_cache[artifact_id]
        return cached if cached["content_sha256"] == version["content_sha256"] else None

    def _pin_artifact_check(self, conn, node, pin, cache):
        artifact_id = node.get("source_artifact_id")
        if not artifact_id:
            return False
        # Recheck every pin's expected document hash against the cached parsed
        # artifact metadata. `_artifact_check` reuses bytes/hash/parse work by
        # artifact ID while comparing this caller's expected content hash.
        checked = self._artifact_check(conn, {
            "id": node["version_id"], "source_artifact_id": artifact_id,
            "content_sha256": node["version_sha256"],
        }, cache)
        return checked is not None and checked["sha256"] == pin["artifact_sha256"]

    @staticmethod
    def _context_subtree_hash(conn, version_id, node_id):
        rows = conn.execute("""WITH RECURSIVE tree(id,path) AS (
             SELECT id,printf('%09d',position) FROM document_nodes WHERE id=? AND version_id=?
             UNION ALL
             SELECT child.id,tree.path||'/'||printf('%09d',child.position)
             FROM document_nodes child JOIN tree ON child.parent_id=tree.id WHERE child.version_id=?
           )
           SELECT n.logical_id,n.node_type,n.position,n.content_sha256,tree.path
           FROM tree JOIN document_nodes n ON n.id=tree.id ORDER BY tree.path,n.id""",
                                  (node_id, version_id, version_id)).fetchall()
        return content_hash([dict(row) for row in rows])

    def _pin_for_write(self, conn, shot, requested, artifact_cache=None):
        edge_id = requested["edge_id"]
        edge = conn.execute("SELECT * FROM provenance_edges WHERE id=?", (edge_id,)).fetchone()
        if edge is None:
            raise ObservationContractError("contract_source_pin_not_found", "The selected provenance edge is not in this project.",
                                           {"edge_id": edge_id}, 404)
        edge = dict(edge)
        if edge["retired"]:
            raise ObservationContractError("contract_source_pin_retired", "Retired provenance edges cannot be added to a new contract version.",
                                           {"edge_id": edge_id})
        if edge["relation"] != "visualizes" or edge["source_type"] != "node" or edge["target_type"] != "entity":
            raise ObservationContractError("contract_source_pin_invalid", "A source pin must use an active screenplay visualizes edge.",
                                           {"edge_id": edge_id})
        node = conn.execute("SELECT * FROM document_nodes WHERE id=?", (edge["source_id"],)).fetchone()
        if node is None:
            raise ObservationContractError("contract_source_pin_invalid", "The provenance edge has no source node.",
                                           {"edge_id": edge_id})
        node = dict(node)
        version = conn.execute("SELECT * FROM document_versions WHERE id=?", (node["version_id"],)).fetchone()
        if version is None:
            raise ObservationContractError("contract_source_pin_invalid", "The source node has no immutable document version.",
                                           {"edge_id": edge_id, "node_id": node["id"]})
        version = dict(version)
        document = conn.execute("SELECT * FROM documents WHERE id=?", (version["document_id"],)).fetchone()
        if document is None or document["kind"] != "screenplay" or node["node_type"] == "screenplay":
            raise ObservationContractError("contract_source_pin_invalid", "Only screenplay scenes and elements can be pinned as intent.",
                                           {"edge_id": edge_id, "node_id": node["id"]})
        document = dict(document)
        if node["identity"] != "explicit":
            raise ObservationContractError("contract_source_identity_inferred", "An inferred source identity cannot be treated as an exact contract pin.",
                                           {"edge_id": edge_id, "node_id": node["id"], "identity": node["identity"]})
        if document["archived"]:
            raise ObservationContractError("contract_source_archived", "Restore the screenplay document before adding a source pin.",
                                           {"edge_id": edge_id, "document_id": document["id"]})
        try:
            payload = json.loads(node["payload"])
        except (TypeError, ValueError) as exc:
            raise ObservationContractError("contract_source_hash_mismatch", "The source node snapshot is malformed.",
                                           {"edge_id": edge_id, "node_id": node["id"]}) from exc
        actual_node_hash = content_hash(payload)
        if actual_node_hash != node["content_sha256"]:
            raise ObservationContractError("contract_source_hash_mismatch", "The source node no longer matches its stored content hash.",
                                           {"edge_id": edge_id, "node_id": node["id"], "expected": node["content_sha256"], "actual": actual_node_hash})
        artifact = self._artifact_check(conn, version, artifact_cache)
        if artifact is None:
            raise ObservationContractError("contract_source_hash_mismatch", "The pinned screenplay bytes or version hash no longer match the imported source.",
                                           {"edge_id": edge_id, "version_id": version["id"]})

        try:
            source_snapshot = json.loads(edge["source_snapshot"])
            target_snapshot = json.loads(edge["target_snapshot"])
        except (TypeError, ValueError) as exc:
            raise ObservationContractError("contract_source_hash_mismatch", "The provenance edge snapshot is malformed.",
                                           {"edge_id": edge_id}) from exc
        if (source_snapshot.get("id") != node["id"]
                or source_snapshot.get("version_id") != version["id"]
                or source_snapshot.get("logical_id") != node["logical_id"]
                or source_snapshot.get("content_sha256") != node["content_sha256"]
                or target_snapshot.get("id") != edge["target_id"]):
            raise ObservationContractError("contract_source_hash_mismatch", "The provenance snapshot does not match its exact source identity.",
                                           {"edge_id": edge_id})

        target_id = edge["target_id"]
        if target_id == shot["id"] and edge["target_type"] == "entity":
            scope = "direct-element"
            target_kind = "shot"
        elif target_id == shot["parent_id"] and edge["target_type"] == "entity":
            scope = "scene-context"
            target_kind = "scene"
        else:
            raise ObservationContractError("contract_source_pin_target_mismatch", "A source edge must target this shot directly or its parent storyboard scene.",
                                           {"edge_id": edge_id, "shot_id": shot["id"], "target_id": target_id})
        try:
            target = self.service.entity(conn, target_id, target_kind, active=False)
        except StoryboardError as exc:
            raise ObservationContractError("contract_source_pin_target_mismatch", "The provenance edge target is no longer available.",
                                           {"edge_id": edge_id, "target_id": target_id}) from exc
        if target["archived"]:
            raise ObservationContractError("contract_source_archived", "Restore the storyboard target before adding a source pin.",
                                           {"edge_id": edge_id, "target_id": target_id})
        if scope != requested["source_scope"]:
            raise ObservationContractError("contract_source_scope_mismatch", "The declared source scope does not match the provenance edge target.",
                                           {"edge_id": edge_id, "expected": scope, "provided": requested["source_scope"]})

        scope_hash = (node["content_sha256"] if scope == "direct-element"
                      else self._context_subtree_hash(conn, version["id"], node["id"]))
        captured = {
            "document_id": document["id"], "document_version_id": version["id"],
            "document_sha256": version["content_sha256"], "artifact_sha256": artifact["sha256"],
            "node_id": node["id"], "logical_id": node["logical_id"], "node_type": node["node_type"],
            "identity": node["identity"], "source_sha256": node["content_sha256"],
            "scope_sha256": scope_hash, "payload": payload,
        }
        return {
            "version_id": None, "edge_id": edge_id, "source_scope": scope,
            "document_id": document["id"], "source_version_id": version["id"], "node_id": node["id"],
            "logical_id": node["logical_id"], "source_sha256": node["content_sha256"],
            "scope_sha256": scope_hash, "document_sha256": version["content_sha256"],
            "artifact_sha256": artifact["sha256"], "source_snapshot": dumps(captured),
            "edge_source_snapshot": dumps(source_snapshot), "edge_target_snapshot": dumps(target_snapshot),
        }

    @staticmethod
    def _entity_row(conn, record_id):
        row = conn.execute("SELECT id,kind,parent_id,position,title,description,fields,archived FROM entities WHERE id=?", (record_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["fields"] = json.loads(result["fields"])
        return result

    def _effective_context(self, conn, shot):
        chain, current, seen = [], shot, set()
        while current:
            if current["id"] in seen:
                return {"error": "hierarchy_cycle"}
            seen.add(current["id"])
            chain.append(current)
            current = self._entity_row(conn, current.get("parent_id")) if current.get("parent_id") else None
        chain.reverse()
        scalars, blocks = {}, {}
        for owner in chain:
            fields = owner["fields"]
            for key in SCALAR_CONTEXT:
                value = fields.get(key)
                if value not in (None, ""):
                    scalars[key] = {"value": value, "source_id": owner["id"]}
            for key in DIRECTION_CONTEXT:
                value = fields.get(key)
                if value:
                    blocks.setdefault(key, []).append({"owner_id": owner["id"], "source": "field", "text": value})
            authored = conn.execute("SELECT id,key,operation,text FROM context_blocks WHERE owner_id=? ORDER BY key,id", (owner["id"],)).fetchall()
            for block in authored:
                if block["key"] not in DIRECTION_CONTEXT:
                    continue
                values = blocks.setdefault(block["key"], [])
                if block["operation"] in ("replace", "exclude"):
                    values.clear()
                if block["operation"] != "exclude" and block["text"]:
                    values.append({"owner_id": owner["id"], "source": "context-block", "block_id": block["id"], "text": block["text"]})
        return {"chain": [{"id": owner["id"], "kind": owner["kind"], "archived": bool(owner["archived"])} for owner in chain],
                "scalars": {key: scalars[key] for key in sorted(scalars)},
                "directions": {key: blocks[key] for key in sorted(blocks) if blocks[key]}}

    @staticmethod
    def _assignment_basis(conn, shot_id):
        rows = conn.execute("""SELECT a.id,a.role,a.asset_id,a.media_id,m.sha256 AS media_sha256
          FROM assignments a LEFT JOIN media m ON m.id=a.media_id
          WHERE a.shot_id=? ORDER BY a.role,a.asset_id,a.id""", (shot_id,)).fetchall()
        return [{"assignment_id": row["id"], "role": row["role"], "asset_id": row["asset_id"],
                 "media_id": row["media_id"], "media_sha256": row["media_sha256"]} for row in rows]

    def _basis(self, conn, shot_id, body):
        shot = self._entity_row(conn, shot_id)
        if shot is None or shot["kind"] != "shot":
            raise ObservationContractError("contract_shot_not_found", "The storyboard shot is no longer available.", {"shot_id": shot_id}, 404)
        shot_basis = {"shot_id": shot["id"], "parent_scene_id": shot["parent_id"], "archived": bool(shot["archived"])}
        for key in SHOT_BASIS_FIELDS:
            shot_basis[key] = shot["fields"].get(key)
        shot_basis["effective_context"] = self._effective_context(conn, shot)
        shot_basis["assignments"] = self._assignment_basis(conn, shot_id)
        continuity_basis = []
        for note in body["continuity"]:
            for related_id in note["related_shot_ids"]:
                related = self._entity_row(conn, related_id)
                if related is None or related["kind"] != "shot":
                    continuity_basis.append({"shot_id": related_id, "missing": True})
                    continue
                related_basis = {"shot_id": related_id, "parent_scene_id": related["parent_id"], "archived": bool(related["archived"])}
                for key in SHOT_BASIS_FIELDS:
                    related_basis[key] = related["fields"].get(key)
                related_basis["assignments"] = self._assignment_basis(conn, related_id)
                related_basis["effective_context"] = self._effective_context(conn, related)
                continuity_basis.append(related_basis)
        referenced_ids = set(body["references"])
        for basis_shot in [shot_basis, *continuity_basis]:
            location = basis_shot.get("effective_context") or {}
            location = location.get("scalars", {}).get("location_id")
            if location and isinstance(location.get("value"), str):
                referenced_ids.add(location["value"])
            referenced_ids.update(assignment["asset_id"] for assignment in basis_shot.get("assignments", []))
        assets = []
        for asset_id in sorted(referenced_ids):
            row = conn.execute("SELECT id,kind,description,fields,archived FROM entities WHERE id=?", (asset_id,)).fetchone()
            if row is None or row["kind"] != "asset":
                assets.append({"asset_id": asset_id, "missing": True})
                continue
            fields = json.loads(row["fields"])
            tags = [item[0] for item in conn.execute("SELECT tag FROM entity_tags WHERE entity_id=? ORDER BY tag", (asset_id,))]
            aliases = [item[0] for item in conn.execute("SELECT name FROM aliases WHERE entity_id=? ORDER BY name", (asset_id,))]
            media = [dict(item) for item in conn.execute("""SELECT am.media_id,am.is_primary,m.sha256
              FROM asset_media am JOIN media m ON m.id=am.media_id WHERE am.asset_id=? ORDER BY am.media_id""", (asset_id,))]
            assets.append({"asset_id": asset_id, "kind": "asset", "archived": bool(row["archived"]),
                           "description": row["description"],
                           "fields": {key: fields.get(key) for key in ("type", "notes")},
                           "tags": tags, "aliases": aliases, "media": media})
        return {
            "schema": BASIS_SCHEMA,
            "registry": {
                "shot_fields": list(SHOT_BASIS_FIELDS),
                "effective_context_scalars": list(SCALAR_CONTEXT),
                "effective_context_directions": list(DIRECTION_CONTEXT),
                "excluded": ["title", "shot number", "story order", "free-form notes", "frames", "camera verification"],
            },
            "shot": shot_basis,
            "continuity_shots": sorted(continuity_basis, key=lambda item: item["shot_id"]),
            "referenced_assets": assets,
        }

    def _reference_for_write(self, conn, reference_id):
        row = self._entity_row(conn, reference_id)
        if row is None or row["kind"] != "asset":
            raise ObservationContractError("contract_reference_invalid", "References must be storyboard library asset IDs in this project.",
                                           {"reference_id": reference_id})
        if row["archived"]:
            raise ObservationContractError("contract_reference_archived", "Restore a library reference before adding it to a contract version.",
                                           {"reference_id": reference_id})
        return {"reference_id": reference_id, "kind": "asset", "type": row["fields"].get("type")}

    def _insert_version(self, conn, header, body, operation, artifact_cache=None):
        artifact_cache = artifact_cache if artifact_cache is not None else {}
        shot = self._shot(conn, header["shot_id"])
        pin_rows = [self._pin_for_write(conn, shot, pin, artifact_cache) for pin in body["source_pins"]]
        refs = [self._reference_for_write(conn, record_id) for record_id in body["references"]]
        for note in body["continuity"]:
            if shot["id"] in note["related_shot_ids"]:
                raise ObservationContractError("contract_continuity_self_reference", "A continuity note cannot point back to its own shot.",
                                               {"shot_id": shot["id"], "continuity_id": note["id"]})
            for related_id in note["related_shot_ids"]:
                related = self._shot(conn, related_id)
                if related["archived"]:
                    raise ObservationContractError("contract_continuity_archived", "Restore a related shot before adding a continuity reference.",
                                                   {"shot_id": related_id, "continuity_id": note["id"]})
        version_id = uid()
        number = conn.execute("SELECT coalesce(max(number),0)+1 FROM observation_contract_versions WHERE contract_id=?", (header["id"],)).fetchone()[0]
        parent_id = header["current_version_id"]
        basis = self._basis(conn, shot["id"], body)
        content_json = dumps(body)
        basis_json = dumps(basis)
        created = now()
        conn.execute("""INSERT INTO observation_contract_versions
          (id,contract_id,parent_version_id,number,schema_version,contract_json,content_sha256,basis_json,basis_sha256,operation,sealed,created_at)
          VALUES(?,?,?,?,1,?,?,?,?,?,0,?)""",
                     (version_id, header["id"], parent_id, number, content_json, content_hash(body), basis_json,
                      content_hash(basis), operation, created))
        for pin in pin_rows:
            pin["version_id"] = version_id
            pin["created_at"] = created
            conn.execute("""INSERT INTO observation_source_pins
              (version_id,edge_id,source_scope,document_id,source_version_id,node_id,logical_id,source_sha256,scope_sha256,
               document_sha256,artifact_sha256,source_snapshot,edge_source_snapshot,edge_target_snapshot,created_at)
              VALUES(:version_id,:edge_id,:source_scope,:document_id,:source_version_id,:node_id,:logical_id,:source_sha256,
                     :scope_sha256,:document_sha256,:artifact_sha256,:source_snapshot,:edge_source_snapshot,:edge_target_snapshot,:created_at)""", pin)
        for ref in refs:
            conn.execute("INSERT INTO observation_reference_pins(version_id,reference_id,snapshot_json,created_at) VALUES(?,?,?,?)",
                         (version_id, ref["reference_id"], dumps(ref), created))
        # Membership is sealed before a version can become a header's current pointer.
        conn.execute("UPDATE observation_contract_versions SET sealed=1 WHERE id=?", (version_id,))
        return {"id": version_id, "number": number, "parent_version_id": parent_id, "schema_version": 1,
                "contract_json": content_json, "content_sha256": content_hash(body), "basis_json": basis_json,
                "basis_sha256": content_hash(basis), "operation": operation, "created_at": created}

    def create(self, shot_id, expected_shot_revision, contract):
        body = _validate_body(contract)
        with self.repo.transaction() as conn:
            shot = self._shot(conn, shot_id)
            self.repo.check(shot, expected_shot_revision)
            existing = conn.execute("SELECT id FROM observation_contracts WHERE shot_id=?", (shot_id,)).fetchone()
            if existing:
                raise ObservationContractError("contract_already_exists", "This storyboard shot already has an observation contract.",
                                               {"shot_id": shot_id, "contract_id": existing[0]}, 409)
            stamp = now()
            header = {"id": uid(), "shot_id": shot["id"], "current_version_id": None, "revision": 1,
                      "created_at": stamp, "updated_at": stamp}
            conn.execute("INSERT INTO observation_contracts(id,shot_id,current_version_id,revision,created_at,updated_at) VALUES(?,?,NULL,1,?,?)",
                         (header["id"], header["shot_id"], stamp, stamp))
            artifact_cache = {}
            version = self._insert_version(conn, header, body, "create", artifact_cache)
            conn.execute("UPDATE observation_contracts SET current_version_id=? WHERE id=?", (version["id"], header["id"]))
            self.repo.event(conn, "observation_contract.created", header["id"],
                            {"shot_id": shot["id"], "version_id": version["id"]})
            return self._show(conn, header["id"], version["id"], artifact_cache)

    def _revise(self, contract_id, revision, contract, operation):
        body = _validate_body(contract)
        with self.repo.transaction() as conn:
            header = self._header(conn, contract_id)
            self.repo.check(header, revision)
            shot = self._shot(conn, header["shot_id"])
            _, current = self._version(conn, contract_id)
            current_body = _validate_body(self._safe_json(current["contract_json"]))
            artifact_cache = {}
            requested_pins = {pin["edge_id"]: pin["source_scope"] for pin in body["source_pins"]}
            current_pins = {pin["edge_id"]: pin["source_scope"] for pin in current_body["source_pins"]}
            if operation == "revise":
                if requested_pins != current_pins:
                    raise ObservationContractError("contract_rebase_required", "Use explicit rebase to change exact source pins.",
                                                   {"current_edge_ids": sorted(current_pins), "requested_edge_ids": sorted(requested_pins)})
                current_basis = self._basis(conn, shot["id"], current_body)
                saved_pins = [dict(row) for row in conn.execute("SELECT * FROM observation_source_pins WHERE version_id=? ORDER BY edge_id", (current["id"],))]
                stale_pins = [self._pin_state(conn, pin, shot["id"], artifact_cache) for pin in saved_pins]
                changed_basis = content_hash(current_basis) != current["basis_sha256"]
                stale_edges = [pin["edge_id"] for pin in stale_pins if pin["stale"]]
                if changed_basis or stale_edges:
                    raise ObservationContractError("contract_rebase_required", "The saved source or authored basis changed. Rebase with explicit source pins before revising.",
                                                   {"basis_changed": changed_basis, "stale_edge_ids": stale_edges,
                                                    "current_version_id": current["id"]})
            version = self._insert_version(conn, header, body, operation, artifact_cache)
            conn.execute("UPDATE observation_contracts SET current_version_id=?,revision=revision+1,updated_at=? WHERE id=?",
                         (version["id"], now(), contract_id))
            self.repo.event(conn, "observation_contract." + operation, contract_id,
                            {"shot_id": header["shot_id"], "version_id": version["id"], "revision": revision + 1})
            return self._show(conn, contract_id, version["id"], artifact_cache)

    def revise(self, contract_id, revision, contract):
        return self._revise(contract_id, revision, contract, "revise")

    def rebase(self, contract_id, revision, contract):
        # A complete v1 body is required, including the caller's exact edge IDs.
        return self._revise(contract_id, revision, contract, "rebase")

    def _pin_integrity_reasons(self, conn, pin, shot_id, artifact_cache=None):
        """Check a saved pin against its exact immutable rows, independent of live status."""
        reasons = []
        edge = conn.execute("SELECT * FROM provenance_edges WHERE id=?", (pin["edge_id"],)).fetchone()
        version = conn.execute("SELECT * FROM observation_contract_versions WHERE id=?", (pin["version_id"],)).fetchone()
        try:
            basis = self._safe_json(version["basis_json"], code="contract_basis_invalid", label="saved basis") if version else {}
        except ObservationContractError:
            basis = {}
            reasons.append("basis_snapshot_invalid")
        saved_parent = basis.get("shot", {}).get("parent_scene_id") if isinstance(basis, dict) else None
        if edge is None:
            reasons.append("edge_missing")
        elif (edge["relation"] != "visualizes" or edge["source_type"] != "node"
              or edge["source_id"] != pin["node_id"] or edge["target_type"] != "entity"):
            reasons.append("edge_identity_changed")
        node = conn.execute("""SELECT n.*,v.document_id,v.content_sha256 AS version_sha256,
            v.source_artifact_id,d.kind AS document_kind FROM document_nodes n
            JOIN document_versions v ON v.id=n.version_id JOIN documents d ON d.id=v.document_id
            WHERE n.id=?""", (pin["node_id"],)).fetchone()
        if node is None:
            reasons.append("node_missing")
        else:
            node = dict(node)
            if (node["document_id"] != pin["document_id"] or node["version_id"] != pin["source_version_id"]
                    or node["logical_id"] != pin["logical_id"] or node["content_sha256"] != pin["source_sha256"]
                    or node["version_sha256"] != pin["document_sha256"]):
                reasons.append("pin_identity_mismatch")
            if node["identity"] != "explicit" or node["document_kind"] != "screenplay" or node["node_type"] == "screenplay":
                reasons.append("source_identity_invalid")
            try:
                payload = json.loads(node["payload"])
                if content_hash(payload) != node["content_sha256"] or content_hash(payload) != pin["source_sha256"]:
                    reasons.append("source_hash_mismatch")
                expected_scope = (node["content_sha256"] if pin["source_scope"] == "direct-element"
                                  else self._context_subtree_hash(conn, node["version_id"], node["id"]))
                if expected_scope != pin["scope_sha256"]:
                    reasons.append("scope_hash_mismatch")
                source_snapshot = self._safe_json(pin["source_snapshot"], label="source pin snapshot")
                expected_snapshot = {
                    "document_id": node["document_id"], "document_version_id": node["version_id"],
                    "document_sha256": node["version_sha256"], "artifact_sha256": pin["artifact_sha256"],
                    "node_id": node["id"], "logical_id": node["logical_id"], "node_type": node["node_type"],
                    "identity": node["identity"], "source_sha256": node["content_sha256"],
                    "scope_sha256": expected_scope, "payload": payload,
                }
                if source_snapshot != expected_snapshot:
                    reasons.append("source_snapshot_mismatch")
            except (ObservationContractError, TypeError, ValueError, KeyError):
                reasons.append("source_snapshot_invalid")
            if not self._pin_artifact_check(conn, node, pin, artifact_cache if artifact_cache is not None else {}):
                reasons.append("artifact_unavailable_or_changed")
        if edge is not None:
            if edge["source_snapshot"] != pin["edge_source_snapshot"] or edge["target_snapshot"] != pin["edge_target_snapshot"]:
                reasons.append("edge_snapshot_mismatch")
            try:
                edge_source = self._safe_json(pin["edge_source_snapshot"], label="edge source snapshot")
                edge_target = self._safe_json(pin["edge_target_snapshot"], label="edge target snapshot")
                if node is not None and (edge_source.get("id") != node["id"]
                        or edge_source.get("type") != "node" or edge_source.get("version_id") != node["version_id"]
                        or edge_source.get("document_id") != node["document_id"]
                        or edge_source.get("logical_id") != node["logical_id"]
                        or edge_source.get("node_type") != node["node_type"]
                        or edge_source.get("content_sha256") != node["content_sha256"]):
                    reasons.append("edge_source_snapshot_mismatch")
                target_id = (shot_id if pin["source_scope"] == "direct-element" else saved_parent)
                target = conn.execute("SELECT kind FROM entities WHERE id=?", (edge["target_id"],)).fetchone()
                expected_kind = "shot" if pin["source_scope"] == "direct-element" else "scene"
                if (edge_target.get("id") != edge["target_id"] or edge_target.get("type") != "entity"
                        or edge["target_id"] != target_id or target is None or target["kind"] != expected_kind
                        or edge_target.get("kind") != expected_kind):
                    reasons.append("edge_target_snapshot_mismatch")
            except (ObservationContractError, TypeError, ValueError, KeyError):
                reasons.append("edge_snapshot_invalid")
        return sorted(set(reasons))

    def _pin_state(self, conn, pin, shot_id, artifact_cache=None):
        reasons = self._pin_integrity_reasons(conn, pin, shot_id, artifact_cache)
        edge = conn.execute("SELECT * FROM provenance_edges WHERE id=?", (pin["edge_id"],)).fetchone()
        if edge is not None:
            if edge["retired"]:
                reasons.append("edge_retired")
            shot = conn.execute("SELECT parent_id FROM entities WHERE id=? AND kind='shot'", (shot_id,)).fetchone()
            expected_target = shot["parent_id"] if pin["source_scope"] == "scene-context" and shot else shot_id
            if edge["target_type"] != "entity" or edge["target_id"] != expected_target:
                reasons.append("edge_target_mismatch")
            target_state = conn.execute("SELECT kind,archived FROM entities WHERE id=?", (edge["target_id"],)).fetchone()
            expected_kind = "scene" if pin["source_scope"] == "scene-context" else "shot"
            if target_state is None or target_state["kind"] != expected_kind:
                reasons.append("edge_target_mismatch")
            elif target_state["archived"]:
                reasons.append("target_archived")
        node = conn.execute("""SELECT n.*,v.document_id,v.content_sha256 AS version_sha256,v.source_artifact_id,
            d.current_version_id,d.archived AS document_archived FROM document_nodes n
            JOIN document_versions v ON v.id=n.version_id JOIN documents d ON d.id=v.document_id WHERE n.id=?""",
                            (pin["node_id"],)).fetchone()
        if node is None:
            reasons.append("node_missing")
            return {"edge_id": pin["edge_id"], "source_scope": pin["source_scope"], "stale": True,
                    "reasons": sorted(set(reasons)), "current_version_id": None}
        node = dict(node)
        if node["document_archived"]:
            reasons.append("document_archived")
        if node["current_version_id"] is None:
            reasons.append("document_has_no_current_version")
        current = None
        if node["current_version_id"]:
            current = conn.execute("SELECT * FROM document_nodes WHERE version_id=? AND logical_id=? AND identity='explicit'",
                                   (node["current_version_id"], node["logical_id"])).fetchone()
        if current is None:
            reasons.append("source_missing_from_current_version")
        else:
            current = dict(current)
            try:
                current_payload = json.loads(current["payload"])
                if content_hash(current_payload) != current["content_sha256"]:
                    reasons.append("current_source_hash_mismatch")
                elif pin["source_scope"] == "direct-element" and current["content_sha256"] != pin["source_sha256"]:
                    reasons.append("source_content_changed")
                elif pin["source_scope"] == "scene-context":
                    current_scope = self._context_subtree_hash(conn, node["current_version_id"], current["id"])
                    if current_scope != pin["scope_sha256"]:
                        reasons.append("source_context_changed")
            except (TypeError, ValueError):
                reasons.append("current_source_hash_mismatch")
        return {"edge_id": pin["edge_id"], "source_scope": pin["source_scope"], "stale": bool(reasons),
                "reasons": sorted(set(reasons)), "document_id": pin["document_id"],
                "pinned_version_id": pin["source_version_id"], "current_version_id": node["current_version_id"],
                "source_node_type": node["node_type"],
                "coverage_kind": ("scene-context" if pin["source_scope"] == "scene-context"
                                  else "direct-scene-link" if node["node_type"] == "scene"
                                  else "direct-element-link"),
                "version_current": node["version_id"] == node["current_version_id"],
                "node_id": pin["node_id"], "logical_id": pin["logical_id"],
                "source_sha256": pin["source_sha256"], "scope_sha256": pin["scope_sha256"]}

    def _reference_states(self, conn, version_id, body):
        items = []
        for reference_id in body["references"]:
            row = conn.execute("SELECT id,kind,archived FROM entities WHERE id=?", (reference_id,)).fetchone()
            if row is None or row["kind"] != "asset":
                items.append({"reference_id": reference_id, "state": "dangling", "reason": "reference_missing"})
            elif row["archived"]:
                items.append({"reference_id": reference_id, "state": "unresolved", "reason": "reference_archived"})
            else:
                items.append({"reference_id": reference_id, "state": "available"})
        actual = {row[0] for row in conn.execute("SELECT reference_id FROM observation_reference_pins WHERE version_id=?", (version_id,))}
        if actual != set(body["references"]):
            items.append({"reference_id": None, "state": "conflict", "reason": "reference_pin_mismatch"})
        return items

    def _validate(self, conn, header, version, artifact_cache=None):
        artifact_cache = artifact_cache if artifact_cache is not None else {}
        findings, conflicts, unresolved = [], False, False
        try:
            body = _validate_body(self._safe_json(version["contract_json"]))
        except ObservationContractError as exc:
            return {"status": "conflict", "findings": [{"code": "contract_json_invalid", "details": exc.details}],
                    "requirements": [], "source_pins": [], "references": [], "basis_current": False}
        if dumps(body) != version["contract_json"] or content_hash(body) != version["content_sha256"]:
            conflicts = True
            findings.append({"code": "contract_hash_mismatch", "version_id": version["id"]})
        try:
            saved_basis = self._safe_json(version["basis_json"], code="contract_basis_invalid", label="saved basis")
            if dumps(saved_basis) != version["basis_json"] or content_hash(saved_basis) != version["basis_sha256"]:
                conflicts = True
                findings.append({"code": "basis_hash_mismatch", "version_id": version["id"]})
            current_basis = self._basis(conn, header["shot_id"], body)
            basis_current = content_hash(current_basis) == version["basis_sha256"]
            if not basis_current:
                unresolved = True
                findings.append({"code": "authored_basis_changed", "fields": current_basis["registry"]})
            for asset in current_basis["referenced_assets"]:
                if asset.get("missing"):
                    unresolved = True
                    findings.append({"code": "basis_asset_dangling", "asset_id": asset["asset_id"]})
                elif asset.get("archived"):
                    unresolved = True
                    findings.append({"code": "basis_asset_archived", "asset_id": asset["asset_id"]})
        except (ObservationContractError, TypeError, ValueError) as exc:
            basis_current = False
            unresolved = True
            findings.append({"code": "authored_basis_unavailable", "reason": str(exc)})
        pin_rows = [dict(row) for row in conn.execute("SELECT * FROM observation_source_pins WHERE version_id=? ORDER BY edge_id", (version["id"],))]
        expected_pins = {item["edge_id"]: item["source_scope"] for item in body["source_pins"]}
        actual_pins = {row["edge_id"]: row["source_scope"] for row in pin_rows}
        if expected_pins != actual_pins:
            conflicts = True
            findings.append({"code": "source_pin_rows_mismatch", "expected_edge_ids": sorted(expected_pins), "actual_edge_ids": sorted(actual_pins)})
        pin_status = []
        for pin in pin_rows:
            state = self._pin_state(conn, pin, header["shot_id"], artifact_cache)
            pin_status.append(state)
            if state["stale"]:
                unresolved = True
                findings.append({"code": "source_pin_stale", "edge_id": pin["edge_id"], "source_scope": pin["source_scope"], "reasons": state["reasons"]})
        if not body["source_pins"]:
            unresolved = True
            findings.append({"code": "no_declared_source_links"})
        if not body["script_intents"]:
            unresolved = True
            findings.append({"code": "no_declared_purpose"})
        for intent in body["script_intents"]:
            pin_scope = expected_pins.get(intent["source_edge_id"])
            if pin_scope != intent["source_scope"]:
                conflicts = True
                findings.append({"code": "intent_source_scope_mismatch", "intent_id": intent["id"], "edge_id": intent["source_edge_id"]})
            if intent["basis"] == "unknown":
                unresolved = True
                findings.append({"code": "intent_basis_unknown", "intent_id": intent["id"], "edge_id": intent["source_edge_id"]})
        requirements = []
        for requirement in body["requirements"]:
            mappings = [{"edge_id": edge_id, "source_scope": expected_pins.get(edge_id)}
                        for edge_id in requirement["source_edge_ids"]]
            pin_lookup = {row["edge_id"]: row for row in pin_status}
            for mapping in mappings:
                state = pin_lookup.get(mapping["edge_id"], {})
                mapping["coverage_kind"] = state.get("coverage_kind")
                mapping["source_node_type"] = state.get("source_node_type")
            missing = not mappings
            stale_ids = [row["edge_id"] for row in pin_status if row["stale"]]
            unresolved_sources = [mapping["edge_id"] for mapping in mappings if mapping["edge_id"] in stale_ids]
            if requirement["priority"] == "unknown":
                state = "open-question"
                unresolved = True
                findings.append({"code": "unknown_requirement", "requirement_id": requirement["id"], "topic": requirement["topic"]})
            elif requirement["priority"] == "must" and missing:
                state = "unresolved"
                unresolved = True
                findings.append({"code": "must_without_source_mapping", "requirement_id": requirement["id"]})
            elif requirement["basis"] == "unknown":
                state = "unresolved"
                unresolved = True
                findings.append({"code": "requirement_basis_unknown", "requirement_id": requirement["id"]})
            elif unresolved_sources:
                state = "review-needed"
                unresolved = True
                findings.append({"code": "requirement_source_review_needed", "requirement_id": requirement["id"], "edge_ids": unresolved_sources})
            elif requirement["priority"] == "prefer" and missing:
                state = "warning"
                findings.append({"code": "prefer_without_source_mapping", "requirement_id": requirement["id"]})
            else:
                # This means the authored link is structurally present only.
                # It never evaluates the statement's meaning or visual result.
                state = "declared-link"
            requirements.append({"id": requirement["id"], "priority": requirement["priority"],
                                 "basis": requirement["basis"], "state": state,
                                 "source_mappings": mappings})
        references = self._reference_states(conn, version["id"], body)
        for reference in references:
            if reference["state"] in ("dangling", "unresolved", "conflict"):
                unresolved = True
                findings.append({"code": reference["reason"], "reference_id": reference["reference_id"]})
        continuity_ids = {row["id"] for row in body["continuity"]}
        if len(continuity_ids) != len(body["continuity"]):
            conflicts = True
            findings.append({"code": "continuity_id_conflict"})
        for note in body["continuity"]:
            for related_id in note["related_shot_ids"]:
                related = conn.execute("SELECT kind,archived FROM entities WHERE id=?", (related_id,)).fetchone()
                if related is None or related["kind"] != "shot":
                    unresolved = True
                    findings.append({"code": "continuity_reference_dangling", "continuity_id": note["id"], "shot_id": related_id})
                elif related["archived"]:
                    unresolved = True
                    findings.append({"code": "continuity_reference_archived", "continuity_id": note["id"], "shot_id": related_id})
        findings.sort(key=lambda item: (item.get("code", ""), str(item.get("edge_id") or item.get("requirement_id") or item.get("intent_id") or item.get("shot_id") or "")))
        status = "conflict" if conflicts else "unresolved" if unresolved else "consistent"
        return {"status": status, "findings": findings, "requirements": requirements,
                "source_pins": pin_status, "references": references, "basis_current": basis_current,
                "method": "Deterministic checks of declared IDs, exact pins, hashes, and authored basis. Prose is not interpreted; no image, camera, physical, or rendered result is verified."}

    def _show(self, conn, contract_id, version_id=None, artifact_cache=None):
        artifact_cache = artifact_cache if artifact_cache is not None else {}
        header, version = self._version(conn, contract_id, version_id)
        body = self._safe_json(version["contract_json"])
        pins = []
        for row in conn.execute("SELECT * FROM observation_source_pins WHERE version_id=? ORDER BY edge_id", (version["id"],)):
            item = dict(row)
            for field in ("source_snapshot", "edge_source_snapshot", "edge_target_snapshot"):
                item[field] = self._safe_json(item[field], label="source pin snapshot")
            pins.append(item)
        references = []
        for row in conn.execute("SELECT reference_id,snapshot_json FROM observation_reference_pins WHERE version_id=? ORDER BY reference_id", (version["id"],)):
            references.append({"reference_id": row["reference_id"], "snapshot": self._safe_json(row["snapshot_json"], label="reference snapshot")})
        history = [dict(row) for row in conn.execute("SELECT id,number,parent_version_id,schema_version,content_sha256,basis_sha256,operation,created_at FROM observation_contract_versions WHERE contract_id=? ORDER BY number", (contract_id,))]
        return {"id": header["id"], "shot_id": header["shot_id"], "revision": header["revision"],
                "current_version_id": header["current_version_id"], "created_at": header["created_at"],
                "updated_at": header["updated_at"], "selected_version_id": version["id"],
                "version": {k: version[k] for k in ("id", "contract_id", "parent_version_id", "number", "schema_version", "content_sha256", "basis_sha256", "operation", "created_at")},
                "contract": body, "source_pins": pins, "reference_pins": references,
                "history": history, "validation": self._validate(conn, header, version, artifact_cache)}

    def show(self, contract_id, version_id=None):
        with self.repo.transaction(False) as conn:
            return self._show(conn, contract_id, version_id)

    def list(self, shot_id=None, include_archived=False, limit=100, offset=0):
        page_bounds(limit, offset)
        where = ["1=1"]
        args = []
        if not include_archived:
            where.append("e.archived=0")
        if shot_id:
            where.append("c.shot_id=?")
            args.append(shot_id)
        clause = " AND ".join(where)
        with self.repo.transaction(False) as conn:
            total = conn.execute("SELECT count(*) FROM observation_contracts c JOIN entities e ON e.id=c.shot_id WHERE " + clause, args).fetchone()[0]
            rows = conn.execute("""SELECT c.id,c.shot_id,c.current_version_id,c.revision,c.created_at,c.updated_at,
              e.title AS shot_title,e.archived AS shot_archived,v.number AS version_number,v.content_sha256
              FROM observation_contracts c JOIN entities e ON e.id=c.shot_id
              JOIN observation_contract_versions v ON v.id=c.current_version_id WHERE """ + clause +
                               " ORDER BY c.created_at,c.id LIMIT ? OFFSET ?", (*args, limit, offset)).fetchall()
            return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset,
                    "next_offset": offset + len(rows) if offset + len(rows) < total else None,
                    "truncated": offset + len(rows) < total}

    def validate(self, contract_id, version_id=None):
        with self.repo.transaction(False) as conn:
            header, version = self._version(conn, contract_id, version_id)
            return {"contract_id": contract_id, "shot_id": header["shot_id"], "revision": header["revision"],
                    "version_id": version["id"], **self._validate(conn, header, version)}

    def diff(self, contract_id, before_version_id, after_version_id):
        with self.repo.transaction(False) as conn:
            header, before = self._version(conn, contract_id, before_version_id)
            _, after = self._version(conn, contract_id, after_version_id)
            left = self._safe_json(before["contract_json"])
            right = self._safe_json(after["contract_json"])
            changes = []
            scalar_keys = ("schema", "notes")
            for key in scalar_keys:
                if left.get(key) != right.get(key):
                    changes.append({"path": "/" + key, "before": left.get(key), "after": right.get(key)})
            groups = (("source_pins", "edge_id"), ("script_intents", "id"),
                      ("requirements", "id"), ("continuity", "id"))
            for group, key in groups:
                old = {item[key]: item for item in left.get(group, [])}
                new = {item[key]: item for item in right.get(group, [])}
                for item_id in sorted(old.keys() | new.keys()):
                    if old.get(item_id) != new.get(item_id):
                        changes.append({"path": f"/{group}/{item_id}", "before": old.get(item_id), "after": new.get(item_id)})
            old_refs, new_refs = sorted(left.get("references", [])), sorted(right.get("references", []))
            if old_refs != new_refs:
                changes.append({"path": "/references", "before": old_refs, "after": new_refs})
            return {"contract_id": contract_id, "shot_id": header["shot_id"],
                    "before_version_id": before["id"], "after_version_id": after["id"],
                    "before_sha256": before["content_sha256"], "after_sha256": after["content_sha256"],
                    "content_changed": before["content_sha256"] != after["content_sha256"],
                    "changes": changes}

    def integrity_issues(self):
        """Read-only doctor checks for contract headers and immutable records."""
        issues = []
        artifact_cache = {}
        with self.repo.readonly_transaction() as conn:
            headers = conn.execute("SELECT * FROM observation_contracts ORDER BY id").fetchall()
            for header_row in headers:
                header = dict(header_row)
                try:
                    versions = [dict(row) for row in conn.execute("SELECT * FROM observation_contract_versions WHERE contract_id=? ORDER BY number", (header["id"],))]
                    if not versions or header["current_version_id"] != versions[-1]["id"] or header["revision"] != len(versions):
                        raise ValueError("header_revision_or_pointer_mismatch")
                    for version in versions:
                        body = self._safe_json(version["contract_json"], label="saved contract")
                        normalized = _validate_body(body)
                        if normalized != body or dumps(body) != version["contract_json"] or content_hash(body) != version["content_sha256"]:
                            raise ValueError("contract_content_mismatch")
                        basis = self._safe_json(version["basis_json"], code="contract_basis_invalid", label="saved basis")
                        if dumps(basis) != version["basis_json"] or content_hash(basis) != version["basis_sha256"]:
                            raise ValueError("contract_basis_mismatch")
                        pins = [dict(row) for row in conn.execute("SELECT * FROM observation_source_pins WHERE version_id=? ORDER BY edge_id", (version["id"],))]
                        if {pin["edge_id"]: pin["source_scope"] for pin in pins} != {pin["edge_id"]: pin["source_scope"] for pin in body["source_pins"]}:
                            raise ValueError("contract_pin_rows_mismatch")
                        pin_issues = []
                        for pin in pins:
                            pin_reasons = self._pin_integrity_reasons(conn, pin, header["shot_id"], artifact_cache)
                            if pin_reasons:
                                pin_issues.append(pin["edge_id"] + "=" + ",".join(pin_reasons))
                        if pin_issues:
                            raise ValueError("contract_source_pin_integrity_mismatch:" + ";".join(pin_issues))
                        refs = {row[0] for row in conn.execute("SELECT reference_id FROM observation_reference_pins WHERE version_id=?", (version["id"],))}
                        if refs != set(body["references"]):
                            raise ValueError("contract_reference_pins_mismatch")
                        for ref in conn.execute("SELECT snapshot_json FROM observation_reference_pins WHERE version_id=?", (version["id"],)):
                            self._safe_json(ref[0], label="reference snapshot")
                except Exception as exc:
                    issues.append({"severity": "error", "code": "observation_contract_integrity", "contract_id": header["id"],
                                   "message": "An observation contract version or exact pin is inconsistent. Preserve the project folder and inspect a verified backup.",
                                   "details": {"reason": str(exc)}})
        return issues
