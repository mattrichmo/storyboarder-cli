# Verification report — 28 September 2026

## Executed results

| Check | Observed result |
|---|---|
| Python application/API/CLI/TUI tests | **118 passed**; see verification/pytest.txt and pytest.xml |
| Canvas geometry tests | **10 passed**, using Node's native test runner and the actual TypeScript geometry module |
| TypeScript diagnostics/build | Passed; 12 application modules compiled and packaged with local React runtime |
| Compiled React browser acceptance | **20 recorded checks passed**, no page or console errors |
| Demo export | Six shots, three-page PDF, one PNG contact sheet, HTML board and exact-media scene ZIP |
| PDF visual review | All three rendered PDF pages inspected; no clipping or missing reference images in this fixture |
| Demo health | SQLite integrity OK, schema 2, eight managed images hash-verified |
| Metadata benchmark | 1,003 records / 1,000 shots; capped graph and filtered search verified |

The browser acceptance report and benchmark JSON are included in `docs/verification/`.
Screenshots are in `docs/images/`. Authoring screenshots may contain `Acceptance prop`
records because the harness deliberately edits a disposable test project. The README
and overview captures use a fresh, clean fictional demo.

## What the Python suite exercises

Project isolation/switch/discovery/relocation; manifest/database title consistency;
existing-folder protection; missing/corrupt/future/checksum migration errors; actual
schema-1-to-2 upgrade preserving authored data and making a pre-upgrade DB backup;
transaction rollback and simultaneous stale writes; title/tag/type/role validation;
reparent/order identity; typed links and cycle rules; reference-aware lifecycle and
asset merges; exact selected media and membership guards; context provenance,
append/replace/exclude; candidate version/approval protection; presentation-only
layouts and bounded graph views; five still-image formats, recursive staging,
duplicates, tampering and path safety; deterministic self-contained exports and
concurrent commits; PDF/PNG/HTML output and TIFF originals/previews; backup restore,
relocation, archive traversal/hashes; Host/Origin/write-token protections, body limits,
scoped upload and private-file denial; CLI JSON/exit codes; trusted script registry,
request snapshots, timeout/log redaction, cancellation/retry races, output validation
and idempotent reviewed import; full prompt_toolkit application page rendering,
keyboard asset creation, palette cancellation and project switching.

## Browser interaction results

The test renders all application pages, creates a typed asset and verifies it by an
independent HTTP read, creates a valid canonical link with L/Enter, drags and arrow-moves
a canvas card, saves a named layout without changing canonical entities, exercises
hide-versus-delete, attaches a managed frame candidate and compares two versions,
creates/download-checks an HTML/PDF/PNG ZIP, verifies 390px library overflow and mobile
inspector focus/Escape behavior, creates an isolated workspace project and switches back.

A real keyboard bug was found and fixed: Enter opened a link dialog but its default
button activation then closed it. Canvas Enter now prevents default activation. Other
regressions fixed during execution include filtering new membership images incorrectly,
hiding other frame candidates after the first Compare selection, and startup navigation
racing an in-progress project open. Backend regression tests cover export commit races,
active-job retry races, duplicate-file tampering and duplicate project navigator IDs.

## Browser environment limitation

The host Chromium administrator policy blocks all top-level navigation. The browser
run therefore used the documented **HTTP transport bridge**: the unchanged compiled
React/CSS/runtime runs in about:blank, while fetch and image requests go to the real
loopback FastAPI server through the test harness. The policy was not modified.

This verifies UI behavior against real service effects, but **does not verify normal
browser page navigation, actual browser download UI or browser enforcement of CSP**.
Independent HTTP tests check headers, grants and returned ZIP/media bytes. A normal
navigation path and CI job are included for an unrestricted developer machine; the
remote CI job was not executed here. This is not a blanket end-to-end browser or
third-party production certification.

## Performance observation, not a capacity promise

The disposable 1,000-shot workload created 1,003 metadata records.
Creation: 1.803s; metadata snapshot: 0.029s;
250-node capped graph: 0.056s; filtered search:
0.017s. Graph truncation was explicit and search returned the
matching shot. This measures metadata on this Linux environment, not original-image
loading, full canvas frame rates, remote disks or arbitrary larger productions.
Reproduce with `python scripts/benchmark.py --shots 1000`.

## Reproduction and limits

Python 3.13.5 / Linux; Node 22; TypeScript 5.8.3; installed Chromium.
Exact dependency versions are in requirements-tested.txt. Package retrieval was blocked
in this environment, so available installed dependencies/compiler were used. This does
not prove a fresh network dependency resolution on every platform. CI includes
Linux/macOS/Windows and Python 3.11–3.13; those remote jobs were not executed here.

No screen-reader certification, external penetration test, live provider integration,
untrusted-script sandbox guarantee or unlimited-scale benchmark is claimed. PDF's
built-in fonts do not guarantee full Unicode coverage. HTML/JSON retain full text.

## Installed wheel and final acceptance

The built wheel was installed into a separate virtual environment and imported from
its own site-packages, outside the source root. The container's preinstalled third-party
dependencies were explicitly reused through a .pth entry because network retrieval
was unavailable; this is not a claim of a clean network dependency install. Its
entry point reports 1.0.0; installed schema initialization, HTML/React/favicon serving,
session route and token-authorized asset creation passed. See verification/wheel-check.json.

`scripts/acceptance_walkthrough.py` additionally ran against a nonexistent destination:
created a workspace/project, imported a still, authored hierarchy/context/exact assignment,
created a separate selected frame and named graph layout, moved the entire project,
reopened with unchanged IDs/data, exported the scene/visual board and passed full-hash
doctor. Its measured result is in verification/acceptance-walkthrough.json. Run this
script only with a new disposable directory.
