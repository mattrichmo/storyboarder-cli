# Implemented milestone map

This maps the supplied production plan to shipped implementation, not another roadmap.

| Milestone | Implemented source and acceptance |
|---|---|
| 0 — Foundations | Installable setuptools package, MIT/license notices, explicit formats/limits/versions, design brief, typed domain errors, checksum migrations and documentation |
| 1 — Shared lifecycle | Project/Workspace services, discovery/manifests, isolated SQLite projects, registration/switching, doctor, CLI and TUI dashboards |
| 2 — Loopback React | FastAPI launch grants/token/origin boundary, bundled static app, workspace create/open/switch, port/browser/shutdown handling |
| 3 — References | Staging, still-image hashing/deduplication, intake review, tags/aliases, memberships/primary image, merge, typed links; CLI/TUI/browser workflows |
| 4 — Story authoring | Stable ordered hierarchy, typed fields, scalar/block context provenance, exact shot media, separate candidate frames/states, editable outlines/forms |
| 5 — Graph | Three in-house DOM/SVG views, filters, keyboard links, pointer/keyboard positions, edge/reorder controls, deterministic tidy, revisioned named layouts, reference-aware removal |
| 6 — Delivery | Deterministic composition, JSON/Markdown portable bundles, exact relative references/provenance, HTML/PDF/PNG boards and review previews |
| 7 — Reliability | Backup/restore/relocation, checksums/integrity/cache recovery, concurrent revision checks, scoped uploads, keyboard/mobile review, packaged frontend and release tools |
| 8 — Script seam | User-scoped explicit registration, versioned requests/results, bounded subprocesses, logs, cancel/retry race protection, hashes, pending review and idempotent import |

CLI and TUI call application services directly; React goes through the local API.
No interface writes SQLite from UI code. Canvas movement is saved presentation state,
not implicit story relations. Exact shot-selected media is tested through export and
membership changes. Immutable IDs persist through reorder, rename and project relocation.

Functional verification is recorded in TEST_REPORT, including limitations of the
browser environment and unexecuted platform CI. The sample media and adapter slate are
clearly fictional test material. No live OpenAI/provider integration is claimed.

Deferred items remain those in the supplied plan: collaboration, cloud hosting/sync,
accounts, graphical desktop shell, drawing, automatic recognition/tagging, script
breakdown and bundled provider-specific generators. These are not stub screens
masquerading as implemented authoring features.
