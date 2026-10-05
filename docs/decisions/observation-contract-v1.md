# ADR: Versioned observation contracts for storyboard shots

**Status:** Accepted for v1 domain and focused authoring flows. A broader client redesign remains unselected.

## Context

Shots have mutable fields; screenplay versions and provenance edges have stable identities and history. Embedding contracts in shot fields couples routine edits to review history. A second link model duplicates the many-to-many `visualizes` relationship. Titles and order cannot restore identity reliably.

## Decision

A shot may own one contract header keyed by its stable ID. Create, revise and explicit rebase append hashed immutable versions. Operations use revision compare-and-swap. Ordinary revise preserves exact pins; explicit rebase offers a basis preview and requires its reviewed hash.

Versions pin existing provenance edge IDs and exact screenplay document/version/node IDs and hashes. A shot can pin several edges; one source node can link to several shots. Direct shot links remain distinct from parent-scene context. Requirements attach to source edges and declare `must`, `prefer` or `unknown` with an authored basis.

Validation checks authored action, dialogue, duration, framing, camera direction, continuity and constraints, plus effective scene, sequence, location and asset context. It checks IDs, hashes, lifecycle and revision tokens; titles/order do not establish identity. Uncited shot and contract notes are outside the v1 basis; notes on referenced library or context records remain captured where modeled. Results report consistent, conflict or unresolved, never semantic, image, camera or physical verification.

Portable history uses a separate project-level observation-plan sidecar. Deterministic export and dry-run import expose classifications and losses; apply requires explicit reconciliation and target-state checks. Exact restore uses a scoped internal gate; ordinary authoring remains lifecycle-guarded. Migrations 005/006 add version/pin and history-retention rules without changing earlier migrations.

## Alternatives rejected

Mutable fields erase review history; a duplicate link table duplicates provenance; title/order rebinding guesses identity. A full Concept03-style workspace would fold an unselected redesign into this change.

## Consequences

History survives shot edits and source imports, but stale pins need explicit review. Existing scene bundles and ScreenJSON stay unchanged. CLI, API, TUI and client use shared services and stable errors; downstream visual and physical verification remains with consumers.
