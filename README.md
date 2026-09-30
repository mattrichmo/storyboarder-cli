# Storyboarder
### A local production desk for stories, references, and frames.

A runnable Python application with a scriptable CLI, a full-screen multi-page terminal
interface, and an offline React client served from loopback. All three use the same
application services and the same project-local SQLite database. The graph canvas is
implemented here with React cards, native SVG edges, and internal interaction/layout
code—not a graph-editor dependency.

**Version 1.0.0 · Python 3.11+ · MIT**

![The project overview](docs/images/overview-desktop.png)

## Start here

Unzip the source package and open a terminal in the `storyboarder/` directory.

**macOS / Linux**

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
storyboarder workspace init ./stories
storyboarder ui --workspace ./stories
```

**Windows PowerShell**

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\storyboarder.exe workspace init .\stories
.\.venv\Scripts\storyboarder.exe ui --workspace .\stories
```

The app prints `http://127.0.0.1:7430` and attempts to open your browser. Use the
printed address if the browser does not open. Keep the terminal running. Ctrl+C
stops the server. There is no login or remote account. Use `--port 7431` to choose
another port and `--no-browser` to suppress browser launch.

**Installation needs the declared Python dependencies**, normally downloaded by pip.
After installation the core authoring/export application has no network requirement.
The compiled frontend and licensed React runtime are already included: **end users
do not need Node, npm, a frontend build, a CDN, or provider credentials**. For a fully
offline first installation, prepare a wheelhouse beforehand; see
[installation and release](docs/DEVELOPMENT.md).

An installable wheel is also provided in `dist/`. Install it with `python -m pip
install dist/storyboarder_desk-1.0.0-py3-none-any.whl`, then use the same commands.

## Open a useful example

```sh
python scripts/create_demo.py ./demo-stories
storyboarder ui --workspace ./demo-stories
```

This creates **Winter Station**, a fictional project with a guide, two scenes, six
shots, exact reference assignments, typed relationships, frame candidates, and a
duplicate intake example. Its graphic reference panels are explicitly labelled demo
art, not photographs or production-ready frames. Run against a fresh demo workspace;
the seed script refuses to overwrite an existing project.

## Three ways to work

```sh
# Full-screen terminal authoring desk
storyboarder tui --workspace ./stories

# A standalone portable project; workspace registration is optional
storyboarder project create ./my-film --title "My Film"
storyboarder ui --project ./my-film

# Scriptable operations (all groups have --help)
storyboarder --project ./my-film asset create --title "Mara" --type character --json
storyboarder --project ./my-film import ./references --recursive --json
storyboarder --project ./my-film shot list --json
storyboarder --project ./my-film doctor --hashes --json
```

Running bare `storyboarder` opens the terminal desk only in an interactive terminal;
in a non-interactive shell it prints help. Project discovery works from a project
folder or its descendants. Explicit `--project` and `--workspace` are supported
before or after command groups. Machine output is opt-in `--json`.

## What is implemented

| Surface | Included workflows |
|---|---|
| Workspace / projects | Create, open, register, discover, switch, relocate, health, backup and restore |
| Intake / library | Managed image import, explicit recursive scan, exact-hash duplicates, review, tags, aliases, asset assignment, primary image, merge and relationships |
| Story authoring | Ordered sequences/scenes/shots, revisions, typed fields, context append/replace/exclude, source provenance, location overrides and exact shot references |
| Frames | Separate uploaded/managed candidates, version history, side-by-side comparison, draft/selected/approved/archived states |
| Custom canvas | Story flow, asset network and scene board; filtering, native SVG edges, pan/zoom, pointer/keyboard arrangement, typed links, explicit reorder, collapse/hide and named layouts |
| Delivery | Deterministic JSON/Markdown packages, exact selected media, manifest hashes, HTML/PDF/PNG boards and ZIP archives |
| External scripts | Explicit trusted registration, versioned requests/results, bounded execution, logs, cancellation, explicit retry, validation, pending review and idempotent approval |

Every canonical mutation runs through the shared application layer. Canvas positions
are separate from story relationships. A reference image never silently becomes an
approved frame. A stale write produces a conflict instead of replacing newer work.

## Portable project structure

```text
stories/
  workspace.toml                    # optional navigator, no story database
  projects/
    winter-station/
      project.toml                  # identity and rebuildable title hint
      .storyboarder/
        storyboard.sqlite3          # canonical data, WAL during use
        cache/                      # rebuildable thumbnails
        staging/                    # bounded import/export staging
        jobs/                       # requests, validated pending results, logs
      media/
        items/<media-id>/<name>      # managed source images
        frames/<frame-id>/<name>     # imported frame files
      exports/
        scenes/                     # self-contained data bundles
        boards/                     # presentation exports
        backups/                    # portable recovery archives
```

Database media paths are relative to the project. Original import paths are metadata
only. Stop writers before moving/copying an entire live folder, or use the built-in
SQLite-consistent backup command. A copy retains its project identity; register the
new path to make it the navigator's preferred copy.

## Documentation

Start with [the creator walkthrough](docs/CREATOR_GUIDE.md).

- [Product contract](docs/PRODUCT_CONTRACT.md), [architecture](docs/ARCHITECTURE.md), and [design brief](docs/DESIGN_BRIEF.md)
- [CLI reference](docs/CLI.md), [terminal desk](docs/TUI.md), and [canvas / accessibility](docs/CANVAS.md)
- [Context and media](docs/CONTEXT_AND_MEDIA.md), [exports and recovery](docs/EXPORTS_AND_RECOVERY.md)
- [Local API](docs/API.md), [OpenAPI JSON](docs/openapi.json), and [command schema catalog](docs/commands.json)
- [External script contract](docs/AUTOMATION.md) and [security boundaries](docs/SECURITY.md)
- [Development / packaging](docs/DEVELOPMENT.md), [implementation matrix](docs/IMPLEMENTATION.md), and [verification report](docs/TEST_REPORT.md)

## Development

Node is needed only to rebuild the frontend. Node 20+ is recommended for development;
the checked-in runtime contains React 18.2.0 and ReactDOM 18.2.0 with their licenses.

```sh
python -m pip install -e '.[dev]'
cd clients/web
npm ci
npm run build
npm test
cd ../..
python -m pytest
```

`npm run dev` watches TypeScript/CSS and rebuilds the packaged static folder. Start
`storyboarder ui` separately and refresh the browser after a rebuild. There is no
external dev server or permissive CORS proxy. `python scripts/build_release.py`
builds the wheel and source distribution from the checked-in frontend.

The local `stories/` workspace is ignored by Git so project databases, media, and
source materials are not accidentally added to the application repository. Keep
production projects there only as local working data; use `examples/` for disposable
demo output.

## Scope and important boundaries

This is local authoring software, not a hosted service. Do not expose its server
through a tunnel, reverse proxy, LAN bind, or public deployment. An external script
is a **trusted local executable with your OS permissions**, not sandboxed code.
The protocol does not give it a database handle; it cannot make malicious code safe.

Cloud sync, live collaboration, accounts, in-app drawing, automatic recognition,
script breakdown, video/audio ingestion, and bundled generation providers are
intentionally outside this release. The full-text HTML/JSON export is authoritative;
fixed-size PDF/image panels abbreviate long notes and use portable built-in fonts.
See the verification report for exactly what ran and the remaining platform/test
limitations. This package does not claim third-party production certification.

## License

New application code is MIT-licensed; see [LICENSE](LICENSE). Vendored runtime
attributions are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and
`clients/web/vendor/THIRD_PARTY_LICENSES.txt`. No font files are distributed.
