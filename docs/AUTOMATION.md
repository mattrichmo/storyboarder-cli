# External-script seam

The core contains no live provider SDK, API key, automatic project-script execution,
or bundled image-generation provider. A script is registered explicitly in the user's
configuration directory, outside portable projects. The adapter receives a versioned
request plus copied inputs and returns files with a result manifest. It receives no
SQLite handle and is not given the project root as a protocol parameter.

**Registered scripts are trusted programs running with the user's OS permissions.**
This is an integration protocol and safety boundary for normal adapters, not an OS
sandbox. A malicious executable could inspect user files or make network calls anyway.
Only register code you trust. Do not embed credentials in titles, prompts, files,
project settings or result metadata.

## Try the included offline adapter

From the installed source root, substitute an actual existing project path:

```sh
python scripts/register_sample.py
storyboarder job create --project ./demo-stories/projects/winter-station \
  --script offline-sample --target asset --title "Adapter test slate" --json
```

The helper registers the absolute current Python interpreter and absolute
`examples/sample_adapter.py` path, using the same application registry as the CLI.
Then use the returned job ID/revision:

```sh
storyboarder job run --project ./demo-stories/projects/winter-station --id JOB_ID --revision 1 --json
storyboarder job preview --project ./demo-stories/projects/winter-station --id JOB_ID --json
storyboarder job list --project ./demo-stories/projects/winter-station --json
storyboarder job approve --project ./demo-stories/projects/winter-station --id JOB_ID --revision CURRENT_REVISION --json
```

Revision 1 is valid for a newly queued, unmodified job. Read the current revision after
a run/cancel/retry. In TUI/browser use External scripts: prepare, launch (confirmation),
review outputs/logs, then **Import reviewed outputs** (confirmation). The sample creates
a labelled slate, not a purported photographic frame or provider-generated result.

For a frame request choose target `frame` and `--shot-id SHOT_ID`. Approval attaches a
new ordinary **draft** candidate; it never replaces an approved frame. Approval is
idempotent: repeating it does not duplicate imported records.

## Register another script

```sh
storyboarder script register my-adapter \
  --command '["/absolute/path/python", "/absolute/path/my_adapter.py"]' \
  --timeout 120 --env-keys MY_PROVIDER_API_KEY \
  --max-file-bytes 52428800 --max-output-bytes 262144000
```

Commands are JSON argument arrays, not shell strings. The adapter must accept two
appended positional arguments: `REQUEST_JSON_PATH OUTPUT_DIRECTORY`. Use absolute
paths for script files because execution uses its own working directory. Registration
is user-initiated, not discovered from a project directory. Replace `MY_PROVIDER_API_KEY`
with a variable name only; set the secret in your own environment. The registry stores
names, never the values. `STORYBOARDER_CONFIG_DIR` overrides the default
`~/.config/storyboarder` for testing or a deliberate alternate trust registry.

## Request and result contract

`../schemas/job-request-v1.schema.json` describes the request. It contains version, job
and project IDs, target, explicit prompt, resolved context/provenance, typed authored
shot fields and assignments, copied source references with relative `inputs/` paths,
limits, destination and creation time. The request snapshot is retained for provenance.
It intentionally does not contain a database path, database credentials, or provider
secrets. The input snapshot itself is authored material and may be sensitive.

Write `OUTPUT_DIRECTORY/result.json` using
`../schemas/job-result-v1.schema.json`, for example:

```json
{
  "schema": "storyboarder.result/v1",
  "provider": "my-local-adapter",
  "model": "my-model-name",
  "outputs": [{
    "key": "candidate-01",
    "path": "candidate.png",
    "title": "Dawn at the platform",
    "notes": "Pending review; not an approved frame.",
    "sha256": "OPTIONAL_64_LOWERCASE_HEX_CHARACTERS"
  }]
}
```

Omit `sha256` entirely rather than copying the placeholder. Paths must be unique,
relative files within the output directory; keys must be unique simple identifiers.
The app decodes and hashes every output, checks supplied hashes, and records provider,
model, request/input snapshot, timestamps, output hashes and imported links.

## Execution and review

States: queued → running → succeeded/failed/cancelled. Successful validated results
remain pending review, not auto-imported. Failed/cancelled requests require an explicit
retry; active workers hold a per-job lock, and stale workers cannot overwrite a later
attempt. Retry is refused while the previous run is still stopping. Approved history
is immutable; create a new job for another generation.

Each attempt uses a dedicated working/output directory with copied inputs. Stdout and
stderr are captured with bounded logs; configured secret values are redacted from
captured text. The child inherits a small required OS environment plus explicitly
allowed variable names. Timeout is 1–3600 seconds (default 120). Limits are 16 output
images, 50 MiB/image, 250 MiB total, a 1 MiB result manifest, 10 MiB request snapshot
and bounded output-directory entry counts. Registration may tighten file/total limits.

Cancellation stops the subprocess; POSIX also signals its process group. On Windows,
full arbitrary descendant-tree containment is not an OS-sandbox guarantee. CPU/memory
quotas and network isolation are outside this adapter. Run untrusted/heavy providers
in an independently managed sandbox instead of assuming the protocol supplies one.

Approval validates stored output hashes again and imports through ordinary media/asset
or frame services. Outputs cannot silently overwrite existing originals or approved
frames. External scripts that intentionally modify the project database violate the
contract and are not trusted adapters.
