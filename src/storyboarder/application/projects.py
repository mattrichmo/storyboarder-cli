"""Portable project lifecycle and optional workspace navigation."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import tomllib
from filelock import FileLock
from storyboarder import PROJECT_VERSION
from storyboarder.domain.errors import NotFound, StoryboardError, UnsafePath
from storyboarder.domain.models import uid, now, title, slug, validate_fields
from storyboarder.media.files import safe_path
from storyboarder.storage.repository import Repository


def atomic_toml(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".manifest-")
    try:
        with os.fdopen(fd, "wb") as handle:
            lines = []
            for key, value in data.items():
                if key != "projects":
                    lines.append(f"{key} = {json.dumps(value, ensure_ascii=False)}")
            for entry in data.get("projects", []):
                lines.append("\n[[projects]]")
                lines.extend(f"{key} = {json.dumps(value, ensure_ascii=False)}" for key, value in entry.items())
            if "projects" in data and not data["projects"]:
                lines.append("projects = []")
            handle.write(("\n".join(lines) + "\n").encode())
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def discover(start=None):
    path = Path(start or Path.cwd()).expanduser().resolve()
    if path.is_file():
        path = path.parent
    for candidate in (path, *path.parents):
        if (candidate / "project.toml").is_file():
            return candidate
    raise NotFound("No project was found here. Pass --project PATH, select a workspace project, or create one.")


class WorkspaceConfigError(StoryboardError):
    code = "invalid_workspace_config"
    status = 422


class Project:
    def __init__(self, root):
        self._load(root, migrate=True)

    def _load(self, root, migrate):
        self.root = Path(root).expanduser().resolve()
        manifest = self.root / "project.toml"
        if not manifest.is_file() or manifest.is_symlink():
            raise NotFound(f"No project.toml at {self.root}. Choose a Storyboarder project folder.")
        try:
            self.manifest = tomllib.loads(manifest.read_text())
        except (tomllib.TOMLDecodeError, OSError) as exc:
            raise StoryboardError(f"Cannot read project manifest: {exc}") from exc
        if self.manifest.get("format_version") != PROJECT_VERSION:
            raise StoryboardError("Unsupported project manifest version. Upgrade Storyboarder before opening it.")
        self.id = self.manifest.get("id", "")
        db_path = safe_path(self.root, ".storyboarder/storyboard.sqlite3")
        if not db_path.is_file():
            raise NotFound("Project data is missing from this folder. Restore a full backup; Storyboarder did not create an empty replacement.")
        self.repo = Repository(db_path)
        self.repo.verify_initialized()
        if migrate:
            self.repo.migrate()
        with self.repo.readonly_transaction() as conn:
            entity = self.repo.get(conn, "entities", self.id)
            if entity["kind"] != "project":
                raise StoryboardError("The manifest identity does not match the project database.")

    @classmethod
    def inspect(cls, root):
        """Read a project for navigation without upgrading or changing it."""
        project = cls.__new__(cls)
        project._load(root, migrate=False)
        return project

    @classmethod
    def diagnostic(cls, root):
        """Open only the project identity needed by doctor, without DB reads."""
        project = cls.__new__(cls)
        project.root = Path(root).expanduser().resolve()
        manifest = project.root / "project.toml"
        if not manifest.is_file() or manifest.is_symlink():
            raise NotFound(f"No project.toml at {project.root}. Choose a Storyboarder project folder.")
        try:
            project.manifest = tomllib.loads(manifest.read_text())
        except (tomllib.TOMLDecodeError, OSError) as exc:
            raise StoryboardError(f"Cannot read project manifest: {exc}") from exc
        project.id = project.manifest.get("id", "")
        project.repo = Repository(safe_path(project.root, ".storyboarder/storyboard.sqlite3"))
        return project

    @classmethod
    def create(cls, root, project_title):
        root = Path(root).expanduser().resolve()
        project_title = title(project_title)
        if root.exists() and (not root.is_dir() or any(root.iterdir())):
            raise StoryboardError("Create a project in a new or empty folder; existing content is never overwritten.")
        root.parent.mkdir(parents=True, exist_ok=True)
        temp = Path(tempfile.mkdtemp(prefix=".storyboarder-create-", dir=root.parent))
        try:
            for folder in (".storyboarder/cache", ".storyboarder/staging", ".storyboarder/jobs", "media/items", "media/frames", "exports/scenes", "exports/boards", "exports/backups"):
                (temp / folder).mkdir(parents=True, exist_ok=True)
            project_id = uid()
            manifest = {"format_version": PROJECT_VERSION, "id": project_id, "title": project_title, "created_at": now()}
            atomic_toml(temp / "project.toml", manifest)
            repo = Repository(temp / ".storyboarder/storyboard.sqlite3")
            repo.migrate()
            with repo.transaction() as conn:
                repo.insert(conn, "entities", {"id": project_id, "kind": "project", "title": project_title, "fields": validate_fields("project", {}), "created_at": now(), "updated_at": now()})
                repo.event(conn, "project.created", project_id)
            if root.exists():
                root.rmdir()  # Fails safely if something has appeared since the emptiness check.
            os.replace(temp, root)
            return cls(root)
        finally:
            if temp.exists():
                shutil.rmtree(temp)

    def summary(self):
        with self.repo.readonly_transaction() as conn:
            row = self.repo.get(conn, "entities", self.id)
            row["path"] = str(self.root)
            row["counts"] = {r["kind"]: r["n"] for r in conn.execute("SELECT kind,count(*) n FROM entities WHERE archived=0 GROUP BY kind")}
            row["counts"]["media"] = conn.execute("SELECT count(*) FROM media").fetchone()[0]
            row["counts"]["intake"] = conn.execute("SELECT count(*) FROM intake WHERE state='pending'").fetchone()[0]
            return row

    def sync_manifest(self):
        # Manifest title is a rebuildable navigator hint; the database title is authoritative.
        self.manifest["title"] = self.summary()["title"]
        atomic_toml(self.root / "project.toml", self.manifest)


class Workspace:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.path = self.root / "workspace.toml"

    def _read(self):
        if not self.path.exists():
            return {"format_version": 1, "recent": "", "projects": []}
        if self.path.is_symlink():
            raise UnsafePath("Workspace manifest cannot be a symbolic link.")
        try:
            data = tomllib.loads(self.path.read_text())
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
            raise WorkspaceConfigError(f"Cannot read workspace.toml: {exc}", {"field": "workspace.toml"}) from exc
        if not isinstance(data, dict):
            raise WorkspaceConfigError("Workspace configuration must be a TOML table.", {"field": "workspace.toml"})
        if "format_version" not in data:
            raise WorkspaceConfigError("Workspace format_version is required.", {"field": "format_version"})
        version = data["format_version"]
        if not isinstance(version, int) or isinstance(version, bool):
            raise WorkspaceConfigError("Workspace format_version must be an integer.", {"field": "format_version"})
        if version != 1:
            raise WorkspaceConfigError("Unsupported workspace version.", {"field": "format_version", "supported": 1, "found": version})
        recent = data.get("recent", "")
        if not isinstance(recent, str):
            raise WorkspaceConfigError("Workspace recent must be a project ID string.", {"field": "recent"})
        projects = data.get("projects", [])
        if not isinstance(projects, list):
            raise WorkspaceConfigError("Workspace projects must be an array of tables.", {"field": "projects"})
        for index, entry in enumerate(projects):
            if not isinstance(entry, dict):
                raise WorkspaceConfigError("Each workspace project must be a table.", {"field": "projects", "index": index})
            project_id = entry.get("id")
            path = entry.get("path")
            if not isinstance(project_id, str) or not project_id.strip():
                raise WorkspaceConfigError("Each workspace project needs a non-empty string ID.", {"field": f"projects[{index}].id"})
            if not isinstance(path, str) or not path.strip() or "\x00" in path:
                raise WorkspaceConfigError("Each workspace project needs a valid path string.", {"field": f"projects[{index}].path"})
        data["recent"] = recent
        data["projects"] = projects
        return data

    def init(self):
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "projects").mkdir(exist_ok=True)
        with FileLock(str(self.path) + ".lock"):
            if not self.path.exists():
                atomic_toml(self.path, self._read())
        return {"path": str(self.root), **self._read()}

    def register(self, path, recent=True):
        project = Project(path)
        self.init()
        with FileLock(str(self.path) + ".lock"):
            data = self._read()
            try:
                stored = str(project.root.relative_to(self.root))
            except ValueError:
                stored = str(project.root)
            data["projects"] = [p for p in data.get("projects", []) if p["id"] != project.id]
            data["projects"].append({"id": project.id, "path": stored})
            if recent:
                data["recent"] = project.id
            atomic_toml(self.path, data)
        return project.summary()

    def list(self):
        data = self._read()
        known = list(data.get("projects", []))
        # Rebuild the navigator from workspace-local project manifests, without requiring registration.
        root = self.root / "projects"
        if root.is_dir() and not root.is_symlink():
            paths = {str((self.root / p["path"]).resolve()) for p in known}
            for manifest in sorted(root.glob("*/project.toml")):
                if not manifest.parent.is_symlink() and str(manifest.parent.resolve()) not in paths:
                    known.append({"path": str(manifest.parent), "id": ""})
        result = []
        for entry in known:
            path = (self.root / entry["path"]).resolve()
            try:
                row = Project.inspect(path).summary()
                row["available"] = True
            except (StoryboardError, OSError) as exc:
                row = {**entry, "title": path.name, "path": str(path), "available": False, "error": str(exc)}
            row["recent"] = row["id"] == data.get("recent")
            row["browser_accessible"] = path.is_relative_to((self.root / "projects").resolve())
            # Copies/restores retain identity. The registered path wins over discovered
            # copies so a workspace never exposes two editable rows with the same ID.
            duplicate = next((r for r in result if r["id"] == row["id"] and r.get("available")), None)
            if duplicate and row.get("available"):
                duplicate.setdefault("duplicate_paths", []).append(row["path"])
                continue
            result.append(row)
        return result

    def current(self):
        entries = [p for p in self.list() if p.get("available")]
        recent = next((p for p in entries if p["recent"]), None)
        if recent:
            return Project(recent["path"])
        if len(entries) == 1:
            return Project(entries[0]["path"])
        raise NotFound("Choose a workspace project with project switch, or pass --project PATH.")

    def create(self, project_title, folder):
        self.init()
        root = safe_path(self.root, "projects/" + slug(folder))
        project = Project.create(root, project_title)
        self.register(project.root)
        return project

    def switch(self, project_id):
        match = next((p for p in self.list() if p["id"] == project_id and p.get("available")), None)
        if not match:
            raise NotFound("That project is not available in this workspace.")
        return self.register(match["path"])
