# CLI reference

The installed command is `storyboarder`. The full shared command catalog below is
generated from the implemented application layer. `--help` is available on every
group/subcommand. This is not a selection of representative endpoints.

## Global options and lifecycle

`--project/-p PATH`, `--workspace/-w PATH`, `--json`; `--verbose` and `--version` at
the root. Explicit paths override current-directory discovery. A workspace remembers
recent selection; projects remain directly openable without it.

```text
storyboarder workspace init [PATH]
storyboarder workspace list --workspace PATH
storyboarder workspace register PROJECT_PATH --workspace PATH
storyboarder workspace switch PROJECT_ID --workspace PATH
storyboarder project create NEW_PATH --title TITLE
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

Script registration also accepts `--description`, `--max-file-bytes`, and
`--max-output-bytes`; see AUTOMATION. `import`, `compose`, `doctor`, `backup` are
convenience entry points over the same services.

## JSON input/output and exit codes

Every catalog command accepts `--payload '{"field":"value"}'` or
`--payload @path/to/input.json`. Named flags override payload fields. JSON objects
are used for structured fields; tags may be comma-separated strings or arrays.
Boolean flags use `--flag` / `--no-flag`. JSON output is deterministic in key order
and does not include a terminal table. Update/delete operations require an actual
last-read revision, not an invented constant.

Exit 0: successful operation/help; 1: validation/domain failure; 2: not found or
argument parsing failure; 3: revision conflict; 4: unhealthy doctor/partial import
or failed job result; 130: interrupted. Error JSON uses an `error` object.

## Application commands


### `asset create` — New asset

Application operation; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--title` | yes | text | — |
| `--description` | no | textarea | — |
| `--notes` | no | textarea | — |
| `--type` | no | select | character, location, prop, reference |
| `--tags` | no | tags | — |
| `--aliases` | no | tags | — |

### `asset update` — Edit asset

Application operation; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / assets | — |
| `--revision` | yes | integer | — |
| `--title` | no | text | — |
| `--description` | no | textarea | — |
| `--notes` | no | textarea | — |
| `--type` | no | select | character, location, prop, reference |
| `--tags` | no | tags | — |
| `--aliases` | no | tags | — |

### `asset list` — List assets

Read-only; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--query` | no | text | — |
| `--tag` | no | text | — |
| `--asset-type` | no | text | character, location, prop, reference |
| `--parent-id` | no | text | — |
| `--archived` | no | boolean | — |
| `--limit` | no | integer | 200 |
| `--offset` | no | integer | 0 |

### `asset show` — Show asset

Read-only; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / assets | — |

### `sequence create` — New sequence

Application operation; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--title` | yes | text | — |
| `--description` | no | textarea | — |
| `--notes` | no | textarea | — |
| `--location-id` | no | text / locations | — |
| `--time` | no | text | — |
| `--framing` | no | text | — |
| `--camera` | no | textarea | — |
| `--constraints` | no | textarea | — |
| `--arc` | no | textarea | — |
| `--tone` | no | textarea | — |

### `sequence update` — Edit sequence

Application operation; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / sequences | — |
| `--revision` | yes | integer | — |
| `--title` | no | text | — |
| `--description` | no | textarea | — |
| `--notes` | no | textarea | — |
| `--location-id` | no | text / locations | — |
| `--time` | no | text | — |
| `--framing` | no | text | — |
| `--camera` | no | textarea | — |
| `--constraints` | no | textarea | — |
| `--arc` | no | textarea | — |
| `--tone` | no | textarea | — |

### `sequence list` — List sequences

Read-only; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--query` | no | text | — |
| `--tag` | no | text | — |
| `--asset-type` | no | text | character, location, prop, reference |
| `--parent-id` | no | text | — |
| `--archived` | no | boolean | — |
| `--limit` | no | integer | 200 |
| `--offset` | no | integer | 0 |

### `sequence show` — Show sequence

Read-only; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / sequences | — |

### `scene create` — New scene

Application operation; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--title` | yes | text | — |
| `--parent-id` | yes | text / sequences | — |
| `--description` | no | textarea | — |
| `--notes` | no | textarea | — |
| `--location-id` | no | text / locations | — |
| `--time` | no | text | — |
| `--framing` | no | text | — |
| `--camera` | no | textarea | — |
| `--constraints` | no | textarea | — |
| `--summary` | no | textarea | — |
| `--continuity` | no | textarea | — |

### `scene update` — Edit scene

Application operation; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / scenes | — |
| `--revision` | yes | integer | — |
| `--title` | no | text | — |
| `--description` | no | textarea | — |
| `--notes` | no | textarea | — |
| `--location-id` | no | text / locations | — |
| `--time` | no | text | — |
| `--framing` | no | text | — |
| `--camera` | no | textarea | — |
| `--constraints` | no | textarea | — |
| `--summary` | no | textarea | — |
| `--continuity` | no | textarea | — |

### `scene list` — List scenes

Read-only; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--query` | no | text | — |
| `--tag` | no | text | — |
| `--asset-type` | no | text | character, location, prop, reference |
| `--parent-id` | no | text | — |
| `--archived` | no | boolean | — |
| `--limit` | no | integer | 200 |
| `--offset` | no | integer | 0 |

### `scene show` — Show scene

Read-only; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / scenes | — |

### `shot create` — New shot

Application operation; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--title` | yes | text | — |
| `--parent-id` | yes | text / scenes | — |
| `--description` | no | textarea | — |
| `--notes` | no | textarea | — |
| `--location-id` | no | text / locations | — |
| `--time` | no | text | — |
| `--framing` | no | text | — |
| `--camera` | no | textarea | — |
| `--constraints` | no | textarea | — |
| `--number` | no | text | — |
| `--action` | no | textarea | — |
| `--dialogue` | no | textarea | — |
| `--duration` | no | number | — |
| `--continuity` | no | textarea | — |

### `shot update` — Edit shot

Application operation; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / shots | — |
| `--revision` | yes | integer | — |
| `--title` | no | text | — |
| `--description` | no | textarea | — |
| `--notes` | no | textarea | — |
| `--location-id` | no | text / locations | — |
| `--time` | no | text | — |
| `--framing` | no | text | — |
| `--camera` | no | textarea | — |
| `--constraints` | no | textarea | — |
| `--number` | no | text | — |
| `--action` | no | textarea | — |
| `--dialogue` | no | textarea | — |
| `--duration` | no | number | — |
| `--continuity` | no | textarea | — |

### `shot list` — List shots

Read-only; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--query` | no | text | — |
| `--tag` | no | text | — |
| `--asset-type` | no | text | character, location, prop, reference |
| `--parent-id` | no | text | — |
| `--archived` | no | boolean | — |
| `--limit` | no | integer | 200 |
| `--offset` | no | integer | 0 |

### `shot show` — Show shot

Read-only; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / shots | — |

### `project update` — Edit project guide

Application operation; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / projects | — |
| `--revision` | yes | integer | — |
| `--title` | no | text | — |
| `--description` | no | textarea | — |
| `--notes` | no | textarea | — |
| `--location-id` | no | text / locations | — |
| `--time` | no | text | — |
| `--framing` | no | text | — |
| `--camera` | no | textarea | — |
| `--constraints` | no | textarea | — |
| `--premise` | no | textarea | — |
| `--visual-style` | no | textarea | — |

### `entity update` — Apply structured authoring changes

Application operation; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / entities | — |
| `--revision` | yes | integer | — |
| `--changes` | yes | json | — |

### `entity usage` — Inspect record references

Read-only; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / entities | — |

### `entity archive` — Archive record

Application operation; browser/CLI/TUI; confirmation in interactive interfaces.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / entities | — |
| `--revision` | yes | integer | — |

### `entity restore` — Restore record

Application operation; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / entities | — |
| `--revision` | yes | integer | — |

### `entity delete` — Delete record

Application operation; browser/CLI/TUI; confirmation in interactive interfaces.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / entities | — |
| `--revision` | yes | integer | — |

### `story move` — Move / reorder story record

Application operation; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / story | — |
| `--revision` | yes | integer | — |
| `--position` | yes | integer | — |
| `--parent-id` | no | text / parents | — |

### `media import` — Import file or folder

Application operation; CLI/TUI only.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--path` | yes | text | — |
| `--recursive` | no | boolean | — |

### `media tags` — Tag media

Application operation; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / media | — |
| `--revision` | yes | integer | — |
| `--tags` | yes | tags | — |

### `media show` — Inspect media

Read-only; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / media | — |

### `asset attach` — Attach managed reference

Application operation; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--asset-id` | yes | text / assets | — |
| `--media-id` | yes | text / media | — |

### `asset primary` — Use as primary reference

Application operation; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / asset_media | — |
| `--revision` | yes | integer | — |

### `asset detach` — Detach reference

Application operation; browser/CLI/TUI; confirmation in interactive interfaces.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / asset_media | — |
| `--revision` | yes | integer | — |

### `asset merge` — Merge assets

Application operation; browser/CLI/TUI; confirmation in interactive interfaces.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--source-id` | yes | text / assets | — |
| `--revision` | yes | integer | — |
| `--target-id` | yes | text / assets | — |
| `--target-revision` | yes | integer | — |

### `intake accept` — Accept intake item

Application operation; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / intake | — |
| `--revision` | yes | integer | — |
| `--asset-id` | no | text / assets | — |
| `--create-title` | no | text | — |
| `--create-type` | no | select | character, location, prop, reference |
| `--tags` | no | tags | — |

### `intake discard` — Discard intake item

Application operation; browser/CLI/TUI; confirmation in interactive interfaces.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / intake | — |
| `--revision` | yes | integer | — |

### `link create` — Connect assets

Application operation; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--source-id` | yes | text / assets | — |
| `--target-id` | yes | text / assets | — |
| `--relation` | yes | select | appears-at, alternate-view-of, wears, part-of, related-to |

### `assignment create` — Assign exact shot reference

Application operation; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--shot-id` | yes | text / shots | — |
| `--asset-id` | yes | text / assets | — |
| `--role` | yes | select | subject, setting-reference, costume, prop, reference |
| `--media-id` | no | text / asset_images | — |

### `assignment update` — Edit exact shot reference

Application operation; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / assignments | — |
| `--revision` | yes | integer | — |
| `--role` | yes | select | subject, setting-reference, costume, prop, reference |
| `--media-id` | no | text / asset_images | — |

### `context put` — Add / edit direction block

Application operation; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--owner-id` | yes | text / story | — |
| `--key` | yes | text | — |
| `--operation` | yes | select | append, replace, exclude |
| `--content` | no | textarea | — |
| `--revision` | no | integer | — |

### `context resolve` — Preview resolved context

Read-only; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--owner-id` | yes | text / story | — |

### `frame add` — Attach frame image file

Application operation; CLI/TUI only.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--shot-id` | yes | text / shots | — |
| `--path` | yes | text | — |
| `--notes` | no | textarea | — |

### `frame attach` — Attach managed frame candidate

Application operation; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--shot-id` | yes | text / shots | — |
| `--media-id` | yes | text / media | — |
| `--notes` | no | textarea | — |

### `frame state` — Change frame state

Application operation; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / frames | — |
| `--revision` | yes | integer | — |
| `--state` | yes | select | draft, selected, approved, archived |

### `canvas graph` — Read canvas graph

Read-only; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--mode` | no | select | story, assets, scene |
| `--query` | no | text | — |
| `--asset-type` | no | text | character, location, prop, reference |
| `--tag` | no | text | — |
| `--relation` | no | text | appears-at, alternate-view-of, wears, part-of, related-to |
| `--scene-id` | no | text / scenes | — |
| `--sequence-id` | no | text / sequences | — |
| `--limit` | no | integer | 250 |

### `canvas neighbors` — Explore neighbors

Read-only; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / entities | — |

### `canvas save` — Save named layout

Application operation; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--name` | yes | text | — |
| `--mode` | yes | select | story, assets, scene |
| `--positions` | yes | json | — |
| `--settings` | no | json | — |
| `--revision` | no | integer | — |

### `canvas show` — Show named layout

Read-only; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / layouts | — |

### `composition preview` — Preview scene composition

Read-only; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--owner-id` | yes | text / story | — |

### `export bundle` — Export portable scene bundle

Application operation; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--owner-id` | yes | text / story | — |
| `--include-media` | no | boolean | true |

### `export board` — Export visual storyboard

Application operation; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--owner-id` | yes | text / story | — |
| `--format` | no | select | html, pdf, png, all |
| `--approved-only` | no | boolean | — |

### `project doctor` — Check project health

Read-only; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--hashes` | no | boolean | — |

### `project backup` — Create full project backup

Application operation; browser/CLI/TUI.

No command-specific fields.

### `cache rebuild` — Rebuild thumbnail cache

Application operation; browser/CLI/TUI.

No command-specific fields.

### `cache clear` — Clear rebuildable cache

Application operation; browser/CLI/TUI.

No command-specific fields.

### `project sync` — Rebuild manifest title hint

Application operation; browser/CLI/TUI.

No command-specific fields.

### `job create` — Prepare external script request

Application operation; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--script` | yes | text / scripts | — |
| `--target` | yes | select | asset, frame |
| `--shot-id` | no | text / shots | — |
| `--title` | yes | text | — |
| `--asset-type` | no | select | character, location, prop, reference |
| `--prompt` | no | textarea | — |

### `job run` — Launch registered script

Application operation; browser/CLI/TUI; confirmation in interactive interfaces.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / jobs | — |
| `--revision` | yes | integer | — |

### `job cancel` — Cancel external job

Application operation; browser/CLI/TUI; confirmation in interactive interfaces.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / jobs | — |
| `--revision` | yes | integer | — |

### `job retry` — Queue explicit retry

Application operation; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / jobs | — |
| `--revision` | yes | integer | — |

### `job approve` — Import reviewed outputs

Application operation; browser/CLI/TUI; confirmation in interactive interfaces.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / jobs | — |
| `--revision` | yes | integer | — |

### `job preview` — Review outputs and logs

Read-only; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / jobs | — |

### `link remove` — Remove link

Application operation; browser/CLI/TUI; confirmation in interactive interfaces.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / links | — |
| `--revision` | yes | integer | — |

### `assignment remove` — Remove assignment

Application operation; browser/CLI/TUI; confirmation in interactive interfaces.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / assignments | — |
| `--revision` | yes | integer | — |

### `context remove` — Remove direction block

Application operation; browser/CLI/TUI; confirmation in interactive interfaces.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / context_blocks | — |
| `--revision` | yes | integer | — |

### `frame remove` — Remove frame

Application operation; browser/CLI/TUI; confirmation in interactive interfaces.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / frames | — |
| `--revision` | yes | integer | — |

### `canvas remove` — Remove canvas

Application operation; browser/CLI/TUI; confirmation in interactive interfaces.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--id` | yes | text / layouts | — |
| `--revision` | yes | integer | — |

### `media list` — List media

Read-only; browser/CLI/TUI.

No command-specific fields.

### `intake list` — List intake

Read-only; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--state` | no | text | pending, accepted, discarded |

### `link list` — List links

Read-only; browser/CLI/TUI.

No command-specific fields.

### `assignment list` — List assignments

Read-only; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--shot-id` | no | text / shots | — |

### `context list` — List context blocks

Read-only; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--owner-id` | no | text / story | — |

### `frame list` — List frames

Read-only; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--shot-id` | no | text / shots | — |

### `canvas list` — List layouts

Read-only; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--mode` | no | text | story, assets, scene |

### `job list` — List jobs

Read-only; browser/CLI/TUI.

| Flag | Required | Type / source | Default / choices |
|---|---|---|---|
| `--status` | no | text | queued, running, succeeded, failed, cancelled |
