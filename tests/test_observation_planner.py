"""Exact source coverage and atomic multi-shot authoring."""
import copy
import json
import uuid

import pytest

from storyboarder.application.documents import Documents
from storyboarder.application.observation_contracts import CONTRACT_SCHEMA, ObservationContractError, ObservationContracts
from storyboarder.application.observation_planner import (
    ObservationPlanner,
    ObservationPlannerError,
)
from storyboarder.application.provenance import Provenance
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
    # The second item reaches core reference validation only after its shot
    # and edge have been inserted, proving the outer transaction rolls back
    # writes from both items rather than just rejecting a preflight error.
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
