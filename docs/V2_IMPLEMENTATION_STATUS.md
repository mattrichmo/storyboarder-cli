# Storyboarder v2 implementation ledger

Source authority: GitHub `mattrichmo/storyboarder` at `7f58e26b25f52d6c6b6fa569730bd56a5ccb2365`.
Working branch: `feat/provenance-workspace-v2`. The default branch is not modified.
Plan: approved conversation scope; the complete request is retained in the working source.

The previously reported v2 source was not retained. This is a new implementation, not a recovery of that source. Historical screenshots and test reports are not current verification evidence.

## Checkpoints

- Remote source preservation and CI: committed in `60628590d89a30e5c98dc134ac5522a260d5e6bb`.
- Current source archive: downloaded from that commit's Actions artifact and SHA-256 verified.
- Correctness hardening: 11 added regression cases; archived inclusion, JSON parser errors, wrong-domain updates, malformed fields, null defaults and edited ZIP protection verified.
- Service and command decomposition: implemented behind backwards-compatible imports; full suite 129 passed. Bounded queries remain pending.
- Versioned documents and format adapters: pending.
- Provenance, coverage, impact and generation: pending.
- CLI/API workflows: pending.
- React and TUI document workspaces: pending.
- Exports/recovery/installed-package verification: pending.

## Rulings

- Preserve existing storyboard IDs and released migration bytes; documents are a separate domain.
- Source documents have immutable versions. Row revisions remain concurrency tokens, not screenplay drafts.
- Imported identities are document-scoped; repeated imports must not create artificial diffs or duplicate versions.
- Provenance is pinned to source node versions. A new screenplay draft never silently rewrites boards or approvals.
- Existing assignments/frames/job outputs are canonical relations; graph queries project them rather than duplicate them.
- Input adapters retain original bytes and structured payloads, with explicit unsupported-feature errors and no network access during import.
- New browser/TUI document reads are bounded. Full snapshots remain a compatibility/export boundary, not the document navigation API.
- Tests that assert obsolete copy are updated to the current intended UI; functional assertions are retained and expanded.

## Fresh local verification

Linux / Python 3.13.5: `PYTHONPATH=/mnt/data/storyboarder-repo/src python -m pytest -q` — 129 passed in 13.85 seconds. Node 22.16.0 / TypeScript 5.8.3: typecheck passed and 10 geometry tests passed. Remote platform verification is not yet green; the first CI runs exposed the baseline defects.
