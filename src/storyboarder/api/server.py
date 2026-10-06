"""Loopback-only, launch-scoped API and packaged static frontend."""
from pathlib import Path
import asyncio
import json
import logging
import os
import secrets
import tempfile
import threading
import time
import webbrowser
from fastapi import FastAPI, Request, UploadFile, File, Form, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from starlette.concurrency import run_in_threadpool
from storyboarder import __version__, SCHEMA_VERSION
from storyboarder.application.projects import Project, Workspace
from storyboarder.application.service import Service
from storyboarder.application.commands import COMMANDS, execute
from storyboarder.application.recovery import restore
from storyboarder.automation.registry import ScriptRegistry
from storyboarder.automation.jobs import Jobs
from storyboarder.domain.models import FIELD_MODELS
from storyboarder.domain.errors import StoryboardError, NotFound, UnsafePath
from storyboarder.media.files import safe_path, thumbnail, MAX_FILE_BYTES, FORMATS, safe_name
from .limits import RequestBodyLimit, request_limit
from .schemas import CreateProject, SelectProject, CreateEntity, UpdateEntity

log = logging.getLogger(__name__)


class Launch:
    def __init__(self, project=None, workspace=None, port=7430):
        self.project = project
        self.workspace = workspace
        self.token = secrets.token_urlsafe(32)
        self.port = port
        self.active = project.id if project else None
        self.services = {}
        if project:
            self.services[project.id] = Service(project)

    def projects(self):
        if self.project:
            return [self.project.summary() | {"available": True, "browser_accessible": True, "recent": True}]
        return [p for p in self.workspace.list() if p.get("browser_accessible")]

    def service(self, project_id):
        if project_id in self.services:
            return self.services[project_id]
        entry = next((p for p in self.projects() if p["id"] == project_id and p.get("available")), None)
        if not entry:
            raise NotFound("This project is not open in this Storyboarder window. Open it from Workspace or relaunch Storyboarder with the project folder.")
        service = Service(entry["path"])
        self.services[project_id] = service
        return service


def create_app(project=None, workspace=None, port=7430):
    if isinstance(project, (str, Path)):
        project = Project(project)
    if isinstance(workspace, (str, Path)):
        workspace = Workspace(workspace)
    if not project and not workspace:
        raise StoryboardError("Launch a project or a workspace explicitly.")
    launch = Launch(project, workspace, port)
    app = FastAPI(title="Storyboarder local API", version=__version__, docs_url=None, redoc_url=None, openapi_url="/api/v1/openapi.json")
    app.add_middleware(RequestBodyLimit)
    app.state.launch = launch
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    origins = {"http://" + h for h in hosts}

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        host = request.headers.get("host", "").lower()
        if host not in hosts:
            return JSONResponse({"error": {"code": "invalid_host", "message": "Use the exact loopback URL printed at launch."}}, status_code=403)
        fetch_site = request.headers.get("sec-fetch-site", "")
        origin = request.headers.get("origin")
        if fetch_site == "cross-site" or (origin is not None and origin not in origins):
            return JSONResponse({"error": {"code": "cross_origin", "message": "Cross-origin requests are not allowed."}}, status_code=403)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if not secrets.compare_digest(request.headers.get("x-storyboarder-token", ""), launch.token):
                return JSONResponse({"error": {"code": "launch_token", "message": "This page belongs to another launch. Reload the app."}}, status_code=403)
            content_length = request.headers.get("content-length", "0")
            try:
                length = int(content_length)
            except ValueError:
                return JSONResponse({"error": {"code": "invalid_length", "message": "Invalid request size."}}, status_code=400)
            maximum = request_limit(request.url.path)
            if length < 0:
                return JSONResponse({"error": {"code": "invalid_length", "message": "Invalid request size."}}, status_code=400)
            if length > maximum:
                return JSONResponse({"error": {"code": "too_large", "message": "Request exceeds the configured size limit."}}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        elif request.url.path in ("/", "/index.html", "/build.json"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.exception_handler(StoryboardError)
    async def domain_error(request, exc):
        return JSONResponse({"error": exc.as_dict()}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def schema_error(request, exc):
        errors = [{"loc": list(e["loc"]), "message": e["msg"], "type": e["type"]} for e in exc.errors()]
        return JSONResponse({"error": {"code": "invalid_request", "message": "Check the labelled fields and try again.", "details": errors}}, status_code=422)

    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        log.exception("Unhandled local API error")
        return JSONResponse({"error": {"code": "internal", "message": "Storyboarder couldn’t finish that action. Try again, then check Project care if the problem continues."}}, status_code=500)

    @app.get("/api/v1/session")
    def session():
        projects = launch.projects()
        current = launch.active or next((p["id"] for p in projects if p.get("recent") and p.get("available")), None)
        return {"version": __version__, "schema_version": SCHEMA_VERSION, "token": launch.token, "workspace": str(launch.workspace.root) if launch.workspace else None, "can_create": launch.workspace is not None, "active_project_id": current, "projects": projects}

    @app.get("/api/v1/meta")
    def metadata():
        return {"commands": [c.public() for c in COMMANDS.values() if c.browser],
                "api_commands": [c.public() for c in COMMANDS.values() if c.api_safe],
                "entity_fields": {k: m.model_json_schema() for k, m in FIELD_MODELS.items()},
                "formats": sorted(FORMATS), "max_file_bytes": MAX_FILE_BYTES,
                "scripts": [{k: r[k] for k in ("name", "description", "timeout", "env_keys")} for r in ScriptRegistry().list()]}

    @app.get("/api/v1/projects")
    def projects():
        return launch.projects()

    @app.post("/api/v1/projects", status_code=201)
    def create_project(payload: CreateProject):
        if not launch.workspace:
            raise UnsafePath("Project creation requires a workspace-scoped launch.")
        project = launch.workspace.create(payload.title, payload.slug)
        launch.services[project.id] = Service(project)
        launch.active = project.id
        return project.summary()

    @app.post("/api/v1/active")
    def active(payload: SelectProject):
        service = launch.service(payload.id)
        launch.active = service.project.id
        if launch.workspace:
            launch.workspace.register(service.root)
        return service.project.summary()

    @app.get("/api/v1/projects/{project_id}/state")
    def state(project_id: str):
        return launch.service(project_id).state()

    @app.get("/api/v1/projects/{project_id}/changes")
    def changes(project_id: str):
        return launch.service(project_id).change_token()

    @app.get("/api/v1/projects/{project_id}/entities")
    def entities(project_id: str, kind: str | None = None, query: str = "", asset_type: str | None = None, tag: str | None = None, parent_id: str | None = None, archived: bool = False, limit: int = Query(200, ge=1, le=1000), offset: int = Query(0, ge=0)):
        return launch.service(project_id).list_entities(kind, query, asset_type, tag, parent_id, archived, limit, offset)

    @app.post("/api/v1/projects/{project_id}/entities", status_code=201)
    def create_entity(project_id: str, payload: CreateEntity):
        return launch.service(project_id).create_entity(payload.kind, payload.title, payload.parent_id, payload.description, payload.fields, payload.tags, payload.aliases)

    @app.get("/api/v1/projects/{project_id}/entities/{entity_id}")
    def entity(project_id: str, entity_id: str):
        return launch.service(project_id).get("entities", entity_id)

    @app.patch("/api/v1/projects/{project_id}/entities/{entity_id}")
    def update_entity(project_id: str, entity_id: str, payload: UpdateEntity):
        return launch.service(project_id).update_entity(entity_id, payload.revision, payload.changes)

    @app.post("/api/v1/projects/{project_id}/commands/{name}")
    def command(project_id: str, name: str, payload: dict):
        return execute(launch.service(project_id), name, payload, api=True)

    def choice_field(name, field_name, values):
        from storyboarder.commands.core import _PAGED_SOURCES
        command = COMMANDS.get(name)
        if command is None or not command.browser:
            raise NotFound("This browser action is not available.")
        field = next((f for f in command.fields if f.name == field_name), None)
        if field is None or field.source not in _PAGED_SOURCES:
            raise NotFound("This action does not have that record picker.")
        try:
            context = json.loads(values)
        except json.JSONDecodeError as exc:
            raise StoryboardError("Record picker details must be a JSON object.") from exc
        if not isinstance(context, dict) or set(context) - {f.name for f in command.fields}:
            raise StoryboardError("Record picker details do not match this action.")
        if any(not isinstance(value, (str, int, float, bool, type(None))) for value in context.values()):
            raise StoryboardError("Record picker details must contain simple field values.")
        return field, context

    @app.get("/api/v1/projects/{project_id}/commands/{name}/fields/{field_name}/choices")
    def command_choices(project_id: str, name: str, field_name: str,
                        values: str = Query('{}', max_length=10000), query: str = Query('', max_length=240),
                        limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0)):
        from storyboarder.commands.core import source_options
        field, context = choice_field(name, field_name, values)
        return source_options(launch.service(project_id), field.source, context, query, limit, offset)

    @app.get("/api/v1/projects/{project_id}/commands/{name}/fields/{field_name}/choices/{record_id}")
    def command_choice(project_id: str, name: str, field_name: str, record_id: str,
                       values: str = Query('{}', max_length=10000)):
        from storyboarder.commands.core import source_record
        field, context = choice_field(name, field_name, values)
        record = source_record(launch.service(project_id), field.source, record_id, context)
        if record is None:
            raise NotFound("This picker record is not available.")
        return record

    @app.get("/api/v1/projects/{project_id}/graph")
    def graph(project_id: str, mode: str = "story", query: str = "", asset_type: str | None = None, tag: str | None = None, relation: str | None = None, scene_id: str | None = None, sequence_id: str | None = None, limit: int = Query(250, ge=1, le=500)):
        return launch.service(project_id).graph(mode, query, asset_type, tag, relation, scene_id, sequence_id, limit)

    @app.get("/api/v1/projects/{project_id}/composition/{owner_id}")
    def composition(project_id: str, owner_id: str):
        return launch.service(project_id).compose(owner_id)

    @app.get("/api/v1/projects/{project_id}/media/{media_id}")
    def media_file(project_id: str, media_id: str, size: int | None = None, download: bool = False):
        service = launch.service(project_id)
        record = service.get("media", media_id)
        path = thumbnail(service.root, record, size) if size else safe_path(service.root, record["path"], must_exist=True)
        mime = "image/jpeg" if size else {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp", "TIFF": "image/tiff", "BMP": "image/bmp"}[record["format"]]
        return FileResponse(path, media_type=mime, filename=record["original_name"] if download else None)

    @app.post("/api/v1/projects/{project_id}/upload", status_code=201)
    async def upload(project_id: str, file: UploadFile = File(...), original_path: str = Form(""), shot_id: str = Form("")):
        service = launch.service(project_id)
        if shot_id:
            with service.repo.transaction(False) as conn:
                service.entity(conn, shot_id, "shot")
        fd, temp_name = tempfile.mkstemp(prefix="storyboarder-upload-")
        total = 0
        try:
            with os.fdopen(fd, "wb") as target:
                while chunk := await file.read(1024*1024):
                    total += len(chunk)
                    if total > MAX_FILE_BYTES:
                        raise StoryboardError("Each image must be no larger than 50 MiB.")
                    target.write(chunk)
            result = await run_in_threadpool(service.import_file, Path(temp_name), file.filename or "image", original_path or file.filename or "browser-upload")
            if shot_id:
                result["frame"] = await run_in_threadpool(service.attach_frame, shot_id, result["media"]["id"])
                await run_in_threadpool(service.review_intake, result["intake"]["id"], result["intake"]["revision"], "accepted")
            return result
        finally:
            Path(temp_name).unlink(missing_ok=True)
            await file.close()

    @app.get("/api/v1/projects/{project_id}/files/{relative:path}")
    def export_file(project_id: str, relative: str, download: bool = False):
        service = launch.service(project_id)
        if not relative.startswith("exports/"):
            raise UnsafePath("Only export files are served through this route.")
        path = safe_path(service.root, relative, must_exist=True)
        return FileResponse(path, filename=path.name if download or path.suffix == ".zip" else None)

    @app.get("/api/v1/projects/{project_id}/jobs/{job_id}/preview")
    def job_preview(project_id: str, job_id: str):
        return Jobs(launch.service(project_id)).preview(job_id)

    @app.get("/api/v1/projects/{project_id}/jobs/{job_id}/outputs/{key}")
    def job_output(project_id: str, job_id: str, key: str):
        service = launch.service(project_id)
        job = service.get("jobs", job_id)
        output = next((o for o in job["result"].get("outputs", []) if o["key"] == key), None)
        if not output:
            raise NotFound("This image result is no longer available. Refresh the Image tools page and try again.")
        path = safe_path(service.root, output["stored_path"], must_exist=True)
        return FileResponse(path)

    @app.post("/api/v1/restore", status_code=201)
    async def restore_upload(file: UploadFile = File(...), slug: str = Form(...)):
        if not launch.workspace:
            raise UnsafePath("Restore through the browser requires a workspace launch.")
        from storyboarder.domain.models import slug as validate_slug
        destination = safe_path(launch.workspace.root, "projects/" + validate_slug(slug))
        fd, temporary = tempfile.mkstemp(prefix="storyboarder-restore-upload-")
        try:
            total = 0
            with os.fdopen(fd, "wb") as out:
                while chunk := await file.read(1024*1024):
                    total += len(chunk)
                    if total > 1024**3:
                        raise StoryboardError("Browser restore supports backups up to 1 GiB. Use CLI restore for larger archives.")
                    out.write(chunk)
            result = await run_in_threadpool(restore, temporary, destination)
            await run_in_threadpool(launch.workspace.register, destination)
            launch.services.pop(result["id"], None)
            return result
        finally:
            Path(temporary).unlink(missing_ok=True)
            await file.close()

    from .documents import install_document_routes
    install_document_routes(app, launch)

    static = Path(__file__).parents[1] / "static"

    @app.get("/{path:path}")
    def frontend(path: str):
        if path.startswith("api/"):
            raise NotFound("Unknown API route.")
        relative = path or "index.html"
        target = safe_path(static, relative)
        if not target.is_file():
            # Client navigation uses hash routes, so missing static assets must remain 404s.
            raise NotFound("Frontend asset not found. Run the documented clients/web build if developing from source.")
        return FileResponse(target)

    return app


def serve(project=None, workspace=None, port=7430, open_browser=True):
    import uvicorn
    if not 1024 <= port <= 65535:
        raise StoryboardError("Choose an unprivileged local port between 1024 and 65535.")
    app = create_app(project, workspace, port)
    url = f"http://127.0.0.1:{port}"
    print(f"Storyboarder · {url}\nLocal-only. Press Ctrl+C to stop. Open this URL manually if the browser does not launch.", flush=True)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False))
    if open_browser:
        def launch_browser():
            for _ in range(100):
                if server.started:
                    webbrowser.open(url)
                    return
                if server.should_exit:
                    return
                time.sleep(0.1)
        threading.Thread(target=launch_browser, daemon=True).start()
    server.run()
