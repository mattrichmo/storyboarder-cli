# Audit fix verification — 4 October 2026

Implemented the confirmed issues #1–15 on `fix/audit-hardening`.

The changes repair source/provenance forms and revision loading across the TUI
and browser, add bounded searchable record pickers, correct outline styling and
keyboard focus, guard TUI worker shutdown, enforce archived endpoint lifecycles,
and align deletion previews with retained references. Workspace enumeration is
read-only, migrations serialize and preserve verified backups, and doctor can
report corrupt records and unreadable databases without migrating them.

Validation on Linux with Python 3.12 and system Chromium:

- Full Python application, API, CLI and TUI suite: **198 passed**.
- Frontend geometry tests and TypeScript diagnostics: passed.
- Compiled browser acceptance: **17 recorded checks passed**, including modal
  handoff, desktop/mobile focus, 390px outline layout, immutable source revision,
  stale-edit draft preservation, and document archive/restore. No unexpected
  page or console errors; the intentional conflict's HTTP 409 was expected.
- Wheel and source distribution build: passed; frontend hashes and migrations
  001–004 verified in the wheel.
- `git diff --check`: passed.

Browser regression coverage runs in GitHub Actions alongside the existing
cross-platform Python matrix. Those remote results are separate from these local
checks. POSIX descendant cleanup has a process-group regression; Windows uses
bounded CTRL_BREAK/taskkill fallback and has not been executed locally.

The historical September verification report remains separate. Broad feature
ideas from the audit are not implied to be implemented by these defect fixes.
