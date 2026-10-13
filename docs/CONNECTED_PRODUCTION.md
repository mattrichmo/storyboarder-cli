# Connected production workspace

## What changed

The `production` command family and **Production** browser workspace operate on a
revision-pinned production graph in the existing portable project. They do not replace
or silently reinterpret the existing outline, document, storyboard, observation or
spatial records. Schema migration **009** is additive. The earlier workspaces remain
available.

One project is the boundary for the connected graph. Its record kinds are `production`,
`sequence`, `script`, `location`, `asset`, `scene`, `action`, `camera_setup`,
`lighting_setup`, `shot`, `panel`, `animatic`, `edit`, `take`, `review`, `annotation`
and `exception`.

A script scene is nested structured source material with a stable identity. A production
scene maps exact script fragments to an actual set revision. An action plan defines
shared blocking. Camera and lighting setups are reusable records. A shot pins those
records and a covered action interval. An editorial selection is a separate `edit`
record; an actual captured take is a separate `take` record. These are intentionally
not one overloaded scene/shot object.

## Run the connected example

Use a new disposable project for this walkthrough. The example command **returns a
batch without writing it**. Its 27 records include preserved Fountain source, a reusable
set, characters and performers, a key handoff, shared blocking, two camera setups,
lighting cues, two shots, panels and an editorial selection. The built-in example is
synthetic and explicitly not a creative-acceptance record.

```sh
python -m pip install -e .
storyboarder project create ./handoff-demo --title "The handoff" --json
storyboarder production schema --project ./handoff-demo --json > production-schema.json
storyboarder production example --project ./handoff-demo --json > example.json
python -c "import json; p=json.load(open('example.json')); json.dump(p['batch'],open('batch.json','w'),indent=2)"
storyboarder production preview --project ./handoff-demo --batch @batch.json --json
storyboarder production apply --project ./handoff-demo --batch @batch.json --json
storyboarder production report --project ./handoff-demo --hashes --json
storyboarder production query --project ./handoff-demo --kind shot --json
storyboarder ui --project ./handoff-demo
```

In the browser open **Production**. The same CLI-authored records appear without a
manual UI construction step. Select the handoff scene or a shot and scrub frame 96.
Switch to top view, select a character and use the arrow keys or drag to create a local
action draft. A shared-action edit is explicit, not an invisible change to a single
angle. Save it as an alternative before deliberately selecting and repinning dependent
shots.

To produce a review package or graph package:

```sh
storyboarder production packet --project ./handoff-demo --json
storyboarder production export --project ./handoff-demo --json > production-package.json
```

`packet` returns project-relative output paths and a source checkpoint. It does not
send, publish, charge for, or upload anything. `export` is a graph/history interchange,
not a media backup.

## Discover the command surface

`storyboarder production --help` lists the commands. Every command supports `--help`,
`--json` and the existing project selection rules. Object and array arguments accept
JSON or `@path/to/file.json`. `--payload @request.json` accepts the whole command payload;
named flags override fields in it. There is no interactive confirmation prompt in the
production CLI mutation path.

| Purpose | Commands |
|---|---|
| Discover/inspect | `schema`, `snapshot`, `show`, `history` |
| Traverse/change tracking | `query`, `changes`, `diff`, `impact` |
| Author and select | `preview`, `apply`, `reconcile` |
| Import source/initial records | `script-import-preview`, `adopt-preview`, `example` |
| Evaluate/report | `evaluate`, `convert-time`, `report` |
| Transfer/output | `export`, `import-preview`, `import-apply`, `packet` |

`query` filters by kind, text, scene ID or script block ID and returns joined context.
It is not arbitrary SQL or an unlimited query-language engine. `snapshot` supports
`selected`/`head`, pagination and an exact-version dependency closure. A proposal with
no selected version can appear for inspection; its header makes the lack of selection
explicit. Selected-plan reports do not silently treat proposals as accepted work.

The installed API command catalog exposes the same names as `production.<command>`.
Use the existing session token and
`POST /api/v1/projects/{project_id}/commands/production.<command>`.
The new commands are API-safe but excluded from the legacy generic form generator;
the dedicated Production workspace supplies its own editor. No MCP server is added.
An external MCP adapter can call this command surface rather than inventing a second
write contract.

CLI failures retain the existing stable envelope, `{"error":{"code":...,"message":...,"details":...}}`.
Expected exit codes are 0 for success, 1 for invalid input/ordinary domain failure,
2 for missing records and 3 for revision/dependency conflicts. Production shape errors
use `production_invalid`; optimistic-write conflicts use `revision_conflict`. The
existing top-level CLI retains its other command-specific exit behavior.

## Revisions, proposals and atomic writes

A header has a mutable `revision`, immutable-version sequence `head_version`, and
explicit `selected_version`. A reference is always `{"id":"UUID","version":1}`.
Labels and three independent order fields can change without changing identity.
Creating version 2 does not alter a shot pinned to version 1. New `put` operations
are proposals by default (`select: false`).

A batch contains:

```json
{
  "expected_checkpoint": 0,
  "operation_id": "f320430b-6743-4a25-95c3-05a3a8d67db2",
  "operations": [
    {
      "op": "put",
      "id": "f0d35d6e-a85c-4921-9bd7-488c4b8e2a16",
      "expected_revision": 0,
      "base_version": null,
      "select": false,
      "data": {"kind": "production", "title": "Untitled production"}
    }
  ]
}
```

Generate fresh UUIDs for new logical requests and records. An update supplies the
observed header revision and exact `base_version`; selection uses `op: "select"`
with an exact version. Archive and restore are batch operations too. One batch may
change a record only once; references to records created in that same batch are valid.
Typed references, graph cycles, external media pins and all staged records are checked
before the transaction commits. Failed batches do not leave partial records or receipts.

`preview` returns a normalized batch and `preview_sha256`. A caller may attach that
hash to its apply request. `apply` checks the global checkpoint and per-record revisions
inside an immediate SQLite transaction. A successful operation stores its durable
receipt. Retrying **the identical request and operation ID** returns that receipt even
if the checkpoint subsequently advanced. Reusing the ID with different contents is a
conflict. After an uncertain response, retry the original request; do not create a new
operation ID and accidentally repeat the edit.

Deletion is recoverable archive/restore, not destructive history erasure. Active
references block archive. Original managed media and legacy entities pinned by connected
history cannot be silently deleted out from under that history.

## Script import and reconciliation

The importer supports core Fountain, structured JSON and the existing ScreenJSON
shape. It preserves original bytes, file name and SHA-256, and retains Unicode-code-point
source positions. Imported wording is distinct from planning notes, provenance and
agent interpretations. A structured import is validated before identity resolution.
Unsupported constructs and ambiguous matches are reported rather than treated as a
successful comprehensive screenplay conversion. PDF/FDX parsing and complete Fountain
syntax are not implemented here.

Identity resolution is conservative: unique source IDs, scene numbers and headings
can establish a scene match; exact passage matches and unambiguous aligned changes can
retain block identity. Ambiguous cases require the reported `identity_map`. Duplicate
headings are not proof of identity. Removed source material remains in old immutable
versions.

A typical revision workflow is:

1. Read `show`/`snapshot` to obtain the script header revision and current checkpoint.
2. Call `script-import-preview` with that script ID, revisions, a fresh operation ID,
   file name and text or base64 bytes. Inspect the import report and scene/block diff.
3. Apply its returned batch, explicitly selecting the source revision only when desired.
4. Call `impact --id SCRIPT_UUID`; select the affected records requiring new pins.
5. Call `reconcile` with exact `from`/`to` refs and the chosen record IDs. Inspect its
   returned batch; revise the actual action/camera/lighting content where necessary.
6. Apply and run `report` again. Author new creative reviews against the new revisions.

`reconcile` is a reviewable structural repinning operation, not a creative scene writer.
It does not infer a new performance from rewritten dialogue, select every alternative,
replace all downstream work, or transfer creative acceptance. It stages transitive
repins for the explicitly chosen dependency set. It deliberately excludes reviews and
exceptions from automatic acceptance transfer. Unchanged covered source passages can
retain valid work even when an unrelated passage in the script changes.

The executable regression `test_cli_and_http_share_the_same_connected_plan` performs
this flow through real CLI subprocesses: creates the plan, revises a line, inspects
impact, reconciles, retains earlier versions, and compares CLI/API evaluation hashes.

## Spatial and timing conventions

Geometry is stored in **metres**, even when production defaults request centimetres or
feet for display. The coordinate frame is right-handed, +X right, +Y forward, +Z up.
Rotation is in degrees; yaw is about +Z, pitch is upward, and child poses are parent-local.
A location revision owns reusable geometry. Scene dressing/action instances do not
rewrite the location. Dimensions explicitly distinguish measured, estimated and unknown.

Action intervals are integer-frame, half-open `[start,end)`. Frame rates are rational
numerator/denominator pairs, 1–240 fps. The evaluator uses rational conversions and
explicit speed mapping between shot and action time. There is no implicit drop-frame
timecode interpretation. `convert-time` returns an exact rational result and reports
when integer rounding is required; rounding must be deliberately chosen.

Position and Euler-angle tracks support documented linear/hold interpolation. This is
not a motion solver or quaternion animation package. Parent transforms and beat-timed
prop attachment/state changes are evaluated. A handoff is explicit and preserves the
shared action dataset. Shot-specific overrides are separate data. Camera framing uses
a pinhole sensor/gate/focal-length model and explicitly reports its assumptions. It does
not calculate real lens distortion, breathing, calibrated exposure or physical depth
of field. Lighting cues evaluate state/intensity/color intent, not photometry.

The new viewer is an interactive SVG projection of proxy geometry, with orbit/top/
front/side/camera modes, paths, marks, labels, safe areas and framing overlays. It is
not a WebGL mesh engine or a physically based renderer. Top-view direct manipulation
currently targets actor/prop action positions; complex setups and tracks remain editable
through the structured record editor/CLI. The existing spatial workspace is retained.

## Review and completeness

`report` keeps three dimensions separate: structural validity, planning completeness and
creative acceptance. A valid incomplete scene remains incomplete. Applicability and
intentionally-unplanned states require reasons; they are not aliases for successful
creative review. Records carry responsibility, next action, constraints and unresolved
provenance questions. Notes, annotations, reviews and intentional exceptions pin exact
subjects and revisions.

Coverage reports show missing or overlapping passage/beat intervals. Overlap may be
intentional; it is not an artistic failure. Advisory continuity checks include actor and
prop cut states, axis/eyeline/facing checks, approximate obstacle intersections,
equipment visibility and setup/coordinate drift. The continuity evaluator is bounded
(maximum 256 sampled frames and 50,000 collision comparisons); it reports truncation
rather than implying every instant was checked. None of these checks certify rigging,
electrical safety, access clearance or an achievable exposure.

## Client reliability

Drafts are project/record scoped, retain their base revision and operation ID, and are
stored locally with bounded storage/error handling. Pending network operations, local
drafts, selected versions, alternatives and stale data are visibly distinct. Responses
are epoch/abort guarded; switching projects cannot apply an old project's response.
Source links open the exact pinned version. Timeline edits retain the current frame.

Remote changes do not replace a local draft. Three-way merge combines disjoint object
field changes; arrays are atomic and conflicting changes require explicit resolution.
Selecting a different base is not a hidden overwrite. Mutation responses lost to a
network timeout retain retry-safe operation identity. Local draft storage failure is
reported; local storage is not a durable production backup.

## Portability and outputs

The canonical graph package includes all immutable versions, headers, hashes, selection,
source checkpoint, inline original scripts and a references-only media manifest. Import
validates canonical shapes, hashes, ancestry and dependencies and only targets an empty
connected graph. It does not merge independently edited histories. Media files and
legacy provenance prerequisites must already exist; use project backup/restore for a
self-contained transfer.

Project backup now includes portable media referenced by historical connected versions,
not merely by selected records. Doctor checks missing files, content hashes, typed pin
indexes and connected history integrity. Its diagnostic snapshot path no longer opens
a write-capable database connection merely to read an unsupported future-schema project.
Migration, export/import and full backup/restore are exercised by tests.

Production packets capture selected revisions within a consistent snapshot. They include
shot/equipment CSV, per-scene JSON, source selection JSON, reports, proxy plot SVG/JSON,
panel SVG/raster copies, editorial/animatic timeline JSON, an HTML review index, optional
PDF and a manifest/checksummed ZIP. Packet publication is atomic; an altered prior packet
is not silently reused. HTML/SVG are escaped, spreadsheet formula prefixes are neutralized
and raster previews are bounded/re-encoded. PDF core fonts have limited Unicode coverage;
HTML/JSON preserve source text. Animatic playback is a silent panel preview; audio cues
are stored, not mixed, and no MP4 renderer is included.

## Adoption and limits

`adopt-preview` can copy active legacy outline/reference/frame records into an empty
connected graph with original IDs, exact legacy revision provenance, retained authored
fields and managed media links. It leaves missing scale, timing, blocking and camera
information visibly incomplete. Applying adoption is explicit; the old data stays intact.
It is **not** bidirectional synchronization or a conversion of every existing spatial
plan into the new shared-action model.

Current limits are 5,000 records, 500 operations per atomic batch, 32 MiB production JSON,
2 MiB original script source, and 25,000 versions/128 MiB in an evaluation closure.
Bigger productions need partitioning or a future storage/evaluation redesign. No paid
model provider, cloud account, background agent, outbound service or MCP runtime is
required or enabled by this patch.

See [Implementation status](PRODUCTION_IMPLEMENTATION_STATUS.md) for the explicit
18-area scope and [Validation](PRODUCTION_VALIDATION.md) for executed checks.
