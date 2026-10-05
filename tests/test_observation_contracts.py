"""Persistent observation-contract history stays exact, advisory, and agent-facing."""
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from storyboarder.api.server import create_app
from storyboarder.application.documents import Documents
from storyboarder.application.observation_contracts import (
    CONTRACT_SCHEMA, ObservationContractError, ObservationContracts, _parse_json, _validate_body,
)
from storyboarder.application.projects import Project
from storyboarder.application.provenance import Provenance
from storyboarder.application.service import Service
from storyboarder.application.source_workflows import SourceWorkflows
from storyboarder.domain.documents import content_hash
from storyboarder.domain.errors import Conflict, InUse, StoryboardError
from storyboarder.domain.models import dumps
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


def test_schema_four_to_six_keeps_backup_and_existing_records_without_synthesis(tmp_path, monkeypatch, screenplay, image_factory):
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

    monkeypatch.setattr(repository, "SCHEMA_VERSION", 6)
    upgraded = Project(project.root)
    backup = upgraded.repo.path.with_name(upgraded.repo.path.name + ".before-v6.bak")
    assert backup.is_file()
    with sqlite3.connect(backup) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
        old_tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "observation_contracts" not in old_tables
    with sqlite3.connect(upgraded.repo.path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 6
        for table in tables:
            assert conn.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall() == before[table]
        assert conn.execute("SELECT count(*) FROM observation_contracts").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM observation_contract_versions").fetchone()[0] == 0
    upgraded_service = Service(upgraded)
    snapshot = upgraded_service.state()
    assert not any(key.startswith("observation_") for key in snapshot)
    assert frame["shot_id"] == shot["id"] and edge["source_id"] == nodes[uid(4)]["id"]
    assert imported["version"]["id"] in {row[0] for row in before["document_versions"]}


def test_schema_five_to_six_preserves_contract_history_and_backup(tmp_path, monkeypatch, screenplay):
    import storyboarder.storage.repository as repository

    monkeypatch.setattr(repository, "SCHEMA_VERSION", 5)
    project = Project.create(tmp_path / "schema-five", "Schema five")
    service = Service(project)
    sequence = service.create_entity("sequence", "Sequence")
    scene = service.create_entity("scene", "Scene", sequence["id"])
    shot = service.create_entity("shot", "Shot", scene["id"])
    _, source = _source_rows(service, screenplay)
    edge = _new_edge(service, source[uid(4)]["id"], shot["id"])
    records = ObservationContracts(service)
    created = records.create(shot["id"], shot["revision"], _contract([(edge, "direct-element")]))
    revised = records.revise(created["id"], 1, _contract([(edge, "direct-element")], notes="Exact old history."))
    db_path = service.repo.path
    names = ("observation_contracts", "observation_contract_versions", "observation_source_pins",
             "observation_reference_pins")
    before = {}
    with sqlite3.connect(db_path) as conn:
        for table in names:
            before[table] = conn.execute(f"SELECT * FROM {table} ORDER BY 1,2").fetchall()
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 5

    monkeypatch.setattr(repository, "SCHEMA_VERSION", 6)
    upgraded = Project(project.root)
    backup = upgraded.repo.path.with_name(upgraded.repo.path.name + ".before-v6.bak")
    assert backup.is_file()
    with sqlite3.connect(backup) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
        assert conn.execute("SELECT id FROM observation_contract_versions ORDER BY id").fetchall()
    with sqlite3.connect(upgraded.repo.path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 6
        for table in names:
            assert conn.execute(f"SELECT * FROM {table} ORDER BY 1,2").fetchall() == before[table]
    restored = ObservationContracts(Service(upgraded)).show(created["id"])
    assert restored["history"] == records.show(created["id"])["history"]
    assert restored["current_version_id"] == revised["version"]["id"]
    assert not any(issue["code"].startswith("observation_contract") for issue in Service(upgraded).doctor()["issues"])


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
    review = records.review_rebase(created["id"], body)
    assert any(change["path"] == "/shot/action" for change in review["changes"])
    rebased = records.rebase(created["id"], created["revision"], body, review["expected_basis_sha256"])
    assert rebased["revision"] == 2 and rebased["validation"]["basis_current"] is True
    assert len(rebased["history"]) == 2 and rebased["history"][0]["id"] == created["version"]["id"]

    shot = service.update_entity(shot["id"], shot["revision"], {"fields": {"duration": 11}})
    duration_result = records.validate(created["id"])
    assert duration_result["basis_current"] is False and duration_result["status"] == "unresolved"

    ref = service.update_entity(reference["id"], reference["revision"], {"description": "New character reference content."})
    changed_asset = records.validate(created["id"])
    assert changed_asset["status"] == "unresolved" and changed_asset["basis_current"] is False
    assert any(item["code"] == "authored_basis_changed" for item in changed_asset["findings"])
    service.lifecycle(ref["id"], ref["revision"], "archive")
    archived_result = records.validate(created["id"])
    assert archived_result["status"] == "unresolved"
    assert any(item["code"] == "basis_asset_archived" for item in archived_result["findings"])

    # A change to the authored scene context invalidates the same version.
    service.update_entity(story["scene"]["id"], story["scene"]["revision"], {"fields": {"summary": "A changed scene context."}})
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
    review = records.review_rebase(created["id"], new_body)
    rebased = records.rebase(created["id"], created["revision"], new_body, review["expected_basis_sha256"])
    assert rebased["source_pins"][0]["edge_id"] == replacement["id"]
    assert rebased["source_pins"][0]["source_version_id"] == later["version"]["id"]
    assert records.show(created["id"], created["version"]["id"])["source_pins"][0]["source_version_id"] == imported["version"]["id"]
    diff = records.diff(created["id"], created["version"]["id"], rebased["version"]["id"])
    assert diff["content_changed"] and any(change["path"].startswith("/source_pins/") for change in diff["changes"])


def test_rebase_requires_unchanged_reviewed_basis_and_preserves_shot_and_frame_state(story, screenplay):
    service = story["service"]
    shot = service.update_entity(story["shot"]["id"], story["shot"]["revision"],
                                 {"fields": {"action": "Initial action", "camera": "Locked-off."}})
    frame = service.attach_frame(shot["id"], story["exact"]["id"])
    _, source = _source_rows(service, screenplay)
    edge = _new_edge(service, source[uid(4)]["id"], shot["id"])
    body = _contract([(edge, "direct-element")])
    records = ObservationContracts(service)
    created = records.create(shot["id"], shot["revision"], body)

    shot = service.update_entity(shot["id"], shot["revision"],
                                 {"fields": {"action": "First changed action"}})
    review = records.review_rebase(created["id"], body)
    assert review["revision"] == created["revision"]
    assert review["basis_changed"] is True
    assert any(change["path"] == "/shot/action" for change in review["changes"])
    assert review["requested_source_pins"] == [{"edge_id": edge["id"], "source_scope": "direct-element"}]

    shot = service.update_entity(shot["id"], shot["revision"],
                                 {"fields": {"action": "Changed again after preview"}})
    before_failed_rebase = service.get("entities", shot["id"])
    frame_before = service.get("frames", frame["id"])
    with service.repo.readonly_transaction() as conn:
        versions_before = conn.execute("SELECT count(*) FROM observation_contract_versions WHERE contract_id=?",
                                       (created["id"],)).fetchone()[0]
        rebase_events_before = conn.execute("SELECT count(*) FROM events WHERE entity_id=? AND action='observation_contract.rebase'",
                                            (created["id"],)).fetchone()[0]
    with pytest.raises(ObservationContractError) as changed:
        records.rebase(created["id"], created["revision"], body, review["expected_basis_sha256"])
    assert changed.value.code == "contract_basis_changed"
    assert changed.value.status == 409
    with service.repo.readonly_transaction() as conn:
        header = conn.execute("SELECT revision,current_version_id FROM observation_contracts WHERE id=?",
                              (created["id"],)).fetchone()
        assert header["revision"] == created["revision"]
        assert header["current_version_id"] == created["version"]["id"]
        assert conn.execute("SELECT count(*) FROM observation_contract_versions WHERE contract_id=?",
                            (created["id"],)).fetchone()[0] == versions_before
        assert conn.execute("SELECT count(*) FROM events WHERE entity_id=? AND action='observation_contract.rebase'",
                            (created["id"],)).fetchone()[0] == rebase_events_before
    assert service.get("entities", shot["id"]) == before_failed_rebase
    assert service.get("frames", frame["id"]) == frame_before

    refreshed = records.review_rebase(created["id"], body)
    assert refreshed["expected_basis_sha256"] != review["expected_basis_sha256"]
    assert any(change["path"] == "/shot/action" for change in refreshed["changes"])
    rebased = records.rebase(created["id"], created["revision"], body,
                             refreshed["expected_basis_sha256"])
    assert rebased["revision"] == created["revision"] + 1
    assert rebased["validation"]["basis_current"] is True
    assert rebased["source_pins"][0]["edge_id"] == edge["id"]
    assert rebased["source_pins"][0]["source_version_id"] == source[uid(4)]["version_id"]
    final_shot = service.get("entities", shot["id"])
    assert final_shot["fields"]["action"] == "Changed again after preview"
    assert final_shot["fields"]["camera"] == "Locked-off."
    assert service.get("frames", frame["id"]) == frame_before


@pytest.mark.parametrize("proposal_change", ["pin", "statement", "priority"])
def test_rebase_review_digest_binds_exact_proposed_contract(story, screenplay, proposal_change):
    service = story["service"]
    shot = service.update_entity(story["shot"]["id"], story["shot"]["revision"],
                                 {"fields": {"camera": "Locked-off."}})
    frame = service.attach_frame(shot["id"], story["exact"]["id"])
    _, source = _source_rows(service, screenplay)
    edge_a = _new_edge(service, source[uid(4)]["id"], shot["id"])
    edge_b = _new_edge(service, source[uid(6)]["id"], shot["id"])
    requirements = []
    if proposal_change in ("statement", "priority"):
        requirements = [{"id": uid(8890), "priority": "must", "basis": "direct",
                         "source_edge_ids": [edge_a["id"]], "statement": "Keep the key visible."}]
    body_a = _contract([(edge_a, "direct-element")], intents=False, requirements=requirements)
    records = ObservationContracts(service)
    created = records.create(shot["id"], shot["revision"], body_a)
    review = records.review_rebase(created["id"], body_a)
    assert review["expected_basis_sha256"] != review["current_basis_sha256"]
    assert review["expected_basis_sha256_kind"] == "sha256(canonical {contract,basis})"

    if proposal_change == "pin":
        proposed = _contract([(edge_b, "direct-element")], intents=False)
    else:
        updated_requirement = dict(body_a["requirements"][0])
        if proposal_change == "statement":
            updated_requirement["statement"] = "Show the key change hands."
        else:
            updated_requirement["priority"] = "prefer"
        proposed = {**body_a, "requirements": [updated_requirement]}
    before_shot = service.get("entities", shot["id"])
    before_frame = service.get("frames", frame["id"])
    with service.repo.readonly_transaction() as conn:
        before_header = dict(conn.execute("SELECT revision,current_version_id FROM observation_contracts WHERE id=?",
                                          (created["id"],)).fetchone())
        before_versions = conn.execute("SELECT count(*) FROM observation_contract_versions WHERE contract_id=?",
                                       (created["id"],)).fetchone()[0]
        before_events = conn.execute("SELECT count(*) FROM events WHERE entity_id=? AND action='observation_contract.rebase'",
                                     (created["id"],)).fetchone()[0]

    with pytest.raises(ObservationContractError) as changed:
        records.rebase(created["id"], created["revision"], proposed, review["expected_basis_sha256"])
    assert changed.value.code == "contract_basis_changed"
    assert changed.value.status == 409
    assert changed.value.details["current_basis_sha256"] == review["current_basis_sha256"]
    assert changed.value.details["current_review_digest_sha256"] != review["expected_basis_sha256"]
    with service.repo.readonly_transaction() as conn:
        after_header = dict(conn.execute("SELECT revision,current_version_id FROM observation_contracts WHERE id=?",
                                         (created["id"],)).fetchone())
        assert after_header == before_header
        assert conn.execute("SELECT count(*) FROM observation_contract_versions WHERE contract_id=?",
                            (created["id"],)).fetchone()[0] == before_versions
        assert conn.execute("SELECT count(*) FROM events WHERE entity_id=? AND action='observation_contract.rebase'",
                            (created["id"],)).fetchone()[0] == before_events
    assert service.get("entities", shot["id"]) == before_shot
    assert service.get("frames", frame["id"]) == before_frame

    refreshed = records.review_rebase(created["id"], proposed)
    rebased = records.rebase(created["id"], created["revision"], proposed,
                             refreshed["expected_basis_sha256"])
    assert rebased["revision"] == created["revision"] + 1
    assert rebased["contract"] == _validate_body(proposed)
    expected_edge = edge_b["id"] if proposal_change == "pin" else edge_a["id"]
    assert [pin["edge_id"] for pin in rebased["source_pins"]] == [expected_edge]
    assert service.get("entities", shot["id"]) == before_shot
    assert service.get("frames", frame["id"]) == before_frame


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
    service.lifecycle(location["id"], location["revision"], "archive")
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


def test_observation_contract_cli_uses_http_status_exit_codes(story):
    service = story["service"]

    def cli(*parts):
        return subprocess.run([sys.executable, "-m", "storyboarder", "--project", str(service.root),
                               *parts, "--json"], capture_output=True, text=True, timeout=15)

    missing = cli("observation", "show", "--contract-id", uid(9690))
    assert missing.returncode == 2
    assert json.loads(missing.stderr)["error"]["code"] == "contract_not_found"

    body = _contract([], intents=False)
    records = ObservationContracts(service)
    created = records.create(story["shot"]["id"], story["shot"]["revision"], body)
    payload = {"shot_id": story["shot"]["id"], "expected_shot_revision": story["shot"]["revision"],
               "contract": body}
    duplicate = cli("observation", "create", "--payload", json.dumps(payload))
    assert duplicate.returncode == 3
    assert json.loads(duplicate.stderr)["error"]["code"] == "contract_already_exists"

    stale_payload = {"contract_id": created["id"], "revision": created["revision"] - 1, "contract": body}
    stale = cli("observation", "revise", "--payload", json.dumps(stale_payload))
    assert stale.returncode == 3
    assert json.loads(stale.stderr)["error"]["code"] == "revision_conflict"

    help_result = subprocess.run([sys.executable, "-m", "storyboarder", "observation", "rebase", "--help"],
                                 capture_output=True, text=True, timeout=15)
    assert help_result.returncode == 0
    assert "--expected-basis-sha256 ARG_EXPECTED_BASIS_SHA256" in help_result.stdout
    assert "Reviewed basis token [required]" in help_result.stdout
    preview_help = subprocess.run([sys.executable, "-m", "storyboarder", "observation", "rebase-preview", "--help"],
                                  capture_output=True, text=True, timeout=15)
    assert preview_help.returncode == 0
    assert "--contract ARG_CONTRACT" in preview_help.stdout
    assert "Versioned observation contract [required]" in preview_help.stdout


def test_rebase_preview_api_cli_share_reviewed_basis_conflict(story, screenplay):
    service = story["service"]
    _, source = _source_rows(service, screenplay)
    edge = _new_edge(service, source[uid(4)]["id"], story["shot"]["id"])
    body = _contract([(edge, "direct-element")])
    created = ObservationContracts(service).create(story["shot"]["id"], story["shot"]["revision"], body)

    app = create_app(project=service.project, port=7430)
    with TestClient(app, base_url="http://127.0.0.1:7430") as client:
        client.headers["X-Storyboarder-Token"] = client.get("/api/v1/session").json()["token"]
        prefix = f"/api/v1/projects/{service.project.id}/commands"
        metadata = client.get("/api/v1/meta").json()
        api_commands = {row["name"]: row for row in metadata["api_commands"]}
        browser_names = {row["name"] for row in metadata["commands"]}
        assert "observation.review_rebase" not in api_commands
        assert "observation.rebase-preview" not in browser_names
        preview_command = api_commands["observation.rebase-preview"]
        assert preview_command["browser"] is False and preview_command["api_safe"] is True
        assert preview_command["read_only"] is True
        assert [field["name"] for field in preview_command["fields"]] == ["contract_id", "contract"]
        rebase_command = api_commands["observation.rebase"]
        assert [field["name"] for field in rebase_command["fields"]] == [
            "contract_id", "revision", "contract", "expected_basis_sha256"]
        assert rebase_command["fields"][-1]["required"] is True

        preview_response = client.post(prefix + "/observation.rebase-preview",
                                       json={"contract_id": created["id"], "contract": body})
        assert preview_response.status_code == 200
        preview = preview_response.json()
        assert preview["basis_changed"] is False
        service.update_entity(story["shot"]["id"], story["shot"]["revision"],
                              {"fields": {"action": "Changed after the saved contract."}})

        stale_payload = {"contract_id": created["id"], "revision": created["revision"],
                         "contract": body, "expected_basis_sha256": preview["expected_basis_sha256"]}
        cli = subprocess.run([sys.executable, "-m", "storyboarder", "--project", str(service.root),
                              "observation", "rebase", "--payload", json.dumps(stale_payload), "--json"],
                             capture_output=True, text=True, timeout=15)
        assert cli.returncode == 3
        cli_error = json.loads(cli.stderr)["error"]
        assert cli_error["code"] == "contract_basis_changed"
        stale_response = client.post(prefix + "/observation.rebase", json=stale_payload)
        assert stale_response.status_code == 409
        assert stale_response.json()["error"] == cli_error

        refreshed = client.post(prefix + "/observation.rebase-preview",
                                json={"contract_id": created["id"], "contract": body})
        assert refreshed.status_code == 200
        assert any(change["path"] == "/shot/action" for change in refreshed.json()["changes"])
        refreshed_payload = stale_payload | {
            "expected_basis_sha256": refreshed.json()["expected_basis_sha256"]}
        rebased = client.post(prefix + "/observation.rebase", json=refreshed_payload)
        assert rebased.status_code == 200, rebased.text
        assert rebased.json()["revision"] == created["revision"] + 1
        assert rebased.json()["source_pins"][0]["edge_id"] == edge["id"]


def test_rebase_review_token_binds_requirement_body_and_exact_pins(story, screenplay):
    service = story["service"]
    _, source = _source_rows(service, screenplay)
    first_edge = _new_edge(service, source[uid(4)]["id"], story["shot"]["id"])
    second_edge = _new_edge(service, source[uid(6)]["id"], story["shot"]["id"])
    original_requirement = {"id": uid(9691), "priority": "must", "basis": "direct",
                            "source_edge_ids": [first_edge["id"]], "statement": "Keep the key visible."}
    proposed_requirement = {"id": uid(9691), "priority": "must", "basis": "direct",
                            "source_edge_ids": [second_edge["id"]], "statement": "Show Mara's hand."}
    original = _contract([(first_edge, "direct-element")], requirements=[original_requirement])
    proposed = _contract([(second_edge, "direct-element")], requirements=[proposed_requirement])
    created = ObservationContracts(service).create(story["shot"]["id"], story["shot"]["revision"], original)

    app = create_app(project=service.project, port=7430)
    with TestClient(app, base_url="http://127.0.0.1:7430") as client:
        client.headers["X-Storyboarder-Token"] = client.get("/api/v1/session").json()["token"]
        prefix = f"/api/v1/projects/{service.project.id}/commands"
        preview = client.post(prefix + "/observation.rebase-preview",
                              json={"contract_id": created["id"], "contract": proposed})
        assert preview.status_code == 200
        reviewed = preview.json()["expected_basis_sha256"]

        stale = client.post(prefix + "/observation.rebase", json={
            "contract_id": created["id"], "revision": created["revision"],
            "contract": original, "expected_basis_sha256": reviewed,
        })
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "contract_basis_changed"
        unchanged = ObservationContracts(service).show(created["id"])
        assert unchanged["revision"] == created["revision"]
        assert unchanged["version"]["id"] == created["version"]["id"]
        assert len(unchanged["history"]) == 1

        refreshed = client.post(prefix + "/observation.rebase-preview",
                                json={"contract_id": created["id"], "contract": original})
        assert refreshed.status_code == 200
        applied = client.post(prefix + "/observation.rebase", json={
            "contract_id": created["id"], "revision": created["revision"],
            "contract": original, "expected_basis_sha256": refreshed.json()["expected_basis_sha256"],
        })
        assert applied.status_code == 200, applied.text
        result = applied.json()
        assert result["contract"]["requirements"][0]["statement"] == "Keep the key visible."
        assert result["source_pins"][0]["edge_id"] == first_edge["id"]


def test_planner_command_schemas_are_json_api_safe_but_agent_only(story, screenplay):
    service = story["service"]
    imported = Documents(service).import_bytes(json.dumps(screenplay).encode(), "planner-api.json", "screenjson")
    action = next(row for row in Documents(service).tree(imported["version"]["id"])["items"]
                  if row["node_type"] == "action")
    source_edge_id = uid(9680)
    contract_id, planned_shot_id = uid(9681), uid(9682)
    item = {
        "shot_id": planned_shot_id, "contract_id": contract_id, "scene_id": story["scene"]["id"],
        "expected_scene_revision": story["scene"]["revision"], "title": "API planned shot",
        "source_edges": [{"edge_id": source_edge_id, "document_id": imported["document"]["id"],
                           "version_id": imported["version"]["id"], "node_id": action["id"],
                           "source_sha256": action["content_sha256"], "source_scope": "direct-element"}],
        "contract": _contract([({"id": source_edge_id}, "direct-element")]),
    }
    app = create_app(project=service.project, port=7430)
    with TestClient(app, base_url="http://127.0.0.1:7430") as client:
        client.headers["X-Storyboarder-Token"] = client.get("/api/v1/session").json()["token"]
        prefix = f"/api/v1/projects/{service.project.id}"
        metadata = client.get("/api/v1/meta").json()
        browser_commands = {row["name"]: row for row in metadata["commands"]}
        api_commands = {row["name"]: row for row in metadata["api_commands"]}
        for name in ("observation.coverage", "observation.create-group"):
            assert name not in browser_commands
            assert api_commands[name]["api_safe"] is True
            assert api_commands[name]["browser"] is False
        assert [field["name"] for field in api_commands["observation.coverage"]["fields"]] == ["request", "limit", "offset"]
        assert [field["name"] for field in api_commands["observation.create-group"]["fields"]] == ["request"]

        coverage = client.post(prefix + "/commands/observation.coverage", json={"request": {"anchors": []}})
        assert coverage.status_code == 200
        assert coverage.json()["schema"] == "storyboarder.observation-coverage/v1"
        malformed = client.post(prefix + "/commands/observation.coverage", json={"request": {"titles": []}})
        assert malformed.status_code == 422
        assert malformed.json()["error"]["code"] == "observation_plan_invalid"
        created = client.post(prefix + "/commands/observation.create-group", json={"request": {"items": [item]}})
        assert created.status_code == 200, created.text
        assert created.json()["items"][0]["shot_id"] == planned_shot_id
        assert created.json()["items"][0]["contract_id"] == contract_id


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


@pytest.mark.parametrize(("tamper", "reason"), [
    ("number_parent", "contract_version_number_sequence_mismatch"),
    ("parent", "contract_version_parent_chain_mismatch"),
    ("sealed", "contract_version_unsealed"),
])
def test_doctor_checks_contiguous_sealed_version_chain(story, screenplay, tamper, reason):
    service = story["service"]
    _, source = _source_rows(service, screenplay)
    edge = _new_edge(service, source[uid(4)]["id"], story["shot"]["id"])
    records = ObservationContracts(service)
    created = records.create(story["shot"]["id"], story["shot"]["revision"],
                             _contract([(edge, "direct-element")]))
    revised = records.revise(created["id"], created["revision"],
                             _contract([(edge, "direct-element")], notes="Second immutable version."))
    with service.repo.transaction() as conn:
        conn.execute("DROP TRIGGER observation_version_seal_once")
        if tamper == "number_parent":
            conn.execute("UPDATE observation_contract_versions SET number=3,parent_version_id=NULL WHERE id=?",
                         (revised["version"]["id"],))
        elif tamper == "parent":
            conn.execute("UPDATE observation_contract_versions SET parent_version_id=NULL WHERE id=?",
                         (revised["version"]["id"],))
        else:
            conn.execute("UPDATE observation_contract_versions SET sealed=0 WHERE id=?",
                         (revised["version"]["id"],))

    before = hashlib.sha256(service.repo.path.read_bytes()).hexdigest()
    report = service.doctor()
    after = hashlib.sha256(service.repo.path.read_bytes()).hexdigest()
    issue = next(issue for issue in report["issues"] if issue["code"] == "observation_contract_integrity")
    assert reason in issue["details"]["reason"]
    assert before == after


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
    assert missing["schema_version"] == 6 and not missing["healthy"]
    assert any(issue["code"] == "observation_contract_integrity_check" for issue in missing["issues"])
    assert before == after

    monkeypatch.setattr(repository, "SCHEMA_VERSION", 4)
    old_project = Project.create(tmp_path / "schema-four-doctor", "Schema four")
    old_service = Service(old_project)
    monkeypatch.setattr(repository, "SCHEMA_VERSION", 6)

    def forbidden_contract_walk(self):
        raise AssertionError("schema 4 must not inspect schema 5 contract tables")

    monkeypatch.setattr(ObservationContracts, "integrity_issues", forbidden_contract_walk)
    before = old_service.repo.path.read_bytes()
    old_report = old_service.doctor()
    after = old_service.repo.path.read_bytes()
    old_codes = {issue["code"] for issue in old_report["issues"]}
    assert old_report["schema_version"] == 4 and old_report["supported_schema_version"] == 6
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
        records = ObservationContracts(destination)
        review = records.review_rebase(header["id"], contract_body)
        records.rebase(header["id"], restored_header["revision"], contract_body, review["expected_basis_sha256"])
    assert rejected_rebase.value.code == "contract_source_pin_retired"
    new_shot = destination.create_entity("shot", "New shot", scene["id"])
    archived_reference_body = _contract([], intents=False, references=[asset["id"]])
    with pytest.raises(ObservationContractError) as rejected_reference:
        ObservationContracts(destination).create(new_shot["id"], new_shot["revision"], archived_reference_body)
    assert rejected_reference.value.code == "contract_reference_archived"


def test_exact_moved_scene_context_history_restores_only_against_saved_parent(story, screenplay, tmp_path):
    source_service = story["service"]
    sequence = source_service.create_entity("sequence", "Second sequence")
    new_scene = source_service.create_entity("scene", "Later scene", sequence["id"])
    _, source = _source_rows(source_service, screenplay)
    edge = _new_edge(source_service, source[uid(3)]["id"], story["scene"]["id"])
    body = _contract([(edge, "scene-context")])
    destination_path = tmp_path / "moved-history-destination"
    shutil.copytree(source_service.root, destination_path)
    destination = Service(Project(destination_path))
    created = ObservationContracts(source_service).create(story["shot"]["id"], story["shot"]["revision"], body)
    with source_service.repo.readonly_transaction() as conn:
        header = dict(conn.execute("SELECT * FROM observation_contracts WHERE id=?", (created["id"],)).fetchone())
        version = dict(conn.execute("SELECT * FROM observation_contract_versions WHERE id=?", (created["version"]["id"],)).fetchone())
        pin = dict(conn.execute("SELECT * FROM observation_source_pins WHERE version_id=?", (version["id"],)).fetchone())

    moved = destination.move(story["shot"]["id"], story["shot"]["revision"], 0, new_scene["id"])
    assert moved["parent_id"] == new_scene["id"]
    with destination.repo.observation_restore_transaction() as conn:
        conn.execute("INSERT INTO observation_contracts(id,shot_id,current_version_id,revision,created_at,updated_at) VALUES(?,?,NULL,1,?,?)",
                     (header["id"], header["shot_id"], header["created_at"], header["updated_at"]))
        conn.execute("""INSERT INTO observation_contract_versions
          (id,contract_id,parent_version_id,number,schema_version,contract_json,content_sha256,basis_json,basis_sha256,operation,sealed,created_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,0,?)""",
                     (version["id"], version["contract_id"], version["parent_version_id"], version["number"],
                      version["schema_version"], version["contract_json"], version["content_sha256"], version["basis_json"],
                      version["basis_sha256"], version["operation"], version["created_at"]))
        conn.execute("""INSERT INTO observation_source_pins VALUES
          (:version_id,:edge_id,:source_scope,:document_id,:source_version_id,:node_id,:logical_id,
           :source_sha256,:scope_sha256,:document_sha256,:artifact_sha256,:source_snapshot,
           :edge_source_snapshot,:edge_target_snapshot,:created_at)""", pin)
        conn.execute("UPDATE observation_contract_versions SET sealed=1 WHERE id=?", (version["id"],))
        conn.execute("UPDATE observation_contracts SET current_version_id=? WHERE id=?", (version["id"], header["id"]))

    records = ObservationContracts(destination)
    restored = records.show(header["id"])
    assert restored["current_version_id"] == version["id"]
    assert restored["validation"]["status"] == "unresolved"
    assert any(finding["code"] == "source_pin_stale"
               and "edge_target_mismatch" in finding["reasons"] for finding in restored["validation"]["findings"])
    assert not any(issue["code"] == "observation_contract_integrity" for issue in destination.doctor()["issues"])

    with pytest.raises(ObservationContractError) as stale_revise:
        records.revise(header["id"], restored["revision"], body)
    assert stale_revise.value.code == "contract_rebase_required"
    with pytest.raises(ObservationContractError) as guarded_rebase:
        review = records.review_rebase(header["id"], body)
        records.rebase(header["id"], restored["revision"], body, review["expected_basis_sha256"])
    assert guarded_rebase.value.code == "contract_source_pin_target_mismatch"

    def rejected_restore(*, forged_parent=False, forged_target_snapshot=False):
        basis = json.loads(version["basis_json"])
        if forged_parent:
            basis["shot"]["parent_scene_id"] = new_scene["id"]
        candidate = dict(version)
        candidate.update(id=uid(9901 if forged_parent else 9902), parent_version_id=version["id"], number=2,
                         basis_json=dumps(basis), basis_sha256=content_hash(basis), operation="rebase", sealed=0)
        candidate_pin = dict(pin, version_id=candidate["id"])
        if forged_target_snapshot:
            target_snapshot = json.loads(candidate_pin["edge_target_snapshot"])
            target_snapshot["id"] = new_scene["id"]
            candidate_pin["edge_target_snapshot"] = dumps(target_snapshot)
        with pytest.raises(StoryboardError, match="active exact screenplay edge"):
            with destination.repo.observation_restore_transaction() as conn:
                conn.execute("""INSERT INTO observation_contract_versions
                  (id,contract_id,parent_version_id,number,schema_version,contract_json,content_sha256,basis_json,basis_sha256,operation,sealed,created_at)
                  VALUES(?,?,?,?,?,?,?,?,?,?,0,?)""",
                             (candidate["id"], candidate["contract_id"], candidate["parent_version_id"], candidate["number"],
                              candidate["schema_version"], candidate["contract_json"], candidate["content_sha256"],
                              candidate["basis_json"], candidate["basis_sha256"], candidate["operation"], candidate["created_at"]))
                conn.execute("""INSERT INTO observation_source_pins VALUES
                  (:version_id,:edge_id,:source_scope,:document_id,:source_version_id,:node_id,:logical_id,
                   :source_sha256,:scope_sha256,:document_sha256,:artifact_sha256,:source_snapshot,
                   :edge_source_snapshot,:edge_target_snapshot,:created_at)""", candidate_pin)

    rejected_restore(forged_parent=True)
    rejected_restore(forged_target_snapshot=True)


@pytest.mark.parametrize("field,value", [("time", "Midnight"), ("location_id", None)])
def test_related_continuity_shot_own_context_changes_invalidate_basis(story, screenplay, field, value):
    service = story["service"]
    _, source = _source_rows(service, screenplay)
    edge = _new_edge(service, source[uid(4)]["id"], story["shot"]["id"])
    related = service.create_entity("shot", "Continuity shot", story["scene"]["id"], fields={"action": "Wait."})
    continuity = {"id": uid(8801), "related_shot_ids": [related["id"]], "statement": "Keep the arrival continuous."}
    result = ObservationContracts(service).create(story["shot"]["id"], story["shot"]["revision"],
                                                  _contract([(edge, "direct-element")], continuity=[continuity]))
    assert result["validation"]["status"] == "consistent"
    changes = {"fields": {field: value}}
    if field == "location_id":
        location = service.create_entity("asset", "Alternate location", fields={"type": "location"})
        changes["fields"][field] = location["id"]
    service.update_entity(related["id"], related["revision"], changes)
    validation = ObservationContracts(service).validate(result["id"], result["version"]["id"])
    assert validation["status"] == "unresolved"
    assert any(finding["code"] == "authored_basis_changed" for finding in validation["findings"])


@pytest.mark.parametrize("change", ["description", "archive"])
def test_related_continuity_location_asset_content_and_archive_are_in_basis(story, screenplay, change):
    service = story["service"]
    _, source = _source_rows(service, screenplay)
    edge = _new_edge(service, source[uid(4)]["id"], story["shot"]["id"])
    location = service.create_entity("asset", "Related shot location", description="A narrow platform.",
                                     fields={"type": "location", "notes": "Morning light."})
    related = service.create_entity("shot", "Continuity shot", story["scene"]["id"],
                                    fields={"action": "Wait.", "location_id": location["id"]})
    note = {"id": uid(8810), "related_shot_ids": [related["id"]], "statement": "Keep the arrival continuous."}
    result = ObservationContracts(service).create(story["shot"]["id"], story["shot"]["revision"],
                                                  _contract([(edge, "direct-element")], continuity=[note]))
    assert result["validation"]["status"] == "consistent"
    if change == "description":
        service.update_entity(location["id"], location["revision"], {"description": "A platform beside the river."})
    else:
        service.lifecycle(location["id"], location["revision"], "archive")
    validation = ObservationContracts(service).validate(result["id"], result["version"]["id"])
    assert validation["status"] == "unresolved"
    assert any(finding["code"] == "authored_basis_changed" for finding in validation["findings"])


def test_validation_and_doctor_recheck_artifact_and_cache_once_per_report(story, screenplay, monkeypatch):
    service = story["service"]
    imported, source = _source_rows(service, screenplay)
    edge_a = _new_edge(service, source[uid(4)]["id"], story["shot"]["id"])
    edge_b = _new_edge(service, source[uid(6)]["id"], story["shot"]["id"])
    records = ObservationContracts(service)
    from pathlib import Path

    original_read_bytes = Path.read_bytes
    calls = []
    with service.repo.readonly_transaction() as conn:
        artifact = dict(conn.execute("SELECT * FROM source_artifacts WHERE id=?",
                                     (imported["version"]["source_artifact_id"],)).fetchone())
    artifact_path = (service.root / artifact["path"]).resolve()

    def counted_read_bytes(path):
        if path.resolve() == artifact_path:
            calls.append(str(path))
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", counted_read_bytes)
    created = records.create(story["shot"]["id"], story["shot"]["revision"],
                             _contract([(edge_a, "direct-element"), (edge_b, "direct-element")]))
    assert len(calls) == 1
    calls.clear()
    assert records.validate(created["id"])["status"] == "consistent"
    assert len(calls) == 1

    original_bytes = original_read_bytes(artifact_path)
    altered = bytes([original_bytes[0] ^ 1]) + original_bytes[1:]
    artifact_path.write_bytes(altered)
    try:
        calls.clear()
        validation = records.validate(created["id"])
        assert len(calls) == 1
        assert validation["status"] == "unresolved"
        assert sum("artifact_unavailable_or_changed" in pin["reasons"] for pin in validation["source_pins"]) == 2
        calls.clear()
        report = service.doctor(hashes=True)
        assert any(issue["code"] == "observation_contract_integrity" for issue in report["issues"])
        assert len(calls) == 1
    finally:
        artifact_path.write_bytes(original_bytes)


def test_doctor_detects_parseable_source_and_edge_snapshot_tampering(story, screenplay):
    service = story["service"]
    _, source = _source_rows(service, screenplay)
    direct = _new_edge(service, source[uid(4)]["id"], story["shot"]["id"])
    context = _new_edge(service, source[uid(3)]["id"], story["scene"]["id"])
    created = ObservationContracts(service).create(
        story["shot"]["id"], story["shot"]["revision"],
        _contract([(direct, "direct-element"), (context, "scene-context")]))
    with service.repo.transaction() as conn:
        conn.execute("DROP TRIGGER observation_source_pin_immutable_update")
        direct_pin = dict(conn.execute("SELECT * FROM observation_source_pins WHERE version_id=? AND edge_id=?",
                                       (created["version"]["id"], direct["id"])).fetchone())
        source_snapshot = json.loads(direct_pin["source_snapshot"])
        source_snapshot["scope_sha256"] = "0" * 64
        conn.execute("UPDATE observation_source_pins SET source_snapshot=?,scope_sha256=? WHERE version_id=? AND edge_id=?",
                     (dumps(source_snapshot), "0" * 64, created["version"]["id"], direct["id"]))
        context_pin = dict(conn.execute("SELECT * FROM observation_source_pins WHERE version_id=? AND edge_id=?",
                                        (created["version"]["id"], context["id"])).fetchone())
        edge_target_snapshot = json.loads(context_pin["edge_target_snapshot"])
        edge_target_snapshot["id"] = uid(8899)
        conn.execute("UPDATE observation_source_pins SET edge_target_snapshot=? WHERE version_id=? AND edge_id=?",
                     (dumps(edge_target_snapshot), created["version"]["id"], context["id"]))
    validation = ObservationContracts(service).validate(created["id"])
    assert validation["status"] == "unresolved"
    assert any("source_snapshot_mismatch" in pin["reasons"] for pin in validation["source_pins"])
    assert any("edge_target_snapshot_mismatch" in pin["reasons"] for pin in validation["source_pins"])
    damaged = service.doctor()
    issue = next(issue for issue in damaged["issues"] if issue["code"] == "observation_contract_integrity")
    assert "scope_hash_mismatch" in issue["details"]["reason"]
    assert "source_snapshot_mismatch" in issue["details"]["reason"]


def test_validation_and_doctor_recompute_full_immutable_source_endpoint_projection(story, screenplay):
    service = story["service"]
    imported, source = _source_rows(service, screenplay)
    edge = _new_edge(service, source[uid(4)]["id"], story["shot"]["id"])
    created = ObservationContracts(service).create(story["shot"]["id"], story["shot"]["revision"],
                                                  _contract([(edge, "direct-element")]))
    with service.repo.transaction() as conn:
        conn.execute("UPDATE documents SET title='Renamed screenplay' WHERE id=?", (imported["document"]["id"],))
    records = ObservationContracts(service)
    assert records.validate(created["id"])["status"] == "consistent"
    assert not any(issue["code"] == "observation_contract_integrity" for issue in service.doctor()["issues"])
    SourceWorkflows(service).archive(imported["document"]["id"], imported["document"]["revision"])
    assert records.validate(created["id"])["status"] == "unresolved"
    assert not any(issue["code"] == "observation_contract_integrity" for issue in service.doctor()["issues"])
    SourceWorkflows(service).archive(imported["document"]["id"], imported["document"]["revision"] + 1, archived=False)
    assert records.validate(created["id"])["status"] == "consistent"
    current_document = Documents(service).show(imported["document"]["id"])
    revised_source = Documents(service).revise_node(
        source[uid(4)]["id"], {"text": {"en": "The latest draft changes this action."}}, current_document["revision"])
    assert revised_source["version"]["id"] != imported["version"]["id"]
    assert records.validate(created["id"])["status"] == "unresolved"
    assert not any(issue["code"] == "observation_contract_integrity" for issue in service.doctor()["issues"])

    with service.repo.transaction() as conn:
        conn.execute("DROP TRIGGER immutable_provenance_endpoints")
        conn.execute("DROP TRIGGER observation_source_pin_immutable_update")
        provenance_snapshot = json.loads(conn.execute(
            "SELECT source_snapshot FROM provenance_edges WHERE id=?", (edge["id"],)).fetchone()[0])
        provenance_snapshot["identity"] = "inferred"
        provenance_snapshot["title"] = "Tampered source title"
        conn.execute("UPDATE provenance_edges SET source_snapshot=? WHERE id=?",
                     (dumps(provenance_snapshot), edge["id"]))
        conn.execute("UPDATE observation_source_pins SET edge_source_snapshot=? WHERE version_id=? AND edge_id=?",
                     (dumps(provenance_snapshot), created["version"]["id"], edge["id"]))

    records = ObservationContracts(service)
    validation = records.validate(created["id"])
    assert validation["status"] in ("unresolved", "conflict")
    pin = validation["source_pins"][0]
    assert "edge_source_snapshot_mismatch" in pin["reasons"]
    show = records.show(created["id"])
    assert show["validation"]["status"] in ("unresolved", "conflict")
    report = service.doctor()
    issue = next(issue for issue in report["issues"] if issue["code"] == "observation_contract_integrity")
    assert "edge_source_snapshot_mismatch" in issue["details"]["reason"]


def test_reference_snapshot_identity_and_kind_are_checked_without_comparing_mutable_type_or_title(story, screenplay):
    service = story["service"]
    _, source = _source_rows(service, screenplay)
    edge = _new_edge(service, source[uid(4)]["id"], story["shot"]["id"])
    reference = service.create_entity("asset", "Reference before rename", fields={"type": "prop"})
    records = ObservationContracts(service)
    created = records.create(story["shot"]["id"], story["shot"]["revision"],
                             _contract([(edge, "direct-element")], references=[reference["id"]]))

    reference = service.update_entity(reference["id"], reference["revision"], {"title": "Renamed reference"})
    validation = records.validate(created["id"])
    assert validation["status"] == "consistent"
    assert validation["references"][0]["state"] == "available"
    reference = service.update_entity(reference["id"], reference["revision"], {"fields": {"type": "character"}})
    changed_type = records.validate(created["id"])
    assert changed_type["status"] == "unresolved"
    assert changed_type["references"][0]["state"] == "available"
    assert not any(issue["code"] == "observation_contract_integrity" for issue in service.doctor()["issues"])
    with service.repo.transaction() as conn:
        conn.execute("DROP TRIGGER observation_reference_pin_immutable_update")
        row = conn.execute("SELECT snapshot_json FROM observation_reference_pins WHERE version_id=? AND reference_id=?",
                           (created["version"]["id"], reference["id"])).fetchone()
        snapshot = json.loads(row[0])
        snapshot["type"] = "historical-type"
        conn.execute("UPDATE observation_reference_pins SET snapshot_json=? WHERE version_id=? AND reference_id=?",
                     (dumps(snapshot), created["version"]["id"], reference["id"]))
    type_tamper = records.validate(created["id"])
    assert type_tamper["status"] == "conflict"
    assert type_tamper["references"][0]["reason"] == "reference_snapshot_basis_type_mismatch"
    assert records.show(created["id"])["reference_pins"][0]["reason"] == "reference_snapshot_basis_type_mismatch"
    type_issue = next(issue for issue in service.doctor()["issues"] if issue["code"] == "observation_contract_integrity")
    assert "reference_snapshot_basis_type_mismatch" in type_issue["details"]["reason"]

    snapshot["reference_id"] = uid(8898)
    snapshot["kind"] = "scene"
    with service.repo.transaction() as conn:
        conn.execute("UPDATE observation_reference_pins SET snapshot_json=? WHERE version_id=? AND reference_id=?",
                     (dumps(snapshot), created["version"]["id"], reference["id"]))
    validation = records.validate(created["id"])
    assert validation["status"] == "conflict"
    assert validation["references"][0]["reason"] == "reference_snapshot_mismatch"
    shown = records.show(created["id"])
    assert shown["reference_pins"][0]["state"] == "conflict"
    assert shown["reference_pins"][0]["reason"] == "reference_snapshot_mismatch"
    issue = next(issue for issue in service.doctor()["issues"] if issue["code"] == "observation_contract_integrity")
    assert "contract_reference_snapshot_integrity_mismatch" in issue["details"]["reason"]


def test_contract_history_retains_owner_reference_and_past_continuity_targets(story, screenplay):
    service = story["service"]
    _, source = _source_rows(service, screenplay)
    edge = _new_edge(service, source[uid(4)]["id"], story["shot"]["id"])
    related = service.create_entity("shot", "Historical continuity shot", story["scene"]["id"])
    reference = service.create_entity("asset", "Referenced prop", fields={"type": "prop"})
    note = {"id": uid(8821), "related_shot_ids": [related["id"]], "statement": "Preserve the same object."}
    records = ObservationContracts(service)
    first = records.create(story["shot"]["id"], story["shot"]["revision"],
                           _contract([(edge, "direct-element")], references=[reference["id"]], continuity=[note]))
    revised_body = _contract([(edge, "direct-element")])
    second = records.revise(first["id"], first["revision"], revised_body)
    assert second["validation"]["status"] == "consistent"

    related_usage = service.usage(related["id"])
    assert related_usage["can_delete"] is False
    assert first["id"] in related_usage["observation_continuity"]
    with pytest.raises(InUse) as related_delete:
        service.lifecycle(related["id"], related["revision"], "delete")
    assert related_delete.value.details["observation_continuity"] == [first["id"]]
    service.lifecycle(related["id"], related["revision"], "archive")
    with pytest.raises(StoryboardError, match="Shot has retained observation continuity history"):
        with service.repo.transaction() as conn:
            conn.execute("DELETE FROM entities WHERE id=?", (related["id"],))
    historical = records.validate(first["id"], first["version"]["id"])
    assert historical["status"] == "unresolved"
    assert any(finding["code"] == "continuity_reference_archived" for finding in historical["findings"])

    asset_usage = service.usage(reference["id"])
    assert asset_usage["can_delete"] is False
    assert first["id"] in asset_usage["observation_references"]
    with pytest.raises(InUse) as asset_delete:
        service.lifecycle(reference["id"], reference["revision"], "delete")
    assert asset_delete.value.details["observation_references"] == [first["id"]]
    with pytest.raises(StoryboardError, match="Asset has retained observation contract references"):
        with service.repo.transaction() as conn:
            conn.execute("DELETE FROM entities WHERE id=?", (reference["id"],))
    service.lifecycle(reference["id"], reference["revision"], "archive")
    historical = records.validate(first["id"], first["version"]["id"])
    assert any(finding["code"] == "reference_archived" for finding in historical["findings"])

    owner_usage = service.usage(story["shot"]["id"])
    assert owner_usage["can_delete"] is False
    assert first["id"] in owner_usage["observation_contracts"]
    with pytest.raises(InUse) as owner_delete:
        service.lifecycle(story["shot"]["id"], story["shot"]["revision"], "delete")
    assert owner_delete.value.details["observation_contracts"] == [first["id"]]
    with pytest.raises(StoryboardError, match="Shot has retained observation contract history"):
        with service.repo.transaction() as conn:
            conn.execute("DELETE FROM entities WHERE id=?", (story["shot"]["id"],))
    service.lifecycle(story["shot"]["id"], story["shot"]["revision"], "archive")


def test_two_connection_contract_revision_compare_and_swap_has_one_winner(story, screenplay):
    service = story["service"]
    _, source = _source_rows(service, screenplay)
    edge = _new_edge(service, source[uid(4)]["id"], story["shot"]["id"])
    records = ObservationContracts(service)
    created = records.create(story["shot"]["id"], story["shot"]["revision"], _contract([(edge, "direct-element")]))
    competing = [ObservationContracts(Service(Project(service.root))) for _ in range(2)]
    barrier = Barrier(2)

    def revise(index):
        barrier.wait(timeout=5)
        body = _contract([(edge, "direct-element")], notes=f"writer-{index}")
        try:
            return competing[index].revise(created["id"], created["revision"], body)
        except Exception as exc:  # return for stable outcome assertions in the parent thread
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(revise, range(2)))
    successes = [item for item in outcomes if isinstance(item, dict)]
    conflicts = [item for item in outcomes if isinstance(item, Conflict)]
    assert len(successes) == 1
    assert len(conflicts) == 1
    assert conflicts[0].code == "revision_conflict"
    with service.repo.readonly_transaction() as conn:
        header = conn.execute("SELECT revision,current_version_id FROM observation_contracts WHERE id=?", (created["id"],)).fetchone()
        versions = conn.execute("SELECT count(*) FROM observation_contract_versions WHERE contract_id=?", (created["id"],)).fetchone()[0]
        events = conn.execute("SELECT count(*) FROM events WHERE entity_id=? AND action='observation_contract.revise'", (created["id"],)).fetchone()[0]
    assert header["revision"] == 2 and header["current_version_id"] == successes[0]["version"]["id"]
    assert versions == 2 and events == 1


def test_artifact_cache_rechecks_each_pin_expected_document_hash(story, screenplay, monkeypatch):
    service = story["service"]
    imported, source = _source_rows(service, screenplay)
    source_version_id = imported["version"]["id"]
    source_scene = source[uid(3)]
    clone_document_id, clone_version_id, clone_node_id = uid(9101), uid(9102), uid(9103)
    correct_edge_id, mismatched_edge_id = uid(9201), uid(9202)
    provenance = Provenance(service)
    with service.repo.transaction() as conn:
        document = dict(conn.execute("SELECT * FROM documents WHERE id=?", (imported["document"]["id"],)).fetchone())
        version = dict(conn.execute("SELECT * FROM document_versions WHERE id=?", (source_version_id,)).fetchone())
        node = dict(conn.execute("SELECT * FROM document_nodes WHERE id=?", (source_scene["id"],)).fetchone())
        conn.execute("""INSERT INTO documents
          (id,kind,format,external_id,title,current_version_id,revision,archived,created_at,updated_at)
          VALUES(?,?,?,?,?,NULL,1,0,?,?)""",
                     (clone_document_id, "screenplay", document["format"], None, "Integrity clone",
                      document["created_at"], document["updated_at"]))
        conn.execute("""INSERT INTO document_versions
          (id,document_id,parent_version_id,number,label,format_version,content_sha256,source_artifact_id,warnings,created_at)
          VALUES(?,?,NULL,1,?,?,?,?,?,?)""",
                     (clone_version_id, clone_document_id, version["label"], version["format_version"],
                      version["content_sha256"], version["source_artifact_id"], version["warnings"], version["created_at"]))
        conn.execute("""INSERT INTO document_nodes
          (id,version_id,logical_id,parent_id,node_type,position,title,text,source_pointer,payload,content_sha256,identity)
          VALUES(?,?,?,NULL,?,?,?,?,?,?,?,?)""",
                     (clone_node_id, clone_version_id, node["logical_id"], node["node_type"], node["position"],
                      node["title"], node["text"], node["source_pointer"], node["payload"],
                      node["content_sha256"], node["identity"]))
        conn.execute("UPDATE documents SET current_version_id=? WHERE id=?", (clone_version_id, clone_document_id))
        target = provenance._endpoint(conn, "entity", story["shot"]["id"])
        for edge_id, node_id in ((correct_edge_id, source_scene["id"]), (mismatched_edge_id, clone_node_id)):
            source_snapshot = provenance._endpoint(conn, "node", node_id)
            conn.execute("""INSERT INTO provenance_edges
              (id,source_type,source_id,target_type,target_id,relation,source_snapshot,target_snapshot,notes,retired,revision,created_at)
              VALUES(?,'node',?,'entity',?,'visualizes',?,?, '',0,1,?)""",
                         (edge_id, node_id, story["shot"]["id"], dumps(source_snapshot), dumps(target), "test"))
    assert version["source_artifact_id"] == imported["version"]["source_artifact_id"]
    body = _contract([(dict(id=correct_edge_id), "direct-element"),
                      (dict(id=mismatched_edge_id), "direct-element")])
    records = ObservationContracts(service)
    created = records.create(story["shot"]["id"], story["shot"]["revision"], body)
    assert created["validation"]["status"] == "consistent"

    with service.repo.transaction() as conn:
        conn.execute("DROP TRIGGER immutable_document_version_update")
        conn.execute("UPDATE document_versions SET content_sha256=? WHERE id=?", ("f" * 64, clone_version_id))
    validation = records.validate(created["id"])
    mismatched_pin = next(pin for pin in validation["source_pins"] if pin["edge_id"] == mismatched_edge_id)
    assert validation["status"] == "unresolved"
    assert "artifact_unavailable_or_changed" in mismatched_pin["reasons"]

    from pathlib import Path

    with service.repo.readonly_transaction() as conn:
        artifact = dict(conn.execute("SELECT * FROM source_artifacts WHERE id=?", (version["source_artifact_id"],)).fetchone())
    artifact_path = (service.root / artifact["path"]).resolve()
    original_read_bytes = Path.read_bytes
    original_bytes = original_read_bytes(artifact_path)
    artifact_path.write_bytes(bytes([original_bytes[0] ^ 1]) + original_bytes[1:])
    reads = []

    def counted_read_bytes(path):
        if path.resolve() == artifact_path:
            reads.append(path)
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", counted_read_bytes)
    try:
        next_validation = records.validate(created["id"])
        assert next_validation["status"] == "unresolved"
        assert len(reads) == 1
        assert all("artifact_unavailable_or_changed" in pin["reasons"] for pin in next_validation["source_pins"])
    finally:
        artifact_path.write_bytes(original_bytes)


def test_two_connection_contract_create_compare_and_swap_has_one_winner(story, screenplay):
    service = story["service"]
    _, source = _source_rows(service, screenplay)
    edge = _new_edge(service, source[uid(4)]["id"], story["shot"]["id"])
    shot_before = service.get("entities", story["shot"]["id"])
    competing = [ObservationContracts(Service(Project(service.root))) for _ in range(2)]
    barrier = Barrier(2)

    def create(index):
        body = _contract([(edge, "direct-element")], notes=f"create-writer-{index}")
        body["script_intents"][0]["id"] = uid(9300 + index)
        barrier.wait(timeout=5)
        try:
            return competing[index].create(story["shot"]["id"], shot_before["revision"], body)
        except Exception as exc:  # return both outcomes for deterministic assertions
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(create, range(2)))
    successes = [item for item in outcomes if isinstance(item, dict)]
    conflicts = [item for item in outcomes if isinstance(item, ObservationContractError)]
    assert len(successes) == 1 and len(conflicts) == 1
    assert conflicts[0].code == "contract_already_exists" and conflicts[0].status == 409
    with service.repo.readonly_transaction() as conn:
        headers = conn.execute("SELECT count(*) FROM observation_contracts WHERE shot_id=?", (story["shot"]["id"],)).fetchone()[0]
        versions = conn.execute("""SELECT count(*) FROM observation_contract_versions v
          JOIN observation_contracts c ON c.id=v.contract_id WHERE c.shot_id=?""", (story["shot"]["id"],)).fetchone()[0]
        events = conn.execute("SELECT count(*) FROM events WHERE entity_id=? AND action='observation_contract.created'",
                              (successes[0]["id"],)).fetchone()[0]
        shot_after = conn.execute("SELECT fields,revision FROM entities WHERE id=?", (story["shot"]["id"],)).fetchone()
    assert headers == versions == events == 1
    assert json.loads(shot_after["fields"]) == shot_before["fields"]
    assert shot_after["revision"] == shot_before["revision"]
