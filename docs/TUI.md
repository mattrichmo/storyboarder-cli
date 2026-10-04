# Terminal production desk

Run `storyboarder tui --workspace PATH` or `storyboarder tui --project PATH`.
Bare `storyboarder` starts this interface when stdin/stdout are interactive.
The implementation uses prompt_toolkit; it is not a command-line setup wizard.

The left navigation contains 12 pages: workspace; overview; intake; asset library;
connections; outline; story guide; scene/shot editor; frames; composition/export;
external scripts; settings/health. Pages share a searchable record list, inspector,
visible focus, contextual actions and status/error messages. Tables and inspectors
read the same service state as the React app.

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
A terminal around 110 columns by 35 rows is recommended for the two-pane desk. The
browser's narrow-window layout is the better choice for small screens.

Script registration remains an explicit CLI trust operation. Once registered, script
requests, launch/cancel, logs, pending review and approval are available in the TUI.
No terminal form bypasses validation or accesses SQLite directly.
