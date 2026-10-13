# CLI reference

`storyboarder` is the installed command. This reference includes lifecycle commands
and all **150 commands** in the shared application catalog. The flag tables are
generated from that catalog. Run `storyboarder --help`, `storyboarder GROUP --help`,
or `storyboarder GROUP ACTION --help` for the commands in your installed checkout.

The browser includes the dedicated **Blocking & lighting** editor. The CLI exposes its
spatial plan, binding, review, diagram, package, and recovery commands; the TUI does not
include this visual editor. Source documents and provenance remain CLI/local API previews.
The TUI has a focused Observation coverage page for exact source pins and contract
authoring, while dedicated visual workspaces for these source workflows remain unfinished.
See [implementation status](V2_IMPLEMENTATION_STATUS.md).

## Project selection and common options

| Option | Behavior |
|---|---|
| `--project`, `-p PATH` | Select a portable project folder explicitly. |
| `--workspace`, `-w PATH` | Use the workspace's current project. |
| `--json` | Emit stable, indented JSON results; errors go to stderr. |
| `--jsonl` | Emit one result per line; pagination metadata and errors go to stderr. |
| `--no-color` | Disable terminal colors. |
| `--verbose` | Enable debug logging; root option. |
| `--version` | Print the application version; root option. |

Project/workspace and output options work before or after command groups.
Without an explicit selection, project commands discover the current project from
the working directory or its ancestors. A workspace remembers its selected project;
projects remain directly openable without a workspace.

## Lifecycle and convenience commands

```text
storyboarder workspace init [PATH]
storyboarder workspace list --workspace PATH
storyboarder workspace register PROJECT_PATH --workspace PATH
storyboarder workspace switch PROJECT_ID --workspace PATH
storyboarder project create NEW_PATH --title TITLE [--workspace PATH]
storyboarder project create --workspace PATH --slug FOLDER --title TITLE
storyboarder project open PROJECT_PATH [--workspace PATH]
storyboarder project show --project PATH
storyboarder project list --workspace PATH
storyboarder project switch PROJECT_ID --workspace PATH
storyboarder ui [--workspace PATH | --project PATH] [--port 7430] [--no-browser]
storyboarder tui [--workspace PATH | --project PATH]
storyboarder import FILE_OR_FOLDER --project PATH [--recursive]
storyboarder compose OWNER_ID --project PATH
storyboarder doctor --project PATH [--hashes]
storyboarder backup --project PATH
storyboarder restore BACKUP_ZIP NEW_DESTINATION [--workspace PATH]
storyboarder script register NAME --command JSON_ARGV [--timeout SECONDS] [--env-keys NAMES]
storyboarder script list
storyboarder script remove NAME
```

Running bare `storyboarder` opens the TUI in an interactive terminal and prints help
otherwise. `ui` serves the bundled app on `127.0.0.1`; keep its terminal running and
press Ctrl+C to stop it. Restore requires a new destination. Workspace project
creation requires a title and folder slug.

Script registration accepts a JSON argument array, not a shell command string. It also
accepts `--description`, `--max-file-bytes`, and `--max-output-bytes`. Registration
explicitly trusts a local executable with your OS permissions; see [automation](AUTOMATION.md).
`import`, `compose`, `doctor`, and `backup` are convenience entry points to shared services.

## Output, payloads, and exit codes

Every shared catalog command accepts `--payload '{"field":"value"}'` or
`--payload @path/to/input.json`. Lifecycle and convenience commands use their own
arguments rather than `--payload`. Named flags override payload fields. Structured
JSON fields also accept `@path/to/file.json`. Tags accept comma-separated strings or
arrays in a JSON payload. Boolean options support `--flag` and `--no-flag`.

```sh
storyboarder --project ./stories/projects/my-film shot list --limit 50 --offset 0 --json
storyboarder --project ./stories/projects/my-film shot list --jsonl
storyboarder --project ./stories/projects/my-film asset create --payload '{"title":"Brass key","type":"prop"}' --json
```

JSON output has deterministic key ordering and contains no terminal table. JSONL
list results emit records individually; a result with `next_offset` also emits paging
metadata on stderr. Consult `total`, `limit`, `offset`, and `next_offset` for paginated
results. Record IDs are returned by create/import/list/show operations.

When a command requires `--revision`, use the actual revision you just read. A
creative document `version_id` identifies an immutable draft; the document's row
`revision` is a separate concurrency token. `document revise` takes a node ID and
the last-read **document revision**. Revising a draft does not repoint existing source links.

| Exit code | Meaning |
|---|---|
| `0` | Operation or help completed successfully. |
| `1` | Validation, domain, input, or I/O failure. |
| `2` | Record/path not found, or argument parsing failure. |
| `3` | Revision or contract conflict, including already-existing contracts. Re-read before retrying. |
| `4` | Unhealthy doctor result, partial import, or failed job result. |
| `130` | Interrupted. |

Exit `0` means the requested operation completed. For observation validation, coverage,
or import preview, inspect structured `status`, `ready`, `findings`, and loss fields to
understand stale, unresolved, or conflicting records; a successful report is not a claim
of semantic or visual verification. An explicitly aborted import and an idempotent
already-present import can also complete without changing project data.

With JSON output enabled, errors use an `error` object on stderr. The command schema
is also available as [commands.json](commands.json). See [format profiles](FORMATS.md)
for source import limits and [the README](../README.md#cli-workflows) for a walkthrough.

Observation planning commands accept JSON objects through `--payload`. `observation.coverage`
uses `{"request":{"anchors":[...]}}` with exact document/version/node/hash pins; `limit`
and `offset` default to 500 and 0. `observation.create-group` uses
`{"request":{"items":[...]}}`, with caller-supplied shot, contract, and edge UUIDs and
the scene revision read before planning. The planner accepts up to 50 items and 512 total
source-edge references per call. Both commands are JSON/API-safe and remain agent-only
(`browser=false`). Contract-specific 404 and 409 errors use the same CLI exit mapping as
their HTTP status: missing contract exits 2; already-exists, stale-revision, and reviewed
basis-token conflicts exit 3. Other contract validation failures keep the legacy exit 1.

`observation.plan-export` returns a portable exact-history plan in the `plan` property.
`observation.plan-import-preview` accepts that JSON object as `plan`, plus optional
contract-ID-to-choice `choices`; it is read-only and returns an explicit reconciliation
receipt. `observation.plan-import-apply` takes the unchanged `plan` and exact `preview`
receipt. All three commands are available in the CLI and JSON API, and appear in the TUI
Coverage page. The CLI export result already wraps the sidecar under `plan`; save that
JSON as `export.json` and pass `--payload @export.json` to preview. Apply uses a payload
with both the unchanged `plan` object and returned `preview` receipt. Export and import preserve
IDs, immutable history, operations, timestamps, and exact pins. Observation-plan import
preview/apply API requests allow 50 MiB for plans up to the application’s 48 MiB limit
and their command envelope; other JSON API requests remain capped at 2 MiB. These
commands are API-safe and remain outside the browser command catalog.

`observation.rebase-preview` accepts `contract_id` and the complete proposed `contract`
body. It is read-only and returns saved/current basis values, exact requested pins, and an
opaque `expected_basis_sha256` rebase-review token. Pass that exact token with the same
body and header `revision` to `observation.rebase`. If the reviewed basis or contract
revision changes before the write, the command returns a 409 contract conflict (CLI exit
3); preview again before retrying. Both commands are JSON/API-safe and agent-only.

## Spatial blocking and lighting

The browser's **Blocking & lighting** workspace is a visual editor for a scene
plan. Open a scene, choose a blank plan or **Doorway example**, place actor, prop,
and wall proxies, then add marks, cameras, lights, modifiers, beats, and timed
tracks. The scrubber previews authored timing. **Review & save** creates a new
immutable plan version. The full-screen TUI does not include this visual editor.

The CLI works with the same project data. It starts with an existing project and
scene; use the built-in Doorway fixture for a complete offline example. Set
`PROJECT` to an existing project folder and `SCENE_ID` to one of its scenes. The
commands below read the current project revision and create a fresh setup ID:

```sh
PROJECT_REVISION=$(storyboarder --project "$PROJECT" project show --json \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["revision"])')
SETUP_ID=$(python3 -c 'import uuid; print(uuid.uuid4())')
storyboarder --project "$PROJECT" spatial fixture --scene-id "$SCENE_ID" --json > doorway-plan.json
```

`spatial fixture` prints the Doorway to table plan payload without changing the
project. For `spatial create-preview` and `spatial create`, the generic
`--payload` is the whole command request: wrap the plan under a nested `payload`
key alongside a new UUID `setup_id` and the current `expected_project_revision`
from `project show`. The commands above set `SETUP_ID` and `PROJECT_REVISION`;
this builds the request from the fixture:

```sh
python3 - "$SETUP_ID" "$PROJECT_REVISION" <<'PY'
import json, sys
plan = json.load(open("doorway-plan.json", encoding="utf-8"))
request = {
    "setup_id": sys.argv[1],
    "expected_project_revision": int(sys.argv[2]),
    "payload": plan,
}
with open("create-request.json", "w", encoding="utf-8") as output:
    json.dump(request, output)
PY

storyboarder --project "$PROJECT" spatial create-preview \
  --payload @create-request.json --json > create-preview.json

python3 - <<'PY'
import json
with open("create-request.json", encoding="utf-8") as source:
    request = json.load(source)
with open("create-preview.json", encoding="utf-8") as source:
    preview = json.load(source)
request["expected_basis_sha256"] = preview["expected_basis_sha256"]
with open("create-apply.json", "w", encoding="utf-8") as output:
    json.dump(request, output)
PY

storyboarder --project "$PROJECT" spatial create \
  --payload @create-apply.json --json
```

The saved response identifies the immutable `version.id`; `spatial history`,
`spatial show`, and `spatial diff` inspect saved versions. To edit a plan, send
its current setup `revision` and the proposed full plan to
`spatial revise-preview`, then apply with the exact returned basis token.
Restore a previous version with `spatial restore-preview` and `spatial restore`;
a restore creates another version rather than erasing history.

A shot binding pins an exact `setup_version_id`, camera plan, and action-time
sample. Prepare this request with IDs and revision from the project:

```json
{
  "shot_id": "SHOT_ID",
  "expected_shot_revision": 1,
  "binding_id": "NEW_BINDING_UUID",
  "binding": {
    "schema": "storyboarder.spatial-binding/v1",
    "status": "active",
    "setup_version_id": "SETUP_VERSION_ID",
    "camera_plan_id": "CAMERA_PLAN_ID",
    "sample": {"kind": "instant", "time_us": 0},
    "time_mapping": {"kind": "none"},
    "notes": "Doorway demo shot"
  }
}
```

Pass it to `spatial bind-preview`; save with `spatial bind` using the returned
`expected_basis_sha256`:

```sh
storyboarder --project "$PROJECT" spatial bind-preview \
  --payload @binding-request.json --json > binding-preview.json
# Add binding-preview.json's expected_basis_sha256 to the request.
storyboarder --project "$PROJECT" spatial bind \
  --payload @binding-apply.json --json
```

When action time maps to shot time, record that mapping explicitly. The binding
does not change the shot's written duration. Rebinding is also preview-and-apply;
`spatial binding-show` and `spatial binding-history` inspect its versions.

An authored spatial review requires an existing v1 observation contract and a
binding for the same shot. Submit a `storyboarder.observation-contract/v2`
review that pins those exact version IDs. For the first review,
`expected_previous_number` is `0`; otherwise read the latest number with
`observation spatial-review-history`.

```json
{
  "shot_id": "SHOT_ID",
  "expected_previous_number": 0,
  "review": {
    "schema": "storyboarder.observation-contract/v2",
    "observation_version_id": "OBSERVATION_VERSION_ID",
    "binding_version_id": "BINDING_VERSION_ID",
    "reviewed": {
      "blocking": true,
      "timing": true,
      "camera_coverage": true,
      "schematic_lighting": true
    },
    "assumptions": [],
    "unresolved": [],
    "notes": "Doorway blocking and coverage reviewed"
  }
}
```

`observation spatial-review-preview` checks the proposed review;
`observation spatial-review` saves it with the exact preview token:

```sh
storyboarder --project "$PROJECT" observation spatial-review-preview \
  --payload @review-request.json --json > review-preview.json
# Add review-preview.json's expected_basis_sha256 to the request.
storyboarder --project "$PROJECT" observation spatial-review \
  --payload @review-apply.json --json
```

`observation spatial-review-show`, `observation spatial-review-validate`, and
`observation spatial-review-history` inspect it. This is an authored checklist,
not physical verification or storyboard-frame approval; it leaves the v1
observation contract unchanged.

Export diagrams for a specific immutable plan with `spatial diagram-export`
and `--version-id VERSION_ID --format all`. Use
`--binding-version-id BINDING_VERSION_ID` to export the exact shot binding, and
optionally supply sample times in microseconds. For explicit times, put the full
command payload in a JSON file because `times_us` is an array:

```json
{"version_id":"VERSION_ID","times_us":[0,4000000],"format":"all"}
```

Pass that file with `spatial diagram-export --payload @diagram-request.json`.
When `times_us` is omitted for a version export, the diagram uses the default
sample at `0`; for a binding export, it uses the binding's pinned sample. The
command returns generated SVG, PNG, PDF, and JSON files under the project's
`exports/boards` folder.

For portable transfer, `spatial plan-export` with `--setup-id SETUP_ID` and
`--scope full-history` writes a native spatial ZIP with setup versions and their
history closure, including associated bindings and reviews. Use the
`native-spatial.zip` path in the command result. Put its base64 contents in an
`archive_base64` field in `import-request.json`, then preview and apply:

```sh
storyboarder --project "$PROJECT" spatial plan-import-preview \
  --payload @import-request.json --json > import-preview.json
# Keep the package and mode unchanged; add import-preview.json's basis token.
storyboarder --project "$PROJECT" spatial plan-import-apply \
  --payload @import-apply.json --json
```

**Exact** import preserves IDs and history and requires the same project
identity. **Copy** creates a new setup root in another project; provide a new
setup UUID and any scene, asset, or media mappings needed to match that project's
IDs. Copy mode does not carry shot bindings or reviews.

For recovery, `spatial doctor` checks spatial data without changing it.
`spatial backup` creates a project backup that includes spatial data.
`spatial backup-restore --archive ARCHIVE --destination NEW_PATH` restores into
a new folder and checks spatial integrity before it completes. In the browser,
the editor can recover an unsaved local draft from browser storage.

Lighting, camera coverage, and floor-plan diagrams communicate authored intent.
They do not calculate photometric exposure, rendered light transport, shadows,
surveyed scale, or physical safety.

## Command catalog

Flags below are command-specific; common options and `--payload` are also available.
A required field must be supplied even when its table shows a default. `—` means no
catalog default or choices. The CLI always supports these commands; commands marked
as local-file operations require explicit filesystem access and are not exposed through
the generic browser command endpoint.

[asset](#asset) · [sequence](#sequence) · [scene](#scene) · [shot](#shot) · [project](#project) · [entity](#entity) · [story](#story) · [link](#link) · [assignment](#assignment) · [context](#context) · [frame](#frame) · [canvas](#canvas) · [media](#media) · [intake](#intake) · [composition](#composition) · [export](#export) · [cache](#cache) · [job](#job) · [document](#document) · [screenplay](#screenplay) · [edit](#edit) · [provenance](#provenance) · [coverage](#coverage) · [observation](#observation) · [annotation](#annotation) · [spatial](#spatial)

### `asset`

#### `asset create` — New library item

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--title` | yes | text | Title | — |
| `--description` | no | textarea | Description | — |
| `--notes` | no | textarea | Notes | — |
| `--type` | no | select | Item type | default: `"reference"`; choices: `character`, `location`, `prop`, `reference` |
| `--tags` | no | tags | Tags (comma-separated) | — |
| `--aliases` | no | tags | Aliases (comma-separated) | — |

#### `asset update` — Edit library item

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Library item (record from assets) | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |
| `--title` | no | text | Title | — |
| `--description` | no | textarea | Description | — |
| `--notes` | no | textarea | Notes | — |
| `--type` | no | select | Item type | choices: `character`, `location`, `prop`, `reference` |
| `--tags` | no | tags | Tags (comma-separated) | — |
| `--aliases` | no | tags | Aliases (comma-separated) | — |

#### `asset list` — Find library items

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--query` | no | text | Search | — |
| `--tag` | no | text | Tag | — |
| `--asset-type` | no | text | Item type | choices: `character`, `location`, `prop`, `reference` |
| `--parent-id` | no | text | Place under | — |
| `--archived` | no | boolean | Include archived | — |
| `--limit` | no | integer | Maximum results | default: `200` |
| `--offset` | no | integer | Start at | default: `0` |

#### `asset show` — View library item details

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Library item (record from assets) | — |

#### `asset attach` — Add image to library item

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--asset-id` | yes | text | Library item (record from assets) | — |
| `--media-id` | yes | text | Image (record from media) | — |

#### `asset primary` — Set cover image

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Library image (record from asset_media) | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |

#### `asset detach` — Remove image from library item

Changes project data or creates output. Removes, archives, retires, or explicitly runs/approves an operation; review the selected record.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Library image (record from asset_media) | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |

#### `asset merge` — Combine library items

Changes project data or creates output. Removes, archives, retires, or explicitly runs/approves an operation; review the selected record.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--source-id` | yes | text | Item to combine (record from assets) | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |
| `--target-id` | yes | text | Keep this item (record from assets) | — |
| `--target-revision` | yes | integer | Version check | — |

### `sequence`

#### `sequence create` — New sequence

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--title` | yes | text | Title | — |
| `--description` | no | textarea | Description | — |
| `--notes` | no | textarea | Notes | — |
| `--location-id` | no | text | Location. Leave blank to use the location set higher in the story. (record from locations) | — |
| `--time` | no | text | Time | — |
| `--framing` | no | text | Framing | — |
| `--camera` | no | textarea | Camera | — |
| `--constraints` | no | textarea | Constraints | — |
| `--arc` | no | textarea | Arc | — |
| `--tone` | no | textarea | Tone | — |

#### `sequence update` — Edit sequence

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Choose item (record from sequences) | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |
| `--title` | no | text | Title | — |
| `--description` | no | textarea | Description | — |
| `--notes` | no | textarea | Notes | — |
| `--location-id` | no | text | Location. Leave blank to use the location set higher in the story. (record from locations) | — |
| `--time` | no | text | Time | — |
| `--framing` | no | text | Framing | — |
| `--camera` | no | textarea | Camera | — |
| `--constraints` | no | textarea | Constraints | — |
| `--arc` | no | textarea | Arc | — |
| `--tone` | no | textarea | Tone | — |

#### `sequence list` — Find sequences

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--query` | no | text | Search | — |
| `--tag` | no | text | Tag | — |
| `--asset-type` | no | text | Item type | choices: `character`, `location`, `prop`, `reference` |
| `--parent-id` | no | text | Place under | — |
| `--archived` | no | boolean | Include archived | — |
| `--limit` | no | integer | Maximum results | default: `200` |
| `--offset` | no | integer | Start at | default: `0` |

#### `sequence show` — View sequence details

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Choose item (record from sequences) | — |

### `scene`

#### `scene create` — New scene

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--title` | yes | text | Title | — |
| `--parent-id` | yes | text | Parent sequence (record from sequences) | — |
| `--description` | no | textarea | Description | — |
| `--notes` | no | textarea | Notes | — |
| `--location-id` | no | text | Location. Leave blank to use the location set higher in the story. (record from locations) | — |
| `--time` | no | text | Time | — |
| `--framing` | no | text | Framing | — |
| `--camera` | no | textarea | Camera | — |
| `--constraints` | no | textarea | Constraints | — |
| `--summary` | no | textarea | Summary | — |
| `--continuity` | no | textarea | Continuity | — |

#### `scene update` — Edit scene

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Choose item (record from scenes) | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |
| `--title` | no | text | Title | — |
| `--description` | no | textarea | Description | — |
| `--notes` | no | textarea | Notes | — |
| `--location-id` | no | text | Location. Leave blank to use the location set higher in the story. (record from locations) | — |
| `--time` | no | text | Time | — |
| `--framing` | no | text | Framing | — |
| `--camera` | no | textarea | Camera | — |
| `--constraints` | no | textarea | Constraints | — |
| `--summary` | no | textarea | Summary | — |
| `--continuity` | no | textarea | Continuity | — |

#### `scene list` — Find scenes

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--query` | no | text | Search | — |
| `--tag` | no | text | Tag | — |
| `--asset-type` | no | text | Item type | choices: `character`, `location`, `prop`, `reference` |
| `--parent-id` | no | text | Place under | — |
| `--archived` | no | boolean | Include archived | — |
| `--limit` | no | integer | Maximum results | default: `200` |
| `--offset` | no | integer | Start at | default: `0` |

#### `scene show` — View scene details

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Choose item (record from scenes) | — |

### `shot`

#### `shot create` — New shot

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--title` | yes | text | Title | — |
| `--parent-id` | yes | text | Parent scene (record from scenes) | — |
| `--description` | no | textarea | Description | — |
| `--notes` | no | textarea | Notes | — |
| `--location-id` | no | text | Location. Leave blank to use the location set higher in the story. (record from locations) | — |
| `--time` | no | text | Time | — |
| `--framing` | no | text | Framing | — |
| `--camera` | no | textarea | Camera | — |
| `--constraints` | no | textarea | Constraints | — |
| `--number` | no | text | Number | — |
| `--action` | no | textarea | Action | — |
| `--dialogue` | no | textarea | Dialogue | — |
| `--duration` | no | number | Duration (seconds) | — |
| `--continuity` | no | textarea | Continuity | — |

#### `shot update` — Edit shot

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Choose item (record from shots) | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |
| `--title` | no | text | Title | — |
| `--description` | no | textarea | Description | — |
| `--notes` | no | textarea | Notes | — |
| `--location-id` | no | text | Location. Leave blank to use the location set higher in the story. (record from locations) | — |
| `--time` | no | text | Time | — |
| `--framing` | no | text | Framing | — |
| `--camera` | no | textarea | Camera | — |
| `--constraints` | no | textarea | Constraints | — |
| `--number` | no | text | Number | — |
| `--action` | no | textarea | Action | — |
| `--dialogue` | no | textarea | Dialogue | — |
| `--duration` | no | number | Duration (seconds) | — |
| `--continuity` | no | textarea | Continuity | — |

#### `shot list` — Find shots

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--query` | no | text | Search | — |
| `--tag` | no | text | Tag | — |
| `--asset-type` | no | text | Item type | choices: `character`, `location`, `prop`, `reference` |
| `--parent-id` | no | text | Place under | — |
| `--archived` | no | boolean | Include archived | — |
| `--limit` | no | integer | Maximum results | default: `200` |
| `--offset` | no | integer | Start at | default: `0` |

#### `shot show` — View shot details

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Choose item (record from shots) | — |

#### `shot link-source` — Link screenplay source

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--shot-id` | yes | text | Shot Id (record from shots) | — |
| `--node-id` | yes | text | Source element | — |
| `--notes` | no | textarea | Notes | — |

#### `shot sources` — Inspect shot sources

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Choose item (record from shots) | — |

### `project`

#### `project update` — Edit project direction

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Choose item (record from projects) | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |
| `--title` | no | text | Title | — |
| `--description` | no | textarea | Description | — |
| `--notes` | no | textarea | Notes | — |
| `--location-id` | no | text | Location. Leave blank to use the location set higher in the story. (record from locations) | — |
| `--time` | no | text | Time | — |
| `--framing` | no | text | Framing | — |
| `--camera` | no | textarea | Camera | — |
| `--constraints` | no | textarea | Constraints | — |
| `--premise` | no | textarea | Premise | — |
| `--visual-style` | no | textarea | Visual Style | — |

#### `project doctor` — Check project health

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--hashes` | no | boolean | Check image contents | — |

#### `project backup` — Back up project

Changes project data or creates output.

No command-specific flags.

#### `project sync` — Update project title

Changes project data or creates output.

No command-specific flags.

### `entity`

#### `entity update` — Edit item details

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Choose item (record from entities) | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |
| `--changes` | yes | json | Changes | — |

#### `entity usage` — See where an item is used

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Choose item (record from entities) | — |

#### `entity archive` — Archive item

Changes project data or creates output. Removes, archives, retires, or explicitly runs/approves an operation; review the selected record.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Choose item (record from entities) | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |

#### `entity restore` — Restore item

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Choose item (record from entities) | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |

#### `entity delete` — Delete item

Changes project data or creates output. Removes, archives, retires, or explicitly runs/approves an operation; review the selected record.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Choose item (record from entities) | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |

### `story`

#### `story move` — Move or reorder a story item

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Story item (record from story) | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |
| `--position` | yes | integer | New position | — |
| `--parent-id` | no | text | Place under (optional) (record from parents) | — |

### `link`

#### `link remove` — Remove connection

Changes project data or creates output. Removes, archives, retires, or explicitly runs/approves an operation; review the selected record.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Connection (record from links) | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |

#### `link create` — Connect library items

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--source-id` | yes | text | First item (record from assets) | — |
| `--target-id` | yes | text | Second item (record from assets) | — |
| `--relation` | yes | select | How they are connected | choices: `appears-at`, `alternate-view-of`, `wears`, `part-of`, `related-to` |

#### `link list` — List connections

Read-only operation.

No command-specific flags.

### `assignment`

#### `assignment remove` — Remove shot reference

Changes project data or creates output. Removes, archives, retires, or explicitly runs/approves an operation; review the selected record.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Shot reference (record from assignments) | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |

#### `assignment create` — Use a reference in a shot

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--shot-id` | yes | text | Shot (record from shots) | — |
| `--asset-id` | yes | text | Library item (record from assets) | — |
| `--role` | yes | select | How it appears in the shot | default: `"reference"`; choices: `subject`, `setting-reference`, `costume`, `prop`, `reference` |
| `--media-id` | no | text | Choose a specific image (optional). Choose an image from this library item. Leave blank if any of its images may be used. (record from asset_images) | — |

#### `assignment update` — Edit shot reference

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Shot reference (record from assignments) | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |
| `--role` | yes | select | How it appears in the shot | choices: `subject`, `setting-reference`, `costume`, `prop`, `reference` |
| `--media-id` | no | text | Choose a specific image (record from asset_images) | — |

#### `assignment list` — List shot references

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--shot-id` | no | text | Shot Id (record from shots) | — |

### `context`

#### `context remove` — Remove direction note

Changes project data or creates output. Removes, archives, retires, or explicitly runs/approves an operation; review the selected record.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Direction note (record from context_blocks) | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |

#### `context put` — Add or edit a direction note

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--owner-id` | yes | text | Apply direction to (record from story) | — |
| `--key` | yes | text | Topic | — |
| `--operation` | yes | select | How it changes earlier direction | default: `"append"`; choices: `append`, `replace`, `exclude` |
| `--content` | no | textarea | Direction notes | — |
| `--revision` | no | integer | Version check | — |

#### `context resolve` — Preview story direction

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--owner-id` | yes | text | Apply direction to (record from story) | — |

#### `context list` — List direction notes

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--owner-id` | no | text | Owner Id (record from story) | — |

### `frame`

#### `frame remove` — Remove storyboard image

Changes project data or creates output. Removes, archives, retires, or explicitly runs/approves an operation; review the selected record.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Storyboard image (record from frames) | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |

#### `frame add` — Add storyboard image from file

Changes project data or creates output. Local-file operation; use the CLI or the dedicated upload API where available.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--shot-id` | yes | text | Shot (record from shots) | — |
| `--path` | yes | text | Image file | — |
| `--notes` | no | textarea | Notes | — |

#### `frame attach` — Use project image as storyboard frame

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--shot-id` | yes | text | Shot (record from shots) | — |
| `--media-id` | yes | text | Image (record from media) | — |
| `--notes` | no | textarea | Notes | — |

#### `frame state` — Update storyboard image status

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Storyboard image (record from frames) | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |
| `--state` | yes | select | Status | choices: `draft`, `selected`, `approved`, `archived` |

#### `frame list` — List storyboard images

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--shot-id` | no | text | Shot Id (record from shots) | — |

### `canvas`

#### `canvas remove` — Remove saved layout

Changes project data or creates output. Removes, archives, retires, or explicitly runs/approves an operation; review the selected record.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Saved arrangement (record from layouts) | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |

#### `canvas graph` — View story connections

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--mode` | no | select | View | default: `"story"`; choices: `story`, `assets`, `scene` |
| `--query` | no | text | Search | — |
| `--asset-type` | no | text | Item type | choices: `character`, `location`, `prop`, `reference` |
| `--tag` | no | text | Tag | — |
| `--relation` | no | select | Connection type | choices: `appears-at`, `alternate-view-of`, `wears`, `part-of`, `related-to` |
| `--scene-id` | no | text | Scene (record from scenes) | — |
| `--sequence-id` | no | text | Sequence (record from sequences) | — |
| `--limit` | no | integer | Maximum cards | default: `250` |

#### `canvas neighbors` — See connected items

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Choose item (record from entities) | — |

#### `canvas save` — Save canvas arrangement

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--name` | yes | text | Name | — |
| `--mode` | yes | select | View | choices: `story`, `assets`, `scene` |
| `--positions` | yes | json | Positions | — |
| `--settings` | no | json | Settings | — |
| `--revision` | no | integer | Existing layout revision | — |
| `--layout-id` | no | select | Saved arrangement (record from layouts) | — |

#### `canvas show` — Show saved arrangement

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Saved arrangement (record from layouts) | — |

#### `canvas list` — List saved arrangements

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--mode` | no | text | Mode | choices: `story`, `assets`, `scene` |

### `media`

#### `media import` — Import file or folder

Changes project data or creates output. Local-file operation; use the CLI or the dedicated upload API where available.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--path` | yes | text | File or folder path | — |
| `--recursive` | no | boolean | Include nested folders | — |

#### `media tags` — Edit image tags

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Image (record from media) | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |
| `--tags` | yes | tags | Tags (comma-separated) | — |

#### `media show` — View image details

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Image (record from media) | — |

#### `media list` — List images

Read-only operation.

No command-specific flags.

### `intake`

#### `intake accept` — Add image to library

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Imported image (record from intake) | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |
| `--asset-id` | no | text | Add to an existing item (record from assets) | — |
| `--create-title` | no | text | Or create a new item | — |
| `--create-type` | no | select | New item type | default: `"reference"`; choices: `character`, `location`, `prop`, `reference` |
| `--tags` | no | tags | Tags (comma-separated) | — |

#### `intake discard` — Remove image from intake

Changes project data or creates output. Removes, archives, retires, or explicitly runs/approves an operation; review the selected record.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Imported image (record from intake) | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |

#### `intake list` — List image intake

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--state` | no | text | State | choices: `pending`, `accepted`, `discarded` |

### `composition`

#### `composition preview` — Preview storyboard

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--owner-id` | yes | text | Apply direction to (record from story) | — |

### `export`

#### `export bundle` — Create project handoff package

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--owner-id` | yes | text | Apply direction to (record from story) | — |
| `--include-media` | no | boolean | Include reference images | default: `true` |

#### `export board` — Export storyboard

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--owner-id` | yes | text | Apply direction to (record from story) | — |
| `--format` | no | select | File format | default: `"all"`; choices: `html`, `pdf`, `png`, `all` |
| `--approved-only` | no | boolean | Use approved storyboard images only | — |

### `cache`

#### `cache rebuild` — Rebuild image previews

Changes project data or creates output.

No command-specific flags.

#### `cache clear` — Clear image previews

Changes project data or creates output.

No command-specific flags.

### `job`

#### `job create` — Prepare an image request

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--script` | yes | text | Image tool (record from scripts) | — |
| `--target` | yes | select | Create | default: `"asset"`; choices: `asset`, `frame` |
| `--shot-id` | no | text | Shot (for a storyboard image) (record from shots) | — |
| `--title` | yes | text | Name for the result | — |
| `--asset-type` | no | select | Library item type | default: `"reference"`; choices: `character`, `location`, `prop`, `reference` |
| `--prompt` | no | textarea | Instructions for the tool | — |

#### `job run` — Run image tool

Changes project data or creates output. Removes, archives, retires, or explicitly runs/approves an operation; review the selected record.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Run (record from jobs) | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |

#### `job cancel` — Stop image tool

Changes project data or creates output. Removes, archives, retires, or explicitly runs/approves an operation; review the selected record.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Run (record from jobs) | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |

#### `job retry` — Run again

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Run (record from jobs) | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |

#### `job approve` — Add reviewed results to project

Changes project data or creates output. Removes, archives, retires, or explicitly runs/approves an operation; review the selected record.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Run (record from jobs) | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |

#### `job preview` — Review image tool results

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Image request (record from jobs) | — |

#### `job list` — List image requests

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--status` | no | text | Status | choices: `queued`, `running`, `succeeded`, `failed`, `cancelled` |

### `document`

#### `document import` — Import source document

Changes project data or creates output. Local-file operation; use the CLI or the dedicated upload API where available.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--path` | yes | text | Source file path | — |
| `--document-id` | no | text | Existing document | — |
| `--revision` | no | integer | Last-read document revision | — |
| `--label` | no | text | Draft label | default: `"Imported draft"` |
| `--dry-run` | no | boolean | Validate without importing | default: `false` |
| `--format` | yes | select | Source format | choices: `screenjson`, `otio` |

#### `document list` — Find source documents

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--kind` | no | text | Kind | choices: `screenplay`, `edit` |
| `--query` | no | text | Query | — |
| `--archived` | no | boolean | Archived | — |
| `--limit` | no | integer | Page size | default: `100` |
| `--offset` | no | integer | Offset | default: `0` |

#### `document show` — Show source document

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Choose item (record from entities) | — |

#### `document versions` — List creative drafts

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--document-id` | yes | text | Document | — |
| `--limit` | no | integer | Page size | default: `100` |
| `--offset` | no | integer | Offset | default: `0` |

#### `document tree` — Read source tree

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--document-id` | yes | text | Document | — |
| `--version-id` | no | text | Draft (blank for current) | — |
| `--query` | no | text | Query | — |
| `--limit` | no | integer | Page size | default: `100` |
| `--offset` | no | integer | Offset | default: `0` |

#### `document children` — Read child elements

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--version-id` | yes | text | Version Id | — |
| `--parent-id` | no | text | Parent Id | — |
| `--limit` | no | integer | Page size | default: `100` |
| `--offset` | no | integer | Offset | default: `0` |

#### `document node` — Read a source element

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Choose item (record from entities) | — |

#### `document validate` — Validate stored source

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--id` | yes | text | Choose item (record from entities) | — |
| `--version-id` | no | text | Draft (blank for current) | — |

#### `document revise` — Save source as a new draft

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--node-id` | yes | text | Source element | — |
| `--changes` | yes | json | Authored changes | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |
| `--label` | no | text | Label | default: `"Revised draft"` |

#### `document diff` — Compare creative drafts

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--before-id` | yes | text | Earlier draft | — |
| `--after-id` | yes | text | Later draft | — |

#### `document export` — Export a source draft

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--document-id` | yes | text | Document | — |
| `--version-id` | no | text | Draft (blank for current) | — |
| `--include-identities` | no | boolean | Add stable OTIO identities | default: `false` |

#### `document archive` — Archive source document

Changes project data or creates output. Removes, archives, retires, or explicitly runs/approves an operation; review the selected record.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--document-id` | yes | text | Document | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |

#### `document restore` — Restore source document

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--document-id` | yes | text | Document | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |

### `screenplay`

#### `screenplay import` — Import screenplay

Changes project data or creates output. Local-file operation; use the CLI or the dedicated upload API where available.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--path` | yes | text | Source file path | — |
| `--document-id` | no | text | Existing document | — |
| `--revision` | no | integer | Last-read document revision | — |
| `--label` | no | text | Draft label | default: `"Imported draft"` |
| `--dry-run` | no | boolean | Validate without importing | default: `false` |

#### `screenplay list` — List screenplay documents

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--limit` | no | integer | Page size | default: `100` |
| `--offset` | no | integer | Offset | default: `0` |

### `edit`

#### `edit import` — Import editorial cut

Changes project data or creates output. Local-file operation; use the CLI or the dedicated upload API where available.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--path` | yes | text | Source file path | — |
| `--document-id` | no | text | Existing document | — |
| `--revision` | no | integer | Last-read document revision | — |
| `--label` | no | text | Draft label | default: `"Imported draft"` |
| `--dry-run` | no | boolean | Validate without importing | default: `false` |

#### `edit list` — List edit documents

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--limit` | no | integer | Page size | default: `100` |
| `--offset` | no | integer | Offset | default: `0` |

### `provenance`

#### `provenance link` — Connect production provenance

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--source-type` | yes | select | Source type | choices: `node`, `entity`, `frame`, `media`, `job`, `version`, `artifact` |
| `--source-id` | yes | text | Source Id | — |
| `--target-type` | yes | select | Result type | choices: `node`, `entity`, `frame`, `media`, `job`, `version`, `artifact` |
| `--target-id` | yes | text | Target Id | — |
| `--relation` | yes | select | Relationship | choices: `visualizes`, `appears-in`, `uses-reference`, `derived-from`, `corresponds-to` |
| `--notes` | no | textarea | Notes | — |

#### `provenance trace` — Trace production lineage

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--kind` | yes | select | Item type | choices: `node`, `entity`, `frame`, `media`, `job`, `version`, `artifact` |
| `--record-id` | yes | text | Item | — |
| `--direction` | no | select | Direction | default: `"both"`; choices: `upstream`, `downstream`, `both` |
| `--depth` | no | integer | Maximum depth | default: `6` |
| `--limit` | no | integer | Maximum nodes | default: `100` |

#### `provenance retire` — Retire a source link

Changes project data or creates output. Removes, archives, retires, or explicitly runs/approves an operation; review the selected record.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--edge-id` | yes | text | Edge Id | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |

#### `provenance impact` — Review downstream draft impact

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--before-id` | yes | text | Before Id | — |
| `--after-id` | yes | text | After Id | — |
| `--limit` | no | integer | Limit | default: `300` |

### `coverage`

#### `coverage report` — Review source and delivery coverage

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--limit` | no | integer | Limit | default: `100` |

### `observation`

#### `observation create` — Create a shot observation contract

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--shot-id` | yes | text | Storyboard shot | — |
| `--expected-shot-revision` | yes | integer | Last-read storyboard shot revision | — |
| `--contract` | yes | json | Versioned observation contract | — |

#### `observation show` — Show a shot observation contract

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--contract-id` | yes | text | Observation contract | — |
| `--version-id` | no | text | Contract version | — |

#### `observation list` — List shot observation contracts

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--shot-id` | no | text | Storyboard shot | — |
| `--include-archived` | no | boolean | Include archived shots | default: false |
| `--limit` | no | integer | Page size | default: 100 |
| `--offset` | no | integer | Offset | default: 0 |

#### `observation revise` — Revise a shot observation contract

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--contract-id` | yes | text | Observation contract | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |
| `--contract` | yes | json | Versioned observation contract | — |

#### `observation validate` — Check declared observation links and basis

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--contract-id` | yes | text | Observation contract | — |
| `--version-id` | no | text | Contract version | — |

#### `observation rebase-preview` — Review basis changes before rebasing a contract

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--contract-id` | yes | text | Observation contract | — |
| `--contract` | yes | json | Versioned observation contract | — |

#### `observation rebase` — Rebase a contract with explicit source pins

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--contract-id` | yes | text | Observation contract | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |
| `--contract` | yes | json | Versioned observation contract | — |
| `--expected-basis-sha256` | yes | text | Reviewed basis token | — |

#### `observation diff` — Compare two observation contract versions

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--contract-id` | yes | text | Observation contract | — |
| `--before-version-id` | yes | text | Earlier version | — |
| `--after-version-id` | yes | text | Later version | — |

#### `observation coverage` — Report exact observation coverage

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--request` | yes | json | Request-scoped exact anchors. JSON object: {"anchors": [{"document_id", "version_id", "node_id", "source_sha256", "priority", "basis"}]}. | — |
| `--limit` | no | integer | Page size | default: 500 |
| `--offset` | no | integer | Offset | default: 0 |

#### `observation create-group` — Create planned shots, source links, and contracts

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--request` | yes | json | Atomic grouped plan. JSON object: {"items": [GroupItem, ...]}; include caller-generated shot_id, contract_id, edge_id, and expected_scene_revision. | — |

#### `observation plan-export` — Export exact observation history plan

Read-only operation.

This command has no command-specific fields.

#### `observation plan-import-preview` — Preview observation plan reconciliation

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--plan` | yes | json | Portable observation plan | — |
| `--choices` | no | json | Explicit conflict choices by contract ID | — |

#### `observation plan-import-apply` — Apply a reviewed observation plan import

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--plan` | yes | json | Portable observation plan | — |
| `--preview` | yes | json | Exact preview receipt | — |

#### `observation spatial-review-preview` — Preview an authored spatial review

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--shot-id` | yes | text | Storyboard shot | — |
| `--expected-previous-number` | yes | integer | Last-read spatial review number | — |
| `--review` | yes | json | Versioned authored spatial review object | — |

#### `observation spatial-review` — Save an authored spatial review

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--shot-id` | yes | text | Storyboard shot | — |
| `--expected-previous-number` | yes | integer | Last-read spatial review number | — |
| `--review` | yes | json | Versioned authored spatial review object | — |
| `--expected-basis-sha256` | yes | text | Exact basis token returned by preview | — |

#### `observation spatial-review-show` — Show a spatial review

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--shot-id` | no | text | Storyboard shot | — |
| `--review-id` | no | text | Spatial review identity | — |

#### `observation spatial-review-validate` — Validate a spatial review

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--shot-id` | no | text | Storyboard shot | — |
| `--review-id` | no | text | Spatial review identity | — |

#### `observation spatial-review-history` — Review spatial review history

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--shot-id` | yes | text | Storyboard shot | — |
| `--limit` | no | integer | Maximum results | default: `100` |
| `--offset` | no | integer | Start at | default: `0` |

### `annotation`

#### `annotation create` — Add a pinned review note

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--endpoint-type` | yes | select | Endpoint Type | choices: `node`, `entity`, `frame`, `media`, `job`, `version`, `artifact` |
| `--endpoint-id` | yes | text | Endpoint Id | — |
| `--content` | yes | textarea | Review note | — |

#### `annotation list` — Read pinned notes

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--kind` | yes | select | Kind | choices: `node`, `entity`, `frame`, `media`, `job`, `version`, `artifact` |
| `--record-id` | yes | text | Record Id | — |
| `--limit` | no | integer | Page size | default: `100` |
| `--offset` | no | integer | Offset | default: `0` |

#### `annotation update` — Update review note

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--annotation-id` | yes | text | Annotation Id | — |
| `--revision` | yes | integer | Version check. Keeps a newer edit from being overwritten. | — |
| `--content` | yes | textarea | Content | — |
| `--state` | no | select | State | default: `"open"`; choices: `open`, `resolved` |

### `spatial`

#### `spatial schema` — Show spatial payload schemas

Read-only operation.

This command has no command-specific fields.

#### `spatial fixture` — Get the Doorway to table plan payload

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--scene-id` | yes | text | Scene included in the plan | — |
| `--chair-asset-id` | no | text | Optional shared chair asset | — |

#### `spatial create-preview` — Preview a new spatial plan

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--setup-id` | yes | text | Spatial setup | — |
| `--expected-project-revision` | yes | integer | Last-read project revision | — |
| `--payload` | yes | json | Complete spatial plan payload | — |

#### `spatial create` — Save a new spatial plan version

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--setup-id` | yes | text | Spatial setup | — |
| `--expected-project-revision` | yes | integer | Last-read project revision | — |
| `--payload` | yes | json | Complete spatial plan payload | — |
| `--expected-basis-sha256` | yes | text | Exact basis token returned by preview | — |
| `--operation-id` | no | text | Optional operation identity for retry safety | — |

#### `spatial list` — List spatial plans

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--scene-id` | no | text | Scene included in the plan | — |
| `--include-archived` | no | boolean | Include archived setups | default: false |
| `--limit` | no | integer | Maximum results | default: `100` |
| `--offset` | no | integer | Start at | default: `0` |

#### `spatial show` — Show a spatial plan version

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--setup-id` | yes | text | Spatial setup | — |
| `--version-id` | no | text | Immutable spatial plan version | — |

#### `spatial history` — Show spatial plan history

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--setup-id` | yes | text | Spatial setup | — |
| `--limit` | no | integer | Maximum results | default: `100` |
| `--offset` | no | integer | Start at | default: `0` |

#### `spatial validate` — Validate a spatial plan payload

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--payload` | yes | json | Complete spatial plan payload | — |
| `--setup-id` | no | text | Spatial setup | — |

#### `spatial revise-preview` — Preview a spatial plan revision

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--setup-id` | yes | text | Spatial setup | — |
| `--revision` | yes | integer | Last-read setup or binding revision | — |
| `--payload` | yes | json | Complete spatial plan payload | — |

#### `spatial revise` — Save a spatial plan revision

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--setup-id` | yes | text | Spatial setup | — |
| `--revision` | yes | integer | Last-read setup or binding revision | — |
| `--payload` | yes | json | Complete spatial plan payload | — |
| `--expected-basis-sha256` | yes | text | Exact basis token returned by preview | — |
| `--operation-id` | no | text | Optional operation identity for retry safety | — |

#### `spatial diff` — Compare spatial plan versions

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--setup-id` | yes | text | Spatial setup | — |
| `--from-version-id` | yes | text | Earlier plan version | — |
| `--to-version-id` | yes | text | Later plan version | — |

#### `spatial restore-preview` — Preview a spatial plan restore

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--setup-id` | yes | text | Spatial setup | — |
| `--revision` | yes | integer | Last-read setup or binding revision | — |
| `--version-id` | yes | text | Immutable spatial plan version | — |

#### `spatial restore` — Restore a prior spatial plan version

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--setup-id` | yes | text | Spatial setup | — |
| `--revision` | yes | integer | Last-read setup or binding revision | — |
| `--version-id` | yes | text | Immutable spatial plan version | — |
| `--expected-basis-sha256` | yes | text | Exact basis token returned by preview | — |

#### `spatial archive` — Archive a spatial plan

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--setup-id` | yes | text | Spatial setup | — |
| `--revision` | yes | integer | Last-read setup or binding revision | — |

#### `spatial unarchive` — Unarchive a spatial plan

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--setup-id` | yes | text | Spatial setup | — |
| `--revision` | yes | integer | Last-read setup or binding revision | — |

#### `spatial duplicate-preview` — Preview a spatial plan duplicate

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--setup-id` | yes | text | Spatial setup | — |
| `--version-id` | yes | text | Immutable spatial plan version | — |
| `--new-setup-id` | yes | text | UUID for the new setup | — |
| `--title` | yes | text | Title for the duplicate | — |

#### `spatial duplicate` — Duplicate a spatial plan version

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--setup-id` | yes | text | Spatial setup | — |
| `--version-id` | yes | text | Immutable spatial plan version | — |
| `--new-setup-id` | yes | text | UUID for the new setup | — |
| `--title` | yes | text | Title for the duplicate | — |
| `--expected-basis-sha256` | yes | text | Exact basis token returned by preview | — |

#### `spatial evaluate` — Evaluate a spatial plan at action times

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--version-id` | yes | text | Immutable spatial plan version | — |
| `--times-us` | yes | json array | Action-time samples in microseconds | — |
| `--target-plane-z-m` | no | number | Diagram target plane height in meters | default: `0.0` |
| `--view-bounds` | no | json | Optional diagram view bounds | — |

#### `spatial bind-preview` — Preview a shot binding

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--shot-id` | yes | text | Storyboard shot | — |
| `--expected-shot-revision` | yes | integer | Last-read shot revision | — |
| `--binding-id` | yes | text | Spatial binding identity | — |
| `--binding` | yes | json | Versioned spatial binding object | — |

#### `spatial bind` — Save a shot binding

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--shot-id` | yes | text | Storyboard shot | — |
| `--expected-shot-revision` | yes | integer | Last-read shot revision | — |
| `--binding-id` | yes | text | Spatial binding identity | — |
| `--binding` | yes | json | Versioned spatial binding object | — |
| `--expected-basis-sha256` | yes | text | Exact basis token returned by preview | — |
| `--operation-id` | no | text | Optional operation identity for retry safety | — |

#### `spatial rebind-preview` — Preview a shot rebind

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--shot-id` | yes | text | Storyboard shot | — |
| `--expected-shot-revision` | yes | integer | Last-read shot revision | — |
| `--binding-id` | yes | text | Spatial binding identity | — |
| `--binding` | yes | json | Versioned spatial binding object | — |
| `--revision` | yes | integer | Last-read setup or binding revision | — |

#### `spatial rebind` — Save a shot rebind

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--shot-id` | yes | text | Storyboard shot | — |
| `--expected-shot-revision` | yes | integer | Last-read shot revision | — |
| `--binding-id` | yes | text | Spatial binding identity | — |
| `--binding` | yes | json | Versioned spatial binding object | — |
| `--revision` | yes | integer | Last-read setup or binding revision | — |
| `--expected-basis-sha256` | yes | text | Exact basis token returned by preview | — |
| `--operation-id` | no | text | Optional operation identity for retry safety | — |

#### `spatial binding-show` — Show shot bindings

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--shot-id` | no | text | Storyboard shot | — |
| `--binding-id` | no | text | Spatial binding identity | — |
| `--version-id` | no | text | Immutable spatial plan version | — |

#### `spatial binding-history` — Show binding history

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--binding-id` | yes | text | Spatial binding identity | — |
| `--limit` | no | integer | Maximum results | default: `100` |
| `--offset` | no | integer | Start at | default: `0` |

#### `spatial detach` — Detach a shot binding

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--binding-id` | yes | text | Spatial binding identity | — |
| `--revision` | yes | integer | Last-read setup or binding revision | — |
| `--expected-shot-revision` | yes | integer | Last-read shot revision | — |

#### `spatial impact` — Find spatial plan dependencies

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--setup-id` | no | text | Spatial setup | — |
| `--dependency-id` | no | text | Spatial dependency identity | — |
| `--limit` | no | integer | Maximum results | default: `100` |
| `--offset` | no | integer | Start at | default: `0` |

#### `spatial operation-show` — Show a spatial operation

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--operation-id` | yes | text | Optional operation identity for retry safety | — |

#### `spatial doctor` — Check spatial project integrity

Read-only operation.

This command has no command-specific fields.

#### `spatial backup` — Create a spatial project backup

Changes project data or creates output.

This command has no command-specific fields.

#### `spatial plan-export` — Export a portable spatial plan

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--setup-id` | yes | text | Spatial setup | — |
| `--scope` | no | select | History included in the portable package | default: "full-history"; choices: `full-history`, `selected-with-history-closure`, `sparse-snapshot` |
| `--version-id` | no | text | Immutable spatial plan version | — |

#### `spatial plan-import-preview` — Preview a spatial package import

Read-only operation.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--package` | no | json | Portable spatial package object | — |
| `--archive-base64` | no | text | Base64-encoded native spatial ZIP | — |
| `--mode` | no | select | Import mode | default: "exact"; choices: `exact`, `copy` |
| `--mappings` | no | json | Explicit IDs and dependency mappings | — |

#### `spatial plan-import-apply` — Apply a reviewed spatial package import

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--package` | no | json | Portable spatial package object | — |
| `--archive-base64` | no | text | Base64-encoded native spatial ZIP | — |
| `--mode` | no | select | Import mode | default: "exact"; choices: `exact`, `copy` |
| `--mappings` | no | json | Explicit IDs and dependency mappings | — |
| `--expected-basis-sha256` | yes | text | Exact basis token returned by preview | — |

#### `spatial diagram-export` — Export spatial diagrams

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--version-id` | no | text | Immutable spatial plan version | — |
| `--binding-version-id` | no | text | Immutable shot binding version | — |
| `--times-us` | no | json array | Action-time samples in microseconds | — |
| `--target-plane-z-m` | no | number | Diagram target plane height in meters | default: `0.0` |
| `--view-bounds` | no | json | Optional diagram view bounds | — |
| `--format` | no | select | Diagram output format | default: "all"; choices: `all`, `svg`, `png`, `pdf` |

#### `spatial backup-restore` — Restore a spatial project backup

Changes project data or creates output.

| Flag | Required | Type | Description | Default / choices |
|---|---|---|---|---|
| `--archive` | yes | text | Backup archive path | — |
| `--destination` | yes | text | New destination folder | — |
