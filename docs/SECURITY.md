# Security and privacy boundaries

This is a local single-user application. It has no accounts, cloud persistence,
telemetry, hosted deployment, authentication service, or bundled provider credentials.
The API is bound to 127.0.0.1. Do not reverse-proxy, tunnel, forward, publicly deploy,
or alter its bind address. Filesystem permissions and access to the logged-in user
account remain the primary local trust boundary.

## Defenses implemented

Exact loopback Host/port checks; same-origin restrictions and cross-site fetch checks;
random launch-scoped write token; no CORS grant; bounded JSON/multipart/restore bodies,
including actual streamed byte counting; scoped file resolution and symlink rejection;
content-validated still images; strict authoring models and explicit command allowlists;
parameterized SQL and foreign keys; record revision conflicts; reference-aware deletion;
output hashes; archive traversal/symlink/expansion limits; no overwrite restore; immutable
managed input paths; controlled static/media/export serving; no arbitrary browser file
paths; script registry outside projects; explicit execution and reviewed import.

## Things this does not claim to defend against

Malicious programs already running as the same OS user can read project files or call
local services. A trusted-script registration is not sandboxing. Secrets passed to a
child environment may be visible to that child and its tools. Log redaction is defense
in depth, not proof that arbitrary output images/metadata cannot disclose a secret.
No application-level disk encryption is included. A backup includes authored data,
original source-path metadata and stored script provenance/logs. Review before sharing.

Media decoding relies on installed Pillow/native codec libraries; keep dependencies
updated and do not treat malformed-media checks as complete defense against unknown
codec vulnerabilities. Security tests establish concrete current behaviors, not absence
of vulnerabilities. Run `doctor --hashes`, preserve backups and apply platform updates.

## Browser launch grants

A workspace launch permits project creation only inside its `projects/` subtree.
Registering a path outside that subtree in the CLI does not grant it to the browser.
Direct `--project PATH` explicitly grants that one project. Session tokens are not
long-lived credentials and are never stored in project manifests or browser storage.
Browser file selectors supply bytes; server-side arbitrary path import is CLI/TUI only.

## Backups, releases and dependency handling

Use a separate disk/location for backups. Do not commit real project data, scripts.json,
provider environments or runtime job outputs to the source repository. The shipped demo
is fictional. The source package contains no `.env` credentials or bundled font files.
The vendored React runtime is pinned and licensed; rebuilding does not fetch code at
runtime. Dependency ranges and a tested-version snapshot are documented, but a full
external vulnerability scan or third-party security audit was not run in this build.

Report security-sensitive issues privately to the maintainer of your adopted copy;
this newly generated project does not invent a hosted support/security address.
