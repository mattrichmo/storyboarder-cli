Please build the complete Storyboarder project described in the production plan below as a real, runnable project folder. Implement all milestones in the plan, including the full CLI, first-class multi-page TUI, local React app, custom in-house graph canvas, project and database structure, packaging, documentation, and the provider-neutral external-script integration seam. Do not answer with another plan, a prototype, or representative snippets. Produce all required files and folders. If this chat has workspace/file-generation tools, create the complete project folder with them; otherwise provide a complete downloadable archive. If a limitation prevents a specific part, state it and still build the rest. Make reasonable implementation decisions without waiting for clarification. Keep the design direction calm and editorial, and make the result runnable from documented commands.

Implement the project in accordance with this full production plan:

# Storyboarder production build plan

## Product outcome

Build a local-first story production workspace with three first-class interfaces: a scriptable CLI, a multi-page TUI, and a React app served from localhost. All three operate on the same projects, records, media, and application workflows.

A creator should be able to start with an empty folder, create or open a project, bring in reference media, connect it to story elements, build a sequence of scenes and shots, explore those connections on a custom node canvas, and export a complete scene package or visual storyboard. Later, external scripts can generate assets and hand their results back through a controlled, provider-independent interface.

The first production release is a dependable offline authoring and export tool. OpenAI integration, cloud services, and collaboration are planned extension points, not prerequisites for the core app.

## Product and storage decisions

- A project is a portable folder. Each project has a manifest, one SQLite database, managed media, cache, and exports. Copying the project folder moves the story with it.
- A workspace is a project navigator. It groups project paths and remembers recent selection. It has no global story database. Projects can also open directly by path.
- SQLite stores structured story data. Media remains on disk. Database media paths are relative to the project root; imported files are copied into managed storage and hashed. The original filename remains metadata.
- The database is canonical. The web canvas, TUI connection views, CLI, and exports are views or operations over the same records. Canvas coordinates are saved presentation state and never define story relationships.
- All interfaces call one application layer. CLI and TUI call local application services directly. The React app calls a versioned local HTTP API, which calls those same services. UI code never writes SQLite directly.
- The React app is local-only. storyboarder ui starts the local API and serves the built frontend on loopback, then opens the browser. The server binds to 127.0.0.1 by default. It does not require an account or external network access.
- Project creation through the browser is workspace-scoped. storyboarder ui --workspace PATH grants the app that workspace; the dashboard creates projects inside its projects/ folder. Opening a project outside the workspace is done by passing its path to the CLI or launching the app for that project. The browser does not receive general filesystem access.
- Concurrent edits have an explicit policy. SQLite uses short transactions and WAL mode. Updates carry record revisions so stale edits are detected and reloaded instead of silently overwriting newer changes. Import stages files before registering them, then finalizes filesystem/database changes safely. Live multi-user collaboration is out of scope.
- Separate source references from storyboard frames. Imported reference media can exist in an intake queue, belong to assets, or be attached to shots. A shot's draft/approved storyboard frame is a separate output record, even when it uses the same underlying file.
- Keep generation provider-neutral. Later scripts receive a versioned JSON job request and return an output manifest plus files. The app validates and previews results before importing them as normal project assets. No third-party script gets direct database access.

Proposed project folders:

    storyboards/
      workspace.toml                 optional known-project and recent-project list
      projects/
        winter-station/
          project.toml                title and project preferences
          .storyboarder/
            storyboard.sqlite3        canonical structured data
            cache/                    rebuildable thumbnails/previews
          media/
            items/<media-id>/<original-name>
            frames/<frame-id>/<filename>
          exports/
            scenes/
            boards/

A standalone project uses the same project folder without the outer workspace. Workspace registration can be rebuilt from project paths and is never required to open a project.

## User-facing application

### CLI

The CLI supports direct, repeatable operations and batch work: create/open projects, import and search assets, edit metadata and links, build sequences/scenes/shots, inspect graph neighbors, preview compositions, export files, and run project health/backup commands. Human-readable output is the default; list/show/export operations also have stable JSON output and exit codes for scripts.

Running storyboarder in an interactive terminal opens the TUI dashboard; in a non-interactive shell it prints help and exits. storyboarder ui opens the React app and prints the URL if a browser cannot be launched. Commands accept an explicit workspace or project path and discover a project from the current folder when that choice is unambiguous.

### Multi-page TUI

The TUI is a full authoring surface, not a setup wizard. It has:

1. Workspace dashboard: create, open, switch, and find projects.
2. Project overview: recent changes, sequences, asset counts, and health issues.
3. Intake queue: review files imported from a folder, identify duplicates, assign types/assets, add tags, and accept or discard staged items.
4. Asset library and detail pages: browse, search, filter, tag, import, and inspect media.
5. Connections explorer: traverse character/location/prop relationships and inspect shot references as a navigable text graph.
6. Story outline: browse and reorder sequences, scenes, and shots.
7. Story guide/context editor: edit project-wide style direction and sequence defaults; inspect which direction flows to a scene or shot.
8. Scene and shot editor: edit authored fields and assign exact assets and reference images.
9. Frame page: attach image files as storyboard-frame candidates for shots, compare revisions, and mark a preferred frame. Drawing stays in an external art tool; later scripts can add generated candidates.
10. Composition/export page: preview inherited context, resolve missing inputs, and write bundles or boards.
11. Project settings and health: inspect project paths, database version, missing media, and backup/restore actions.

Use consistent page navigation, search, keyboard shortcuts, validation messages, and confirmation for destructive changes. Show visual references with terminal thumbnails when supported and provide contact sheets or system-viewer handoff where they are not. The TUI presents the same connection and ordering data as the web app, using a navigable outline, an adjacency/neighbor view, and compact shot cards. It supports the same content operations; 2D canvas dragging remains a web interaction, while TUI users can create links and reorder items through explicit commands/forms.

### React localhost app

The React app has a workspace/project dashboard, intake queue, asset library, story outline, story-guide/context editor, custom canvas, inspector/editor panel, frame comparison page, composition preview, and project settings. From the dashboard, users can create a project under the workspace supplied at launch and switch between known projects. The UI serves project media through the local API and stores canonical content in the project database; browser storage may keep transient preferences only. Folder picking is scoped to the configured workspace; opening an outside path is an explicit CLI launch action.

storyboarder ui --workspace PATH should start the app against a workspace. A project can also be opened directly. Startup reports the local URL and supports a configurable port; Ctrl+C cleanly stops the service.

## Custom node canvas design

Build the graph interface inside the project; do not use a third-party graph editor or React Flow component. Use React components for node cards, a native SVG layer for edges, and internal code for viewport movement, selection, dragging, hit-testing, keyboard behavior, and layout. Keep canvas rendering separate from the data/domain model.

### Node types

- Asset nodes: character, location, prop, or reference. Show type, name, primary thumbnail, tags, and link/reference counts. An asset can hold multiple media files; expanding the node or opening its inspector selects a specific image/version.
- Sequence nodes: title, order, and scene count.
- Scene nodes: title, order, location, and shot count.
- Shot nodes: shot number, framing, short action summary, and attached-asset count.

### Edge types

- Containment/order: sequence → scene → shot. These edges are derived from parent/order records; moving or reordering through the canvas updates the corresponding story records.
- Asset relationship: typed links such as appears-at, alternate-view-of, wears, or part-of.
- Shot assignment: shot → asset with a role such as subject, setting-reference, costume, or prop, plus an optional exact media selection.

The app validates allowed endpoints and relationship types. The canvas can create and remove valid relationships; it does not permit dangling or arbitrary edges that the domain model cannot represent.

### Canvas modes and interactions

Provide three focused views over the same records rather than placing every project node into one crowded graph:

- Story flow: ordered sequence, scene, and shot hierarchy.
- Asset network: filtered graph of selected asset types, tags, and typed relationships.
- Scene board: one scene's ordered shot cards, with their chosen references and shot details.

Users can search/focus nodes, filter by type/tag/relationship, select a node to edit it in an inspector, navigate to related nodes, create valid links, and drag nodes to arrange a saved layout. New records can be created from a canvas toolbar or context action, with a type-specific form before the node is placed. Invalid connections explain which endpoint or relationship rule failed. Include built-in tidy layouts for the hierarchical and relationship views, plus saved named layouts. Store node positions, collapsed groups, and view settings separately from canonical story data. Start with simple deterministic layouts and add more layout options only when the data needs them.

Story-flow edges have visible order markers and move/reorder controls. Semantic asset links and shot assignments use different line styles and labels; color is never their only distinction. Deleting a node opens a reference-aware action that distinguishes removing a canvas view from archiving/deleting its underlying record.

## Product context and visual direction

The primary user is a creator working locally on a film, animation, comic, or other visual story. The main task is to make the correct reference, context, and direction easy to find and assemble for each shot. Treat this as a focused production tool, with the media and story content carrying the visual emphasis.

Confirmed working direction: a calm, editorial production desk. Use clear hierarchy, compact but readable information, neutral surfaces, and restrained semantic colors for node/asset types and workflow states. Keep thumbnails and frame outputs prominent where they answer a real question. Make asset type, relationship, draft/approved state, selection, and validation state clear through text labels or icons as well as color.

The React shell should reserve a predictable navigation area, a flexible work surface, and an inspector that can be opened without hiding the current graph context. Canvas node cards should use consistent type labels and compact metadata; expanded inspection reveals the full description and media. Avoid decorative card nesting and motion. Use motion only to communicate selection, layout, or save state. Keep board exports visually distinct from the editing canvas so a creator can tell a working graph from a presentable storyboard.

The TUI shares the same names, labels, type/status vocabulary, and action order. It provides visible focus, keyboard-only navigation, and a non-color indicator for status. The React app must support keyboard selection and link creation, visible focus, reduced motion, readable contrast, and zoom without clipping controls. Desktop is the primary canvas target; library and project management pages remain usable in narrower windows.

Before building the React shell, turn this direction into a small design brief with sample project dashboard, asset node, shot node, connection edge, inspector, and scene-board layouts. Set semantic type/state colors and typography once, then apply tokens consistently across pages and export templates.

## Content model, context, and media lifecycle

Keep three image roles distinct:

- Intake media: imported files waiting to be classified or attached. A media record can be tagged, ignored, or assigned to one or more assets.
- Reference media: source images attached to a character, location, prop, general reference, or specific shot role. Preserve the exact selected media ID on each shot assignment.
- Storyboard frames: candidate panel images attached to a shot. Track frame revision and state (draft, selected, approved, archived) separately from reference media. V1 accepts uploaded image files; built-in drawing is outside scope.

Support bulk folder import into the intake queue, with recursion an explicit option. The review workflow groups exact hash duplicates, preserves original paths/names as metadata, and lets the user create an asset, attach to an existing asset, merge/reassign, or discard. Direct “create asset from this image” remains a shortcut through the same service. Initial supported formats should be common still-image formats; decide size limits and unsupported-format behavior in milestone 0. Defer broad video, audio, document, and automatic visual classification.

Define authored context at four levels: project, sequence, scene, and shot. Project context holds premise, visual style guide, and global constraints; sequence context holds arc/tone notes; scene context holds summary, location/time defaults, and continuity; shot context holds action, dialogue, framing/camera direction, and shot-specific constraints. Use typed fields for known structure and named text blocks for reusable direction.

Context resolves top-down with explicit rules: list-like direction blocks accumulate unless a lower level explicitly excludes or replaces one; scalar defaults such as location can be overridden at lower levels. The composer preview shows each resolved value and where it came from, and allows a shot to opt out of an inherited block. Avoid invisible prompt concatenation.

## Backend and source boundaries

    src/storyboarder/
      cli/            command parsing and terminal output
      tui/            pages, navigation, and terminal views
      api/            local HTTP routes and request/response schemas
      application/    project, asset, story, canvas, and export workflows
      domain/         IDs, validation, entities, and relationship rules
      storage/        SQLite schema, migrations, repositories, transactions
      media/          import, hashing, path safety, thumbnails, integrity
      rendering/      JSON/Markdown/board composition
      automation/     later job and external-script adapters
    clients/web/      React + TypeScript frontend and internal canvas
    docs/             product, architecture, API, and release documentation

The backend owns project discovery, validation, migrations, record lifecycles, intake/media import, link integrity, context resolution, rendering, backups, and the local API. The frontend owns page layout, interaction state, node presentation, and saved canvas layouts through the API. Derived thumbnails and previews are rebuildable cache data. Bundle the compiled React app with the Python distribution so end users do not need Node installed; Node is a build-time development dependency.

Core records should include project metadata, assets, media, intake state, asset-media membership, aliases, tags and membership, typed asset links, scoped context blocks, sequences, scenes, shots, shot-asset assignments, shot-frame candidates/status, migrations, and named canvas layouts/positions. Use immutable IDs and explicit sequence/scene/shot order. Scene location is a default; a shot can override it. Store action, dialogue, camera, duration, continuity, and notes as separate authored fields. Keep tags plain text initially and avoid a custom-field framework until real workflows establish a need.

The HTTP API should expose versioned project, asset/intake, relationship, story/context, frame, canvas-layout, media, and export operations. Long operations can report progress through request status initially; add a job/event channel only when background work requires it. The server must serve only the selected workspace/project and local media, use safe path resolution and same-origin checks, and stay on loopback by default. Use a launch-scoped token for write operations if same-origin checks alone cannot reliably bind browser requests to the launched app instance.

## Milestones and exit criteria

### 0. Product contract and foundations

Lock project/workspace paths, core names, supported still-image formats and size limits, ID rules, intake states, initial shot/frame fields, context inheritance rules, and API/export versioning. Select the TUI toolkit, local HTTP server framework, and React build/package tool; document development and installed launch paths. Make the Python package installable and establish migration, configuration, error, and logging conventions. Produce the confirmed calm-editorial design brief and interaction vocabulary for statuses, node types, empty states, and errors. Confirm the repository's license and include its license file before distribution.

Exit: a fresh checkout starts from documented commands; paths and schema versions are explicit; migrations can evolve the database without changing the meaning of existing project records.

### 1. Project lifecycle and shared application core

Implement workspace registration, project create/open/show/switch, project discovery, manifest handling, database initialization, and project doctor. Build application services and storage repositories before interface-specific business logic. Add CLI commands and the TUI workspace/project dashboard.

Exit: create two projects, switch between them in the TUI and CLI, and confirm their data stays isolated. Move a project folder and reopen it directly.

### 2. Local API and React project dashboard

Add the loopback HTTP server, versioned API contracts, static frontend serving, and React app shell. Implement workspace/project list, create, open, and switch from the browser. Make storyboarder ui start the server, open localhost, and shut down cleanly. Establish common navigation and visual style without duplicating backend behavior.

Exit: browser-created projects appear in CLI/TUI and vice versa; the web app uses project records from the local API; the server is reachable only through its configured local address.

### 3. Asset library across all interfaces

Implement managed single-file and folder import, explicit recursive scanning, staged intake, asset/media records, primary reference selection, aliases, tags, typed relations, hash-based duplicate detection, search, and media health. Let users assign staged files to new or existing assets, merge assignments, or discard them. Add CLI workflows, the TUI intake/asset/detail/connection pages, and React intake/library/inspector screens.

Exit: import a folder, review staged media, tag, find, link, and inspect assets in any interface; each interface shows the same saved data; project-relative media survives project relocation.

### 4. Sequences, scenes, and shots

Implement the ordered story hierarchy, typed context blocks at project/sequence/scene/shot levels, explicit context inheritance/override rules, structured shot fields, shot-level location overrides, and shot-asset roles with exact media selection. Add shot-frame candidate records with revisions and draft/selected/approved/archived states; V1 attaches existing image files and does not include drawing tools. Add create/edit/reorder workflows in CLI, TUI, and React outline/editor/frame pages. Provide an initial readable Markdown/JSON scene export so this milestone completes the first end-to-end creator workflow.

Exit: the same sequence can be created and edited in all interfaces; stable IDs survive renames and reordering; every shot exposes authored details, inherited context with its source, selected references, and separate frame candidates; the user can export a usable scene package.

### 5. Internal graph canvas and saved layouts

Implement the three canvas modes, node cards, edge styles, selection/inspector, search/focus, pan/zoom, drag, relationship creation/removal, reorder behavior, deterministic initial layout, and named layout persistence. Add a TUI connection explorer and compact story/shot layout page over the same graph records.

Exit: graph edges always correspond to valid stored relationships; canvas edits appear in CLI/TUI; moving a node changes only presentation layout; a large project can be filtered and navigated without loading every node into one view.

### 6. Composition, exports, and visual boards

Build deterministic scene composition and validation. Define a versioned export bundle with a manifest, composed Markdown/JSON, context provenance, and the selected reference files copied under bundle-relative paths, for example scene.json, scene.md, and media/<id>.<ext>. Add preview in both TUI and web. Render sequence/scene board layouts with reference thumbnails, optional approved frame candidates, and notes to shareable HTML/PDF and image/contact-sheet outputs. Keep the editing canvas and presentation board as distinct views and exports.

Exit: exports are repeatable, self-contained when requested, include all selected inputs and context provenance, report missing media, and work offline. A full sequence can be reviewed as data and as a visual board.

### 7. Reliability and production finish

Add database backup/restore, media integrity checks, rebuildable cache handling, recovery guidance, project migration reporting, keyboard/accessibility review, large-project responsiveness, packaged React static assets, and clean install/upgrade/uninstall behavior. Verify simultaneous CLI/TUI/web access uses revision checks and does not lose updates. Refine cross-interface terminology and error messages.

Exit: a project can be backed up, restored, moved, migrated, and reopened; common actions work across all three interfaces; media and database problems provide a clear recovery path.

### 8. External script and generation integration seam

After the core authoring loop is stable, define a versioned job request and result manifest. A request describes the desired asset or frame output, source references, resolved context, constraints, and destination. A script adapter records queued/running/succeeded/failed/cancelled status, captures output and error logs, enforces timeouts, records provenance, validates produced files, and presents pending results for review. Retries must be explicit and idempotent. Approved outputs become ordinary assets or shot-frame candidates with links and metadata.

Keep provider-specific OpenAI calls in optional scripts/adapters. Supply credentials only through a user-configured environment or secret store, never in project manifests or job exports. Record script/provider name, model, prompt/input snapshot, timestamps, and output hashes with generated results. Require explicit user action to launch a registered script; do not execute scripts discovered in a project folder. Give each run a dedicated working/output directory, enforce configurable time and file-size limits, and do not let scripts silently overwrite approved assets or mutate the project database directly.

Exit: a sample external script can consume a request, return files and metadata, and have its result reviewed/imported without changing the core asset and scene schema. This phase creates the integration contract; it does not require live OpenAI credentials in the core application.

## First production release definition

Milestones 0–7 make the standalone authoring product: CLI, first-class multi-page TUI, localhost React app with project switching, asset and story editing, a custom graph canvas, scene composition, visual boards, portability, and recovery. Milestone 8 adds the safe extension contract for later generation scripts.

Ship useful slices before the full production release:

- Project preview (after milestone 2): create/open/switch projects in CLI, TUI, and React; inspect an empty project and its health.
- Creator alpha (after milestone 4): stage/import references, build sequence/scene/shot data, resolve context, and export a basic scene package. The TUI and React app can use outlines and inspector forms while the canvas is still being built.
- Graph preview (after milestone 5): browse and edit supported story and asset links on the internal canvas, with the TUI connection explorer.
- Production 1.0 (after milestone 7): complete boards, portable bundles, recovery, packaging, and cross-interface consistency.
- Automation extension (after milestone 8): external scripts can produce reviewed asset/frame candidates through the job contract.

Do not call the product complete if the canvas is only decorative, if one interface bypasses the shared application layer, if projects depend on absolute media paths, or if exports omit the exact reference media used by a shot. The final acceptance walkthrough starts with an empty workspace and finishes with a moved/reopened project, navigable graph, and exported scene/board.

## Explicitly deferred

Cloud sync and collaboration, hosted accounts, a web deployment, a graphical desktop application, in-app drawing tools, automatic tagging/recognition, script-to-story breakdown, and bundled image-generation providers remain outside this local production build. Stable IDs, API schemas, provenance, and the external job contract leave room for those additions later.
