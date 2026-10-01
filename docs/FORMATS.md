# Source-format support

This checkpoint implements two independently validated JSON profiles. It does not claim upstream certification or broad screenplay/NLE format support.

## ScreenJSON 1.x core profile

Input is a UTF-8 JSON object with root `id`, `version`, language-map `title`, `lang`, `charset`, `dir`, author records and `document`. The document contains a cover and ordered scenes; each scene has a stable UUID, author references, structured heading and ordered body. Supported body types are action, character, dialogue, parenthetical, transition, shot and general. Character cues and dialogue refer to the root character index. Revisions and annotations imported as ancillary metadata remain in the original payload.

Core payloads use strict Pydantic validation. Duplicate UUIDs, undefined author/character references, wrong owning-scene references, invalid bookmarks, unknown core fields, encrypted content, duplicate JSON keys, non-finite numbers and NUL bytes are rejected. Ancillary analysis/layout/note/revision properties are preserved but not fully certified against every upstream constraint.

The published January 2026 schema at `https://screenjson.com/schema.json` combines closed `allOf` object branches that reject each other's fields under standard JSON Schema evaluation. This implementation does not silently modify that schema or claim that validating its own core profile is upstream-schema compliance. The independent adapter is `src/storyboarder/formats/screenjson.py` and its accepted fields are the executable contract. Review upstream schema evolution before widening this profile.

Import retains exact original bytes and SHA-256. Export without optional enrichment retains the same parsed JSON payload. Authoring creates a new immutable version, not an in-place rewrite. Screenplay scene IDs are not storyboard scene IDs; explicit source links connect them.

## OTIO JSON editorial profile

Supported structural objects are Timeline.1, Stack.1, Track.1, Clip.1/2, Gap.1 and Transition.1. RationalTime.1 and TimeRange.1 retain their frame values and rates; invalid rates and negative durations/transition offsets are rejected. Video and Audio tracks are supported. Media URLs, effects, markers and other object properties are retained, not executed, fetched, rendered or conformed. Import never opens referenced media or loads a plug-in.

`metadata.storyboarder.id` is the stable object identity when supplied. Otherwise IDs are inferred from name/media hints and occurrence order. Such identities are explicitly labelled inferred: renaming and repeated clips can require manual reconciliation. Export with `--include-identities` to embed the generated IDs before editing externally. The normal export does not inject them.

This is not a video editor, player, native OTIO binary adapter or promise of interoperability with every NLE. Native OpenTimelineIO is not required by the application. Fixtures test exact JSON round trips and structural/timing validation.

## Limits and history

Source files are limited to 20 MiB; JSON nesting to 64 levels; normalized documents to 100,000 nodes; OTIO structural nesting to 48 levels. Child/list queries expose pagination and do not include full node payloads. Full node inspection, version diff and export explicitly load the relevant payloads.

Version IDs identify immutable creative snapshots. Document row revisions are separate optimistic-concurrency tokens. Source links, notes and generation requests remain pinned to their original versions. Coverage reports describe explicit links, not inferred footage coverage.

Fountain, FDX, PDF, ScreenBaby/ScreenParse compatibility imports and third-party editorial formats are not implemented in this checkpoint.
