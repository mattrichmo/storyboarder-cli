# Storyboarder v2 implementation ledger

Repository: GitHub `mattrichmo/storyboarder`. The source-document and provenance
checkpoint is now integrated into `main`; its original baseline was
`7f58e26b25f52d6c6b6fa569730bd56a5ccb2365`.

The previously reported v2 source was not retained. This is a new implementation. Historical screenshots and test reports are not evidence for these changes.

## Preserved checkpoints

- `60628590d89a30e5c98dc134ac5522a260d5e6bb`: read-only CI and exact-source archives.
- `ace3f85b988827c7c72a48af695ebc5c4956397b`: shared service/command decomposition and audited correctness fixes; 129 local tests passed. Remote Linux and macOS application tests passed. Windows exposed unclosed SQLite backup connections; macOS packaging needed an explicit setuptools development dependency.
- Current source checkpoint: immutable source artifacts, documents, versions and nodes; independently validated ScreenJSON core/OTIO JSON adapters; provenance, pinned annotations, coverage and impact; generation source/media pins; shared CLI/API workflows; source-inclusive backup/restore; Windows connection-close and macOS packaging fixes.

## Fresh verification

Verified on October 3, 2026 at integrated commit `7a7554a`:

- Local macOS / Python 3.14.3: `python -m pytest -q` — **168 passed**. This includes real subprocess CLI commands, FastAPI requests, genuine schema 1/2 upgrades, concurrent source edits, JSON round trips, pinned-generation lineage and backup connection closure.
- The frontend rebuilt with the pinned TypeScript 5.8.3 compiler; **10 canvas geometry tests passed**. The refreshed compiled client is committed.
- Wheel and source-distribution packaging passed locally.
- [GitHub verification](https://github.com/mattrichmo/storyboarder/actions/runs/37162789763) passed on Linux / Python 3.11, macOS / Python 3.12, and Windows / Python 3.13, including frontend builds, Python tests, geometry tests and packaging.

The older screenshots and browser acceptance reports still describe the original
authoring interface. They do not verify unfinished source-document interfaces.

## Remaining work

The current React and TUI are still the original authoring interfaces; their new source workspaces, lazy trees, visual provenance and draft comparison interfaces are not finished. Document structure creation/move/removal, broad legacy/FDX/Fountain/PDF adapters, full old-UI query migration, provenance-complete storyboard handoffs and final release/install checks remain outstanding. This checkpoint is not the completed v2 product and should first be used with backed-up disposable project copies.

## Invariants

Existing storyboard IDs and released migration 001/002 bytes are preserved. Screenplays and edits are separate documents. Versions/nodes/source artifacts are immutable; row revisions are concurrency tokens. Provenance is pinned to node versions and validated endpoints. Canonical assignments/frames/job outputs are projected rather than duplicated. No import executes embedded content or fetches media URLs. New document navigation is paginated; the old metadata snapshot remains a compatibility boundary. Missing links do not prove missing footage.

See FORMATS.md for explicit compatibility limits. Migrations 003/004 are append-only after this checkpoint is published. Back up with the old app before first opening an existing project with schema 4.
