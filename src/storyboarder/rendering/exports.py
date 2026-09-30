from pathlib import Path
import copy
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
import uuid
from filelock import FileLock
from storyboarder.domain.errors import StoryboardError
from storyboarder.domain.models import dumps
from storyboarder.media.files import FORMATS, safe_path, sha256
from .composer import markdown


def json_file(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def deterministic_zip(source, target):
    """Fixed archive timestamps make repeat exports byte-identical."""
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(Path(source).rglob("*")):
            if path.is_file():
                info = zipfile.ZipInfo(path.relative_to(source).as_posix(), date_time=(2020, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes())


def export_bundle(service, owner_id, include_media=True):
    document = service.compose(owner_id)
    if include_media and not document["valid"]:
        raise StoryboardError("One or more chosen images are missing. Review the project health report before exporting.", {"validation": document["validation"]})
    digest = hashlib.sha256(dumps({"document": document, "include_media": include_media}).encode()).hexdigest()[:16]
    relative = f"exports/scenes/{document['owner']['kind']}-{owner_id[:8]}-{digest}"
    destination = safe_path(service.root, relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".bundle-", dir=destination.parent))
    try:
        records = {m["id"]: m for m in service.repo.snapshot()["media"]}
        paths = {}
        if include_media:
            (temp / "media").mkdir()
            for item in document["media"]:
                source = safe_path(service.root, records[item["id"]]["path"], must_exist=True)
                relative_media = f"media/{item['id']}{FORMATS[item['format']]}"
                shutil.copyfile(source, temp / relative_media)
                if sha256(temp / relative_media) != item["sha256"]:
                    raise StoryboardError("A reference image changed while the package was being created. Restore the original from backup or import it again.")
                paths[item["id"]] = relative_media
        def add_paths(value):
            if isinstance(value, dict):
                if value.get("id") in paths and "sha256" in value:
                    value["bundle_path"] = paths[value["id"]]
                for child in value.values():
                    add_paths(child)
            elif isinstance(value, list):
                for child in value:
                    add_paths(child)
        add_paths(document)
        document["self_contained"] = bool(include_media)
        json_file(temp / "scene.json", document)
        (temp / "scene.md").write_text(markdown(document), encoding="utf-8")
        json_file(temp / "context-provenance.json", {"schema": document["schema"], "target": document["context"], "shots": {shot["id"]: shot["context"] for scene in document["scenes"] for shot in scene["shots"]}})
        manifest = {"schema": document["schema"], "kind": "scene-bundle", "project_id": document["project"]["id"], "owner_id": owner_id, "content_digest": digest, "self_contained": bool(include_media), "files": []}
        for file in sorted(temp.rglob("*")):
            if file.is_file():
                manifest["files"].append({"path": file.relative_to(temp).as_posix(), "size": file.stat().st_size, "sha256": sha256(file)})
        json_file(temp / "manifest.json", manifest)
        archive = safe_path(service.root, relative + ".zip")
        commit_export(temp, destination, archive)
        return {"schema": document["schema"], "path": relative, "archive": relative + ".zip", "manifest": manifest, "validation": document["validation"], "files": [relative + "/scene.json", relative + "/scene.md", relative + "/manifest.json", relative + ".zip"]}
    finally:
        if temp.exists():
            shutil.rmtree(temp)


def commit_export(staged, destination, archive):
    """Publish a deterministic directory/ZIP without clobbering user-edited exports.

    The lock serializes identical exports from concurrent CLI/TUI/API calls. The
    manifest itself and the exact file set are checked, not just selected inputs.
    """
    locks = destination.parent / ".locks"
    locks.mkdir(exist_ok=True)
    with FileLock(str(locks / (destination.name + ".lock")), timeout=30):
        if destination.exists():
            expected = {p.relative_to(staged).as_posix(): sha256(p) for p in staged.rglob("*") if p.is_file()}
            actual = {}
            for path in destination.rglob("*"):
                if path.is_symlink():
                    raise StoryboardError("An existing export contains a linked file. Move that export folder aside before exporting again.")
                if path.is_file():
                    actual[path.relative_to(destination).as_posix()] = sha256(path)
            if actual != expected:
                raise StoryboardError("This export folder was edited. Move it aside before creating a fresh copy.")
        else:
            os.replace(staged, destination)
        temporary = archive.with_name(archive.name + ".part-" + uuid.uuid4().hex)
        try:
            deterministic_zip(destination, temporary)
            os.replace(temporary, archive)
        finally:
            temporary.unlink(missing_ok=True)
