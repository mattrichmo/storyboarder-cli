# Local API v1

The installed server binds **127.0.0.1 only**. `--port` changes the port, not the bind
address. It serves only a directly launched project or the supplied workspace's local
projects. Browser requests cannot grant an arbitrary outside path.

Read `GET /api/v1/session` for the active project, visible project list, versions and
launch-scoped token. Send `X-Storyboarder-Token: <token>` on every write. Host must
match the printed loopback address/port; foreign Origin and cross-site fetch metadata
are rejected. No CORS grant is provided. A new launch generates a new token, so reload
stale tabs. This boundary is not protection against malicious same-user local code.

## Routes

- Session, metadata/command catalog, project list/create, active-project selection.
- Project state, a lightweight latest-event token, and paginated/filtered entities; typed create/patch.
- `/api/v1/projects/{project_id}/commands/{name}`: explicit application command allowlist.
- Source record pickers use `GET /api/v1/projects/{project_id}/commands/{name}/fields/{field_name}/choices`
  with `query`, `limit` (1–100), `offset`, and a JSON `values` object containing the
  action's selection context. Only declared source fields of browser-enabled commands
  are accepted. Follow `next_offset` for another page; append `/{record_id}` to resolve
  a selected record and its current revision before submitting an action.
- Graph/neighbor and context/composition operations through dedicated routes/catalog.
- Managed media, thumbnails, upload, export-file delivery and pending job previews.
- Workspace-scoped new-folder backup restore.

The checked-in [OpenAPI JSON](openapi.json) describes exact methods, routes and HTTP
request schemas; [commands.json](commands.json) lists every application command,
field, default, read-only/destructive flag and browser eligibility. Metadata also
publishes typed authoring field JSON schemas. There is no SQL endpoint or dynamic
invocation of arbitrary service methods. CLI/TUI-only filesystem commands are denied
through the browser command route.

## HTTP example

After opening a project, an automated local client can use:

```python
import httpx
with httpx.Client(base_url='http://127.0.0.1:7430') as client:
    session = client.get('/api/v1/session').raise_for_status().json()
    project = session['active_project_id']
    headers = {'X-Storyboarder-Token': session['token']}
    response = client.post(
        f'/api/v1/projects/{project}/commands/asset.create',
        headers=headers,
        json={'title': 'Mara', 'type': 'character', 'tags': ['winter']},
    )
    asset = response.raise_for_status().json()
    client.post(
        f'/api/v1/projects/{project}/commands/asset.update',
        headers=headers,
        json={'id': asset['id'], 'revision': asset['revision'], 'description': 'Station caretaker.'},
    ).raise_for_status()
```

## Errors, limits and serving

Errors have `{ "error": { "code", "message", "details" } }`. Validation gives a
labelled explanation. Stale revision writes return HTTP 409 with current-record
information; missing records return 404; unsafe paths/launch grants are denied.
Pydantic request schemas forbid unknown typed fields. The command dispatcher separately
validates its complete allowlist and values.

JSON bodies are bounded at 2 MiB, uploads at 51 MiB including multipart overhead,
browser restores at 1 GiB. Streaming/chunked bodies are counted before parsing, not
trusted from Content-Length. Negative/invalid lengths are rejected. Individual images
still have the stricter 50 MiB and decoded-pixel limits.

Media/file routes resolve scoped paths and refuse private database/manifest leakage.
Original images, safe thumbnails and created exports are read through controlled
routes. The frontend has no remote fonts/scripts. CSP restricts scripts/connect to
self; object/embed/frame access is disabled. Inline style is allowed for canvas transforms.
Cache headers prevent caching session/project JSON. Long operations currently complete
through their request and show in-page busy/status; they do not imply a collaboration
or event-stream service. Jobs can be cancelled from a separate request while a run is
executing in a worker thread.
