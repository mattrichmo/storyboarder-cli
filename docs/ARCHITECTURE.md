# Architecture

```text
CLI argument parser ─┐
TUI pages/forms ─────┼─> explicit application command catalog / Service
React pages/canvas ─┘       ↑
        versioned loopback API (write token + origin/host boundary)
                            ↓
  domain validation → repositories / short SQLite transactions
                            ↘ managed media → composer/export → external job review
```

The frontend never imports a database library. CLI/TUI invoke the same service
operations as HTTP. The command catalog is a concrete allowlist with labelled fields,
choices, source selectors, read-only/destructive flags and browser eligibility. It
is not arbitrary Python method dispatch, SQL, or a general filesystem API.

## Source map

| Directory | Responsibility |
|---|---|
| `src/storyboarder/cli/` | Parser, JSON/human output, installed entry point, process launch |
| `tui/` | 12 pages, focus/navigation, searchable records, command forms, thumbnails/viewer |
| `api/` | Versioned routes, launch-scoped project grant, request schemas/body limits |
| `application/projects.py` | Portable project and workspace lifecycle/discovery |
| `application/service.py` | Asset, intake, story, context, frame and layout workflows |
| `application/commands.py` | Shared command/form vocabulary and dispatch |
| `application/recovery.py` | Doctor, consistent backup and safe new-folder restore |
| `domain/` | Typed authored fields, relationships, roles, IDs and errors |
| `storage/` | Parameterized SQLite, JSON decoding, revisions, events, migrations |
| `media/` | Safe paths, staging, decoding, hashing and rebuildable thumbnails |
| `rendering/` | Explicit context composition, Markdown/JSON and presentation boards |
| `automation/` | Trusted registry, requests, execution control, validation and approval |
| `static/` | Installed frontend and licenses; no Node runtime required |
| `clients/web/src/canvas/` | DOM/SVG rendering, viewport math, layout and keyboard/pointer behavior |
| `clients/web/src/components/` | Labelled forms, inspector, modal focus management |
| `clients/web/src/pages/` | Workspace, intake, library, outline, guide, editor, frames, delivery/settings |

The React source lives under `clients/web`. The TUI stays at `src/storyboarder/tui`
because it is part of the installable Python package and imports the same application
services directly; putting it in a separate source root would require a packaging and
entry-point redesign without improving runtime boundaries.

## Database

Migration 001 creates entities, media, intake, asset-media membership, links,
assignments, named context blocks, frames, layouts and event history. Tags, entity-tag memberships and aliases have dedicated tables; API snapshots
present tags/aliases as plain arrays on asset records. They remain simple text, not
a custom-field framework. Migration 002 adds jobs and uniquely keyed
job-output approvals without changing asset/scene semantics. The migration ledger
stores checksums, names and application times. `PRAGMA user_version` and the ledger
must agree. Released migration files are append-only.

Each service call opens/closes its own connection. Writers use BEGIN IMMEDIATE and
SQLite's busy timeout; stale revisions are checked inside the write transaction.
Multi-record reorders, merge and frame preference operations are atomic. Read
composition uses a consistent database snapshot. An export is not an implicit edit.

## Filesystem commit strategy

Managed import first validates/stages bytes, then uses a unique final media path and
registers canonical metadata in a write transaction. Rollback cleans staged/new files.
A crash can leave a detectable orphan but must not overwrite an approved input.
Existing deduplicated media is rehashed before reuse. Doctor reports orphan/staging
files rather than guessing whether they should be destroyed.

Exports stage a complete package, hash every file and commit under a per-export file
lock. Existing matching packages are verified and reused; modified packages are not
overwritten silently. Backups use SQLite's backup API with a reserved writer boundary
while gathering immutable managed inputs. Restore verifies manifest hashes before
making a new destination visible.

## Browser state

Project/record data comes from HTTP. Selection, in-progress forms and unsaved canvas
arrangement are UI state. Named positions, collapsed/hidden IDs, filters and viewport
are saved only through layout services. Parent/order edges derive from entity records;
semantic edges derive from links and assignments. Dragging a card does not edit story
order. Search/filter scopes cap canvas views; library cards paginate in groups of 48.

A lightweight event-token check detects another interface's changes and offers Reload
without repeatedly downloading the full project snapshot. It does not replace an
in-progress modal's draft. A write conflict independently protects against missed
notifications. There is no multi-user collaboration engine.

## Limits

The local UI loads a project metadata snapshot, not all original image bytes.
Canvas views are capped at 250 nodes (HTTP up to 500); refine by scene, sequence,
type, tag or search. Thumbnails are lazy/rebuildable and originals served on demand.
This is a bounded single-creator workspace, not a claim of unlimited graph scale.
