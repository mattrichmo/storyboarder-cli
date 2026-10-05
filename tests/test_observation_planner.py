"""Exact source coverage and atomic multi-shot authoring."""
import copy
import hashlib
import json
import sys
import uuid
from pathlib import Path

import pytest

from storyboarder.application.documents import Documents
from storyboarder.application.observation_contracts import CONTRACT_SCHEMA, ObservationContractError, ObservationContracts
from storyboarder.application.observation_planner import (
    ObservationPlanner,
    ObservationPlannerError,
)
import storyboarder.application.observation_contracts as contract_module
from storyboarder.application.provenance import Provenance
from storyboarder.application.source_workflows import SourceWorkflows
from storyboarder.domain.errors import Conflict


def uid(number):
    return str(uuid.UUID(int=number))


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


@pytest.fixture
def imported_screenplay(service, screenplay):
    imported = Documents(service).import_bytes(json.dumps(screenplay).encode(), "winter.screenjson", "screenjson")
    nodes = Documents(service).tree(imported["version"]["id"])["items"]
    return imported, {row["logical_id"]: row for row in nodes}


def contract_body(edges, *, requirement_id=9001):
    pins = [{"edge_id": edge_id, "source_scope": scope} for edge_id, scope in edges]
    intents = [{"id": uid(9100 + index), "source_edge_id": edge_id, "source_scope": scope,
                "purpose": "coverage", "communication": "Record the authored link for review.", "basis": "direct"}
               for index, (edge_id, scope) in enumerate(edges, 1)]
    requirements = []
    if edges:
        requirements.append({"id": uid(requirement_id), "priority": "must", "basis": "direct",
                             "source_edge_ids": [edges[0][0]], "statement": "The authored key handoff is linked."})
    return {"schema": CONTRACT_SCHEMA, "source_pins": pins, "script_intents": intents,
            "requirements": requirements, "references": [], "continuity": [], "notes": ""}


def plan_item(shot_id, contract_id, scene, edges, *, expected_revision=None, title="Planned coverage", fields=None):
    return {"shot_id": shot_id, "contract_id": contract_id, "scene_id": scene["id"],
            "expected_scene_revision": scene["revision"] if expected_revision is None else expected_revision,
            "title": title, "description": "", "fields": fields or {},
            "source_edges": edges,
            "contract": contract_body([(edge["edge_id"], edge["source_scope"]) for edge in edges],
                                      requirement_id=int(shot_id.replace("-", "")[-6:], 16) % 100000 + 9200)}


def exact_edge(edge_id, imported, node, scope="direct-element", *, source_sha256=None):
    return {"edge_id": edge_id, "document_id": imported["document"]["id"],
            "version_id": imported["version"]["id"], "node_id": node["id"],
            "source_sha256": source_sha256 or node["content_sha256"], "source_scope": scope}


def test_coverage_distinguishes_exact_links_context_and_request_anchor_states(story, imported_screenplay):
    service = story["service"]
    imported, nodes = imported_screenplay
    action = nodes[uid(4)]
    dialogue = nodes[uid(6)]
    character = nodes[uid(5)]
    screenplay_scene = nodes[uid(3)]
    direct = Provenance(service).link("node", action["id"], "entity", story["shot"]["id"], "visualizes")
    scene_direct = Provenance(service).link("node", screenplay_scene["id"], "entity", story["shot"]["id"], "visualizes")
    context = Provenance(service).link("node", screenplay_scene["id"], "entity", story["scene"]["id"], "visualizes")
    body = contract_body([(direct["id"], "direct-element")])
    ObservationContracts(service).create(story["shot"]["id"], story["shot"]["revision"], body)

    anchors = [
        {"document_id": imported["document"]["id"], "version_id": imported["version"]["id"],
         "node_id": action["id"], "source_sha256": action["content_sha256"], "priority": "must", "basis": "direct"},
        {"document_id": imported["document"]["id"], "version_id": imported["version"]["id"],
         "node_id": dialogue["id"], "source_sha256": dialogue["content_sha256"], "priority": "prefer", "basis": "interpreted"},
        {"document_id": imported["document"]["id"], "version_id": imported["version"]["id"],
         "node_id": screenplay_scene["id"], "source_sha256": screenplay_scene["content_sha256"], "priority": "must", "basis": "direct"},
        {"document_id": imported["document"]["id"], "version_id": imported["version"]["id"],
         "node_id": character["id"], "source_sha256": character["content_sha256"], "priority": "unknown", "basis": "unknown"},
    ]
    report = ObservationPlanner(service).coverage(anchors)
    assert report["schema"] == "storyboarder.observation-coverage/v1"
    assert [row["state"] for row in report["request_anchors"]] == ["direct-link", "warning", "unresolved", "open-question"]
    scene_anchor = report["request_anchors"][2]
    assert scene_anchor["direct_scene_links"][0]["coverage_kind"] == "direct-scene-link"
    assert scene_anchor["scene_context_links"][0]["coverage_kind"] == "scene-context"
    assert "direct_scene_link_is_not_beat_coverage" in scene_anchor["out_of_date_reasons"]
    links = report["authored_links"]["items"]
    assert {row["edge_id"]: row["coverage_kind"] for row in links} == {
        direct["id"]: "direct-element-link", scene_direct["id"]: "direct-scene-link",
        context["id"]: "scene-context",
    }
    declaration = report["contract_declarations"]["items"][0]
    assert declaration["requirements"][0]["priority"] == "must"
    assert declaration["requirements"][0]["coverage_kinds"] == ["direct-element-link"]


def test_grouped_create_spans_scenes_reuses_exact_source_and_creates_multiple_pins(story, imported_screenplay):
    service = story["service"]
    imported, nodes = imported_screenplay
    sequence_two = service.create_entity("sequence", "Second sequence")
    scene_two = service.create_entity("scene", "Second scene", sequence_two["id"], fields={"time": "Night"})
    scene_one = story["scene"]
    action, dialogue = nodes[uid(4)], nodes[uid(6)]
    action_edge_one = exact_edge(uid(501), imported, action)
    dialogue_edge = exact_edge(uid(502), imported, dialogue)
    action_edge_two = exact_edge(uid(503), imported, action)
    with service.repo.transaction(False) as conn:
        before_frames = conn.execute("SELECT count(*) FROM frames WHERE shot_id=?", (story["shot"]["id"],)).fetchone()[0]
    before_camera = service.get("entities", story["shot"]["id"])["fields"].get("camera")

    result = ObservationPlanner(service).create_group([
        plan_item(uid(510), uid(511), scene_one, [action_edge_one, dialogue_edge],
                  title="First planned shot", fields={"action": "Mara passes the key."}),
        plan_item(uid(520), uid(521), scene_two, [action_edge_two],
                  title="Second planned shot", fields={"action": "Eli closes his hand."}),
    ])
    assert result["count"] == 2
    first, second = result["items"]
    assert (first["shot_id"], second["shot_id"]) == (uid(510), uid(520))
    assert first["contract_id"] == uid(511) and second["contract_id"] == uid(521)
    assert first["scene_id"] == scene_one["id"] and second["scene_id"] == scene_two["id"]
    assert first["shot_revision"] == second["shot_revision"] == 1
    assert first["contract"]["version"]["number"] == second["contract"]["version"]["number"] == 1
    assert set(first["edge_ids"]) == {uid(501), uid(502)} and second["edge_ids"] == [uid(503)]
    pins = first["contract"]["source_pins"]
    assert {pin["edge_id"] for pin in pins} == {uid(501), uid(502)}
    assert second["contract"]["source_pins"][0]["node_id"] == action["id"]
    assert second["contract"]["source_pins"][0]["edge_id"] == uid(503)
    assert first["contract"]["validation"]["status"] == "consistent"
    assert second["contract"]["validation"]["status"] == "consistent"
    assert service.get("entities", uid(510))["parent_id"] == scene_one["id"]
    assert service.get("entities", uid(510))["fields"]["camera"] == ""
    assert service.get("entities", uid(520))["fields"]["camera"] == ""
    with service.repo.transaction(False) as conn:
        assert conn.execute("SELECT count(*) FROM frames WHERE shot_id IN (?,?)", (uid(510), uid(520))).fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM provenance_edges WHERE id IN (?,?,?) AND retired=0",
                            (uid(501), uid(502), uid(503))).fetchone()[0] == 3
    after_camera = service.get("entities", story["shot"]["id"])["fields"].get("camera")
    assert after_camera == before_camera
    with service.repo.transaction(False) as conn:
        assert conn.execute("SELECT count(*) FROM frames WHERE shot_id=?", (story["shot"]["id"],)).fetchone()[0] == before_frames


def test_group_invalid_item_rolls_back_all_entities_edges_contracts_and_events(story, imported_screenplay):
    service = story["service"]
    imported, nodes = imported_screenplay
    valid = plan_item(uid(601), uid(602), story["scene"], [exact_edge(uid(603), imported, nodes[uid(4)])])
    invalid = plan_item(uid(604), uid(605), story["scene"], [exact_edge(uid(606), imported, nodes[uid(6)])])
    # The second contract reaches core reference validation after the batch
    # has staged all shots and exact edges, proving the outer transaction
    # rolls back every earlier row and event.
    invalid["contract"]["references"] = [uid(607)]
    with service.repo.transaction(False) as conn:
        before = {table: conn.execute(query).fetchone()[0] for table, query in {
            "shots": "SELECT count(*) FROM entities WHERE kind='shot'",
            "edges": "SELECT count(*) FROM provenance_edges",
            "contracts": "SELECT count(*) FROM observation_contracts",
            "events": "SELECT count(*) FROM events",
        }.items()}
    with pytest.raises(ObservationContractError) as error:
        ObservationPlanner(service).create_group([valid, invalid])
    assert error.value.code == "contract_reference_invalid"
    with service.repo.transaction(False) as conn:
        after = {table: conn.execute(query).fetchone()[0] for table, query in {
            "shots": "SELECT count(*) FROM entities WHERE kind='shot'",
            "edges": "SELECT count(*) FROM provenance_edges",
            "contracts": "SELECT count(*) FROM observation_contracts",
            "events": "SELECT count(*) FROM events",
        }.items()}
        assert conn.execute("SELECT count(*) FROM entities WHERE id IN (?,?)", (uid(601), uid(604))).fetchone()[0] == 0
    assert after == before


def test_group_rejects_stale_parent_revision_without_writes(story, imported_screenplay):
    service = story["service"]
    imported, nodes = imported_screenplay
    item = plan_item(uid(701), uid(702), story["scene"], [exact_edge(uid(703), imported, nodes[uid(4)])],
                     expected_revision=story["scene"]["revision"] + 1)
    with pytest.raises(Conflict) as error:
        ObservationPlanner(service).create_group([item])
    assert error.value.code == "revision_conflict"
    with service.repo.transaction(False) as conn:
        assert conn.execute("SELECT 1 FROM entities WHERE id=?", (uid(701),)).fetchone() is None
        assert conn.execute("SELECT 1 FROM provenance_edges WHERE id=?", (uid(703),)).fetchone() is None
        assert conn.execute("SELECT 1 FROM observation_contracts WHERE id=?", (uid(702),)).fetchone() is None


@pytest.mark.parametrize("mutation,code", [
    ("cross_document", "observation_source_identity_mismatch"),
    ("wrong_hash", "observation_source_hash_mismatch"),
    ("inferred", "observation_source_identity_inferred"),
])
def test_group_requires_exact_source_document_version_node_and_hash(story, imported_screenplay, mutation, code):
    service = story["service"]
    imported, nodes = imported_screenplay
    edge = exact_edge(uid(801), imported, nodes[uid(4)])
    if mutation == "cross_document":
        edge["document_id"] = uid(99999)
    elif mutation == "wrong_hash":
        edge["source_sha256"] = "f" * 64
    else:
        with service.repo.transaction() as conn:
            original = conn.execute("SELECT * FROM document_nodes WHERE id=?", (nodes[uid(4)]["id"],)).fetchone()
            inferred_id = uid(8001)
            conn.execute("""INSERT INTO document_nodes
              (id,version_id,logical_id,parent_id,node_type,position,title,text,source_pointer,payload,content_sha256,identity)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                         (inferred_id, original["version_id"], "inferred-anchor", original["parent_id"],
                          original["node_type"], 99, original["title"], original["text"], "/test/inferred",
                          original["payload"], original["content_sha256"], "inferred"))
        edge["node_id"] = inferred_id
    item = plan_item(uid(802), uid(803), story["scene"], [edge])
    with pytest.raises(ObservationPlannerError) as error:
        ObservationPlanner(service).create_group([item])
    assert error.value.code == code
    with service.repo.transaction(False) as conn:
        assert conn.execute("SELECT 1 FROM entities WHERE id=?", (uid(802),)).fetchone() is None


def test_title_and_order_changes_do_not_change_exact_anchor_coverage(story, imported_screenplay):
    service = story["service"]
    imported, nodes = imported_screenplay
    action = nodes[uid(4)]
    Provenance(service).link("node", action["id"], "entity", story["shot"]["id"], "visualizes")
    anchor = {"document_id": imported["document"]["id"], "version_id": imported["version"]["id"],
              "node_id": action["id"], "source_sha256": action["content_sha256"], "priority": "must", "basis": "direct"}
    planner = ObservationPlanner(service)
    before = planner.coverage([anchor])["request_anchors"][0]
    sibling = service.create_entity("shot", "Other angle", story["scene"]["id"])
    shot = service.update_entity(story["shot"]["id"], story["shot"]["revision"], {"title": "Retitled shot"})
    service.move(sibling["id"], sibling["revision"], 0)
    after = planner.coverage([anchor])["request_anchors"][0]
    assert before["state"] == after["state"] == "direct-link"
    assert before["node_id"] == after["node_id"] == action["id"]
    assert before["source_sha256"] == after["source_sha256"] == action["content_sha256"]
    assert shot["id"] == story["shot"]["id"]


def test_coverage_rejects_inferred_or_mismatched_request_anchor(story, imported_screenplay):
    service = story["service"]
    imported, nodes = imported_screenplay
    anchor = {"document_id": imported["document"]["id"], "version_id": imported["version"]["id"],
              "node_id": nodes[uid(4)]["id"], "source_sha256": "0" * 64, "priority": "must", "basis": "direct"}
    with pytest.raises(ObservationPlannerError) as error:
        ObservationPlanner(service).coverage([anchor])
    assert error.value.code == "observation_anchor_hash_mismatch"
    with pytest.raises(ObservationPlannerError) as error:
        ObservationPlanner(service).coverage([{**anchor, "source_sha256": nodes[uid(4)]["content_sha256"], "node_id": uid(98765)}])
    assert error.value.code == "observation_anchor_not_found"


def test_coverage_keeps_exact_old_source_version_visible_as_out_of_date(story, imported_screenplay, screenplay):
    service = story["service"]
    imported, nodes = imported_screenplay
    old_action = nodes[uid(4)]
    Provenance(service).link("node", old_action["id"], "entity", story["shot"]["id"], "visualizes")
    changed = copy.deepcopy(screenplay)
    changed["document"]["scenes"][0]["body"][0]["text"]["en"] = "Mara leaves the key on the counter."
    Documents(service).import_bytes(json.dumps(changed).encode(), "winter-v2.screenjson", "screenjson",
                                   document_id=imported["document"]["id"],
                                   revision=imported["document"]["revision"])
    anchor = {"document_id": imported["document"]["id"], "version_id": imported["version"]["id"],
              "node_id": old_action["id"], "source_sha256": old_action["content_sha256"],
              "priority": "must", "basis": "direct"}
    result = ObservationPlanner(service).coverage([anchor])["request_anchors"][0]
    assert result["state"] == "unresolved"
    assert result["version_current"] is False
    assert result["out_of_date"] is True
    assert "source_version_not_current" in result["out_of_date_reasons"]


def test_group_context_edge_is_exact_parent_scene_context(story, imported_screenplay):
    service = story["service"]
    imported, nodes = imported_screenplay
    scene_node = nodes[uid(3)]
    edge = exact_edge(uid(901), imported, scene_node, scope="scene-context")
    item = plan_item(uid(902), uid(903), story["scene"], [edge], fields={"action": "Use scene context."})
    result = ObservationPlanner(service).create_group([item])["items"][0]
    pin = result["contract"]["source_pins"][0]
    assert pin["source_scope"] == "scene-context"
    assert result["contract"]["validation"]["source_pins"][0]["coverage_kind"] == "scene-context"
    report = ObservationPlanner(service).coverage()
    link = next(row for row in report["authored_links"]["items"] if row["edge_id"] == uid(901))
    assert link["coverage_kind"] == "scene-context"
    assert uid(902) in link["inherited_shot_ids"]


def test_grouped_create_resolves_forward_and_backward_cross_shot_continuity(story, imported_screenplay):
    service = story["service"]
    imported, nodes = imported_screenplay
    first = plan_item(uid(1001), uid(1002), story["scene"],
                      [exact_edge(uid(1003), imported, nodes[uid(4)])], title="First shot")
    second = plan_item(uid(1011), uid(1012), story["scene"],
                       [exact_edge(uid(1013), imported, nodes[uid(6)])], title="Second shot")
    first["contract"]["continuity"] = [{"id": uid(1004), "related_shot_ids": [uid(1011)],
                                        "statement": "The next planned shot continues this action."}]
    second["contract"]["continuity"] = [{"id": uid(1014), "related_shot_ids": [uid(1001)],
                                         "statement": "This shot follows the first planned action."}]

    result = ObservationPlanner(service).create_group([first, second])

    assert [item["shot_id"] for item in result["items"]] == [uid(1001), uid(1011)]
    assert result["items"][0]["contract"]["contract"]["continuity"][0]["related_shot_ids"] == [uid(1011)]
    assert result["items"][1]["contract"]["contract"]["continuity"][0]["related_shot_ids"] == [uid(1001)]


def test_grouped_create_shares_one_exact_context_edge_across_same_scene_shots(story, imported_screenplay):
    service = story["service"]
    imported, nodes = imported_screenplay
    shared = exact_edge(uid(1101), imported, nodes[uid(3)], scope="scene-context")
    first = plan_item(uid(1102), uid(1103), story["scene"], [shared], title="Shared context one")
    first["source_edges"].append(shared)
    second = plan_item(uid(1104), uid(1105), story["scene"], [shared], title="Shared context two")

    result = ObservationPlanner(service).create_group([first, second])

    assert [item["edge_ids"] for item in result["items"]] == [[uid(1101)], [uid(1101)]]
    assert [item["contract"]["source_pins"][0]["edge_id"] for item in result["items"]] == [uid(1101), uid(1101)]
    with service.repo.transaction(False) as conn:
        assert conn.execute("SELECT count(*) FROM provenance_edges WHERE id=? AND retired=0", (uid(1101),)).fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM events WHERE action='provenance.linked' AND entity_id=?", (uid(1101),)).fetchone()[0] == 1


def test_grouped_create_reuses_preexisting_exact_active_context_edge(story, imported_screenplay):
    service = story["service"]
    imported, nodes = imported_screenplay
    source = nodes[uid(3)]
    existing = Provenance(service).link("node", source["id"], "entity", story["scene"]["id"], "visualizes")
    edge = exact_edge(existing["id"], imported, source, scope="scene-context")
    item = plan_item(uid(1201), uid(1202), story["scene"], [edge])
    with service.repo.transaction(False) as conn:
        before_link_events = conn.execute("SELECT count(*) FROM events WHERE action='provenance.linked'").fetchone()[0]

    result = ObservationPlanner(service).create_group([item])

    assert result["items"][0]["edge_ids"] == [existing["id"]]
    with service.repo.transaction(False) as conn:
        assert conn.execute("SELECT count(*) FROM provenance_edges WHERE id=?", (existing["id"],)).fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM events WHERE action='provenance.linked'").fetchone()[0] == before_link_events


def test_grouped_create_reuses_context_edge_after_scene_and_document_title_rename(story, imported_screenplay):
    service = story["service"]
    imported, nodes = imported_screenplay
    source = nodes[uid(3)]
    existing = Provenance(service).link("node", source["id"], "entity", story["scene"]["id"], "visualizes")
    with service.repo.transaction(False) as conn:
        before = conn.execute("SELECT source_snapshot,target_snapshot FROM provenance_edges WHERE id=?",
                              (existing["id"],)).fetchone()
        before_link_events = conn.execute("SELECT count(*) FROM events WHERE action='provenance.linked'").fetchone()[0]
    renamed_scene = service.update_entity(story["scene"]["id"], story["scene"]["revision"],
                                          {"title": "Renamed storyboard scene"})
    with service.repo.transaction() as conn:
        conn.execute("UPDATE documents SET title=?,revision=revision+1,updated_at='later' WHERE id=?",
                     ("Renamed screenplay", imported["document"]["id"]))
    item = plan_item(uid(1221), uid(1222), renamed_scene,
                     [exact_edge(existing["id"], imported, source, scope="scene-context")])

    result = ObservationPlanner(service).create_group([item])

    assert result["items"][0]["edge_ids"] == [existing["id"]]
    with service.repo.transaction(False) as conn:
        after = conn.execute("SELECT source_snapshot,target_snapshot FROM provenance_edges WHERE id=?",
                             (existing["id"],)).fetchone()
        assert tuple(after) == tuple(before)
        assert conn.execute("SELECT count(*) FROM provenance_edges WHERE id=?", (existing["id"],)).fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM events WHERE action='provenance.linked'").fetchone()[0] == before_link_events


def test_existing_context_edge_survives_scene_context_edit_and_parent_move(story, imported_screenplay):
    service = story["service"]
    imported, nodes = imported_screenplay
    source = nodes[uid(3)]
    existing = Provenance(service).link("node", source["id"], "entity", story["scene"]["id"], "visualizes")
    with service.repo.transaction(False) as conn:
        original_snapshots = tuple(conn.execute("SELECT source_snapshot,target_snapshot FROM provenance_edges WHERE id=?",
                                                (existing["id"],)).fetchone())
        link_events = conn.execute("SELECT count(*) FROM events WHERE action='provenance.linked'").fetchone()[0]
    changed = service.update_entity(story["scene"]["id"], story["scene"]["revision"],
                                    {"fields": {"summary": "Night replaces dawn."}})
    service.put_context(changed["id"], "time", "replace", "Night")
    new_sequence = service.create_entity("sequence", "Later sequence")
    moved = service.move(changed["id"], changed["revision"], 0, new_sequence["id"])
    item = plan_item(uid(1223), uid(1224), moved,
                     [exact_edge(existing["id"], imported, source, scope="scene-context")])

    result = ObservationPlanner(service).create_group([item])

    assert result["items"][0]["edge_ids"] == [existing["id"]]
    with service.repo.transaction(False) as conn:
        snapshots = tuple(conn.execute("SELECT source_snapshot,target_snapshot FROM provenance_edges WHERE id=?",
                                       (existing["id"],)).fetchone())
        assert snapshots == original_snapshots
        assert conn.execute("SELECT count(*) FROM provenance_edges WHERE id=?", (existing["id"],)).fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM events WHERE action='provenance.linked'").fetchone()[0] == link_events


def test_grouped_create_rejects_corrupt_existing_context_source_hash_snapshot(story, imported_screenplay):
    service = story["service"]
    imported, nodes = imported_screenplay
    source = nodes[uid(3)]
    existing = Provenance(service).link("node", source["id"], "entity", story["scene"]["id"], "visualizes")
    with service.repo.transaction() as conn:
        # Simulate on-disk corruption beneath the immutable-endpoint guard.
        conn.execute("DROP TRIGGER immutable_provenance_endpoints")
        saved = json.loads(conn.execute("SELECT source_snapshot FROM provenance_edges WHERE id=?",
                                        (existing["id"],)).fetchone()[0])
        saved["content_sha256"] = "0" * 64
        conn.execute("UPDATE provenance_edges SET source_snapshot=? WHERE id=?",
                     (json.dumps(saved, sort_keys=True, separators=(",", ":")), existing["id"]))
    item = plan_item(uid(1231), uid(1232), story["scene"],
                     [exact_edge(existing["id"], imported, source, scope="scene-context")])

    with pytest.raises(ObservationPlannerError) as error:
        ObservationPlanner(service).create_group([item])

    assert error.value.code == "observation_group_existing_edge_mismatch"
    with service.repo.transaction(False) as conn:
        assert conn.execute("SELECT 1 FROM entities WHERE id=?", (uid(1231),)).fetchone() is None


def test_grouped_create_rejects_archived_exact_source_when_reusing_context_edge(story, imported_screenplay):
    service = story["service"]
    imported, nodes = imported_screenplay
    source = nodes[uid(3)]
    existing = Provenance(service).link("node", source["id"], "entity", story["scene"]["id"], "visualizes")
    with service.repo.transaction(False) as conn:
        original_snapshots = tuple(conn.execute("SELECT source_snapshot,target_snapshot FROM provenance_edges WHERE id=?",
                                                (existing["id"],)).fetchone())
        link_events = conn.execute("SELECT count(*) FROM events WHERE action='provenance.linked'").fetchone()[0]
    workflows = SourceWorkflows(service)
    archived = workflows.archive(imported["document"]["id"], imported["document"]["revision"], True)
    item = plan_item(uid(1241), uid(1242), story["scene"],
                     [exact_edge(existing["id"], imported, source, scope="scene-context")])

    with pytest.raises(ObservationPlannerError) as error:
        ObservationPlanner(service).create_group([item])

    assert error.value.code == "observation_source_archived"
    with service.repo.transaction(False) as conn:
        assert conn.execute("SELECT 1 FROM entities WHERE id=?", (uid(1241),)).fetchone() is None
    workflows.archive(imported["document"]["id"], archived["revision"], False)
    result = ObservationPlanner(service).create_group([item])
    assert result["items"][0]["edge_ids"] == [existing["id"]]
    with service.repo.transaction(False) as conn:
        assert conn.execute("SELECT count(*) FROM provenance_edges WHERE id=?", (existing["id"],)).fetchone()[0] == 1
        snapshots = tuple(conn.execute("SELECT source_snapshot,target_snapshot FROM provenance_edges WHERE id=?",
                                       (existing["id"],)).fetchone())
        assert snapshots == original_snapshots
        assert conn.execute("SELECT count(*) FROM events WHERE action='provenance.linked'").fetchone()[0] == link_events


def test_grouped_create_rejects_archived_context_target_via_current_lifecycle(story, imported_screenplay):
    service = story["service"]
    imported, nodes = imported_screenplay
    source = nodes[uid(3)]
    existing = Provenance(service).link("node", source["id"], "entity", story["scene"]["id"], "visualizes")
    service.lifecycle(story["shot"]["id"], story["shot"]["revision"], "archive")
    archived_scene = service.lifecycle(story["scene"]["id"], story["scene"]["revision"], "archive")
    item = plan_item(uid(1243), uid(1244), archived_scene,
                     [exact_edge(existing["id"], imported, source, scope="scene-context")])

    with pytest.raises(ObservationPlannerError) as error:
        ObservationPlanner(service).create_group([item])

    assert error.value.code == "observation_group_invalid"
    assert "archived" in str(error.value).casefold()
    with service.repo.transaction(False) as conn:
        assert conn.execute("SELECT 1 FROM entities WHERE id=?", (uid(1243),)).fetchone() is None


def test_grouped_create_requires_the_existing_context_edge_uuid(story, imported_screenplay):
    service = story["service"]
    imported, nodes = imported_screenplay
    source = nodes[uid(3)]
    existing = Provenance(service).link("node", source["id"], "entity", story["scene"]["id"], "visualizes")
    replacement_id = uid(1251)
    edge = exact_edge(replacement_id, imported, source, scope="scene-context")
    item = plan_item(uid(1252), uid(1253), story["scene"], [edge])

    with pytest.raises(ObservationPlannerError) as error:
        ObservationPlanner(service).create_group([item])

    assert error.value.code == "observation_group_existing_edge_mismatch"
    assert error.value.details["existing_edge_id"] == existing["id"]
    with service.repo.transaction(False) as conn:
        assert conn.execute("SELECT 1 FROM entities WHERE id=?", (uid(1252),)).fetchone() is None
        assert conn.execute("SELECT 1 FROM provenance_edges WHERE id=?", (replacement_id,)).fetchone() is None


def test_grouped_create_rejects_shared_edge_id_with_different_scene_target_before_writes(story, imported_screenplay):
    service = story["service"]
    imported, nodes = imported_screenplay
    sequence = service.create_entity("sequence", "Another sequence")
    other_scene = service.create_entity("scene", "Another scene", sequence["id"])
    shared_id = uid(1301)
    source = nodes[uid(3)]
    first = plan_item(uid(1302), uid(1303), story["scene"],
                      [exact_edge(shared_id, imported, source, scope="scene-context")])
    second = plan_item(uid(1304), uid(1305), other_scene,
                       [exact_edge(shared_id, imported, source, scope="scene-context")])

    with pytest.raises(ObservationPlannerError) as error:
        ObservationPlanner(service).create_group([first, second])

    assert error.value.code == "observation_plan_edge_id_mismatch"
    with service.repo.transaction(False) as conn:
        assert conn.execute("SELECT count(*) FROM entities WHERE id IN (?,?)", (uid(1302), uid(1304))).fetchone()[0] == 0
        assert conn.execute("SELECT 1 FROM provenance_edges WHERE id=?", (shared_id,)).fetchone() is None


def test_grouped_create_rejects_existing_context_edge_for_another_scene(story, imported_screenplay):
    service = story["service"]
    imported, nodes = imported_screenplay
    sequence = service.create_entity("sequence", "Another sequence")
    other_scene = service.create_entity("scene", "Another scene", sequence["id"])
    source = nodes[uid(3)]
    existing = Provenance(service).link("node", source["id"], "entity", story["scene"]["id"], "visualizes")
    edge = exact_edge(existing["id"], imported, source, scope="scene-context")
    item = plan_item(uid(1401), uid(1402), other_scene, [edge])

    with pytest.raises(ObservationPlannerError) as error:
        ObservationPlanner(service).create_group([item])

    assert error.value.code == "observation_group_existing_edge_mismatch"
    with service.repo.transaction(False) as conn:
        assert conn.execute("SELECT 1 FROM entities WHERE id=?", (uid(1401),)).fetchone() is None
        assert conn.execute("SELECT 1 FROM observation_contracts WHERE id=?", (uid(1402),)).fetchone() is None


def test_grouped_create_rejects_corrupt_existing_context_target_identity(story, imported_screenplay):
    service = story["service"]
    imported, nodes = imported_screenplay
    source = nodes[uid(3)]
    existing = Provenance(service).link("node", source["id"], "entity", story["scene"]["id"], "visualizes")
    with service.repo.transaction() as conn:
        # Simulate on-disk corruption beneath the immutable-endpoint guard.
        conn.execute("DROP TRIGGER immutable_provenance_endpoints")
        saved = json.loads(conn.execute("SELECT target_snapshot FROM provenance_edges WHERE id=?",
                                        (existing["id"],)).fetchone()[0])
        saved["id"] = uid(1999)
        conn.execute("UPDATE provenance_edges SET target_snapshot=? WHERE id=?",
                     (json.dumps(saved, sort_keys=True, separators=(",", ":")), existing["id"]))
    edge = exact_edge(existing["id"], imported, source, scope="scene-context")
    item = plan_item(uid(1501), uid(1502), story["scene"], [edge])

    with pytest.raises(ObservationPlannerError) as error:
        ObservationPlanner(service).create_group([item])

    assert error.value.code == "observation_group_existing_edge_mismatch"
    with service.repo.transaction(False) as conn:
        assert conn.execute("SELECT 1 FROM entities WHERE id=?", (uid(1501),)).fetchone() is None


def test_grouped_create_does_not_reuse_preexisting_direct_edge(story, imported_screenplay):
    service = story["service"]
    imported, nodes = imported_screenplay
    source = nodes[uid(4)]
    existing = Provenance(service).link("node", source["id"], "entity", story["shot"]["id"], "visualizes")
    edge = exact_edge(existing["id"], imported, source, scope="direct-element")
    item = plan_item(uid(1601), uid(1602), story["scene"], [edge])

    with pytest.raises(ObservationPlannerError) as error:
        ObservationPlanner(service).create_group([item])

    assert error.value.code == "observation_group_existing_edge_mismatch"
    with service.repo.transaction(False) as conn:
        assert conn.execute("SELECT 1 FROM entities WHERE id=?", (uid(1601),)).fetchone() is None


def test_planner_artifact_cache_is_operation_local_and_checks_each_exact_node(story, imported_screenplay, monkeypatch):
    service = story["service"]
    imported, nodes = imported_screenplay
    with service.repo.transaction(False) as conn:
        artifact = conn.execute("SELECT path FROM source_artifacts WHERE id=?",
                                (imported["version"]["source_artifact_id"],)).fetchone()
    artifact_path = (service.root / artifact["path"]).resolve()
    original_read = Path.read_bytes
    original_sha256 = hashlib.sha256
    raw_artifact = original_read(artifact_path)
    changed_artifact = raw_artifact + b" "
    changed = [False]
    file_reads = []
    artifact_hashes = []
    artifact_parses = []
    real_parse = contract_module.parse

    def read_bytes(path):
        if path.resolve() == artifact_path:
            file_reads.append(path)
            return changed_artifact if changed[0] else raw_artifact
        return original_read(path)

    def sha256(data=b"", *args, **kwargs):
        caller = sys._getframe(1)
        if caller.f_code.co_name == "_artifact_check" and caller.f_globals.get("__name__") == contract_module.__name__:
            artifact_hashes.append(data)
        return original_sha256(data, *args, **kwargs)

    def parse(raw, format):
        if format == "screenjson":
            artifact_parses.append(raw)
        return real_parse(raw, format)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    monkeypatch.setattr(contract_module.hashlib, "sha256", sha256)
    monkeypatch.setattr(contract_module, "parse", parse)
    anchors = [{"document_id": imported["document"]["id"], "version_id": imported["version"]["id"],
                "node_id": nodes[logical_id]["id"], "source_sha256": nodes[logical_id]["content_sha256"],
                "priority": "must", "basis": "direct"} for logical_id in (uid(4), uid(6))]

    coverage = ObservationPlanner(service).coverage(anchors)

    assert [row["node_id"] for row in coverage["request_anchors"]] == [nodes[uid(4)]["id"], nodes[uid(6)]["id"]]
    assert [row["source_sha256"] for row in coverage["request_anchors"]] == [nodes[uid(4)]["content_sha256"], nodes[uid(6)]["content_sha256"]]
    assert len(file_reads) == len(artifact_hashes) == len(artifact_parses) == 1

    direct_edges = [exact_edge(uid(1701), imported, nodes[uid(4)]),
                    exact_edge(uid(1702), imported, nodes[uid(6)])]
    group = [plan_item(uid(1703), uid(1704), story["scene"], [direct_edges[0]]),
             plan_item(uid(1705), uid(1706), story["scene"], [direct_edges[1]])]
    created = ObservationPlanner(service).create_group(group)
    assert created["count"] == 2
    assert {pin["node_id"] for item in created["items"]
            for pin in item["contract"]["source_pins"]} == {nodes[uid(4)]["id"], nodes[uid(6)]["id"]}
    assert len(file_reads) == len(artifact_hashes) == len(artifact_parses) == 2

    changed[0] = True
    stale = ObservationPlanner(service).coverage(anchors)
    assert all("source_artifact_unavailable_or_changed" in row["out_of_date_reasons"]
               for row in stale["request_anchors"])
    assert len(file_reads) == len(artifact_hashes) == 3
    assert len(artifact_parses) == 2


def test_grouped_create_edge_reference_budget_accepts_512_and_rejects_513(story, imported_screenplay):
    service = story["service"]
    imported, nodes = imported_screenplay
    edge = exact_edge(uid(1801), imported, nodes[uid(3)], scope="scene-context")
    items = []
    for index in range(4):
        item = plan_item(uid(1810 + index), uid(1820 + index), story["scene"], [edge])
        item["source_edges"] = [edge] * 128
        items.append(item)

    result = ObservationPlanner(service).create_group(items)

    assert result["count"] == 4
    assert all(item["edge_ids"] == [edge["edge_id"]] for item in result["items"])
    assert len({item["edge_ids"][0] for item in result["items"]}) == 1

    over_limit = []
    for index, count in enumerate((128, 128, 128, 128, 1)):
        item = plan_item(uid(1830 + index), uid(1840 + index), story["scene"], [edge])
        item["source_edges"] = [edge] * count
        over_limit.append(item)
    with pytest.raises(ObservationPlannerError) as error:
        ObservationPlanner(service).create_group(over_limit)
    assert error.value.code == "observation_plan_too_many_edge_references"
    assert error.value.details == {"limit": 512, "provided": 513}
    with service.repo.transaction(False) as conn:
        assert conn.execute("SELECT count(*) FROM entities WHERE id IN (?,?,?,?,?)",
                            tuple(uid(1830 + index) for index in range(5))).fetchone()[0] == 0
