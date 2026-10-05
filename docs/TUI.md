# Terminal production desk

Run `storyboarder tui --workspace PATH` or `storyboarder tui --project PATH`.
Bare `storyboarder` starts this interface when stdin/stdout are interactive.
The implementation uses prompt_toolkit; it is not a command-line setup wizard.

The left navigation contains 13 pages: Workspace; Project overview; Image intake;
Reference library; Connections; Story outline; Story guide; Scene & shot editor;
Storyboard frames; Board & exports; Image tools; Observation coverage; and Project care. Pages share a
searchable record list, inspector, visible focus, contextual actions and status/error
messages. Tables and inspectors read the same service state as the React app.

| Key | Action |
|---|---|
| Tab / Shift+Tab | Next / previous focusable control |
| Up / Down, Enter | Select / inspect a record or activate the focused action |
| Ctrl+K | Search all application actions, including less common maintenance operations |
| Ctrl+N / Ctrl+E | Create for the current page / edit selected record |
| Ctrl+F | Focus page search |
| Ctrl+P / Ctrl+L / Ctrl+O | Workspace / asset library / outline |
| F6 / F5 / F1 | Connections / reload current records / keyboard help |
| Escape | Close a modal without committing |
| Ctrl+Q or Ctrl+C | Quit when idle; wait for an active local action to finish |

Forms are generated from the common command catalog. Relationship/assignment selectors
show eligible records; stale revision errors retain edits and offer reload. Destructive
actions show a confirmation. Reorder uses an explicit parent/position form. Connection
rows traverse canonical neighbors; story rows show compact hierarchy/shot data.
2D pointer dragging is intentionally a browser interaction, not a hidden TUI graph.

The **Observation coverage** page lists each contract with its protected header revision.
Show and Validate inspect exact document/version/node/hash/edge pins, purpose, priorities,
basis labels, saved history, and current findings; Diff compares selected immutable
versions. **Plan shot + contract** captures the selected scene revision, lets the editor
choose multiple exact screenplay nodes, and atomically creates one shot, its source links,
and its first contract. A conflict keeps the complete draft and its exact IDs and pins for
an explicit retry. Editing one purpose or requirement field preserves every untouched
row, source pin, reference, continuity note, and note. **Contract for existing shot** lets
the editor choose an active shot, captures its current revision, and builds a first contract
from that shot’s existing exact screenplay links. It labels direct shot links separately
from parent-scene context, then collects purpose, communication, and multiple requirements
with priority and basis labels. A stale shot revision keeps that exact draft for retry.
Rebase is a separate explicit
review action: the page shows saved/current basis values and the exact retained edge IDs,
then asks before saving with its review token. A conflict keeps the draft and pins for a
fresh review. Source labels distinguish **Direct shot link** from **Scene context** and
show the screenplay node kind, so a whole-scene context link is not presented as beat coverage.

Source actions use searchable, paginated document, draft, element, provenance and note
pickers. Selecting a mutable source record supplies its current revision automatically.
These generic forms support the CLI/API preview workflows; a dedicated source-document
workspace and visual draft comparison remain unfinished.

Intake accepts file/folder paths with an explicit recursion option, tags, create/attach
and discard workflows. Frames accept external files or managed images, show state and
revision, and provide **Compare / pin** plus a generated contact sheet/system-viewer
handoff. **View image** opens the selected managed file only on explicit request.

ANSI half-block thumbnails are available as a compact aid. Set
`STORYBOARDER_NO_THUMBNAILS=1` to disable them. A true-color terminal offers the best
preview; all file names, roles, statuses and authoring operations remain textual.
The desk adapts at 80×24, 100×30, 110×35, and 160×50. At 60×20 it hides the side
navigation and stacks the coverage list and inspector so the key actions remain usable.
The two-pane record view is most comfortable around 110 columns by 35 rows.

Script registration remains an explicit CLI trust operation. Once registered, script
requests, launch/cancel, logs, pending review and approval are available in the TUI.
No terminal form bypasses validation or accesses SQLite directly.
