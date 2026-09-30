# Product contract — 1.0

This document records implemented decisions, not a future build plan.

## Formats and identities

App 1.0.0; project/workspace TOML format 1; SQLite schema 2; API `/api/v1`;
scene export `storyboarder.export/v1`; script request `storyboarder.job/v1`;
script result `storyboarder.result/v1`; trusted registry `storyboarder.scripts/v1`.
UUID4 strings are immutable record IDs. Renames/reorders do not replace IDs.
Titles are non-empty, at most 240 characters. Workspace folder slugs are 1–64
lowercase ASCII letters/numbers/hyphens and start with a letter or number.

SQLite is the canonical store. Project metadata also has a database entity; the
manifest's title is a rebuildable navigator hint. A workspace contains only paths,
IDs, and recent selection. Project creation refuses a nonempty destination. A missing
project database is an error, not permission to silently create a replacement.

## Supported media

Single still JPEG, PNG, WebP, TIFF and BMP images, identified by decoded content.
Up to 50 MiB and 50 megapixels per image; animated/multi-page images are rejected.
SVG, HEIC, RAW, GIF, videos, audio, PDFs and other unsupported formats are rejected
with a per-item reason. Convert an unsupported file externally first. Folder scans
are non-recursive unless explicitly requested; each scan is bounded to 2,000 files.

Managed files are copied, decoded/validated, hashed with SHA-256 and stored under
relative paths. The original name and source location are retained as metadata.
Intake is pending/accepted/discarded. A duplicate means the exact same SHA-256;
there is no perceptual similarity classifier. Discarding intake is non-destructive
to shared managed media.

## Records and lifecycles

Assets: character, location, prop, reference; aliases, plain tags, multiple media,
primary image, typed connections. Ordered hierarchy: project → sequence → scene →
shot. Entities have title, description, authored fields, revision, timestamps and
archive state. Shot fields include number, action, dialogue, camera, framing,
duration, continuity, constraints and notes. Location and time are inherited defaults.

Assignments retain a role and optional exact media ID. Allowed roles: subject,
setting-reference, costume, prop, reference. Exact images must belong to that asset.
An unspecified image stays unspecified; exports do not silently substitute the asset's
current primary image. Frame records are separate: per-shot candidate version,
media ID, notes, provenance and draft/selected/approved/archived state. Only one
preferred selected/approved frame exists per shot. Approval must be explicitly undone
before a conflicting preferred candidate can replace it.

Deleting a referenced entity is refused. Inspect usage, remove/reassign its references,
or archive it instead. Canvas hiding only changes the saved layout. Archiving is
reversible; it does not silently sever the canonical relationships or delete media.

## Context and concurrency

Context scopes are project, sequence, scene and shot. Non-empty scalar location,
time, framing and camera values override ancestors. Blank scalars inherit. Named
text blocks append by default, replace a same-key inherited direction when requested,
or explicitly exclude it. Composer output contains the scope chain and provenance
for each resolved value; no hidden prompt concatenation is used.

WAL mode, short transactions, foreign keys and a 10-second busy timeout support
simultaneous local access. Updates/removals require the last-read record revision.
Stale writes return current data in a conflict; forms retain drafts until explicitly
reloaded. List creation assigns ordering transactionally. Stored layout revisions
are checked independently of canonical story revisions.

## Chosen stack and packaging

Python 3.11+; standard SQLite3; Pydantic typed validation; FastAPI/Uvicorn loopback
server; prompt_toolkit full-screen TUI; Rich CLI formatting; Pillow still-image
handling; ReportLab PDF rendering; React/TypeScript and an internal bundler/canvas.
No graph-editor dependency, CDN, cloud database, or live provider SDK is required.
Setuptools packages the compiled static app inside the Python wheel. New code is MIT.
