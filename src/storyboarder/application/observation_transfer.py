"""Portable, deterministic export and exact-history restore for observation plans.

The plan contains no project filesystem locations. Contract bodies, saved bases,
and pin snapshots remain byte-for-byte canonical JSON values; data that cannot
be represented safely is reported instead of being rewritten.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import uuid
from typing import Any

from storyboarder.domain.documents import content_hash
from storyboarder.domain.errors import StoryboardError
from storyboarder.domain.models import dumps
from .observation_contracts import (
    BASIS_SCHEMA,
    ObservationContractError,
    ObservationContracts,
    _validate_body,
)


PLAN_SCHEMA = "storyboarder.observation-plan/v1"
MAX_PLAN_BYTES = 48 * 1024 * 1024
MAX_CONTRACTS = 10_000
MAX_VERSIONS = 100_000
MAX_JSON_DEPTH = 80
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
ABSOLUTE_PATH_RE = re.compile(
    r"(?:^|[\s\"'=(])/(?!/)[A-Za-z0-9._~+-]+(?:/[^\s\"'<>|?]*)?|"
    r"(?:^|[\s\"'=(])[A-Za-z]:[\\/](?:[^\\/\s]+[\\/])*[^\\/\s]+|"
    r"\\\\[^\\\s]+\\[^\\\s]+|file://",
    re.IGNORECASE,
)
SECRET_VALUE_RE = re.compile(
    r"\bBearer\s+\S+|\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{20,}|"
    r"AKIA[A-Z0-9]{16}|AIza[A-Za-z0-9_-]{30,}|xox[baprs]-[A-Za-z0-9-]{20,}|"
    r"glpat-[A-Za-z0-9_-]{20,})\b|\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b|"
    r"\b(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*[A-Za-z0-9_./+-]{8,}",
    re.IGNORECASE,
)
SENSITIVE_KEYS = {
    "access_token", "api_key", "apikey", "authorization", "client_secret",
    "credential", "credentials", "password", "private_key", "secret", "token",
}
RUNTIME_KEYS = {
    "argv", "cwd", "command", "environment", "env", "executable", "launch",
    "launch_args", "launch_options", "launcher", "pid", "process_id",
    "runtime", "working_directory", "workspace", "workspace_path", "path",
    "file_path", "source_path", "artifact_path", "project_root", "root", "directory",
}
HEADER_KEYS = {"id", "shot_id", "current_version_id", "revision", "created_at", "updated_at", "versions"}
VERSION_KEYS = {
    "id", "contract_id", "parent_version_id", "number", "schema_version",
    "contract_json", "content_sha256", "basis_json", "basis_sha256", "operation",
    "sealed", "created_at", "source_pins", "reference_pins",
}
PIN_KEYS = {
    "version_id", "edge_id", "source_scope", "document_id", "source_version_id",
    "node_id", "logical_id", "source_sha256", "scope_sha256", "document_sha256",
    "artifact_sha256", "source_snapshot", "edge_source_snapshot", "edge_target_snapshot",
    "created_at",
}
REFERENCE_PIN_KEYS = {"version_id", "reference_id", "snapshot", "created_at"}
HEX_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SCREENPLAY_SCENE_POINTER_RE = re.compile(r"^/document/scenes/(?:0|[1-9][0-9]*)$")
SCREENPLAY_ELEMENT_POINTER_RE = re.compile(r"^/document/scenes/(?:0|[1-9][0-9]*)/body/(?:0|[1-9][0-9]*)$")


class ObservationTransferError(StoryboardError):
    """Expected transfer rejection with a stable cross-interface code."""

    def __init__(self, code: str, message: str, details: dict | None = None, status: int = 422):
        super().__init__(message, details)
        self.code = code
        self.status = status


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _load_json_object(raw: str, label: str) -> Any:
    def unique_pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON property: {key}")
            result[key] = value
        return result

    def finite_float(token):
        number = float(token)
        if not math.isfinite(number):
            raise ValueError(f"Invalid number: {token}")
        return number

    try:
        value = json.loads(
            raw,
            object_pairs_hook=unique_pairs,
            parse_float=finite_float,
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(f"Invalid number: {token}")),
        )
    except (TypeError, ValueError, json.JSONDecodeError, RecursionError) as exc:
        raise ObservationTransferError("observation_plan_invalid", f"The {label} is not valid strict JSON.", {"reason": str(exc)}) from exc
    _check_depth(value, label)
    return value


def _check_depth(value: Any, label: str) -> None:
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > MAX_JSON_DEPTH:
            raise ObservationTransferError("observation_plan_invalid", f"The {label} exceeds the supported nesting depth.")
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)


def _strict_json_value(raw: str, label: str) -> Any:
    value = _load_json_object(raw, label)
    if not isinstance(value, (dict, list, str, int, float, bool)) and value is not None:
        raise ObservationTransferError("observation_plan_invalid", f"The {label} has an unsupported JSON value.")
    if dumps(value) != raw:
        raise ObservationTransferError("observation_plan_integrity_error", f"The saved {label} is not canonical JSON.")
    return value


def _supported_source_pointer(value: Any, node_type: Any) -> bool:
    """Accept only the source pointers emitted for screenplay scene and element nodes."""
    if not isinstance(value, str):
        return False
    if node_type == "scene":
        return SCREENPLAY_SCENE_POINTER_RE.fullmatch(value) is not None
    if isinstance(node_type, str) and node_type not in ("", "screenplay"):
        return SCREENPLAY_ELEMENT_POINTER_RE.fullmatch(value) is not None
    return False


def _is_typed_edge_source_pointer(path: tuple[str | int, ...]) -> bool:
    """Identify the source pointer field by its record shape, never by a suffix alone."""
    if (len(path) == 8 and path[0] == "contracts" and isinstance(path[1], int)
            and path[2] == "versions" and isinstance(path[3], int)
            and path[4] == "source_pins" and isinstance(path[5], int)
            and path[6:] == ("edge_source_snapshot", "source_pointer")):
        return True
    return (len(path) == 6 and path[0] == "versions" and isinstance(path[1], int)
            and path[2] == "source_pins" and isinstance(path[3], int)
            and path[4:] == ("edge_source_snapshot", "source_pointer"))


def _portable_losses(value: Any) -> list[dict[str, str]]:
    """Fail closed on path, credential, and runtime fields without sanitizing history."""
    losses: list[dict[str, str]] = []
    stack = [((), "$", value)]
    while stack:
        path, pointer, item = stack.pop()
        if isinstance(item, dict):
            for key, child in item.items():
                child_path = path + (key,)
                child_pointer = f"{pointer}/{key}"
                if key == "source_pointer" and _is_typed_edge_source_pointer(child_path):
                    if _supported_source_pointer(child, item.get("node_type")):
                        continue
                    losses.append({"path": child_pointer, "reason": "unsupported_source_pointer"})
                    continue
                key_lower = str(key).casefold()
                compact = re.sub(r"[^a-z0-9]", "", key_lower)
                sensitive = key_lower in SENSITIVE_KEYS or any(
                    marker in compact for marker in ("apikey", "accesstoken", "refreshtoken", "clientsecret", "password", "credential", "privatekey", "signingkey", "certificate")
                )
                runtime = key_lower in RUNTIME_KEYS or any(
                    marker in compact for marker in ("launch", "runtime", "argv", "executable", "workingdirectory", "workingdir", "workspace", "path", "directory", "root", "cwd", "environment", "processid", "pid")
                )
                if sensitive:
                    losses.append({"path": child_pointer, "reason": "credential_field"})
                elif runtime:
                    losses.append({"path": child_pointer, "reason": "runtime_launch_field"})
                else:
                    stack.append((child_path, child_pointer, child))
        elif isinstance(item, list):
            stack.extend((path + (index,), f"{pointer}/{index}", child) for index, child in enumerate(item))
        elif isinstance(item, str):
            if ABSOLUTE_PATH_RE.search(item):
                losses.append({"path": pointer, "reason": "absolute_path"})
            if SECRET_VALUE_RE.search(item):
                losses.append({"path": pointer, "reason": "credential_shaped_value"})
    return sorted(losses, key=lambda row: (row["path"], row["reason"]))


def _canonical_snapshot(raw: str, label: str) -> Any:
    return _strict_json_value(raw, label)


def _pin_record(row) -> dict:
    item = dict(row)
    for key in ("source_snapshot", "edge_source_snapshot", "edge_target_snapshot"):
        item[key] = _canonical_snapshot(item[key], "source pin snapshot")
    return item


def _reference_record(row) -> dict:
    item = dict(row)
    item["snapshot"] = _canonical_snapshot(item.pop("snapshot_json"), "reference snapshot")
    return item


def _version_record(conn, row) -> dict:
    version = dict(row)
    version["contract_json"] = _canonical_snapshot(version.pop("contract_json"), "saved contract")
    version["basis_json"] = _canonical_snapshot(version.pop("basis_json"), "saved contract basis")
    version["source_pins"] = [
        _pin_record(pin)
        for pin in conn.execute("SELECT * FROM observation_source_pins WHERE version_id=? ORDER BY edge_id", (version["id"],))
    ]
    version["reference_pins"] = [
        _reference_record(ref)
        for ref in conn.execute("SELECT * FROM observation_reference_pins WHERE version_id=? ORDER BY reference_id", (version["id"],))
    ]
    return version


def _build_manifest(core: dict) -> dict:
    version_index = []
    for contract in core["contracts"]:
        for version in contract["versions"]:
            version_index.append({
                "contract_id": contract["id"],
                "version_id": version["id"],
                "record_sha256": _sha(version),
                "content_sha256": version["content_sha256"],
                "basis_sha256": version["basis_sha256"],
            })
    return {"payload_sha256": _sha(core), "versions": version_index}


def export_observation_plan(service) -> bytes:
    """Return a deterministic UTF-8 project plan with exact immutable history."""
    contracts = []
    with service.repo.readonly_transaction() as conn:
        headers = conn.execute("SELECT * FROM observation_contracts ORDER BY id").fetchall()
        total_versions = 0
        for row in headers:
            header = dict(row)
            versions = conn.execute(
                "SELECT * FROM observation_contract_versions WHERE contract_id=? ORDER BY number",
                (header["id"],),
            ).fetchall()
            total_versions += len(versions)
            contracts.append({
                "id": header["id"],
                "shot_id": header["shot_id"],
                "current_version_id": header["current_version_id"],
                "revision": header["revision"],
                "created_at": header["created_at"],
                "updated_at": header["updated_at"],
                "versions": [_version_record(conn, version) for version in versions],
            })
        if len(contracts) > MAX_CONTRACTS or total_versions > MAX_VERSIONS:
            raise ObservationTransferError("observation_plan_too_large", "The project has more observation history than one portable plan supports.")
        core = {"schema": PLAN_SCHEMA, "project_id": service.project.id, "contracts": contracts}
        losses = _portable_losses(core)
        if losses:
            raise ObservationTransferError(
                "observation_plan_not_portable",
                "The plan contains path, credential, or runtime-only data that cannot be exported without changing saved history.",
                {"adapter_losses": losses[:200], "loss_count": len(losses)},
            )
        result = {**core, "manifest": _build_manifest(core)}
    encoded = _canonical_bytes(result) + b"\n"
    if len(encoded) > MAX_PLAN_BYTES:
        raise ObservationTransferError("observation_plan_too_large", "The project history exceeds the 48 MiB portable plan limit.")
    return encoded


def _read_plan(source: bytes | str) -> dict:
    if isinstance(source, bytes):
        raw_bytes = source
        try:
            raw = source.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ObservationTransferError("observation_plan_invalid", "The plan must be UTF-8 JSON.") from exc
    elif isinstance(source, str):
        raw = source
        try:
            raw_bytes = source.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ObservationTransferError("observation_plan_invalid", "The plan must be UTF-8 JSON.") from exc
    else:
        raise ObservationTransferError("observation_plan_invalid", "Provide the plan as UTF-8 text or bytes.")
    if len(raw_bytes) > MAX_PLAN_BYTES:
        raise ObservationTransferError("observation_plan_too_large", "The plan exceeds the 48 MiB import limit.")
    result = _load_json_object(raw, "observation plan")
    _validate_plan(result)
    return result


def _require_keys(value: Any, keys: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise ObservationTransferError("observation_plan_invalid", f"The {label} has missing or unsupported fields.",
                                       {"expected": sorted(keys), "actual": sorted(value) if isinstance(value, dict) else None})
    return value


def _require_string(value: Any, label: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ObservationTransferError("observation_plan_invalid", f"The {label} must be non-empty text.")
    return value


def _require_id(value: Any, label: str) -> str:
    text = _require_string(value, label)
    if not UUID_RE.fullmatch(text) or str(uuid.UUID(text)) != text:
        raise ObservationTransferError("observation_plan_invalid", f"The {label} must be a canonical lowercase UUID.")
    return text


def _require_sha(value: Any, label: str) -> str:
    text = _require_string(value, label)
    if not HEX_SHA256_RE.fullmatch(text):
        raise ObservationTransferError("observation_plan_invalid", f"The {label} must be a lowercase SHA-256 digest.")
    return text


def _validate_pin(pin: Any, version_id: str) -> None:
    pin = _require_keys(pin, PIN_KEYS, "source pin")
    if pin["version_id"] != version_id:
        raise ObservationTransferError("observation_plan_integrity_error", "A source pin belongs to a different contract version.")
    for field in ("version_id", "edge_id", "document_id", "source_version_id", "node_id"):
        _require_id(pin[field], f"source pin {field}")
    for field in ("logical_id", "source_scope", "created_at"):
        _require_string(pin[field], f"source pin {field}")
    if pin["source_scope"] not in ("direct-element", "scene-context"):
        raise ObservationTransferError("observation_plan_invalid", "A source pin has an unsupported scope.")
    for field in ("source_sha256", "scope_sha256", "document_sha256", "artifact_sha256"):
        _require_sha(pin[field], f"source pin {field}")
    for field in ("source_snapshot", "edge_source_snapshot", "edge_target_snapshot"):
        if not isinstance(pin[field], dict):
            raise ObservationTransferError("observation_plan_invalid", f"The source pin {field} must be an object.")
        if dumps(pin[field]) != _canonical_bytes(pin[field]).decode("utf-8"):
            raise ObservationTransferError("observation_plan_invalid", f"The source pin {field} is not canonicalizable.")
    expected_keys = {
        "source_snapshot": {"document_id", "document_version_id", "document_sha256", "artifact_sha256", "node_id", "logical_id", "node_type", "identity", "source_sha256", "scope_sha256", "payload"},
        "edge_source_snapshot": {"id", "version_id", "logical_id", "parent_id", "node_type", "position", "title", "source_pointer", "content_sha256", "identity", "document_id", "document_kind", "version_label", "is_current", "archived", "type", "key", "label"},
        "edge_target_snapshot": {"id", "kind", "parent_id", "position", "title", "description", "fields", "tags", "aliases", "archived", "revision", "created_at", "updated_at", "type", "key", "label"},
    }
    for field, keys in expected_keys.items():
        if set(pin[field]) != keys:
            raise ObservationTransferError("observation_plan_invalid", f"The source pin {field} does not match the supported typed snapshot.")
    source_snapshot = pin["source_snapshot"]
    if (source_snapshot["document_id"] != pin["document_id"]
            or source_snapshot["document_version_id"] != pin["source_version_id"]
            or source_snapshot["node_id"] != pin["node_id"]
            or source_snapshot["logical_id"] != pin["logical_id"]
            or source_snapshot["source_sha256"] != pin["source_sha256"]
            or source_snapshot["scope_sha256"] != pin["scope_sha256"]
            or source_snapshot["document_sha256"] != pin["document_sha256"]
            or source_snapshot["artifact_sha256"] != pin["artifact_sha256"]
            or not isinstance(source_snapshot["payload"], dict)):
        raise ObservationTransferError("observation_plan_integrity_error", "A source pin snapshot does not match its exact IDs and hashes.")
    if (pin["edge_source_snapshot"].get("id") != pin["node_id"]
            or pin["edge_source_snapshot"].get("version_id") != pin["source_version_id"]):
        raise ObservationTransferError("observation_plan_integrity_error", "An edge source snapshot does not match its exact source pin.")
    if not _supported_source_pointer(pin["edge_source_snapshot"].get("source_pointer"),
                                     pin["edge_source_snapshot"].get("node_type")):
        raise ObservationTransferError("observation_plan_invalid", "An edge source snapshot has an unsupported screenplay source pointer.")
    if pin["edge_target_snapshot"].get("id") is None:
        raise ObservationTransferError("observation_plan_integrity_error", "An edge target snapshot must preserve its target ID.")


def _validate_version(version: Any, contract_id: str, expected_number: int) -> None:
    version = _require_keys(version, VERSION_KEYS, "contract version")
    version_id = _require_id(version["id"], "version id")
    if _require_id(version["contract_id"], "version contract_id") != contract_id:
        raise ObservationTransferError("observation_plan_integrity_error", "A version is assigned to a different contract.")
    parent = version["parent_version_id"]
    if parent is not None:
        _require_id(parent, "parent version id")
    if isinstance(version["number"], bool) or not isinstance(version["number"], int) or version["number"] != expected_number:
        raise ObservationTransferError("observation_plan_integrity_error", "Contract history numbers must be contiguous and ordered.")
    if isinstance(version["schema_version"], bool) or not isinstance(version["schema_version"], int) or version["schema_version"] != 1:
        raise ObservationTransferError("observation_plan_invalid", "Only observation contract version schema 1 is supported.")
    if isinstance(version["sealed"], bool) or not isinstance(version["sealed"], int) or version["sealed"] != 1:
        raise ObservationTransferError("observation_plan_integrity_error", "Only sealed immutable contract history can be transferred.")
    if version["operation"] not in ("create", "revise", "rebase"):
        raise ObservationTransferError("observation_plan_invalid", "A contract version has an unsupported operation.")
    _require_string(version["created_at"], "version created_at")
    for field in ("content_sha256", "basis_sha256"):
        _require_sha(version[field], field)
    body, basis = version["contract_json"], version["basis_json"]
    if not isinstance(body, dict) or not isinstance(basis, dict):
        raise ObservationTransferError("observation_plan_invalid", "Saved contract and basis values must be JSON objects.")
    try:
        normalized = _validate_body(body)
    except ObservationContractError as exc:
        raise ObservationTransferError("observation_plan_invalid", "A saved contract body does not match its schema.", {"details": exc.details}) from exc
    if normalized != body or content_hash(body) != version["content_sha256"]:
        raise ObservationTransferError("observation_plan_integrity_error", "A saved contract body does not match its canonical hash.")
    _validate_basis_shape(basis)
    if content_hash(basis) != version["basis_sha256"]:
        raise ObservationTransferError("observation_plan_integrity_error", "A saved contract basis does not match its canonical hash.")
    if not isinstance(version["source_pins"], list) or not isinstance(version["reference_pins"], list):
        raise ObservationTransferError("observation_plan_invalid", "Contract pins must be arrays.")
    pin_ids = [pin.get("edge_id") for pin in version["source_pins"] if isinstance(pin, dict)]
    if len(pin_ids) != len(version["source_pins"]) or len(pin_ids) != len(set(pin_ids)):
        raise ObservationTransferError("observation_plan_integrity_error", "A version repeats or malforms an exact source pin row.")
    for pin in version["source_pins"]:
        _validate_pin(pin, version_id)
    if {row["edge_id"]: row["source_scope"] for row in version["source_pins"]} != {
        row["edge_id"]: row["source_scope"] for row in body["source_pins"]
    }:
        raise ObservationTransferError("observation_plan_integrity_error", "Saved source pin rows do not match the contract body.")
    references = set()
    for reference in version["reference_pins"]:
        reference = _require_keys(reference, REFERENCE_PIN_KEYS, "reference pin")
        if reference["version_id"] != version_id:
            raise ObservationTransferError("observation_plan_integrity_error", "A reference pin belongs to a different version.")
        _require_id(reference["version_id"], "reference pin version_id")
        _require_id(reference["reference_id"], "reference pin reference_id")
        _require_string(reference["created_at"], "reference pin created_at")
        snapshot = reference["snapshot"]
        if (not isinstance(snapshot, dict) or set(snapshot) != {"reference_id", "kind", "type"}
                or snapshot.get("reference_id") != reference["reference_id"] or snapshot.get("kind") != "asset"
                or snapshot.get("type") not in {"character", "location", "prop", "reference"}):
            raise ObservationTransferError("observation_plan_integrity_error", "A reference snapshot does not match its exact asset identity.")
        if reference["reference_id"] in references:
            raise ObservationTransferError("observation_plan_invalid", "A version repeats a reference pin.")
        references.add(reference["reference_id"])
    if references != set(body["references"]):
        raise ObservationTransferError("observation_plan_integrity_error", "Saved reference rows do not match the contract body.")


def _validate_basis_shape(basis: dict) -> None:
    top_keys = {"schema", "registry", "shot", "continuity_shots", "referenced_assets"}
    if set(basis) != top_keys or basis.get("schema") != BASIS_SCHEMA:
        raise ObservationTransferError("observation_plan_invalid", "The saved basis does not match the supported typed basis schema.")
    registry_keys = {"shot_fields", "effective_context_scalars", "effective_context_directions", "excluded"}
    registry = basis["registry"]
    if (not isinstance(registry, dict) or set(registry) != registry_keys
            or any(not isinstance(registry[key], list) or any(not isinstance(item, str) for item in registry[key]) for key in registry_keys)):
        raise ObservationTransferError("observation_plan_invalid", "The saved basis registry is not in the supported shape.")
    shot_fields = {"action", "dialogue", "framing", "camera", "duration", "continuity", "constraints"}
    shot_keys = {"shot_id", "parent_scene_id", "archived", "effective_context", "assignments"} | shot_fields
    shot = basis["shot"]
    if not isinstance(shot, dict) or set(shot) != shot_keys or not isinstance(shot["archived"], bool):
        raise ObservationTransferError("observation_plan_invalid", "The saved shot basis is not in the supported shape.")
    if not isinstance(shot["assignments"], list) or not isinstance(shot["effective_context"], dict):
        raise ObservationTransferError("observation_plan_invalid", "The saved shot context is not in the supported shape.")
    if not isinstance(basis["continuity_shots"], list) or not isinstance(basis["referenced_assets"], list):
        raise ObservationTransferError("observation_plan_invalid", "Saved continuity and reference basis values must be arrays.")
    for item in basis["continuity_shots"]:
        if not isinstance(item, dict):
            raise ObservationTransferError("observation_plan_invalid", "A continuity basis entry must be an object.")
        if item.get("missing") is True:
            if set(item) != {"shot_id", "missing"}:
                raise ObservationTransferError("observation_plan_invalid", "A missing continuity basis entry has unsupported fields.")
        elif set(item) != {"shot_id", "parent_scene_id", "archived", "assignments", "effective_context"} | shot_fields:
            raise ObservationTransferError("observation_plan_invalid", "A continuity shot basis is not in the supported shape.")
        elif not isinstance(item["archived"], bool) or not isinstance(item["assignments"], list):
            raise ObservationTransferError("observation_plan_invalid", "A continuity shot basis is not in the supported shape.")
    asset_keys = {"asset_id", "kind", "archived", "description", "fields", "tags", "aliases", "media"}
    for asset in basis["referenced_assets"]:
        if not isinstance(asset, dict):
            raise ObservationTransferError("observation_plan_invalid", "A referenced asset basis entry must be an object.")
        if asset.get("missing") is True:
            if set(asset) != {"asset_id", "missing"}:
                raise ObservationTransferError("observation_plan_invalid", "A missing asset basis entry has unsupported fields.")
        elif set(asset) != asset_keys:
            raise ObservationTransferError("observation_plan_invalid", "A referenced asset basis entry is not in the supported shape.")
        elif (asset.get("kind") != "asset" or not isinstance(asset.get("archived"), bool)
              or not isinstance(asset.get("fields"), dict) or set(asset["fields"]) != {"type", "notes"}
              or not isinstance(asset.get("tags"), list) or not isinstance(asset.get("aliases"), list)
              or not isinstance(asset.get("media"), list)):
            raise ObservationTransferError("observation_plan_invalid", "A referenced asset basis entry is not in the supported shape.")


def _validate_plan(plan: Any) -> None:
    top = _require_keys(plan, {"schema", "project_id", "contracts", "manifest"}, "plan")
    if top["schema"] != PLAN_SCHEMA:
        raise ObservationTransferError("observation_plan_invalid", "This observation plan schema is not supported.")
    _require_id(top["project_id"], "project id")
    if not isinstance(top["contracts"], list) or len(top["contracts"]) > MAX_CONTRACTS:
        raise ObservationTransferError("observation_plan_too_large", "The plan contains too many contracts.")
    contract_ids, shots, version_ids, total_versions = set(), set(), set(), 0
    previous_contract_id = ""
    for contract in top["contracts"]:
        contract = _require_keys(contract, HEADER_KEYS, "contract header")
        contract_id = _require_id(contract["id"], "contract id")
        shot_id = _require_id(contract["shot_id"], "shot id")
        if contract_id <= previous_contract_id:
            raise ObservationTransferError("observation_plan_invalid", "Contracts must be sorted by stable contract ID.")
        previous_contract_id = contract_id
        if contract_id in contract_ids or shot_id in shots:
            raise ObservationTransferError("observation_plan_invalid", "A plan repeats a contract ID or shot owner.")
        contract_ids.add(contract_id)
        shots.add(shot_id)
        _require_id(contract["current_version_id"], "current version id")
        if isinstance(contract["revision"], bool) or not isinstance(contract["revision"], int) or contract["revision"] < 1:
            raise ObservationTransferError("observation_plan_invalid", "A contract revision must be a positive integer.")
        _require_string(contract["created_at"], "contract created_at")
        _require_string(contract["updated_at"], "contract updated_at")
        versions = contract["versions"]
        if not isinstance(versions, list) or not versions or contract["revision"] != len(versions):
            raise ObservationTransferError("observation_plan_integrity_error", "A contract must include its complete revision history.")
        previous = None
        for number, version in enumerate(versions, 1):
            _validate_version(version, contract_id, number)
            if version["id"] in version_ids or version["id"] == contract_id:
                raise ObservationTransferError("observation_plan_invalid", "A plan repeats a stable history ID.")
            version_ids.add(version["id"])
            expected_parent = previous
            if version["parent_version_id"] != expected_parent:
                raise ObservationTransferError("observation_plan_integrity_error", "Contract history does not form one exact parent chain.")
            if number == 1 and version["operation"] != "create":
                raise ObservationTransferError("observation_plan_integrity_error", "The first contract version must preserve its create operation.")
            previous = version["id"]
            total_versions += 1
    if total_versions > MAX_VERSIONS:
        raise ObservationTransferError("observation_plan_too_large", "The plan contains too many contract versions.")
    for contract in top["contracts"]:
        if contract["current_version_id"] != contract["versions"][-1]["id"]:
            raise ObservationTransferError("observation_plan_integrity_error", "A contract current version must point to the end of its history.")
    manifest = _require_keys(top["manifest"], {"payload_sha256", "versions"}, "hash manifest")
    _require_sha(manifest["payload_sha256"], "manifest payload hash")
    if not isinstance(manifest["versions"], list):
        raise ObservationTransferError("observation_plan_invalid", "The version hash manifest must be an array.")
    core = {"schema": top["schema"], "project_id": top["project_id"], "contracts": top["contracts"]}
    expected = _build_manifest(core)
    if manifest != expected:
        raise ObservationTransferError("observation_plan_integrity_error", "The observation plan hash manifest does not match its content.")
    losses = _portable_losses(core)
    if losses:
        raise ObservationTransferError("observation_plan_not_portable", "The plan contains non-portable or credential-shaped content.",
                                       {"adapter_losses": losses[:200], "loss_count": len(losses)})


def _db_contract(conn, contract_id: str) -> dict | None:
    header = conn.execute("SELECT * FROM observation_contracts WHERE id=?", (contract_id,)).fetchone()
    if header is None:
        return None
    item = dict(header)
    versions = conn.execute("SELECT * FROM observation_contract_versions WHERE contract_id=? ORDER BY number", (contract_id,)).fetchall()
    return {
        "id": item["id"], "shot_id": item["shot_id"], "current_version_id": item["current_version_id"],
        "revision": item["revision"], "created_at": item["created_at"], "updated_at": item["updated_at"],
        "versions": [_version_record(conn, version) for version in versions],
    }


def _target_digest(conn) -> str:
    """Hash logical project state so a dry-run receipt cannot outlive edits."""
    tables = []
    names = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    for name in names:
        safe_name = '"' + name.replace('"', '""') + '"'
        columns = [row[1] for row in conn.execute(f"PRAGMA table_info({safe_name})")]
        if not columns:
            continue
        try:
            rows = conn.execute(f"SELECT * FROM {safe_name} ORDER BY rowid").fetchall()
        except Exception:
            rows = conn.execute(f"SELECT * FROM {safe_name}").fetchall()
        encoded_rows = []
        for row in rows:
            encoded = []
            for value in tuple(row):
                if isinstance(value, bytes):
                    encoded.append({"$bytes": base64.b64encode(value).decode("ascii")})
                elif isinstance(value, float) and not math.isfinite(value):
                    raise ObservationTransferError("observation_transfer_state_invalid", "Target project state contains a non-finite number.")
                else:
                    encoded.append(value)
            encoded_rows.append(encoded)
        tables.append({"name": name, "columns": columns, "rows": encoded_rows})
    return _sha({"schema_version": conn.execute("PRAGMA user_version").fetchone()[0], "tables": tables})


def _artifact_state(conn, service, plan: dict) -> tuple[str, dict[str, bool]]:
    """Bind relevant source bytes into dry-run receipts without exporting paths."""
    checker = ObservationContracts(service)
    versions = {}
    for contract in plan["contracts"]:
        for version in contract["versions"]:
            for pin in version["source_pins"]:
                versions[pin["source_version_id"]] = None
    state, available = [], {}
    for version_id in sorted(versions):
        row = conn.execute("SELECT source_artifact_id,content_sha256 FROM document_versions WHERE id=?", (version_id,)).fetchone()
        if row is None:
            actual = None
            artifact_hash = None
        else:
            artifact = conn.execute("SELECT sha256 FROM source_artifacts WHERE id=?", (row["source_artifact_id"],)).fetchone()
            artifact_hash = artifact["sha256"] if artifact else None
            checked = checker._artifact_check(conn, {"source_artifact_id": row["source_artifact_id"],
                                                     "content_sha256": row["content_sha256"]})
            actual = checked["sha256"] if checked else None
        available[version_id] = actual is not None
        state.append({"source_version_id": version_id, "artifact_sha256": artifact_hash,
                      "verified_bytes_sha256": actual})
    return _sha(state), available


def _pin_conflict(conn, pin: dict, shot_id: str, historical_scene_id: str | None) -> str | None:
    edge = conn.execute("SELECT * FROM provenance_edges WHERE id=?", (pin["edge_id"],)).fetchone()
    if edge is None:
        return "source_edge_missing"
    edge = dict(edge)
    expected_target = shot_id if pin["source_scope"] == "direct-element" else historical_scene_id
    if (edge["source_type"] != "node" or edge["source_id"] != pin["node_id"]
            or edge["target_type"] != "entity" or edge["target_id"] != expected_target
            or edge["relation"] != "visualizes"):
        return "source_edge_identity_mismatch"
    source_node = conn.execute("""SELECT n.*,v.document_id,v.content_sha256 AS version_sha256,v.source_artifact_id,
       d.kind AS document_kind,d.archived AS document_archived,a.sha256 AS artifact_sha256
       FROM document_nodes n JOIN document_versions v ON v.id=n.version_id
       JOIN documents d ON d.id=v.document_id JOIN source_artifacts a ON a.id=v.source_artifact_id
       WHERE n.id=?""", (pin["node_id"],)).fetchone()
    if source_node is None:
        return "source_node_missing"
    node = dict(source_node)
    if (node["version_id"] != pin["source_version_id"] or node["document_id"] != pin["document_id"]
            or node["logical_id"] != pin["logical_id"] or node["identity"] != "explicit"
            or node["node_type"] == "screenplay" or node["document_kind"] != "screenplay"
            or node["content_sha256"] != pin["source_sha256"]
            or node["version_sha256"] != pin["document_sha256"]
            or node["artifact_sha256"] != pin["artifact_sha256"]):
        return "source_hash_or_identity_mismatch"
    try:
        payload = _load_json_object(node["payload"], "source node payload")
        edge_source = _load_json_object(edge["source_snapshot"], "edge source snapshot")
        edge_target = _load_json_object(edge["target_snapshot"], "edge target snapshot")
    except ObservationTransferError:
        return "source_snapshot_invalid"
    if content_hash(payload) != node["content_sha256"]:
        return "source_hash_or_identity_mismatch"
    if edge_source != pin["edge_source_snapshot"] or edge_target != pin["edge_target_snapshot"]:
        return "source_edge_snapshot_mismatch"
    if edge_source.get("id") != node["id"] or edge_source.get("version_id") != node["version_id"]:
        return "source_edge_snapshot_mismatch"
    if edge_target.get("id") != edge["target_id"]:
        return "source_edge_snapshot_mismatch"
    scope_hash = pin["source_sha256"] if pin["source_scope"] == "direct-element" else ObservationContracts._context_subtree_hash(conn, node["version_id"], node["id"])
    if scope_hash != pin["scope_sha256"]:
        return "source_scope_hash_mismatch"
    expected_source = {
        "document_id": node["document_id"], "document_version_id": node["version_id"],
        "document_sha256": node["version_sha256"], "artifact_sha256": node["artifact_sha256"],
        "node_id": node["id"], "logical_id": node["logical_id"], "node_type": node["node_type"],
        "identity": node["identity"], "source_sha256": node["content_sha256"],
        "scope_sha256": scope_hash, "payload": payload,
    }
    if pin["source_snapshot"] != expected_source:
        return "source_pin_snapshot_mismatch"
    target = conn.execute("SELECT id,kind FROM entities WHERE id=?", (edge["target_id"],)).fetchone()
    target_kind = "shot" if pin["source_scope"] == "direct-element" else "scene"
    if target is None or target["kind"] != target_kind:
        return "source_edge_target_kind_mismatch"
    return None


def _contract_conflicts(conn, service, contract: dict) -> list[dict[str, str]]:
    conflicts = []
    shot = conn.execute("SELECT id,kind FROM entities WHERE id=?", (contract["shot_id"],)).fetchone()
    if shot is None or shot["kind"] != "shot":
        conflicts.append({"code": "shot_missing_or_wrong_kind", "id": contract["shot_id"]})
        return conflicts
    for version in contract["versions"]:
        historical_parent = version["basis_json"].get("shot", {}).get("parent_scene_id")
        for pin in version["source_pins"]:
            reason = _pin_conflict(conn, pin, contract["shot_id"], historical_parent)
            if reason:
                conflicts.append({"code": reason, "id": pin["edge_id"], "version_id": version["id"]})
        for reference in version["reference_pins"]:
            entity = conn.execute("SELECT kind FROM entities WHERE id=?", (reference["reference_id"],)).fetchone()
            if entity is None or entity["kind"] != "asset":
                conflicts.append({"code": "reference_missing_or_wrong_kind", "id": reference["reference_id"], "version_id": version["id"]})
    return conflicts


def _classify_contract(conn, service, package: dict) -> dict:
    existing = _db_contract(conn, package["id"])
    if existing is not None:
        if existing == package:
            return {"contract_id": package["id"], "status": "already_present", "conflicts": [], "stale_versions": []}
        return {"contract_id": package["id"], "status": "conflict", "conflicts": [{"code": "contract_id_collision", "id": package["id"]}], "stale_versions": []}
    owner = conn.execute("SELECT id FROM observation_contracts WHERE shot_id=?", (package["shot_id"],)).fetchone()
    if owner:
        return {"contract_id": package["id"], "status": "conflict", "conflicts": [{"code": "shot_already_has_contract", "id": package["shot_id"]}], "stale_versions": []}
    conflicts = _contract_conflicts(conn, service, package)
    if conflicts:
        return {"contract_id": package["id"], "status": "conflict", "conflicts": conflicts, "stale_versions": []}
    checker = ObservationContracts(service)
    stale_versions = []
    for version in package["versions"]:
        body = version["contract_json"]
        try:
            current_basis = checker._basis(conn, package["shot_id"], body)
            stale = content_hash(current_basis) != version["basis_sha256"]
        except (ObservationContractError, StoryboardError, ValueError, TypeError):
            stale = True
        if stale:
            stale_versions.append(version["id"])
    return {"contract_id": package["id"], "status": "importable", "conflicts": [], "stale_versions": stale_versions}


def _receipt(source_hash: str, target_hash: str, artifact_hash: str, choices: dict[str, str]) -> str:
    return _sha({"source_manifest_sha256": source_hash, "target_state_sha256": target_hash,
                 "artifact_state_sha256": artifact_hash, "choices": choices})


def _reconciliation_report(results: list[dict], choices: dict[str, str], artifact_available: dict[str, bool]) -> dict:
    """Derive loss and unresolved details from verified state and explicit choices."""
    return {
        "losses": [
            {"contract_id": contract_id, "reason": "explicit_conflict_skip"}
            for contract_id in sorted(choices) if choices[contract_id] == "skip-conflict"
        ],
        "unresolved": [
            {"contract_id": row["contract_id"], "code": conflict["code"], "id": conflict.get("id")}
            for row in results for conflict in row["conflicts"]
        ] + [
            {"contract_id": contract_id, "reason": "abort_selected"}
            for contract_id in sorted(choices) if choices[contract_id] == "abort"
        ] + [
            {"source_version_id": version_id, "code": "source_artifact_bytes_unavailable"}
            for version_id, available in sorted(artifact_available.items()) if not available
        ],
    }


def preview_observation_import(service, source: bytes | str, choices: dict[str, str] | None = None) -> dict:
    """Read-only import preview. No database, event, file, or backup writes occur."""
    plan = _read_plan(source)
    if plan["project_id"] != service.project.id:
        raise ObservationTransferError("observation_plan_project_mismatch", "The plan belongs to a different project identity.",
                                       {"source_project_id": plan["project_id"], "target_project_id": service.project.id})
    core = {"schema": plan["schema"], "project_id": plan["project_id"], "contracts": plan["contracts"]}
    source_hash = plan["manifest"]["payload_sha256"]
    supplied = choices or {}
    if not isinstance(supplied, dict) or any(not isinstance(key, str) for key in supplied):
        raise ObservationTransferError("observation_plan_invalid", "Reconciliation choices must map contract IDs to choices.")
    with service.repo.readonly_transaction() as conn:
        state_hash = _target_digest(conn)
        artifact_hash, artifact_available = _artifact_state(conn, service, core)
        results = [_classify_contract(conn, service, contract) for contract in core["contracts"]]
    conflicts = {row["contract_id"] for row in results if row["status"] == "conflict"}
    if set(supplied) - conflicts:
        raise ObservationTransferError("observation_plan_choice_invalid", "A reconciliation choice was supplied for a contract without a conflict.",
                                       {"contract_ids": sorted(set(supplied) - conflicts)})
    invalid = {key: value for key, value in supplied.items() if value not in ("skip-conflict", "abort")}
    if invalid:
        raise ObservationTransferError("observation_plan_choice_invalid", "Choose skip-conflict or abort for each conflict.", {"choices": invalid})
    missing = sorted(conflicts - set(supplied))
    aborted = sorted(key for key, value in supplied.items() if value == "abort")
    decisions = {key: supplied[key] for key in sorted(supplied)}
    ready = not missing
    receipt = _receipt(source_hash, state_hash, artifact_hash, decisions) if ready else None
    report = _reconciliation_report(results, decisions, artifact_available)
    output = []
    for row in results:
        item = dict(row)
        if item["status"] == "conflict":
            decision = supplied.get(item["contract_id"])
            item["choice"] = decision or "required"
            item["action"] = "skip" if decision == "skip-conflict" else "abort" if decision == "abort" else "unresolved"
        else:
            item["action"] = "keep" if item["status"] == "already_present" else "import"
        output.append(item)
    return {
        "schema": PLAN_SCHEMA,
        "source_manifest_sha256": source_hash,
        "target_state_sha256": state_hash,
        "artifact_state_sha256": artifact_hash,
        "choices": decisions,
        "ready": ready,
        "aborted": bool(aborted),
        "required_choices": missing,
        "receipt": receipt,
        "contracts": output,
        **report,
    }


def _insert_contract(conn, service, package: dict) -> None:
    conn.execute(
        "INSERT INTO observation_contracts(id,shot_id,current_version_id,revision,created_at,updated_at) VALUES(?,?,NULL,1,?,?)",
        (package["id"], package["shot_id"], package["created_at"], package["updated_at"]),
    )
    for version in package["versions"]:
        conn.execute("""INSERT INTO observation_contract_versions
          (id,contract_id,parent_version_id,number,schema_version,contract_json,content_sha256,basis_json,basis_sha256,
           operation,sealed,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,0,?)""",
                     (version["id"], version["contract_id"], version["parent_version_id"], version["number"],
                      version["schema_version"], dumps(version["contract_json"]), version["content_sha256"],
                      dumps(version["basis_json"]), version["basis_sha256"], version["operation"], version["created_at"]))
        for pin in version["source_pins"]:
            conn.execute("""INSERT INTO observation_source_pins
              (version_id,edge_id,source_scope,document_id,source_version_id,node_id,logical_id,source_sha256,
               scope_sha256,document_sha256,artifact_sha256,source_snapshot,edge_source_snapshot,edge_target_snapshot,created_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                         (version["id"], pin["edge_id"], pin["source_scope"], pin["document_id"],
                          pin["source_version_id"], pin["node_id"], pin["logical_id"], pin["source_sha256"],
                          pin["scope_sha256"], pin["document_sha256"], pin["artifact_sha256"],
                          dumps(pin["source_snapshot"]), dumps(pin["edge_source_snapshot"]),
                          dumps(pin["edge_target_snapshot"]), pin["created_at"]))
        for reference in version["reference_pins"]:
            conn.execute("INSERT INTO observation_reference_pins(version_id,reference_id,snapshot_json,created_at) VALUES(?,?,?,?)",
                         (version["id"], reference["reference_id"], dumps(reference["snapshot"]), reference["created_at"]))
        conn.execute("UPDATE observation_contract_versions SET sealed=1 WHERE id=?", (version["id"],))
    for version in package["versions"]:
        current = conn.execute("SELECT current_version_id,revision FROM observation_contracts WHERE id=?", (package["id"],)).fetchone()
        next_revision = current["revision"] if current["current_version_id"] is None else current["revision"] + 1
        conn.execute("UPDATE observation_contracts SET current_version_id=?,revision=?,updated_at=? WHERE id=?",
                     (version["id"], next_revision, package["updated_at"], package["id"]))
    service.repo.event(conn, "observation_contract.imported", package["id"],
                       {"shot_id": package["shot_id"], "version_count": len(package["versions"]),
                        "current_version_id": package["current_version_id"], "revision": package["revision"]})


def apply_observation_import(service, source: bytes | str, preview: dict) -> dict:
    """Atomically apply a previously reviewed preview or return a stable CAS conflict."""
    plan = _read_plan(source)
    if plan["project_id"] != service.project.id:
        raise ObservationTransferError("observation_plan_project_mismatch", "The plan belongs to a different project identity.")
    if not isinstance(preview, dict) or not preview.get("ready") or not isinstance(preview.get("receipt"), str):
        raise ObservationTransferError("observation_transfer_preview_required", "Run a complete dry-run and resolve every conflict before applying.")
    source_hash = plan["manifest"]["payload_sha256"]
    choices = preview.get("choices")
    if not isinstance(choices, dict):
        raise ObservationTransferError("observation_transfer_receipt_invalid", "The dry-run receipt has invalid choices.")
    expected_receipt = _receipt(source_hash, preview.get("target_state_sha256", ""),
                                preview.get("artifact_state_sha256", ""), choices)
    if (preview.get("source_manifest_sha256") != source_hash or preview.get("receipt") != expected_receipt):
        raise ObservationTransferError("observation_transfer_receipt_invalid", "The dry-run receipt does not match this plan and its reconciliation choices.")

    packages = {item["id"]: item for item in plan["contracts"]}
    inserted, existing, skipped = [], [], []
    try:
        with service.repo.observation_restore_transaction() as conn:
            current_digest = _target_digest(conn)
            if current_digest != preview["target_state_sha256"]:
                raise ObservationTransferError(
                    "observation_transfer_target_changed",
                    "The project changed after this dry-run. Run a new dry-run before applying the plan.",
                    {"expected_target_state_sha256": preview["target_state_sha256"], "actual_target_state_sha256": current_digest},
                    409,
                )
            artifact_digest, artifact_available = _artifact_state(conn, service, plan)
            if artifact_digest != preview.get("artifact_state_sha256"):
                raise ObservationTransferError(
                    "observation_transfer_target_changed",
                    "A pinned source artifact changed after this dry-run. Run a new dry-run before applying the plan.",
                    {"expected_artifact_state_sha256": preview.get("artifact_state_sha256"),
                     "actual_artifact_state_sha256": artifact_digest},
                    409,
                )
            classified = [_classify_contract(conn, service, package) for package in plan["contracts"]]
            conflict_ids = {row["contract_id"] for row in classified if row["status"] == "conflict"}
            if set(choices) != conflict_ids or any(choice not in ("skip-conflict", "abort") for choice in choices.values()):
                raise ObservationTransferError("observation_transfer_target_changed", "Conflict status changed after dry-run. Run a new dry-run before applying.", status=409)
            report = _reconciliation_report(classified, choices, artifact_available)
            if any(choice == "abort" for choice in choices.values()):
                return {"applied": False, "aborted": True, "imported": [], "already_present": [], "skipped": [],
                        **report}
            for result in classified:
                package = packages[result["contract_id"]]
                if result["status"] == "already_present":
                    existing.append(result["contract_id"])
                elif result["status"] == "conflict":
                    if choices[result["contract_id"]] != "skip-conflict":
                        raise ObservationTransferError("observation_transfer_target_changed", "A conflict lacks an explicit skip choice.", status=409)
                    skipped.append(result["contract_id"])
                else:
                    # Run the same explicit data-safety check inside the write transaction.
                    losses = _portable_losses(package)
                    if losses:
                        raise ObservationTransferError("observation_plan_not_portable", "A plan contains non-portable data.", {"adapter_losses": losses[:100]})
                    _insert_contract(conn, service, package)
                    inserted.append(result["contract_id"])
            validations = []
            checker = ObservationContracts(service)
            for contract_id in inserted:
                package = packages[contract_id]
                for version in package["versions"]:
                    header, record = checker._version(conn, contract_id, version["id"])
                    validation = checker._validate(conn, header, record)
                    unavailable = [pin["edge_id"] for pin in version["source_pins"]
                                   if not artifact_available.get(pin["source_version_id"], False)]
                    if unavailable:
                        validation["findings"].extend({"code": "source_artifact_bytes_unavailable", "edge_id": edge_id}
                                                       for edge_id in unavailable)
                        for pin_state in validation["source_pins"]:
                            if pin_state["edge_id"] in unavailable:
                                pin_state["stale"] = True
                                pin_state["reasons"] = sorted(set(pin_state["reasons"] + ["artifact_bytes_unavailable"]))
                        if validation["status"] == "consistent":
                            validation["status"] = "unresolved"
                    validations.append({"contract_id": contract_id, "version_id": version["id"], **validation})
    except ObservationTransferError:
        raise
    except StoryboardError as exc:
        raise ObservationTransferError("observation_transfer_apply_failed", "The plan could not be restored exactly; the transaction was rolled back.",
                                       {"reason": str(exc)}, 409) from exc
    except Exception as exc:
        raise ObservationTransferError("observation_transfer_apply_failed", "The plan could not be restored exactly; the transaction was rolled back.",
                                       {"error_type": type(exc).__name__}, 409) from exc
    return {
        "applied": bool(inserted), "aborted": False, "imported": inserted, "already_present": existing,
        "skipped": skipped,
        **report,
        "validations": validations,
    }
