"""Explicitly registered trusted commands, outside any portable project."""
from pathlib import Path
import json
import os
import re
import shutil
import tempfile
from filelock import FileLock
from storyboarder.domain.errors import StoryboardError, NotFound


def config_root():
    return Path(os.environ.get("STORYBOARDER_CONFIG_DIR", Path.home() / ".config" / "storyboarder")).expanduser().resolve()


class ScriptRegistry:
    def __init__(self, root=None):
        self.root = Path(root) if root else config_root()
        self.path = self.root / "scripts.json"

    def list(self):
        if not self.path.exists():
            return []
        try:
            document = json.loads(self.path.read_text())
            if document.get("schema") != "storyboarder.scripts/v1":
                raise StoryboardError("Unsupported script registry version.")
            return document["scripts"]
        except (ValueError, KeyError, OSError) as exc:
            raise StoryboardError(f"Cannot read trusted script registry: {exc}") from exc

    def get(self, name):
        result = next((r for r in self.list() if r["name"] == name), None)
        if not result:
            raise NotFound("Register this trusted script explicitly with storyboarder script register first. Project folders are never scanned for executable scripts.")
        return result

    def _save(self, scripts):
        self.root.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=self.root)
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump({"schema": "storyboarder.scripts/v1", "scripts": scripts}, handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def register(self, name, command, timeout=120, env_keys=None, description="", max_file_bytes=50*1024*1024, max_output_bytes=250*1024*1024):
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", name or ""):
            raise StoryboardError("Script name must contain 1–64 letters, numbers, underscores or hyphens.")
        if not isinstance(command, list) or not command or len(command) > 32 or any(not isinstance(a, str) or not a or "\x00" in a for a in command):
            raise StoryboardError('Command must be a JSON argument array, e.g. ["python", "/absolute/path/adapter.py"]. No shell command strings.')
        executable = shutil.which(command[0]) or (str(Path(command[0]).expanduser().resolve()) if Path(command[0]).expanduser().is_file() else None)
        if not executable:
            raise StoryboardError("The command executable was not found. Install it and register again.")
        if type(timeout) is not int or not 1 <= timeout <= 3600:
            raise StoryboardError("Script timeout must be 1–3600 seconds.")
        if type(max_file_bytes) is not int or not 1 <= max_file_bytes <= 50*1024*1024:
            raise StoryboardError("Per-file output limit must be 1–52,428,800 bytes.")
        if type(max_output_bytes) is not int or not max_file_bytes <= max_output_bytes <= 250*1024*1024:
            raise StoryboardError("Combined output limit must be at least the file limit and at most 262,144,000 bytes.")
        keys = env_keys or []
        if isinstance(keys, str):
            keys = [k.strip() for k in keys.split(",") if k.strip()]
        if any(not re.fullmatch(r"[A-Z_][A-Z0-9_]{0,127}", k) for k in keys):
            raise StoryboardError("Environment entries must be variable names, never credential values.")
        record = {"name": name, "command": [executable, *command[1:]], "timeout": timeout, "env_keys": sorted(set(keys)), "description": str(description)[:1000], "max_file_bytes": max_file_bytes, "max_output_bytes": max_output_bytes}
        self.root.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.path) + ".lock"):
            entries = [s for s in self.list() if s["name"] != name]
            self._save([*entries, record])
        return record

    def remove(self, name):
        self.root.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.path) + ".lock"):
            self.get(name)
            self._save([s for s in self.list() if s["name"] != name])
        return {"name": name, "removed": True}
