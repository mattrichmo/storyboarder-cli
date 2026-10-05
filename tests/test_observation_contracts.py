"""Persistent observation-contract history stays exact, advisory, and agent-facing."""
import copy
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import uuid

import pytest
from fastapi.testclient import TestClient

from storyboarder.api.server import create_app
from storyboarder.application.documents import Documents
from storyboarder.application.observation_contracts import (
    CONTRACT_SCHEMA, ObservationContractError, ObservationContracts, _parse_json,
)
from storyboarder.application.projects import Project
from storyboarder.application.provenance import Provenance
from storyboarder.application.service import Service
from storyboarder.application.source_workflows import SourceWorkflows
from storyboarder.domain.errors import Conflict, StoryboardError
from test_documents import uid


@pytest.fixture
def screenplay():
    author, character, scene = uid(1), uid(2), uid(3)
    return {
        "id": uid(100), "version": "1.0.0", "title": {"en": "Winter Station"},
        "lang": "en", "charset": "utf-8", "dir": "ltr",
        "authors": [{"id": author, "given": "Test", "family": "Writer"}],
        "characters": [{"id": character, "name": "MARA"}],
        "document": {"cover": {"title": {"en": "Winter Station"}, "authors": [author]},
                     "scenes": [{"id": scene, "authors": [author],
                                 "heading": {"context": "INT", "setting": "STATION", "time": "DAWN"},
                                 "meta": {"production": {"weather": "snow"}},
                                 "body": [
                                     {"id": uid(4), "authors": [author], "type": "action",
                                      "text": {"en": "Mara turns the key."}},
                                     {"id": uid(5), "authors": [author], "type": "character", "character": character},
                                     {"id": uid(6), "authors": [author], "type": "dialogue", "character": character,
                                      "dual": False, "text": {"en": "We stay."}},
                                 ]}]},
    }


def _source_rows(service, screenplay):
    imported = Documents(service).import_bytes(json.dumps(screenplay).encode(), "winter.screenjson", "screenjson")
    rows = Documents(service).tree(imported["version"]["id"])["items"]
    return imported, {row["logical_id"]: row for row in rows}


def _contract(edges=(), *, intents=True, requirements=(), references=(), continuity=(), notes=""):
    source_pins = [{"edge_id": edge["id"], "source_scope": scope} for edge, scope in edges]
    script_intents = []
    if intents:
        for index, (edge, scope) in enumerate(edges, 1):
            script_intents.append({"id": uid(1000 + index), "source_edge_id": edge["id"], "source_scope": scope,
                                   "purpose": "insert" if scope == "direct-element" else "context",
                                   "communication": "The authored source relationship stays visible to the planner.",
                                   "basis": "direct"})
    return {"schema": CONTRACT_SCHEMA, "source_pins": source_pins, "script_intents": script_intents,
            "requirements": list(requirements), "references": list(references),
            "continuity": list(continuity), "notes": notes}


def _new_edge(service, node_id, target_id):
    return Provenance(service).link("node", node_id, "entity", target_id, "visualizes")


def _created(story, screenplay, edges, *, requirements=(), references=(), continuity=()):
    service = story["service"]
    body = _contract(edges, requirements=requirements, references=references, continuity=continuity)
    return ObservationContracts(service).create(story["shot"]["id"], story["shot"]["revision"], body), body


def test_schema_four_to_five_keeps_backup_and_existing_records_without_synthesis(tmp_path, monkeypatch, screenplay, image_factory):
    import storyboarder.storage.repository as repository

    monkeypatch.setattr(repository, "SCHEMA_VERSION", 4)
    project = Project.create(tmp_path / "legacy", "Schema four")
    service = Service(project)
    sequence = service.create_entity("sequence", "Sequence")
    scene = service.create_entity("scene", "Scene", sequence["id"])
    shot = service.create_entity("shot", "Shot", scene["id"], fields={"action": "Existing action"})
    media = service.import_file(image_factory("old-frame.png"))["media"]
    frame = service.attach_frame(shot["id"], media["id"])
    imported, nodes = _source_rows(service, screenplay)
    edge = _new_edge(service, nodes[uid(4)]["id"], shot["id"])
    db_path = project.repo.path
    tables = ("entities", "media", "frames", "documents", "document_versions", "document_nodes", "provenance_edges")
    before = {}
    with sqlite3.connect(db_path) as conn:
        for table in tables:
            before[table] = conn.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 4

    monkeypatch.setattr(repository, "SCHEMA_VERSION", 5)
    upgraded = Project(project.root)
    backup = upgraded.repo.path.with_name(upgraded.repo.path.name + ".before-v5.bak")
    assert backup.is_file()
    with sqlite3.connect(backup) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
        old_tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "observation_contracts" not in old_tables
    with sqlite3.connect(upgraded.repo.path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
        for table in tables:
            assert conn.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall() == before[table]
        assert conn.execute("SELECT count(*) FROM observation_contracts").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM observation_contract_versions").fetchone()[0] == 0
    upgraded_service = Service(upgraded)
    snapshot = upgraded_service.state()
    assert not any(key.startswith("observation_") for key in snapshot)
    assert frame["shot_id"] == shot["id"] and edge["source_id"] == nodes[uid(4)]["id"]
    assert imported["version"]["id"] in {row[0] for row in before["document_versions"]}


def test_contract_pins_are_many_to_many_and_keep_direct_and_context_scopes(story, screenplay):
    service = story["service"]
    imported, source = _source_rows(service, screenplay)
    direct_action = _new_edge(service, source[uid(4)]["id"], story["shot"]["id"])
    direct_dialogue = _new_edge(service, source[uid(6)]["id"], story["shot"]["id"])
    scene_context = _new_edge(service, source[uid(3)]["id"], story["scene"]["id"])
    required = {"id": uid(2001), "priority": "must", "basis": "direct",
                "source_edge_ids": [direct_action["id"], direct_dialogue["id"]],
                "statement": "The key changes hands before Eli turns away."}
    preferred = {"id": uid(2002), "priority": "prefer", "basis": "interpreted",
                 "source_edge_ids": [scene_context["id"]], "statement": "Keep Eli's reaction in the coverage."}
    body = _contract([(direct_action, "direct-element"), (direct_dialogue, "direct-element"),
                      (scene_context, "scene-context")], requirements=[required, preferred])
    records = ObservationContracts(service)
    created = records.create(story["shot"]["id"], story["shot"]["revision"], body)
    assert created["contract"]["schema"] == CONTRACT_SCHEMA
    assert created["version"]["schema_version"] == 1
    assert created["validation"]["status"] == "consistent"
    assert {pin["edge_id"] for pin in created["source_pins"]} == {direct_action["id"], direct_dialogue["id"], scene_context["id"]}
    assert all(pin["document_id"] == imported["document"]["id"] for pin in created["source_pins"])
    assert all(pin["source_version_id"] == imported["version"]["id"] for pin in created["source_pins"])
    mappings = created["validation"]["requirements"][0]["source_mappings"]
    assert {mapping["coverage_kind"] for mapping in mappings} == {"direct-element-link"}
    assert created["validation"]["requirements"][1]["source_mappings"][0]["coverage_kind"] == "scene-context"

    second_shot = service.create_entity("shot", "A second angle", story["scene"]["id"], fields={"action": "Second angle"})
    second_edge = _new_edge(service, source[uid(4)]["id"], second_shot["id"])
    second = records.create(second_shot["id"], second_shot["revision"], _contract([(second_edge, "direct-element")]))
    assert second["source_pins"][0]["node_id"] == next(pin for pin in created["source_pins"]
                                                           if pin["edge_id"] == direct_action["id"])["node_id"]
    assert second["source_pins"][0]["edge_id"] != created["source_pins"][0]["edge_id"]
    assert records.list()["total"] == 2


def test_direct_screenplay_scene_to_shot_is_not_reported_as_beat_coverage(story, screenplay):
    service = story["service"]
    _, source = _source_rows(service, screenplay)
    edge = _new_edge(service, source[uid(3)]["id"], story["shot"]["id"])
    result, _ = _created(story, screenplay, [(edge, "direct-element")])
    mapping = result["validation"]["requirements"]
    assert mapping == []
    pin = result["validation"]["source_pins"][0]
    assert pin["source_node_type"] == "scene"
    assert pin["coverage_kind"] == "direct-scene-link"
    assert "beat" not in pin["coverage_kind"]


def test_advisory_must_prefer_unknown_and_no_inferred_coverage(story, screenplay):
    service = story["service"]
    _, source = _source_rows(service, screenplay)
    edge = _new_edge(service, source[uid(4)]["id"], story["shot"]["id"])
    requirements = [
        {"id": uid(3001), "priority": "must", "basis": "direct", "source_edge_ids": [edge["id"]],
         "statement": "The key is visible in Mara's hand."},
        {"id": uid(3002), "priority": "prefer", "basis": "interpreted", "source_edge_ids": [],
         "statement": "Keep a reaction in this coverage."},
        {"id": uid(3003), "priority": "unknown", "basis": "direct", "source_edge_ids": [edge["id"]],
         "topic": "Whether the reflection must be visible."},
    ]
    result, _ = _created(story, screenplay, [(edge, "direct-element")], requirements=requirements)
    assert result["validation"]["status"] == "unresolved"
    by_id = {row["id"]: row for row in result["validation"]["requirements"]}
    assert by_id[uid(3001)]["state"] == "declared-link"
    assert by_id[uid(3002)]["state"] == "warning"
    assert by_id[uid(3003)]["state"] == "open-question"
    assert any(item["code"] == "unknown_requirement" for item in result["validation"]["findings"])
    assert any(item["code"] == "prefer_without_source_mapping" for item in result["validation"]["findings"])
    assert "not interpreted" in result["validation"]["method"]

    # The legacy visualizes edge does not count as declared contract coverage.
    unpinned_shot = service.create_entity("shot", "Unpinned angle", story["scene"]["id"])
    no_pin = ObservationContracts(service).create(unpinned_shot["id"], unpinned_shot["revision"], _contract([], intents=False))
    assert no_pin["validation"]["status"] == "unresolved"
    assert {item["code"] for item in no_pin["validation"]["findings"]} >= {"no_declared_source_links", "no_declared_purpose"}


@pytest.mark.parametrize("mutation,code", [
    ("unsupported", "contract_invalid"), ("duplicate_stable_id", "contract_invalid"), ("extra_key", "contract_invalid"),
])
def test_strict_contract_schema_rejects_unsupported_and_duplicate_data(story, screenplay, mutation, code):
    service = story["service"]
    _, source = _source_rows(service, screenplay)
    edge = _new_edge(service, source[uid(4)]["id"], story["shot"]["id"])
    body = _contract([(edge, "direct-element")])
    body["requirements"] = [
        {"id": uid(4001), "priority": "prefer", "basis": "direct", "source_edge_ids": [edge["id"]], "statement": "One"},
        {"id": uid(4001), "priority": "must", "basis": "interpreted", "source_edge_ids": [edge["id"]], "statement": "Two"},
    ]
    if mutation == "unsupported":
        body["schema"] = "storyboarder.observation-contract/v99"
    elif mutation == "duplicate_stable_id":
        pass
    else:
        body["internal_metadata"] = {"latest": True}
    with pytest.raises(ObservationContractError) as error:
        ObservationContracts(service).create(story["shot"]["id"], story["shot"]["revision"], body)
    assert error.value.code == code
    assert error.value.details["issues"]
    if mutation == "duplicate_stable_id":
        assert "unique across" in error.value.details["issues"][0]["message"]
    with pytest.raises(ObservationContractError) as malformed:
        _parse_json('{"schema":')
    assert malformed.value.code == "contract_invalid"


@pytest.mark.parametrize("failure", ["cross_project", "wrong_target", "retired", "archived_document", "archived_scene", "inferred", "source_hash"])
def test_new_pins_recheck_project_identity_edge_lifecycle_and_hashes(story, screenplay, tmp_path, failure):
    service = story["service"]
    imported, source = _source_rows(service, screenplay)
    target_id = story["shot"]["id"]
    edge = _new_edge(service, source[uid(4)]["id"], target_id)
    scope = "direct-element"
    if failure == "cross_project":
        other = Service(Project.create(tmp_path / "other", "Other project"))
        _, other_source = _source_rows(other, screenplay)
        other_sequence = other.create_entity("sequence", "Q")
        other_scene = other.create_entity("scene", "Other scene", other_sequence["id"])
        other_shot = other.create_entity("shot", "Other shot", other_scene["id"])
        foreign = _new_edge(other, other_source[uid(4)]["id"], other_shot["id"])
        edge_id = foreign["id"]
    elif failure == "wrong_target":
        other_shot = service.create_entity("shot", "Other target", story["scene"]["id"])
        edge_id = edge["id"]
        target_id = other_shot["id"]
    elif failure == "retired":
        Provenance(service).retire(edge["id"], edge["revision"])
        edge_id = edge["id"]
    elif failure == "archived_document":
        SourceWorkflows(service).archive(imported["document"]["id"], imported["document"]["revision"])
        edge_id = edge["id"]
    elif failure == "archived_scene":
        context = _new_edge(service, source[uid(3)]["id"], story["scene"]["id"])
        with service.repo.transaction() as conn:
            conn.execute("UPDATE entities SET archived=1 WHERE id=?", (story["scene"]["id"],))
        edge_id, scope = context["id"], "scene-context"
    elif failure == "inferred":
        with service.repo.transaction() as conn:
            conn.execute("DROP TRIGGER immutable_document_node_update")
            conn.execute("UPDATE document_nodes SET identity='inferred' WHERE id=?", (source[uid(4)]["id"],))
        edge_id = edge["id"]
    else:
        version = Documents(service).version(imported["version"]["id"])
        source_path = service.root / version["source"]["path"]
        source_path.write_bytes(b"tampered screenplay bytes")
        edge_id = edge["id"]
    body = _contract([({"id": edge_id}, scope)])
    with pytest.raises(ObservationContractError) as error:
        ObservationContracts(service).create(target_id, service.get("entities", target_id)["revision"], body)
    expected = {
        "cross_project": "contract_source_pin_not_found", "wrong_target": "contract_source_pin_target_mismatch",
        "retired": "contract_source_pin_retired", "archived_document": "contract_source_archived",
        "archived_scene": "contract_source_archived", "inferred": "contract_source_identity_inferred",
        "source_hash": "contract_source_hash_mismatch",
    }[failure]
    assert error.value.code == expected


def test_header_revision_immutable_versions_and_pins_seal(story, screenplay):
    service = story["service"]
    _, source = _source_rows(service, screenplay)
    edge = _new_edge(service, source[uid(4)]["id"], story["shot"]["id"])
    records = ObservationContracts(service)
    body = _contract([(edge, "direct-element")])
    created = records.create(story["shot"]["id"], story["shot"]["revision"], body)
    with pytest.raises(Conflict) as stale:
        records.revise(created["id"], 99, body)
    assert stale.value.details["expected"] == 99
    revised = records.revise(created["id"], 1, body | {"notes": "A second authored version."})
    assert revised["revision"] == 2 and revised["version"]["parent_version_id"] == created["version"]["id"]
    with pytest.raises(StoryboardError, match="immutable"):
        with service.repo.transaction() as conn:
            conn.execute("UPDATE observation_contract_versions SET content_sha256='bad' WHERE id=?", (created["version"]["id"],))
    with pytest.raises(StoryboardError, match="created unsealed"):
        with service.repo.transaction() as conn:
            conn.execute("""INSERT INTO observation_contract_versions
              (id,contract_id,parent_version_id,number,schema_version,contract_json,content_sha256,basis_json,basis_sha256,operation,sealed,created_at)
              VALUES(?,?,NULL,1,1,'{}','bad','{}','bad','create',1,'now')""",
                         (uid(7777), created["id"]))
    with pytest.raises(StoryboardError, match="sealed"):
        with service.repo.transaction() as conn:
            conn.execute("""INSERT INTO observation_source_pins
              SELECT version_id,edge_id,source_scope,document_id,source_version_id,node_id,logical_id,source_sha256,
                     scope_sha256,document_sha256,artifact_sha256,source_snapshot,edge_source_snapshot,edge_target_snapshot,created_at
              FROM observation_source_pins WHERE version_id=?""", (created["version"]["id"],))
    with pytest.raises(StoryboardError, match="next child"):
        with service.repo.transaction() as conn:
            conn.execute("UPDATE observation_contracts SET current_version_id=?,revision=revision+1 WHERE id=?",
                         (created["version"]["id"], created["id"]))
    another_shot = service.create_entity("shot", "Another contract owner", story["scene"]["id"])
    with pytest.raises(StoryboardError, match="belongs to another contract"):
        with service.repo.transaction() as conn:
            conn.execute("""INSERT INTO observation_contracts
              (id,shot_id,current_version_id,revision,created_at,updated_at) VALUES(?,?,?,1,'now','now')""",
                         (uid(7778), another_shot["id"], revised["version"]["id"]))


def test_title_number_order_are_excluded_but_relevant_shot_context_and_asset_changes_need_rebase(story, screenplay):
    service = story["service"]
    _, source = _source_rows(service, screenplay)
    edge = _new_edge(service, source[uid(4)]["id"], story["shot"]["id"])
    body = _contract([(edge, "direct-element")], references=[story["character"]["id"]])
    records = ObservationContracts(service)
    created = records.create(story["shot"]["id"], story["shot"]["revision"], body)
    second = service.create_entity("shot", "Earlier order", story["scene"]["id"], fields={"action": "A separate angle"})
    shot = service.update_entity(story["shot"]["id"], created["revision"],
                                 {"title": "Renamed shot", "fields": {"number": "99"}})
    shot = service.move(shot["id"], shot["revision"], 1)
    reference = service.update_entity(story["character"]["id"], story["character"]["revision"], {"title": "Renamed reference"})
    assert records.validate(created["id"])["basis_current"] is True
    assert records.validate(created["id"])["status"] == "consistent"

    shot = service.update_entity(shot["id"], shot["revision"], {"fields": {"action": "Mara gives the key away."}})
    stale = records.validate(created["id"])
    assert stale["basis_current"] is False and stale["status"] == "unresolved"
    with pytest.raises(ObservationContractError) as needs_rebase:
        records.revise(created["id"], created["revision"], body | {"notes": "Try to acknowledge the changed action."})
    assert needs_rebase.value.code == "contract_rebase_required"
    rebased = records.rebase(created["id"], created["revision"], body)
    assert rebased["revision"] == 2 and rebased["validation"]["basis_current"] is True
    assert len(rebased["history"]) == 2 and rebased["history"][0]["id"] == created["version"]["id"]

    shot = service.update_entity(shot["id"], shot["revision"], {"fields": {"duration": 11}})
    duration_result = records.validate(created["id"])
    assert duration_result["basis_current"] is False and duration_result["status"] == "unresolved"

    ref = service.update_entity(reference["id"], reference["revision"], {"description": "New character reference content."})
    changed_asset = records.validate(created["id"])
    assert changed_asset["status"] == "unresolved" and changed_asset["basis_current"] is False
    assert any(item["code"] == "authored_basis_changed" for item in changed_asset["findings"])
    archived = service.lifecycle(ref["id"], ref["revision"], "archive")
    archived_result = records.validate(created["id"])
    assert archived_result["status"] == "unresolved"
    assert any(item["code"] == "basis_asset_archived" for item in archived_result["findings"])

    # A change to the authored scene context invalidates the same version.
    scene = service.update_entity(story["scene"]["id"], story["scene"]["revision"], {"fields": {"summary": "A changed scene context."}})
    scene_result = records.validate(created["id"])
    assert scene_result["status"] == "unresolved" and scene_result["basis_current"] is False
    assert second["kind"] == "shot"


def test_scene_context_subtree_and_explicit_rebase_never_retarget(story, screenplay):
    service = story["service"]
    imported, source = _source_rows(service, screenplay)
    context_edge = _new_edge(service, source[uid(3)]["id"], story["scene"]["id"])
    body = _contract([(context_edge, "scene-context")])
    records = ObservationContracts(service)
    created = records.create(story["shot"]["id"], story["shot"]["revision"], body)
    later = Documents(service).revise_node(source[uid(4)]["id"], {"text": {"en": "The action changes."}}, imported["document"]["revision"])
    result = records.validate(created["id"])
    assert result["status"] == "unresolved"
    assert any("source_context_changed" in item.get("reasons", []) for item in result["findings"])
    assert created["source_pins"][0]["source_version_id"] == imported["version"]["id"]
    new_source = next(row for row in Documents(service).tree(later["version"]["id"])["items"] if row["logical_id"] == uid(3))
    replacement = _new_edge(service, new_source["id"], story["scene"]["id"])
    new_body = _contract([(replacement, "scene-context")])
    rebased = records.rebase(created["id"], created["revision"], new_body)
    assert rebased["source_pins"][0]["edge_id"] == replacement["id"]
    assert rebased["source_pins"][0]["source_version_id"] == later["version"]["id"]
    assert records.show(created["id"], created["version"]["id"])["source_pins"][0]["source_version_id"] == imported["version"]["id"]
    diff = records.diff(created["id"], created["version"]["id"], rebased["version"]["id"])
    assert diff["content_changed"] and any(change["path"].startswith("/source_pins/") for change in diff["changes"])


def test_create_uses_expected_shot_revision(story):
    service = story["service"]
    shot = story["shot"]
    service.update_entity(shot["id"], shot["revision"], {"title": "Changed before contract creation"})
    with pytest.raises(Conflict) as stale:
        ObservationContracts(service).create(shot["id"], shot["revision"], _contract([], intents=False))
    assert stale.value.details["expected"] == shot["revision"]
    assert stale.value.details["current_revision"] == shot["revision"] + 1
    assert ObservationContracts(service).list()["total"] == 0


def test_reference_asset_and_assignment_media_content_are_in_basis(story, screenplay):
    service = story["service"]
    _, source = _source_rows(service, screenplay)
    edge = _new_edge(service, source[uid(4)]["id"], story["shot"]["id"])
    body = _contract([(edge, "direct-element")], references=[story["character"]["id"]])
    records = ObservationContracts(service)
    created = records.create(story["shot"]["id"], story["shot"]["revision"], body)
    assignment = story["assignment"]
    service.update_assignment(assignment["id"], assignment["revision"], "reference", story["exact"]["id"])
    result = records.validate(created["id"])
    assert result["status"] == "unresolved" and result["basis_current"] is False


def test_effective_location_asset_content_and_archive_state_are_in_basis(story, screenplay):
    service = story["service"]
    _, source = _source_rows(service, screenplay)
    edge = _new_edge(service, source[uid(4)]["id"], story["shot"]["id"])
    records = ObservationContracts(service)
    created = records.create(story["shot"]["id"], story["shot"]["revision"],
                             _contract([(edge, "direct-element")]))
    location = service.update_entity(story["location"]["id"], story["location"]["revision"],
                                     {"description": "A different platform layout."})
    result = records.validate(created["id"])
    assert result["basis_current"] is False and result["status"] == "unresolved"
    archived = service.lifecycle(location["id"], location["revision"], "archive")
    result = records.validate(created["id"])
    assert result["status"] == "unresolved"
    assert any(finding["code"] == "basis_asset_archived" for finding in result["findings"])


def test_contract_workflow_has_no_frame_or_camera_side_effects(story, screenplay):
    service = story["service"]
    shot = service.update_entity(story["shot"]["id"], story["shot"]["revision"], {"fields": {"camera": "Locked-off."}})
    frame = service.attach_frame(shot["id"], story["exact"]["id"])
    before = service.get("entities", shot["id"])["fields"]["camera"]
    frame_before = service.get("frames", frame["id"])
    _, source = _source_rows(service, screenplay)
    edge = _new_edge(service, source[uid(4)]["id"], shot["id"])
    records = ObservationContracts(service)
    body = _contract([(edge, "direct-element")])
    created = records.create(shot["id"], shot["revision"], body)
    revised = records.revise(created["id"], created["revision"], body | {"notes": "Editorial note only."})
    records.validate(revised["id"])
    assert service.get("entities", shot["id"])["fields"]["camera"] == before
    assert service.get("frames", frame["id"]) == frame_before


def test_cli_and_api_share_contract_errors_and_safe_catalog(story, tmp_path):
    service = story["service"]
    body = _contract([])
    body["schema"] = "storyboarder.observation-contract/v2"
    payload = {"shot_id": story["shot"]["id"], "expected_shot_revision": story["shot"]["revision"], "contract": body}
    payload_file = tmp_path / "invalid-contract.json"
    payload_file.write_text(json.dumps(payload), encoding="utf-8")
    cli = subprocess.run([sys.executable, "-m", "storyboarder", "--project", str(service.root),
                          "observation", "create", "--payload", "@" + str(payload_file), "--json"],
                         capture_output=True, text=True, timeout=20)
    assert cli.returncode == 1
    cli_error = json.loads(cli.stderr)["error"]

    app = create_app(project=service.project, port=7430)
    with TestClient(app, base_url="http://127.0.0.1:7430") as client:
        client.headers["X-Storyboarder-Token"] = client.get("/api/v1/session").json()["token"]
        prefix = f"/api/v1/projects/{service.project.id}"
        metadata = client.get("/api/v1/meta").json()
        browser_names = {command["name"] for command in metadata["commands"]}
        api_names = {command["name"] for command in metadata["api_commands"]}
        assert "observation.create" not in browser_names and "observation.create" in api_names
        assert "document.import" not in api_names and "document.import" not in browser_names
        api = client.post(prefix + "/commands/observation.create", json=payload)
        assert api.status_code == 422
        assert api.json()["error"] == cli_error
        assert client.post(prefix + "/commands/document.import", json={"path": "/tmp/source"}).status_code == 422


def test_doctor_checks_contract_history_read_only(story, screenplay):
    service = story["service"]
    _, source = _source_rows(service, screenplay)
    edge = _new_edge(service, source[uid(4)]["id"], story["shot"]["id"])
    created = ObservationContracts(service).create(story["shot"]["id"], story["shot"]["revision"],
                                                  _contract([(edge, "direct-element")]))
    before = hashlib.sha256(service.repo.path.read_bytes()).hexdigest()
    report = service.doctor()
    after = hashlib.sha256(service.repo.path.read_bytes()).hexdigest()
    assert not any(issue["code"].startswith("observation_contract") for issue in report["issues"])
    assert before == after
    with service.repo.transaction() as conn:
        conn.execute("DROP TRIGGER observation_version_seal_once")
        conn.execute("UPDATE observation_contract_versions SET content_sha256='broken' WHERE id=?", (created["version"]["id"],))
    damaged = service.doctor()
    assert any(issue["code"] == "observation_contract_integrity" for issue in damaged["issues"])


def test_doctor_handles_missing_contract_table_and_schema_four_without_mutation(story, tmp_path, monkeypatch):
    import storyboarder.storage.repository as repository
    from storyboarder.application.observation_contracts import ObservationContracts

    service = story["service"]
    with service.repo.transaction() as conn:
        conn.execute("DROP TABLE observation_contracts")
    database = service.repo.path
    before = database.read_bytes()
    missing = service.doctor()
    after = database.read_bytes()
    assert missing["schema_version"] == 5 and not missing["healthy"]
    assert any(issue["code"] == "observation_contract_integrity_check" for issue in missing["issues"])
    assert before == after

    monkeypatch.setattr(repository, "SCHEMA_VERSION", 4)
    old_project = Project.create(tmp_path / "schema-four-doctor", "Schema four")
    old_service = Service(old_project)
    monkeypatch.setattr(repository, "SCHEMA_VERSION", 5)

    def forbidden_contract_walk(self):
        raise AssertionError("schema 4 must not inspect schema 5 contract tables")

    monkeypatch.setattr(ObservationContracts, "integrity_issues", forbidden_contract_walk)
    before = old_service.repo.path.read_bytes()
    old_report = old_service.doctor()
    after = old_service.repo.path.read_bytes()
    old_codes = {issue["code"] for issue in old_report["issues"]}
    assert old_report["schema_version"] == 4 and old_report["supported_schema_version"] == 5
    assert "migration_state" in old_codes and "observation_contract_integrity_check" not in old_codes
    assert before == after


def test_internal_restore_gate_preserves_exact_inactive_history_and_cannot_leak(tmp_path, screenplay):
    source = Service(Project.create(tmp_path / "restore-source", "Restore source"))
    sequence = source.create_entity("sequence", "Sequence")
    scene = source.create_entity("scene", "Scene", sequence["id"])
    shot = source.create_entity("shot", "Shot", scene["id"], fields={"action": "Open the brass box."})
    asset = source.create_entity("asset", "Brass box", fields={"type": "prop"})
    imported, nodes = _source_rows(source, screenplay)
    edge = _new_edge(source, nodes[uid(4)]["id"], shot["id"])
    contract_body = _contract([(edge, "direct-element")], references=[asset["id"]])
    destination_path = tmp_path / "restore-destination"
    shutil.copytree(source.root, destination_path)
    destination = Service(Project(destination_path))
    source_records = ObservationContracts(source)
    first = source_records.create(shot["id"], shot["revision"], contract_body)
    second = source_records.revise(first["id"], 1, contract_body | {"notes": "Preserve the original reference."})

    Provenance(source).retire(edge["id"], edge["revision"])
    Provenance(destination).retire(edge["id"], edge["revision"])
    source.lifecycle(asset["id"], asset["revision"], "archive")
    destination.lifecycle(asset["id"], asset["revision"], "archive")

    with source.repo.readonly_transaction() as conn:
        header = dict(conn.execute("SELECT * FROM observation_contracts WHERE id=?", (first["id"],)).fetchone())
        versions = [dict(row) for row in conn.execute(
            "SELECT * FROM observation_contract_versions WHERE contract_id=? ORDER BY number", (first["id"],))]
        pins_by_version = {row["id"]: [dict(pin) for pin in conn.execute(
            "SELECT * FROM observation_source_pins WHERE version_id=? ORDER BY edge_id", (row["id"],))] for row in versions}
        refs_by_version = {row["id"]: [dict(ref) for ref in conn.execute(
            "SELECT * FROM observation_reference_pins WHERE version_id=? ORDER BY reference_id", (row["id"],))] for row in versions}

    with destination.repo.observation_restore_transaction() as conn:
        assert conn.execute("SELECT observation_restore_authorized()").fetchone()[0] == 1
        conn.execute("""INSERT INTO observation_contracts
          (id,shot_id,current_version_id,revision,created_at,updated_at) VALUES(?,?,NULL,1,?,?)""",
                     (header["id"], header["shot_id"], header["created_at"], header["updated_at"]))
        for version in versions:
            conn.execute("""INSERT INTO observation_contract_versions
              (id,contract_id,parent_version_id,number,schema_version,contract_json,content_sha256,basis_json,basis_sha256,operation,sealed,created_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,0,?)""",
                         (version["id"], version["contract_id"], version["parent_version_id"], version["number"],
                          version["schema_version"], version["contract_json"], version["content_sha256"],
                          version["basis_json"], version["basis_sha256"], version["operation"], version["created_at"]))
            for pin in pins_by_version[version["id"]]:
                if version["number"] == 1:
                    corrupted = dict(pin)
                    corrupted["source_sha256"] = "0" * 64
                    with pytest.raises(sqlite3.IntegrityError, match="active exact screenplay edge"):
                        conn.execute("""INSERT INTO observation_source_pins VALUES
                          (:version_id,:edge_id,:source_scope,:document_id,:source_version_id,:node_id,:logical_id,
                           :source_sha256,:scope_sha256,:document_sha256,:artifact_sha256,:source_snapshot,
                           :edge_source_snapshot,:edge_target_snapshot,:created_at)""", corrupted)
                conn.execute("""INSERT INTO observation_source_pins VALUES
                  (:version_id,:edge_id,:source_scope,:document_id,:source_version_id,:node_id,:logical_id,
                   :source_sha256,:scope_sha256,:document_sha256,:artifact_sha256,:source_snapshot,
                   :edge_source_snapshot,:edge_target_snapshot,:created_at)""", pin)
            for ref in refs_by_version[version["id"]]:
                conn.execute("INSERT INTO observation_reference_pins VALUES(?,?,?,?)",
                             (ref["version_id"], ref["reference_id"], ref["snapshot_json"], ref["created_at"]))
            conn.execute("UPDATE observation_contract_versions SET sealed=1 WHERE id=?", (version["id"],))
            conn.execute("UPDATE observation_contracts SET current_version_id=?,revision=? WHERE id=?",
                         (version["id"], version["number"], header["id"]))

    with destination.repo.readonly_transaction() as conn:
        restored_header = dict(conn.execute("SELECT * FROM observation_contracts WHERE id=?", (header["id"],)).fetchone())
        restored_versions = [dict(row) for row in conn.execute(
            "SELECT * FROM observation_contract_versions WHERE contract_id=? ORDER BY number", (header["id"],))]
        assert restored_header == header
        assert restored_versions == versions
        for version in versions:
            assert [dict(row) for row in conn.execute(
                "SELECT * FROM observation_source_pins WHERE version_id=? ORDER BY edge_id", (version["id"],))] == pins_by_version[version["id"]]
            assert [dict(row) for row in conn.execute(
                "SELECT * FROM observation_reference_pins WHERE version_id=? ORDER BY reference_id", (version["id"],))] == refs_by_version[version["id"]]

    restored = ObservationContracts(destination).show(header["id"])
    assert restored["current_version_id"] == second["version"]["id"]
    assert restored["validation"]["status"] == "unresolved"
    assert any(finding["code"] == "source_pin_stale" for finding in restored["validation"]["findings"])
    assert any(finding["code"] == "reference_archived" for finding in restored["validation"]["findings"])
    assert not any(issue["code"].startswith("observation_contract") for issue in destination.doctor()["issues"])

    with pytest.raises(RuntimeError, match="rollback gate check"):
        with destination.repo.observation_restore_transaction() as conn:
            assert conn.execute("SELECT observation_restore_authorized()").fetchone()[0] == 1
            raise RuntimeError("rollback gate check")
    with pytest.raises(StoryboardError, match="active exact screenplay edge"):
        with destination.repo.transaction() as conn:
            assert conn.execute("SELECT observation_restore_authorized()").fetchone()[0] == 0
            next_version_id = uid(7770)
            original = versions[-1]
            conn.execute("""INSERT INTO observation_contract_versions
              (id,contract_id,parent_version_id,number,schema_version,contract_json,content_sha256,basis_json,basis_sha256,operation,sealed,created_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,0,?)""",
                         (next_version_id, header["id"], original["id"], original["number"] + 1,
                          original["schema_version"], original["contract_json"], original["content_sha256"],
                          original["basis_json"], original["basis_sha256"], "rebase", "now"))
            inactive_pin = dict(pins_by_version[original["id"]][0])
            inactive_pin["version_id"] = next_version_id
            inactive_pin["created_at"] = "now"
            conn.execute("""INSERT INTO observation_source_pins VALUES
              (:version_id,:edge_id,:source_scope,:document_id,:source_version_id,:node_id,:logical_id,
               :source_sha256,:scope_sha256,:document_sha256,:artifact_sha256,:source_snapshot,
               :edge_source_snapshot,:edge_target_snapshot,:created_at)""", inactive_pin)

    restored_header = ObservationContracts(destination).show(header["id"])
    with pytest.raises(ObservationContractError) as rejected_rebase:
        ObservationContracts(destination).rebase(header["id"], restored_header["revision"], contract_body)
    assert rejected_rebase.value.code == "contract_source_pin_retired"
    new_shot = destination.create_entity("shot", "New shot", scene["id"])
    archived_reference_body = _contract([], intents=False, references=[asset["id"]])
    with pytest.raises(ObservationContractError) as rejected_reference:
        ObservationContracts(destination).create(new_shot["id"], new_shot["revision"], archived_reference_body)
    assert rejected_reference.value.code == "contract_reference_archived"
