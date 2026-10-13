# Production expansion — implementation status

This patch implements a substantial connected-model layer and a usable dedicated visual
workspace. It is **not a claim that every advanced feature in the 18-area product direction
is finished**. The distinction below is intentional: a persisted schema, a working rule,
a guided interaction and a physical simulation are different deliverables.

| Area from the product direction | Implemented in this patch | Remaining depth / boundaries |
|---|---|---|
| 1. Production/project structure | Typed project graph; production types; separate stable IDs/labels and narrative/shoot/editorial ordering; units/rate/aspect/frame defaults; exact selections and alternatives. | One connected graph per portable project, not a multi-production studio/scheduling system. |
| 2. Scripts/revisions | Structured scene/action/dialogue source, stable source identities, original bytes/hashes, positions, CLI amendment/import, conservative reconciliation, structured revision diff; unscripted objectives. | Core Fountain/ScreenJSON/structured JSON only; full Fountain grammar, FDX and PDF screenplay parsing remain. No automatic repair of ambiguous source identities. |
| 3. Script-to-production mapping | Many-to-many exact scene/passage fragments; shot coverage; omission/defer/unfilmed reasons; content-aware impact; reviewable structural repinning. | Reconciliation does not creatively rewrite blocking or shot intent. A caller must author changed downstream content. |
| 4. Scene definitions/breakdowns | Purpose, story/actual location, interior/exterior, story time, shoot date, conditions, requirements, constraints, objectives, shared action links, readiness/responsibility. | Complex scheduling, casting logistics and detailed departmental breakdown forms remain outside this layer. |
| 5. Locations/3D sets | Reusable versioned proxy geometry, marks/zones, coordinate/scale conventions, floor-plan media/calibration data, scene placements, dimension-quality flags and dependency staleness. | No automatic floor-plan tracing, full mesh pipeline, calibrated photogrammetry, or dedicated floor-plan calibration wizard. Richer shapes are proxies, not accurate architectural simulation. |
| 6. Characters/performers/assets | Typed asset library; separate performer/character; instances, dimensions, facing/eyeline; props/state/ownership; instance parenting/attachments; camera/lens/light/modifier/grip specifications and references. | Advanced rig constraints, articulated hands, moving camera-rig hierarchies, and complete placed grip/support geometry remain. |
| 7. Shared action/blocking | Beat/action timelines, explicit time base, instances, paths/pose keys, facing/targets, timed parent/state changes, continuity anchors, alternatives and shot overrides. | No motion/IK solver, automatic avoidance, or comprehensive declarative relative-placement constraint engine. Complex events/keys use JSON/CLI rather than a full dope-sheet editor. |
| 8. Shots/coverage/panels | Shot types/purpose, coverage, exact action/camera/lighting pins, duration/handles, requirements, overrides; multiple panels with vectors/artwork/dialogue/annotations; missing/overlap reports; panel animatic records. | No full raster/vector drawing application or judgement of artistic sufficiency. Contact/storyboard review output is a basic production-packet layout. |
| 9. Cameras/lenses | Named reusable setups, position/target/path keys, sensor/gate/focal length, FOV, focus target/distance, camera previews, safe areas; several cameras can share action. | Pinhole planning only: no calibrated lens distortion/breathing, physical depth-of-field rendering or collision-certified camera rig. |
| 10. Lighting/grip | Shared 3D fixture placement/orientation, specifications/roles/modifiers/support references, named setups, shot overrides, timed cues/practical states, equipment report and approximate obstruction advice. | Symbolic geometry/state preview, not light transport/photometry/exposure. Full stand/flag/deformation/rigging/electrical planning is not implemented. |
| 11. Timing/takes/editorial | Rational rates, half-open intervals, explicit shot/action mapping, handles, panel/take times, separate cuts/transitions/order and match-action anchors, silent timed panel playback. | Audio mixing/playback, rendered video animatics, actual-media timecode ingest and complete editorial interchange remain. |
| 12. Continuity/consistency | Referential/type/frame checks; revision staleness; sampled actor/prop cut-state, axis/facing/eyeline, obstacle and visibility advice; pinned intentional exceptions with reasons. | Sampling is bounded/reported, not exhaustive physical collision or artistic continuity proof. |
| 13. Agent-first CLI | JSON schemas/catalog/help; inspect/query/create/update/select/archive/restore/validate/diff/export; joins; atomic batches, checkpoints, preview hashes, idempotent receipts, changes/impact/missing-data reports; shared API. | No arbitrary query language or bundled MCP server. Advanced operations are expressed as typed batches, not a separate bespoke command for every field. |
| 14. Agent revision workflow | Machine-operable source import, proposed plans, provenance/assumptions/questions, selected-vs-proposed state, targeted reconciliation and revision-stamped review packet. | This is an agent-facing planning substrate, not a bundled autonomous creative agent, model integration or automatic shot-generation service. |
| 15. Visual workspace | Six connected views; source-to-shot navigation; SVG 3D/orthographic/camera proxies; scrubber, paths/layers/marks; top-view actor editing; record/version compare; panels; review/report; strict draft/stale/retry states; responsive layout. | SVG projection, not WebGL/PBR. Complex asset/light/camera editing still uses structured records. No true dual synchronized 3D viewport comparison or comprehensive spatial gizmo suite. |
| 16. Completeness/review | Distinct structural/planning/creative dimensions; linked gaps; missing location/action/camera/coverage; applicability reasons; revision-pinned review and staleness; responsibility/next-action fields. | Readiness is rule-based and bounded; a complete-looking plan is not creative approval or on-set certification. |
| 17. Reliability/portability | Additive schema 9, immutable graph versions/receipts, exact reference indexes, atomic writes, optimistic concurrency, recovery archive, media hashing, backup/restore, canonical graph roundtrip, migration/concurrency/CLI/client tests. | No distributed collaboration/CRDT or arbitrary history merge. The graph export is references-only for media; use project backup for complete portable media. Ordinary browser navigation still requires validation on an unrestricted machine. |
| 18. Production outputs | Selected-revision shot/equipment lists, scene JSON, coverage/continuity reports, panel sheets, top-view proxy plots, timeline JSON, HTML/PDF review packet, manifest and checksum ZIP. | No photoreal frames or video renderer; no elaborate per-department drafting/CAD/PDF publishing system. Audio cues are retained data, not playable mixed sound. |

## Existing-project integration boundary

The old outline, source-document, canvas, storyboard, observation and spatial workflows
remain available. Initial legacy adoption is explicit and previewable; it preserves IDs
and original data but does not create hidden dual-write behavior. Existing spatial plans
are not automatically reinterpreted as physically calibrated connected locations.

The highest-value acceptance path is executable: CLI-authored source + location + shared
action + cameras + lighting + shots, inspection in the new workspace, changed source,
impact report, targeted new versions, and retained unaffected/older work. The tests and
local fixture exercise that path; they do not stand in for the remaining feature depth
listed above.
