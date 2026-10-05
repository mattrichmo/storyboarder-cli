# Observation planner reports and grouped authoring

`ObservationPlanner(service)` provides two application operations for exact-source planning:

```python
from storyboarder.application.observation_planner import ObservationPlanner

planner = ObservationPlanner(service)
report = planner.coverage(anchors=[...])
created = planner.create_group([...])
```

The shared command catalog exposes these as agent-only JSON-safe `observation.coverage`
and `observation.create-group` commands. Both are available through the CLI and JSON API;
neither is browser-visible. The TUI adds a focused one-shot shot-and-contract authoring
flow, rather than a wizard for arbitrary multi-shot groups.

## Coverage report

`coverage(anchors=None, limit=500, offset=0)` reports the screenplay `visualizes` edges already authored to storyboard scenes and shots and the current versions of shot contracts. It does not search unlinked imported screenplay nodes. Link records identify exact document, immutable version, node, source hash, edge lifecycle, target kind, and snapshot integrity. A storyboard scene target is reported as scene context and lists its child shots; an edge from a screenplay scene directly to a shot is reported as `direct-scene-link`, never beat coverage. Contract declarations retain requirement priority and basis and show their exact edge mappings and validation state.

Optional request-scoped anchors must provide all of:

```json
{
  "document_id": "00000000-0000-0000-0000-000000000101",
  "version_id": "00000000-0000-0000-0000-000000000102",
  "node_id": "00000000-0000-0000-0000-000000000103",
  "source_sha256": "<lowercase SHA-256 of that exact node>",
  "priority": "must",
  "basis": "direct"
}
```

The report verifies the supplied document/version/node identity, explicit source identity, node hash, and backing artifact. It never substitutes another version. A fresh direct element-to-shot edge is reported as a structural direct link; a missing direct link leaves `must` unresolved, `prefer` as a warning, and `unknown` open. Scene-context and direct screenplay-scene links remain separate and cannot satisfy a direct element anchor. An old exact source version, retired edge, archived target, unavailable artifact, or unknown basis remains visible as out of date or unresolved. No status claims that an image communicates the authored statement.

Request-scoped anchors last only for that report call. Persistent requirements belong in each shot's immutable observation-contract version. The report has no inferred anchor set, completion percentage, semantic match, or image/render verification.

## Atomic grouped authoring

`create_group(items)` accepts between one and fifty item objects with at most 512 total
source-edge references in a request. Each item supplies caller UUIDs for `shot_id`,
`contract_id`, and every `source_edges[].edge_id`, plus `scene_id`,
`expected_scene_revision`, title, optional description/shot fields, exact `source_edges`,
and a complete v1 `contract` body. Every source edge must include exact `document_id`,
`version_id`, `node_id`, `source_sha256`, and `source_scope`. A `direct-element` edge
targets the new shot; `scene-context` targets its existing parent scene. The contract
must pin exactly the source edges in its item. At the command boundary the JSON shape is
`{"request":{"items":[...]}}`; coverage takes `{"request":{"anchors":[...]}}`.

The planner validates the request shape, caller UUIDs, shot fields, and canonical contract bodies before opening the write. Parent-scene revision checks, exact source identities and hashes, backing artifacts, active endpoint/archive state, edge semantics, contract references, and all writes then run inside one SQLite write transaction. Each item creates its shot, exact `visualizes` edges, stable contract header, and first immutable version. Any invalid item rolls back every item in the group. Returned records include caller IDs and generated first-version IDs/revisions. Ordering positions are allocated only after validation and are not source identity. The operation creates no camera, frame, approval, or render state.

Typical use:

```python
result = planner.create_group([
    {
        "shot_id": "00000000-0000-0000-0000-000000000201",
        "contract_id": "00000000-0000-0000-0000-000000000202",
        "scene_id": "00000000-0000-0000-0000-000000000203",
        "expected_scene_revision": 1,
        "title": "Key changes hands",
        "fields": {"action": "Mara gives Eli the key."},
        "source_edges": [{
            "edge_id": "00000000-0000-0000-0000-000000000204",
            "document_id": "00000000-0000-0000-0000-000000000101",
            "version_id": "00000000-0000-0000-0000-000000000102",
            "node_id": "00000000-0000-0000-0000-000000000103",
            "source_sha256": "<lowercase SHA-256 of that exact node>",
            "source_scope": "direct-element"
        }],
        "contract": {"schema": "storyboarder.observation-contract/v1", "source_pins": [
            {"edge_id": "00000000-0000-0000-0000-000000000204", "source_scope": "direct-element"}
        ], "script_intents": [], "requirements": [], "references": [], "continuity": [], "notes": ""}
    }
])
```

The terminal flow lets a person create one shot with one or more exact screenplay links
and its first purpose/requirements contract in one transaction. Its document, immutable
version, node, node hash, priority, basis, and scene revision are explicit. Multiple shots
can independently select the same exact beat. The terminal page preserves existing IDs,
hidden contract data, and pins when a person edits one field. Arbitrary grouped planning
remains an advanced CLI/API request. The planner does not expose import/export or batch
updates to existing shots. Exact-history transfer of a scene-context pin authored before
a shot moved remains a separate core/schema concern; ordinary grouped authoring always
targets the current parent scene.
