<p align="center">
  <img src="clients/web/favicon.svg" width="56" alt="">
</p>

<h1 align="center">Storyboarder</h1>

<p align="center">
  <strong>A local production desk for stories, references, and frames.</strong><br>
  Plan your shots. Keep your references connected. Build a storyboard you can share.
</p>

<p align="center">
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/Python-3.11%2B-49654f?style=flat-square" alt="Python 3.11 or later"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-49654f?style=flat-square" alt="MIT license"></a>
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> ·
  <a href="#cli-workflows">CLI workflows</a> ·
  <a href="#command-map">Command map</a> ·
  <a href="#source-documents-and-provenance">Source documents</a> ·
  <a href="#documentation">Documentation</a>
</p>

![Story flow canvas showing the Winter Station sequence, scenes, and connected shot cards](docs/images/canvas-desktop.png)

<p align="center"><em>The story flow canvas, using the included fictional Winter Station demo.</em></p>

Storyboarder helps filmmakers, storyboard artists, and small production teams organize
visual planning in a project folder they own. Build a sequence → scene → shot outline,
collect character and location references, compare storyboard images, and export boards
and production handoffs.

Work in the **browser**, a **full-screen terminal desk**, or the **CLI**. The original
authoring workflows share the same application services and project database across all
three. After installation, core authoring and exports work offline. There is no account,
subscription, or required generation provider.

## What you can do

| Workflow | What Storyboarder gives you |
|---|---|
| **Plan the story** | Ordered sequences, scenes, and shots with action, dialogue, framing, camera direction, duration, and continuity notes. |
| **Organize references** | A typed library for characters, locations, props, and general references; tags, aliases, exact-image assignments, and duplicate intake review. |
| **Carry direction into each shot** | Project, sequence, scene, and shot notes that append to, replace, or exclude inherited direction. |
| **Arrange the production visually** | Story flow, asset network, and scene board canvases with pan/zoom, filtering, keyboard controls, typed connections, and saved layouts. |
| **Review storyboard images** | Separate frame candidates, version history, comparison, and explicit draft, selected, approved, or archived states. |
| **Deliver and recover** | HTML/PDF/PNG boards, JSON/Markdown handoff packages, managed media, manifest hashes, health checks, and portable backups. |
| **Automate your own tools** | Structured CLI output and explicitly registered local scripts with requests, logs, cancellation, result review, and approval. |

The current source also includes **ScreenJSON and OTIO JSON documents, immutable drafts,
and production provenance through the CLI and local API**. These are an implementation
preview; their dedicated browser and terminal workspaces are still unfinished.
See [source documents and provenance](#source-documents-and-provenance) for the supported workflow.

<details>
<summary><strong>See the project overview</strong></summary>

![Project overview with scene and shot counts, creative direction, project health, and recent changes](docs/images/overview-desktop.png)

Screenshots show the original authoring interface. The reference panels are labelled
fictional demo graphics; they are examples of the workflow, not finished shot artwork.

</details>

## Quick start

**Requires Python 3.11 or later.** Clone the repository, or extract a source archive
and open a terminal in its `storyboarder` folder.

```sh
git clone https://github.com/mattrichmo/storyboarder.git
cd storyboarder
```

### macOS / Linux

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .

storyboarder workspace init ./stories
storyboarder project create --workspace ./stories --slug my-film --title "My Film"
storyboarder ui --workspace ./stories
```

<details>
<summary><strong>Windows PowerShell</strong></summary>

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .

.\.venv\Scripts\storyboarder.exe workspace init .\stories
.\.venv\Scripts\storyboarder.exe project create --workspace .\stories --slug my-film --title "My Film"
.\.venv\Scripts\storyboarder.exe ui --workspace .\stories
```

Use `.\.venv\Scripts\storyboarder.exe` in place of `storyboarder` in the examples
below, or activate the virtual environment with `.\.venv\Scripts\Activate.ps1`.

</details>

Open **http://127.0.0.1:7430** if your browser does not launch automatically.
Keep the terminal running; **Ctrl+C** stops the server. Add `--port 7431` to use
another port, or `--no-browser` to skip automatic browser launch.

Installation normally downloads Python dependencies. The packaged React client is
already built: **Node, npm, a CDN, and API keys are not needed to use the app**.
For an offline first installation, prepare a wheelhouse on a connected machine;
see [installation and packaging](docs/DEVELOPMENT.md#fully-offline-installation-preparation).

### Try a populated demo

From the repository root, with the virtual environment active:

```sh
python scripts/create_demo.py ./stories/demo
storyboarder ui --workspace ./stories/demo
```

**Winter Station** includes a story guide, two scenes, six shots, reference assignments,
relationships, frame candidates, and a duplicate intake example. Use a fresh destination;
the script refuses to overwrite an existing project. Its generated panels are demo art.

### Choose your interface

| Interface | Start it | Best for |
|---|---|---|
| Browser | `storyboarder ui --workspace ./stories` | Visual planning, reference review, canvas arrangement, and frame comparison. |
| Terminal | `storyboarder tui --workspace ./stories` | Authoring and reviewing a project from a full-screen terminal. |
| CLI | `storyboarder --project ./stories/projects/my-film shot list` | Repeatable operations, shell workflows, and integrations. |

A standalone project works too: create it with
`storyboarder project create ./stories/standalone --title "My Film"`, then open it
with `storyboarder ui --project ./stories/standalone`. Workspace registration is optional.
Running bare `storyboarder` opens the terminal desk in an interactive terminal and
prints help in a non-interactive shell.

## CLI workflows

Commands discover a project from its folder or descendants. Use `--project/-p PATH`
to select one explicitly, or `--workspace/-w PATH` to use a workspace's current project.
These options, `--json`, `--jsonl`, and `--no-color` work before or after command groups.

### Build a scene and its first shot

After the quick start, enter the project folder. Commands that create records return
an `id`; replace `SEQUENCE_ID` and `SCENE_ID` below with those returned values.

```sh
cd stories/projects/my-film

storyboarder sequence create --title "The last morning" --json
storyboarder scene create --parent-id "SEQUENCE_ID" --title "Before the first arrival" --json
storyboarder shot create --parent-id "SCENE_ID" --title "The platform waits" \
  --number "01" --framing "Locked wide" --duration 12 \
  --action "Mara enters from frame left." --camera "Hold before she enters." --json

storyboarder shot list --json
```

Keep the returned `SHOT_ID` for the frame and provenance examples. Each command's
`--help` describes its flags:

```sh
storyboarder --help
storyboarder shot create --help
storyboarder document --help
```

### Bring in references and storyboard images

Run these from the project folder. Substitute your reference directory, image path,
and the shot ID created above.

```sh
# Import still images into the intake queue for review.
storyboarder import /path/to/references --recursive --json
storyboarder intake list --state pending --json

# Create a library item, or accept imported images into one through intake accept.
storyboarder asset create --title "Mara" --type character --tags "winter,caretaker" --json

# Add a storyboard candidate to a specific shot.
storyboarder frame add --shot-id "SHOT_ID" --path /path/to/frame.png --json
storyboarder frame list --shot-id "SHOT_ID" --json
```

Imported references and storyboard candidates have separate roles. Review intake with
`intake accept`; use `assignment create` to connect a library item and, optionally,
an exact reference image to a shot. Use `frame state --id FRAME_ID --revision REVISION
--state approved` to approve a candidate after reading its current revision.

### Export, check, and back up

`SCENE_ID` can also be a project, sequence, or shot ID for composition and export commands.

```sh
storyboarder compose "SCENE_ID" --json
storyboarder export board --owner-id "SCENE_ID" --format pdf --json
storyboarder export bundle --owner-id "SCENE_ID" --include-media --json
storyboarder doctor --hashes --json
storyboarder backup --json
```

Export and backup results include their output paths. Restore a backup into a **new**
folder with `storyboarder restore /path/to/backup.zip /path/to/restored-project`.

### Use JSON in scripts

`--json` returns structured results and errors; `--jsonl` emits one result per line
and sends pagination metadata to stderr. Commands that support paging expose `--limit`
and `--offset`; inspect `next_offset` to continue.

```sh
storyboarder shot list --limit 50 --offset 0 --json
storyboarder shot list --jsonl
storyboarder asset create --payload '{"title":"Brass key","type":"prop"}' --json
storyboarder shot create --payload @shot.json --json
```

`shot.json` must contain a JSON object with the required `title` and `parent_id` fields.
Named flags override values in `--payload`. Update and removal commands that require
`--revision` must use the value you just read from that record. A stale revision exits
with a conflict instead of overwriting newer work. See the
[CLI reference](docs/CLI.md#output-payloads-and-exit-codes) for exit codes and error output.

## Command map

Every group and subcommand has `--help`. The
[full CLI reference](docs/CLI.md#command-catalog) documents all **111 shared application
commands**, including their flags, choices, defaults, and required fields, plus lifecycle commands.

| Area | Commands to reach for |
|---|---|
| Launch and select projects | `ui`, `tui`, `workspace init/list/register/switch`, `project create/open/show/list/switch` |
| Story and guide | `sequence`, `scene`, `shot` → `create/update/list/show`; `project update`, `story move` |
| Library and relationships | `asset create/update/list/show/attach/primary/detach/merge`, `link create/list/remove` |
| Import and review | `import`, `media import/list/show/tags`, `intake list/accept/discard` |
| Shot references and direction | `assignment create/update/list/remove`, `context put/resolve/list/remove` |
| Storyboard candidates | `frame add/attach/list/state/remove` |
| Canvas arrangements | `canvas graph/neighbors/save/show/list/remove` |
| Composition and handoffs | `compose`, `composition preview`, `export board/bundle` |
| Source drafts | `screenplay import/list`, `edit import/list`, `document import/list/show/tree/children/node/versions/validate/revise/diff/export/archive/restore` |
| Production lineage and notes | `shot link-source/sources`, `provenance link/trace/impact/retire`, `coverage report`, `annotation create/list/update` |
| Local adapters | `script register/list/remove`, `job create/run/preview/cancel/retry/approve/list` |
| Maintenance and recovery | `doctor`, `backup`, `restore`, `project doctor/backup/sync`, `cache rebuild/clear`, `entity update/usage/archive/restore/delete` |

## Source documents and provenance

**CLI / local API preview.** Import ScreenJSON core-profile screenplays and OTIO JSON
editorial timelines as separate documents. Imports preserve original bytes and hashes;
creative revisions create immutable versions. Explicit links connect source elements
to storyboard shots and frames, and can connect those results to editorial clips.

From a project folder, using your own supported source files:

```sh
# Validate without creating a document, then import a screenplay draft.
storyboarder screenplay import --path /path/to/draft.screenjson --dry-run --json
storyboarder screenplay import --path /path/to/draft.screenjson --label "White draft" --json

# Inspect the document ID returned by import.
storyboarder document tree --document-id "DOCUMENT_ID" --limit 100 --json
storyboarder document versions --document-id "DOCUMENT_ID" --json

# Link a source-node ID from the tree to a storyboard shot.
storyboarder shot link-source --shot-id "SHOT_ID" --node-id "NODE_ID" --json
storyboarder shot sources --id "SHOT_ID" --json
storyboarder provenance trace --kind entity --record-id "SHOT_ID" --direction upstream --json

# Bring in an editorial cut and report explicit coverage links.
storyboarder edit import --path /path/to/assembly.otio --json
storyboarder coverage report --json
storyboarder document export --document-id "DOCUMENT_ID" --json
```

Source-node IDs identify elements in a particular immutable draft. Existing links stay
pinned when a new draft arrives; `document diff` and `provenance impact` help review
what changed. Coverage reports describe explicit links, rather than infer missing footage.
OTIO imports preserve media references without fetching or playing the referenced media.

Dedicated source-document workspaces and visual draft comparison remain unfinished; the
terminal desk includes a focused exact Observation coverage page. Fountain, FDX, PDF screenplay imports, and general
NLE interoperability are not implemented. Read the [format profiles](docs/FORMATS.md)
and [implementation status](docs/V2_IMPLEMENTATION_STATUS.md) before adopting these
preview workflows. Back up existing projects before opening them with the newer schema.

## Portable projects

A **workspace** is an optional navigator for multiple projects. Each **project** has
its own SQLite database, managed images, source documents, and exports.

```text
stories/
├── workspace.toml                 # workspace navigation and selection
└── projects/
    └── my-film/
        ├── project.toml           # project identity and title hint
        ├── .storyboarder/
        │   ├── storyboard.sqlite3 # canonical project data
        │   ├── cache/             # rebuildable image previews
        │   ├── staging/           # temporary import/export work
        │   └── jobs/              # requests, pending results, and logs
        ├── media/
        │   ├── items/             # managed reference images
        │   └── frames/            # storyboard image files
        ├── sources/               # retained document bytes, created on import
        └── exports/               # boards, handoffs, documents, and backups
```

Media paths are relative to the project. Use `backup` for a SQLite-consistent archive;
stop writers before moving or copying a live project folder. A copied project retains
its identity; explicitly register its new path to choose the preferred copy.

The repository's `stories/` directory is ignored by Git. Keep production data there
or outside the checkout, and keep separate backups of material you care about.

## Documentation

| If you want to… | Read |
|---|---|
| Walk through a production project | [Creator guide](docs/CREATOR_GUIDE.md) |
| Find exact CLI flags and output behavior | [CLI reference](docs/CLI.md) · [Command schema catalog](docs/commands.json) |
| Work in the terminal or canvas | [Terminal desk](docs/TUI.md) · [Canvas and accessibility](docs/CANVAS.md) |
| Understand references, direction, and delivery | [Context and media](docs/CONTEXT_AND_MEDIA.md) · [Exports and recovery](docs/EXPORTS_AND_RECOVERY.md) |
| Import screenplay and editorial sources | [Format profiles](docs/FORMATS.md) · [Implementation status](docs/V2_IMPLEMENTATION_STATUS.md) |
| Integrate a local tool | [Local API](docs/API.md) · [External script contract](docs/AUTOMATION.md) |
| Understand the product and its internals | [Product contract](docs/PRODUCT_CONTRACT.md) · [Architecture](docs/ARCHITECTURE.md) · [Design brief](docs/DESIGN_BRIEF.md) |
| Develop, package, or inspect verification | [Development](docs/DEVELOPMENT.md) · [Implementation matrix](docs/IMPLEMENTATION.md) · [Verification report](docs/TEST_REPORT.md) |

## Development

Use an active Python virtual environment. **Node 20+** is recommended for rebuilding
the frontend. End users can run the checked-in client without Node.

```sh
python -m pip install -e '.[dev]'
cd clients/web
npm ci
npm run typecheck
npm test
npm run build
cd ../..
python -m pytest
python scripts/build_release.py
```

`npm run dev` watches TypeScript/CSS and rebuilds packaged assets. Run `storyboarder ui`
separately and refresh after a rebuild. The release helper creates a wheel and source
archive in the ignored `dist/` directory; those files are generated, not included in a
fresh Git clone. Install a generated wheel with
`python -m pip install dist/storyboarder_desk-1.0.0-py3-none-any.whl`.


## Scope and trust

Storyboarder runs on loopback for local authoring. Keep its server local. Cloud sync,
live collaboration, user accounts, in-app drawing, automatic script breakdown,
video/audio ingestion, and bundled generation providers are outside the current product.
Importing editorial metadata does not turn it into a video editor.

Registered adapters are trusted local executables with your OS permissions. Review a
script before registering it; generated outputs remain pending until you approve them.
See the [script contract](docs/AUTOMATION.md) and [security boundaries](docs/SECURITY.md).

HTML/JSON exports retain full text. Fixed-size PDF and image panels abbreviate long
notes and use portable built-in fonts; inspect exports before a production handoff.

## License

Application code is [MIT licensed](LICENSE). The bundled React 18.2.0 runtime and
ReactDOM attributions are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and
[the vendored license file](clients/web/vendor/THIRD_PARTY_LICENSES.txt).
