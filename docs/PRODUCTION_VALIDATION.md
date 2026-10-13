# Connected production patch — validation

Validation was executed against the supplied reference archive plus this patch in Linux,
Python 3.13, Node 22 and TypeScript 5.8.3. It was not run against an independently fetched
GitHub HEAD, macOS/Windows installation or a production project. No live user data was
changed.

## Executed results

| Check | Observed result |
|---|---|
| `tests/test_production_graph.py` | **30 passed**; final targeted run 15.23 seconds. |
| `node --test clients/web/tests/*.test.mjs` | **19 passed**, including 9 new production-state tests. |
| `node clients/web/build.mjs --check` | Passed with no TypeScript errors. |
| Client bundle build | Passed; checked-in entry/style match `static/build.json` content hashes. |
| Isolated Chromium workspace harness | Passed all six views, frame-96 edit, alternative save, camera preview, stale-draft/three-way rebase and mobile overflow checks; no page errors. |
| Review PDF | Generated and all three pages rendered/visually inspected; panel headings and source stamps remain with artwork. |
| Broad Python regression run, excluding the native-navigation test | **354 passed, 1 failed, 1 deselected**. The failure was the existing terminal-form timing test described below. This is not an all-green full-suite claim. |
| Terminal-form test rerun alone | `test_document_revise_form_uses_document_revision`: **1 passed** in 0.57 seconds. |
| Earlier targeted legacy CLI/doctor checks | **24 passed**. |

### What the new backend tests cover

The tests exercise strict finite data and typed references, exact-version dependency
cycles, atomic rollback, durable retry receipts, concurrent writers, immutable database
triggers, alternatives/selection, recoverable archive, shared-action handoff and lighting
cues, camera/action time mapping, coverage joins and independent readiness dimensions.
They also exercise script identity and content-aware impact, reviewable reconciliation,
retention of unchanged/older work, malformed source input, graph package tampering and
exact history roundtrip, legacy adoption with media, safe packet output, schema-8-to-9
migration, full backup/restore including historical portable media, missing/hash-invalid
media, and non-transfer of creative acceptance.

The CLI acceptance test invokes real subprocesses, creates all 27 fixture records,
retries the initial mutation, changes the preserved source, reports impact, applies
reviewable reconciliation and compares the exact evaluated revision with the HTTP API.
It also checks rejection of a wrong API token.

### Native browser limitation

The available Chromium is managed with a policy blocking all URL navigation. The existing
`test_export_documents_are_isolated_and_board_preview_still_works` fails at `page.goto`
with `ERR_BLOCKED_BY_ADMINISTRATOR`, before its product assertions. It was excluded from
the broad run above. The browser policy was not changed or bypassed for native navigation.

`tools/verify_production_workspace.py` instead mounts the compiled frontend in an isolated
DOM and connects its test fetch transport to the actual FastAPI `TestClient`. This tests
real React interactions and service writes, but **not** native page navigation, browser
CSP/origin enforcement, real network timing or browser download behavior. The test-only
transport is not included in the shipped application bundle. Its JSON result is included
in `docs/verification/production-workspace.json`.

Run the normal browser suite on an unrestricted machine before release. The separate
API tests exercise token checks and output behavior but are not a replacement for those
native browser checks.

### Terminal-UI timeout

The broad run timed out waiting for the pre-existing `document.revise` terminal form's
four-second completion assertion. It passed when rerun independently, but repeated broad
runs still reproduced the timeout. No test timeout was relaxed and the existing TUI was
not rewritten to hide it. The cause is not established; it remains a release-validation
caveat rather than a claimed passing regression.

## Reproduce

```sh
python -m pip install -e '.[dev]'
python -m pytest tests/test_production_graph.py -q
python -m pytest -q
cd clients/web
npm ci
npm run typecheck
npm test
npm run build
cd ../..
```

The isolated UI harness additionally needs Playwright and an installed Chromium:

```sh
python -m pip install playwright
python tools/verify_production_workspace.py --output /tmp/storyboarder-ui-proof
```

Use the normal existing browser acceptance commands in `docs/DEVELOPMENT.md` on a host
where loopback navigation is permitted. The harness creates and edits only its disposable
fixture; do not substitute an important project into an exploratory test.

## Not established by these checks

These results do not establish exhaustive collision checking, physical camera/light
accuracy, electrical/rigging safety, full screenplay-format support, unlimited production
size, cross-platform release readiness, distributed collaboration, or completion of all
advanced roadmap items. The implementation matrix documents those boundaries separately.
