"""Exact and portable project-level transfer for observation contract history."""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
import uuid

import pytest

from storyboarder.application.documents import Documents
from storyboarder.application.observation_contracts import CONTRACT_SCHEMA, ObservationContracts
from storyboarder.domain.documents import content_hash
from storyboarder.application.observation_transfer import (
    ObservationTransferError,
    apply_observation_import,
    export_observation_plan,
    preview_observation_import,
)
from storyboarder.application.projects import Project
from storyboarder.application.provenance import Provenance
from storyboarder.application.service import Service
from storyboarder.application.source_workflows import SourceWorkflows


def _uid(number: int) -> str:
    return str(uuid.UUID(int=number))


def _screenplay(*, metadata=None):
    author, scene_one, scene_two = _uid(1), _uid(10), _uid(20)
    first_action, second_action = _uid(11), _uid(21)
    return {
        "id": _uid(100), "version": "1.0.0", "title": {"en": "Winter Station"},
        "lang": "en", "charset": "utf-8", "dir": "ltr",
        "authors": [{"id": author, "given": "Ari", "family": "Writer"}],
        "characters": [{"id": _uid(2), "name": "MARA"}],
        "document": {
            "cover": {"title": {"en": "Winter Station"}, "authors": [author]},
            "scenes": [
                {"id": scene_one, "authors": [author],
                 "heading": {"context": "INT", "setting": "STATION", "time": "DAWN"},
                 "meta": metadata or {"production": {"weather": "snow"}},
                 "body": [{"id": first_action, "authors": [author], "type": "action", "text": {"en": "Mara turns the key."}}]},
                {"id": scene_two, "authors": [author],
                 "heading": {"context": "EXT", "setting": "PLATFORM", "time": "MORNING"},
                 "meta": {"production": {"weather": "clear"}},
                 "body": [{"id": second_action, "authors": [author], "type": "action", "text": {"en": "The train arrives."}}]},
            ],
        },
    }


def _base(service, screenplay=None):
    screenplay = screenplay or _screenplay()
    imported = Documents(service).import_bytes(json.dumps(screenplay, ensure_ascii=False).encode(), "winter.screenjson", "screenjson")
    with service.repo.readonly_transaction() as conn:
        nodes = {row["logical_id"]: dict(row) for row in conn.execute(
            "SELECT id,logical_id,node_type FROM document_nodes WHERE version_id=?", (imported["version"]["id"],))}
    sequence = service.create_entity("sequence", "Sequence")
    station = service.create_entity("asset", "Station", fields={"type": "location"})
    platform = service.create_entity("asset", "Platform", fields={"type": "location"})
    scene_a = service.create_entity("scene", "Station", sequence["id"], fields={"location_id": station["id"], "time": "Dawn"})
    scene_b = service.create_entity("scene", "Platform", sequence["id"], fields={"location_id": platform["id"], "time": "Morning"})
    shot_a = service.create_entity("shot", "Key turns", scene_a["id"], fields={"action": "Mara turns the key."})
    shot_b = service.create_entity("shot", "Second coverage", scene_a["id"], fields={"action": "The hand leaves frame."})
    shot_c = service.create_entity("shot", "Train arrival", scene_b["id"], fields={"action": "The train arrives."})
    reference = service.create_entity("asset", "Brass key", fields={"type": "prop", "notes": "Continuity reference."})
    edges = {
        "shot_a": Provenance(service).link("node", nodes[_uid(11)]["id"], "entity", shot_a["id"], "visualizes"),
        "shot_b": Provenance(service).link("node", nodes[_uid(11)]["id"], "entity", shot_b["id"], "visualizes"),
        "shot_c": Provenance(service).link("node", nodes[_uid(20)]["id"], "entity", scene_b["id"], "visualizes"),
        "scene_a": Provenance(service).link("node", nodes[_uid(10)]["id"], "entity", scene_a["id"], "visualizes"),
    }
    return {"service": service, "document": imported["document"], "shots": [shot_a, shot_b, shot_c],
            "scenes": [scene_a, scene_b], "locations": [station, platform],
            "reference": reference, "edges": edges, "nodes": nodes}


def _contract(edge, scope, number, *, references=(), continuity=(), notes="First authored pass"):
    return {
        "schema": CONTRACT_SCHEMA,
        "source_pins": [{"edge_id": edge["id"], "source_scope": scope}],
        "script_intents": [{"id": _uid(5000 + number), "source_edge_id": edge["id"], "source_scope": scope,
                            "purpose": "coverage", "communication": "Keep the authored action readable in the cut.",
                            "basis": "direct"}],
        "requirements": [], "references": list(references), "continuity": list(continuity), "notes": notes,
    }


def _populate_history(story):
    records = ObservationContracts(story["service"])
    outputs = []
    for index, (shot, edge, scope) in enumerate(zip(story["shots"], story["edges"].values(),
                                                     ("direct-element", "direct-element", "scene-context")), 1):
        continuity = []
        if index == 1:
            continuity = [{"id": _uid(6001), "related_shot_ids": [story["shots"][1]["id"]],
                           "statement": "Keep the brass key in Mara's right hand."}]
        body = _contract(edge, scope, index, references=[story["reference"]["id"]] if index == 1 else (),
                         continuity=continuity)
        created = records.create(shot["id"], shot["revision"], body)
        revised_body = copy.deepcopy(body)
        revised_body["notes"] = "Second authored pass" if index == 1 else body["notes"]
        if index == 1:
            revised = records.revise(created["id"], created["revision"], revised_body)
            outputs.append(revised)
        else:
            outputs.append(created)
    return outputs


def _clone_project(service, path):
    shutil.copytree(service.project.root, path)
    return Service(Project(path))


def _file_state(root):
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _event_count(service):
    with service.repo.readonly_transaction() as conn:
        return conn.execute("SELECT count(*) FROM events").fetchone()[0]


def _rehash_plan(plan):
    core = {"schema": plan["schema"], "project_id": plan["project_id"], "contracts": plan["contracts"]}
    versions = []
    for contract in plan["contracts"]:
        for version in contract["versions"]:
            version["basis_sha256"] = content_hash(version["basis_json"])
            encoded = json.dumps(version, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
            versions.append({"contract_id": contract["id"], "version_id": version["id"],
                             "record_sha256": hashlib.sha256(encoded).hexdigest(),
                             "content_sha256": version["content_sha256"],
                             "basis_sha256": version["basis_sha256"]})
    raw = json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    plan["manifest"] = {"payload_sha256": hashlib.sha256(raw).hexdigest(), "versions": versions}
    return json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def test_multi_scene_multi_shot_roundtrip_preserves_all_history_exactly(service, tmp_path):
    story = _base(service)
    target = _clone_project(service, tmp_path / "portable-copy")
    _populate_history(story)
    renamed = target.get("entities", story["shots"][0]["id"])
    target.update_entity(renamed["id"], renamed["revision"], {"title": "Renamed after export"})
    reordered = target.get("entities", story["shots"][1]["id"])
    target.move(reordered["id"], reordered["revision"], 0)
    exported = export_observation_plan(service)
    assert exported == export_observation_plan(service)
    assert str(service.project.root).encode() not in exported
    assert b"/workspace/" not in exported
    assert b"credential" not in exported.lower()
    assert b"runtime" not in exported.lower()

    preview = preview_observation_import(target, exported)
    assert preview["ready"] and [row["action"] for row in preview["contracts"]] == ["import"] * 3
    result = apply_observation_import(target, exported, preview)
    assert len(result["imported"]) == 3
    assert all(item["status"] in ("consistent", "unresolved") for item in result["validations"])
    assert export_observation_plan(target) == exported


def test_dry_run_has_no_writes_and_receipt_detects_target_changes(service, tmp_path):
    story = _base(service)
    target = _clone_project(service, tmp_path / "dry-run-copy")
    _populate_history(story)
    exported = export_observation_plan(service)
    files_before = _file_state(target.project.root)
    events_before = _event_count(target)
    preview = preview_observation_import(target, exported)
    assert preview["ready"]
    assert _file_state(target.project.root) == files_before
    assert _event_count(target) == events_before
    assert not list(target.project.root.rglob("*.bak"))

    target.create_entity("asset", "Concurrent edit", fields={"type": "reference"})
    with pytest.raises(ObservationTransferError) as changed:
        apply_observation_import(target, exported, preview)
    assert changed.value.code == "observation_transfer_target_changed"
    with target.repo.readonly_transaction() as conn:
        assert conn.execute("SELECT count(*) FROM observation_contracts").fetchone()[0] == 0
    fresh_preview = preview_observation_import(target, exported)
    assert fresh_preview["ready"]
    assert len(apply_observation_import(target, exported, fresh_preview)["imported"]) == 3


def test_reimport_is_idempotent_and_does_not_reset_revision_or_add_events(service, tmp_path):
    story = _base(service)
    target = _clone_project(service, tmp_path / "idempotent-copy")
    _populate_history(story)
    exported = export_observation_plan(service)
    first = apply_observation_import(target, exported, preview_observation_import(target, exported))
    assert first["applied"]
    before_events = _event_count(target)
    before_bytes = _file_state(target.project.root)
    again = preview_observation_import(target, exported)
    assert all(row["status"] == "already_present" for row in again["contracts"])
    second = apply_observation_import(target, exported, again)
    assert not second["applied"] and len(second["already_present"]) == 3
    assert _event_count(target) == before_events
    assert _file_state(target.project.root) == before_bytes
    assert export_observation_plan(target) == exported


def test_conflict_requires_explicit_skip_or_abort(service, tmp_path):
    story = _base(service)
    target = _clone_project(service, tmp_path / "conflict-copy")
    _populate_history(story)
    exported = export_observation_plan(service)
    package = json.loads(exported)
    source_contract = next(row for row in package["contracts"] if row["shot_id"] == story["shots"][0]["id"])
    contract_id = source_contract["id"]
    # Occupy one stable contract ID with a different but structurally valid body.
    target_story = {**story, "service": target}
    shot = target_story["shots"][0]
    edge = target_story["edges"]["shot_a"]
    target_body = _contract(edge, "direct-element", 20, notes="Different existing history")
    ObservationContracts(target).create(shot["id"], shot["revision"], target_body)
    with target.repo.transaction() as conn:
        current = conn.execute("SELECT id FROM observation_contracts WHERE shot_id=?", (shot["id"],)).fetchone()[0]
        if current != contract_id:
            row = conn.execute("SELECT * FROM observation_contracts WHERE id=?", (current,)).fetchone()
            # The collision is attached to the same shot, which is enough to
            # exercise the explicit per-contract skip/abort reconciliation.
            assert row is not None
    unresolved = preview_observation_import(target, exported)
    assert not unresolved["ready"] and contract_id in unresolved["required_choices"]
    before_abort_events = _event_count(target)
    aborted_preview = preview_observation_import(target, exported, {contract_id: "abort"})
    aborted = apply_observation_import(target, exported, aborted_preview)
    assert aborted["aborted"] and not aborted["imported"]
    assert _event_count(target) == before_abort_events
    skipped = preview_observation_import(target, exported, {contract_id: "skip-conflict"})
    assert skipped["losses"] == [{"contract_id": contract_id, "reason": "explicit_conflict_skip"}]
    assert skipped["unresolved"] == [{
        "contract_id": contract_id,
        "code": "shot_already_has_contract",
        "id": shot["id"],
    }]
    skipped["losses"] = []
    skipped["unresolved"] = []
    skipped["aborted"] = True
    result = apply_observation_import(target, exported, skipped)
    assert not result["aborted"]
    assert contract_id in result["skipped"]
    assert len(result["imported"]) == 2
    assert result["losses"] == [{"contract_id": contract_id, "reason": "explicit_conflict_skip"}]
    assert result["unresolved"] == [{
        "contract_id": contract_id,
        "code": "shot_already_has_contract",
        "id": shot["id"],
    }]


def test_abort_choice_overrides_tampered_summary_and_writes_nothing(service, tmp_path):
    story = _base(service)
    target = _clone_project(service, tmp_path / "abort-with-skip-copy")
    _populate_history(story)
    exported = export_observation_plan(service)
    packages = json.loads(exported)["contracts"]
    by_shot = {row["shot_id"]: row for row in packages}
    skipped_id = by_shot[story["shots"][0]["id"]]["id"]
    aborted_id = by_shot[story["shots"][1]["id"]]["id"]
    target_story = {**story, "service": target}
    for index, edge_key in ((0, "shot_a"), (1, "shot_b")):
        shot = target_story["shots"][index]
        existing = target.get("entities", shot["id"])
        ObservationContracts(target).create(
            shot["id"], existing["revision"],
            _contract(target_story["edges"][edge_key], "direct-element", 30 + index,
                      notes="Different local history"),
        )

    decisions = {skipped_id: "skip-conflict", aborted_id: "abort"}
    preview = preview_observation_import(target, exported, decisions)
    assert preview["ready"] and preview["aborted"]
    preview["losses"] = []
    preview["unresolved"] = []
    preview["aborted"] = False
    before_events = _event_count(target)
    before_files = _file_state(target.project.root)

    result = apply_observation_import(target, exported, preview)

    assert result["aborted"] and not result["applied"]
    assert result["imported"] == [] and result["already_present"] == [] and result["skipped"] == []
    assert result["losses"] == [{"contract_id": skipped_id, "reason": "explicit_conflict_skip"}]
    conflict_rows = sorted(
        ((row["id"], row["shot_id"]) for row in packages if row["id"] in decisions),
        key=lambda item: item[0],
    )
    assert result["unresolved"] == [
        {"contract_id": contract_id, "code": "shot_already_has_contract", "id": shot_id}
        for contract_id, shot_id in conflict_rows
    ] + [{"contract_id": aborted_id, "reason": "abort_selected"}]
    assert _event_count(target) == before_events
    assert _file_state(target.project.root) == before_files


def test_archived_and_retired_exact_pins_restore_original_rows(service, tmp_path):
    story = _base(service)
    target = _clone_project(service, tmp_path / "archived-copy")
    created = ObservationContracts(service).create(
        story["shots"][0]["id"], story["shots"][0]["revision"],
        _contract(story["edges"]["shot_a"], "direct-element", 1),
    )
    edge, document, shot = story["edges"]["shot_a"], story["document"], story["shots"][0]
    for candidate in (service, target):
        Provenance(candidate).retire(edge["id"], 1)
        current_doc = Documents(candidate).show(document["id"])
        SourceWorkflows(candidate).archive(document["id"], current_doc["revision"])
        current_shot = candidate.get("entities", shot["id"])
        candidate.lifecycle(shot["id"], current_shot["revision"], "archive")
    exported = export_observation_plan(service)
    preview = preview_observation_import(target, exported)
    assert preview["ready"]
    result = apply_observation_import(target, exported, preview)
    assert result["imported"] == [created["id"]]
    assert any(row["status"] == "unresolved" for row in result["validations"])
    assert export_observation_plan(target) == exported


def test_changed_target_basis_preserves_history_and_reports_unresolved(service, tmp_path):
    story = _base(service)
    target = _clone_project(service, tmp_path / "stale-copy")
    _populate_history(story)
    exported = export_observation_plan(service)
    shot = target.get("entities", story["shots"][0]["id"])
    target.update_entity(shot["id"], shot["revision"], {"fields": {"action": "The current action changed after authoring."}})
    preview = preview_observation_import(target, exported)
    source_plan = json.loads(exported)
    changed_contract = next(row for row in source_plan["contracts"] if row["shot_id"] == shot["id"])
    preview_item = next(row for row in preview["contracts"] if row["contract_id"] == changed_contract["id"])
    assert preview_item["stale_versions"]
    result = apply_observation_import(target, exported, preview)
    assert any(row["status"] == "unresolved" for row in result["validations"])
    assert export_observation_plan(target) == exported


def test_artifact_change_after_dry_run_requires_new_preview_and_import_stays_unresolved(service, tmp_path):
    story = _base(service)
    target = _clone_project(service, tmp_path / "changed-artifact-copy")
    _populate_history(story)
    exported = export_observation_plan(service)
    preview = preview_observation_import(target, exported)
    source_version_id = json.loads(exported)["contracts"][0]["versions"][0]["source_pins"][0]["source_version_id"]
    with target.repo.readonly_transaction() as conn:
        artifact_path = conn.execute("""SELECT a.path FROM source_artifacts a
          JOIN document_versions v ON v.source_artifact_id=a.id WHERE v.id=?""", (source_version_id,)).fetchone()[0]
    target_bytes = target.project.root / artifact_path
    content = bytearray(target_bytes.read_bytes())
    content[0] ^= 1
    target_bytes.write_bytes(content)
    with pytest.raises(ObservationTransferError) as changed:
        apply_observation_import(target, exported, preview)
    assert changed.value.code == "observation_transfer_target_changed"

    fresh = preview_observation_import(target, exported)
    assert any(item["code"] == "source_artifact_bytes_unavailable" for item in fresh["unresolved"])
    result = apply_observation_import(target, exported, fresh)
    assert any(row["status"] == "unresolved" for row in result["validations"])
    assert any(item["code"] == "source_artifact_bytes_unavailable" for item in result["unresolved"])


def test_reparented_shot_restores_exact_context_history_as_stale(service, tmp_path):
    story = _base(service)
    target = _clone_project(service, tmp_path / "reparent-copy")
    created = ObservationContracts(service).create(
        story["shots"][2]["id"], story["shots"][2]["revision"],
        _contract(story["edges"]["shot_c"], "scene-context", 3),
    )
    exported = export_observation_plan(service)
    source_plan = json.loads(exported)
    source_contract = next(row for row in source_plan["contracts"] if row["id"] == created["id"])
    source_version = source_contract["versions"][0]
    source_pin = source_version["source_pins"][0]
    shot = target.get("entities", story["shots"][2]["id"])
    target.move(shot["id"], shot["revision"], 0, parent_id=story["scenes"][0]["id"])
    preview = preview_observation_import(target, exported)
    result = apply_observation_import(target, exported, preview)
    assert result["imported"] == [created["id"]]
    validation = next(row for row in result["validations"] if row["version_id"] == source_version["id"])
    assert validation["status"] == "unresolved"
    stale_pin = next(row for row in validation["source_pins"] if row["edge_id"] == source_pin["edge_id"])
    assert stale_pin["stale"]
    assert "edge_target_mismatch" in stale_pin["reasons"]

    restored_plan = json.loads(export_observation_plan(target))
    restored_contract = next(row for row in restored_plan["contracts"] if row["id"] == created["id"])
    restored_version = restored_contract["versions"][0]
    assert restored_version["id"] == source_version["id"]
    assert restored_version["content_sha256"] == source_version["content_sha256"]
    assert restored_version["basis_sha256"] == source_version["basis_sha256"]
    assert restored_version["source_pins"] == source_version["source_pins"]
    assert export_observation_plan(target) == exported


@pytest.mark.parametrize("mutation,expected_code", [
    ("historical_parent", "source_edge_identity_mismatch"),
    ("edge_snapshot", "source_edge_snapshot_mismatch"),
])
def test_forged_historical_parent_or_pin_snapshot_is_a_conflict(service, tmp_path, mutation, expected_code):
    story = _base(service)
    target = _clone_project(service, tmp_path / f"forgery-{mutation}")
    shot_index = 2 if mutation == "historical_parent" else 0
    edge_key = "shot_c" if mutation == "historical_parent" else "shot_a"
    scope = "scene-context" if mutation == "historical_parent" else "direct-element"
    created = ObservationContracts(service).create(
        story["shots"][shot_index]["id"], story["shots"][shot_index]["revision"],
        _contract(story["edges"][edge_key], scope, 1),
    )
    plan = json.loads(export_observation_plan(service))
    package = next(row for row in plan["contracts"] if row["id"] == created["id"])
    version = package["versions"][0]
    if mutation == "historical_parent":
        version["basis_json"]["shot"]["parent_scene_id"] = story["scenes"][0]["id"]
    else:
        version["source_pins"][0]["edge_target_snapshot"]["id"] = story["scenes"][1]["id"]
    tampered = _rehash_plan(plan)
    preview = preview_observation_import(target, tampered)
    item = next(row for row in preview["contracts"] if row["contract_id"] == created["id"])
    assert item["status"] == "conflict"
    assert expected_code in {row["code"] for row in item["conflicts"]}
    assert not preview["ready"]


@pytest.mark.parametrize("raw", [
    b'{"schema":"storyboarder.observation-plan/v1","schema":"duplicate"}',
    b'{"schema":NaN}',
    b'{"schema":1e9999}',
])
def test_import_rejects_duplicate_keys_and_nonfinite_json(service, raw):
    with pytest.raises(ObservationTransferError) as error:
        preview_observation_import(service, raw)
    assert error.value.code == "observation_plan_invalid"


def test_manifest_tampering_and_unknown_runtime_fields_are_rejected(service, tmp_path):
    story = _base(service)
    _populate_history(story)
    original = export_observation_plan(service)
    data = json.loads(original)
    data["contracts"][0]["versions"][0]["basis_json"]["shot"]["action"] = "tampered"
    with pytest.raises(ObservationTransferError) as tampered:
        preview_observation_import(service, json.dumps(data))
    assert tampered.value.code == "observation_plan_integrity_error"

    metadata = _screenplay(metadata={"production": {
        "launch_options": {"argv": ["renderer"]},
        "api_key": "sk-example-not-a-real-key-12345",
    }})
    unsafe_root = tmp_path / "unsafe-source"
    unsafe = Service(Project.create(unsafe_root, "Unsafe source"))
    unsafe_story = _base(unsafe, screenplay=metadata)
    # A shot basis with a credential-shaped authored value is retained exactly;
    # export reports the adapter loss instead of sanitizing or hashing it anew.
    unsafe_shot = unsafe_story["shots"][0]
    unsafe.update_entity(unsafe_shot["id"], unsafe_shot["revision"], {"fields": {"action": "/workspace/private/shot.json"}})
    unsafe_shot = unsafe.get("entities", unsafe_shot["id"])
    unsafe_shot = unsafe.get("entities", unsafe_shot["id"])
    ObservationContracts(unsafe).create(
        unsafe_shot["id"], unsafe_shot["revision"], _contract(unsafe_story["edges"]["scene_a"], "scene-context", 11),
    )
    with pytest.raises(ObservationTransferError) as nonportable:
        export_observation_plan(unsafe)
    assert nonportable.value.code == "observation_plan_not_portable"
    reasons = {loss["reason"] for loss in nonportable.value.details["adapter_losses"]}
    assert "absolute_path" in reasons and "runtime_launch_field" in reasons and "credential_field" in reasons


def test_nested_source_pointer_in_screenplay_payload_is_not_exempted(service, tmp_path):
    unsafe = Service(Project.create(tmp_path / "nested-pointer-source", "Nested pointer source"))
    story = _base(unsafe, screenplay=_screenplay(metadata={"source_pointer": "/secret/project/credential.json"}))
    ObservationContracts(unsafe).create(
        story["shots"][0]["id"], story["shots"][0]["revision"],
        _contract(story["edges"]["scene_a"], "scene-context", 12),
    )

    with pytest.raises(ObservationTransferError) as nonportable:
        export_observation_plan(unsafe)

    assert nonportable.value.code == "observation_plan_not_portable"
    losses = nonportable.value.details["adapter_losses"]
    assert any(
        loss["path"].endswith("/source_snapshot/payload/meta/source_pointer")
        and loss["reason"] == "absolute_path"
        for loss in losses
    )


def test_typed_edge_source_pointer_must_match_supported_screenplay_syntax(service):
    story = _base(service)
    created = ObservationContracts(service).create(
        story["shots"][0]["id"], story["shots"][0]["revision"],
        _contract(story["edges"]["shot_a"], "direct-element", 13),
    )
    plan = json.loads(export_observation_plan(service))
    contract = next(row for row in plan["contracts"] if row["id"] == created["id"])
    contract["versions"][0]["source_pins"][0]["edge_source_snapshot"]["source_pointer"] = "/secret/project/credential.json"

    with pytest.raises(ObservationTransferError) as invalid:
        preview_observation_import(service, _rehash_plan(plan))

    assert invalid.value.code == "observation_plan_invalid"


def test_atomic_rollback_when_event_write_fails(service, tmp_path, monkeypatch):
    story = _base(service)
    target = _clone_project(service, tmp_path / "rollback-copy")
    _populate_history(story)
    exported = export_observation_plan(service)
    before_events = _event_count(target)
    original_event = target.repo.event

    def fail_event(*args, **kwargs):
        raise RuntimeError("simulated late transaction failure")

    monkeypatch.setattr(target.repo, "event", fail_event)
    preview = preview_observation_import(target, exported)
    with pytest.raises(ObservationTransferError) as failed:
        apply_observation_import(target, exported, preview)
    assert failed.value.code == "observation_transfer_apply_failed"
    monkeypatch.setattr(target.repo, "event", original_event)
    with target.repo.readonly_transaction() as conn:
        assert conn.execute("SELECT count(*) FROM observation_contracts").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM observation_contract_versions").fetchone()[0] == 0
    assert _event_count(target) == before_events
