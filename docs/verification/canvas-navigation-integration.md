# Canvas navigation integration — PR #20 and PR #21

Compared inputs:
- Main: 23e44959293821bb32aa74c8f00d2155fccc27c7
- PR #20: 9468a11e283c5f076c053ea46b100a690056f0b2
- PR #21: 2a7d3c64bef817f0cd33c1b0d8ee83ca0079992e

## Chosen behavior

App owns one session-only Canvas presentation snapshot per project. Page, hash,
history, and project navigation preserve it without a save. Snapshot restoration
includes layout ID/revision, the exact saved baseline, conflict state and field choices.
Closing/reloading warns for dirty drafts even on inactive pages/projects.

Save / Discard / Stay applies to replacing a draft through mode/layout changes.
Page navigation also waits while a save is in flight; Discard is disabled during
that request. Save completion synchronously publishes the accepted revision into
the App snapshot before any queued navigation can unmount Canvas. New edits made
during a save remain dirty. Revision conflicts keep ordinary Save locked until
comparison and latest-revision CAS reapplication. Both prior commit histories are
preserved; #21 incorporates #20's navigation model and regression rather than
reintroducing a page-navigation replacement gate.

## Local validation (2026-10-06 UTC)

- Python: 318 passed; one existing Starlette/httpx deprecation warning.
- Web geometry: 10 passed.
- TypeScript 5.8.3 no-emit check and production build passed.
- Targeted Canvas/navigation: 10 checks passed using actual loopback HTTP in Chromium.
  Includes real same-field conflict, retained Keep local choice, CAS recovery,
  failed saves, project isolation, restored viewport, hash/history navigation,
  inactive-draft unload protection, Stay and Discard on mode replacement.
- Full browser acceptance including source forms: 39 checks passed; no page or
  console errors; nine expected HTTP 409 conflict responses.
  Includes serialized saves, edits and attempted navigation during an in-flight
  save, field-level conflicts, saved-layout/mode replacement and CAS recovery.
- Phase-one reliability: 8 groups passed across 7 viewport widths, with no page
  or console errors. Trusted sample-adapter registration existed only in a
  disposable test configuration.
- Observation-contract real-service regression: 7 groups passed. The disposable
  fixture includes an authored screenplay link and consistent must requirement.
- Targeted navigation helper Ruff and browser helper py_compile passed.
- Packaged entry/style SHA-256 values and index references verified.
- Application, test, and build-tool files not changed by the reconciliation match
  the exact PR #21 blobs; changes are limited to App/Canvas, navigation/browser
  tests, Canvas/development docs and the rebuilt entry/index/build manifest.

All browser suites used disposable workspaces and normal loopback navigation.
No hosted Actions were requested. Merge messages use [skip ci], and the final
tree retains PR #21's removal of the GitHub workflow files.
