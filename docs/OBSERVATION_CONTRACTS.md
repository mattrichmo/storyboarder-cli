# Observation contracts v1

An observation contract records the authored purpose and communication requirements for one storyboard shot. It lives beside the mutable shot fields, so a later contract edit retains its earlier versions. A shot keeps one stable contract ID; each create, revise, or explicit rebase appends an immutable version.

Contracts use the `storyboarder.observation-contract/v1` JSON schema. A body has `source_pins`, `script_intents`, `requirements`, `references`, `continuity`, and `notes`. Every intent and requirement has a stable UUID. A source pin names an existing `visualizes` provenance edge and declares either `direct-element` (the edge targets this shot) or `scene-context` (the edge targets its parent storyboard scene). The saved pin also captures the screenplay document, immutable version and node IDs, hashes, edge snapshots, and source snapshot. The same screenplay node may link to multiple shots through separate exact provenance edges; one contract version may pin several source nodes.

`script_intents` record purpose and communication for a declared source edge. `requirements` have an explicit `priority` (`must`, `prefer`, or `unknown`) and `basis` (`direct`, `interpreted`, or `unknown`), plus exact `source_edge_ids`. A `must` or `prefer` uses a `statement`; an `unknown` uses a `topic` and remains open. These labels describe authored intent. They do not certify that an image satisfies it.

For example, the `contract` value in a create payload can look like this:

```json
{
  "schema": "storyboarder.observation-contract/v1",
  "source_pins": [
    {"edge_id": "00000000-0000-0000-0000-000000000101", "source_scope": "direct-element"}
  ],
  "script_intents": [
    {
      "id": "00000000-0000-0000-0000-000000000201",
      "source_edge_id": "00000000-0000-0000-0000-000000000101",
      "source_scope": "direct-element",
      "purpose": "insert",
      "communication": "The key is visible in Mara's hand.",
      "basis": "direct"
    }
  ],
  "requirements": [
    {
      "id": "00000000-0000-0000-0000-000000000301",
      "priority": "must",
      "basis": "direct",
      "source_edge_ids": ["00000000-0000-0000-0000-000000000101"],
      "statement": "Show the key changing hands."
    }
  ],
  "references": [],
  "continuity": [],
  "notes": ""
}
```

Create requires the caller's last-read `expected_shot_revision`; it also fails if that shot already owns a contract. Revise and rebase require the current contract-header `revision`. Ordinary revise keeps the exact edge ID and scope set and is rejected with `contract_rebase_required` if a pin or relevant authored basis is stale. Rebase takes a complete replacement body, including the caller-selected exact edges, and appends a version without changing earlier history. It never searches for or selects a latest source import automatically.

`review_rebase` returns `saved_basis_sha256` and `current_basis_sha256` as raw hashes of the saved and current modeled basis. Its `expected_basis_sha256` is an opaque review token: a hash of the canonical normalized proposed contract together with the current modeled basis. Submit that token and the same proposal to `rebase`; changing either the proposal or relevant authored basis after review returns `contract_basis_changed` without writing. Refresh the review to obtain a token for the new proposal or basis.

The deterministic basis includes shot action, dialogue, duration, framing, camera direction, continuity, and constraints; effective project, sequence, scene, and location context; and continuity-referenced shots. Location, reference, and assigned assets contribute stable IDs, descriptions, modeled fields, notes, tags, aliases, linked media hashes, and archived state. Assignment IDs, roles, asset IDs, and media IDs/hashes are also captured. Cosmetic titles, shot numbers, story order, uncited shot or contract notes, frames, and layout state are excluded. Validation exposes the basis registry and reports changes as unresolved until explicitly rebased.

`validate` returns `consistent`, `conflict`, or `unresolved`. It checks declared IDs and relationships, active source edges, explicit source identity, saved hashes and snapshots, current source content, references, and basis changes. A direct screenplay scene-to-shot edge is reported as a direct scene link, not beat coverage; a parent-scene edge is reported as scene context. Validation does not infer coverage from unpinned edges, interpret prose, score a shot, or verify camera feasibility, physical correctness, images, or renders.

The shared service is available through JSON CLI commands `observation.create`, `observation.show`, `observation.list`, `observation.revise`, `observation.validate`, `observation.rebase-preview`, `observation.rebase`, and `observation.diff`. The create payload has `shot_id`, `expected_shot_revision`, and `contract`; revise uses `contract_id`, `revision`, and `contract`; rebase also requires the `expected_basis_sha256` token returned by `observation.rebase-preview` for that exact proposal. The same commands are available at `/api/v1/projects/{project_id}/commands/{command}`. The `commands` property of `/api/v1/meta` remains the browser-visible catalog; its separate `api_commands` property is the explicit JSON API-safe catalog and includes these agent-facing commands without exposing legacy filesystem actions.

Contract errors use stable machine codes and the same error object through JSON CLI and API. The read-only project doctor checks contract version chains, canonical JSON and hashes, sealed pin membership, and header pointers. Contract history is intentionally excluded from generic client state snapshots. Existing `scene.json`, ScreenJSON, OTIO, and bundle consumers are unchanged.

The exact-anchor report and grouped shot/source authoring are implemented as the application-level `ObservationPlanner` described in [OBSERVATION_PLANNER.md](OBSERVATION_PLANNER.md). `observation.coverage` and `observation.create-group` are registered JSON-safe CLI/API commands; the TUI offers focused single-shot authoring and contract creation for an existing linked shot. Coverage accepts only caller-supplied request-scoped anchors pinned by exact document, immutable version, node, and source hash; it does not scan every imported beat or infer IDs. A missing direct edge leaves `must` unresolved, `prefer` as a warning, and `unknown` open; a scene-context edge cannot satisfy a direct element anchor. Persistent per-shot requirements remain in the contract. Grouped authoring accepts caller UUIDs and expected parent-scene revisions and creates multiple shots, exact source edges, and initial contracts in one transaction; one invalid item rolls back the batch.

Exact history portability uses the project-level observation-plan sidecar in [OBSERVATION_TRANSFER.md](OBSERVATION_TRANSFER.md). The registered `observation.plan-export`, `observation.plan-import-preview`, and `observation.plan-import-apply` commands accept JSON objects through the CLI and JSON API; preview performs a read-only dry run, while apply requires its unchanged manifest-bound preview receipt and explicit choices for conflicts. The repository's internal, connection-scoped restore gate preserves old pins to retired edges or archived endpoints only when their exact identities, hashes, and snapshots match; the gate closes before commit or rollback. Ordinary create/revise/rebase remain lifecycle-guarded.
