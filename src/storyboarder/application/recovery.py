"""Non-destructive health reporting, consistent backups and guarded restore."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import tempfile
import zipfile
from storyboarder import SCHEMA_VERSION
from storyboarder.domain.errors import StoryboardError, UnsafePath
from storyboarder.domain.models import now, uid, validate_fields, check_relation, check_role
from storyboarder.media.files import safe_path, sha256
from storyboarder.rendering.exports import json_file
from .projects import Project

MAX_BACKUP_BYTES = 10 * 1024**3
MAX_BACKUP_FILES = 100000


def _semantic_issues(snapshot):
    entities = {row["id"]: row for row in snapshot["entities"]}
    issues = []

    def add(code, record_id, message):
        issues.append({"severity": "error", "code": code, "record_id": record_id, "message": message})

    expected_parent = {"project": None, "asset": None, "sequence": "project", "scene": "sequence", "shot": "scene"}
    for row in snapshot["entities"]:
        fields = row.get("fields") if isinstance(row.get("fields"), dict) else {}
        try:
            validate_fields(row["kind"], row["fields"])
        except (StoryboardError, TypeError, ValueError):
            add("invalid_entity_fields", row["id"], "Some saved details are not valid for this item. Open it and review its fields.")
        parent = entities.get(row["parent_id"]) if row.get("parent_id") else None
        required = expected_parent.get(row["kind"], "unknown")
        if required == "unknown" or (required is None and parent) or (required is not None and (not parent or parent["kind"] != required)):
            add("invalid_hierarchy", row["id"], "A story item is under the wrong level. Sequences hold scenes, and scenes hold shots.")
        location_id = fields.get("location_id")
        if location_id:
            location = entities.get(location_id) if isinstance(location_id, str) else None
            location_fields = location.get("fields") if location and isinstance(location.get("fields"), dict) else {}
            if not location or location["kind"] != "asset" or location_fields.get("type") != "location":
                add("invalid_location_default", row["id"], "This item points to a location that is no longer available. Choose a current location.")
        seen, current = set(), row
        while current and current.get("parent_id"):
            if current["id"] in seen:
                add("hierarchy_cycle", row["id"], "The story order loops back on itself. Move the affected item under a different sequence or scene.")
                break
            seen.add(current["id"])
            current = entities.get(current["parent_id"])

    part_of = {}
    assets = {row["id"] for row in snapshot["entities"] if row["kind"] == "asset"}
    for row in snapshot["links"]:
        source, target = entities.get(row["source_id"]), entities.get(row["target_id"])
        try:
            if not source or not target:
                raise StoryboardError("A relationship endpoint is missing.")
            check_relation(source, target, row["relation"])
            if row["relation"] == "part-of":
                part_of.setdefault(row["source_id"], []).append(row["target_id"])
        except (StoryboardError, KeyError, TypeError):
            add("invalid_relationship", row["id"], "A connection is no longer valid. Remove it or connect compatible items.")
    indegree = {asset_id: 0 for asset_id in assets}
    for targets in part_of.values():
        for target_id in targets:
            indegree[target_id] = indegree.get(target_id, 0) + 1
    ready = [asset_id for asset_id, degree in indegree.items() if degree == 0]
    visited = 0
    while ready:
        source_id = ready.pop()
        visited += 1
        for target_id in part_of.get(source_id, ()):
            indegree[target_id] -= 1
            if indegree[target_id] == 0:
                ready.append(target_id)
    if visited != len(indegree):
        add("relationship_cycle", None, "The “part of” connections create a loop. Change one of those connections.")

    memberships = {(row["asset_id"], row["media_id"]) for row in snapshot["asset_media"]}
    media_ids = {row["id"] for row in snapshot["media"]}
    for row in snapshot["asset_media"]:
        asset = entities.get(row["asset_id"])
        if not asset or asset["kind"] != "asset" or row["media_id"] not in media_ids:
            add("invalid_media_membership", row["id"], "A reference item is missing one of its images. Add the image to the library item again.")
    for row in snapshot["assignments"]:
        shot, asset = entities.get(row["shot_id"]), entities.get(row["asset_id"])
        try:
            if not shot or shot["kind"] != "shot" or not asset or asset["kind"] != "asset":
                raise StoryboardError("Assignment endpoints have the wrong record kinds.")
            check_role(asset, row["role"])
            if row["media_id"] and (row["asset_id"], row["media_id"]) not in memberships:
                raise StoryboardError("Exact assignment media is not attached to its asset.")
        except (StoryboardError, KeyError, TypeError):
            add("invalid_assignment", row["id"], "A shot reference is incomplete or no longer valid. Review its image and role.")
    for row in snapshot["frames"]:
        shot = entities.get(row["shot_id"])
        if not shot or shot["kind"] != "shot" or row["media_id"] not in media_ids:
            add("invalid_frame", row["id"], "A storyboard image is no longer attached to its shot or project.")
    for row in snapshot["context_blocks"]:
        owner = entities.get(row["owner_id"])
        if not owner or owner["kind"] == "asset":
            add("invalid_context_owner", row["id"], "A direction note is no longer attached to a project, sequence, scene, or shot.")
    return issues


def doctor(service, hashes=False):
    issues = []
    with service.repo.transaction(False) as conn:
        integrity = [r[0] for r in conn.execute("PRAGMA integrity_check")]
        foreign_keys = [dict(r) for r in conn.execute("PRAGMA foreign_key_check")]
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        migrations = [dict(r) for r in conn.execute("SELECT * FROM schema_migrations ORDER BY version")]
        if integrity != ["ok"]:
            issues.append({"severity": "error", "code": "database_integrity", "message": "The project data file could not be read completely. Make a backup before editing further.", "details": integrity})
        if foreign_keys:
            issues.append({"severity": "error", "code": "foreign_keys", "message": "Some project links are inconsistent. Make a backup before editing further.", "details": foreign_keys})
        if version != SCHEMA_VERSION or [row["version"] for row in migrations] != list(range(1, SCHEMA_VERSION + 1)):
            issues.append({"severity": "error", "code": "migration_state", "message": "This project needs a compatible Storyboarder version before you continue."})
    snapshot = service.repo.snapshot()
    issues.extend(_semantic_issues(snapshot))
    known = set()
    for media in snapshot["media"]:
        known.add(media["path"])
        try:
            file = safe_path(service.root, media["path"], must_exist=True)
            if file.stat().st_size != media["size"]:
                issues.append({"severity": "error", "code": "size_mismatch", "media_id": media["id"], "path": media["path"], "message": "An image has changed since it was added. Restore the original from backup or import it again."})
            elif hashes and sha256(file) != media["sha256"]:
                issues.append({"severity": "error", "code": "hash_mismatch", "media_id": media["id"], "path": media["path"], "message": "An image’s contents have changed since it was added. Restore the original from backup or import it again."})
        except (StoryboardError, OSError) as exc:
            issues.append({"severity": "error", "code": "missing_or_unsafe_media", "media_id": media["id"], "path": media["path"], "message": "An image is missing or can’t be opened from the project folder. Restore it or import it again."})
    try:
        media_root = safe_path(service.root, "media")
    except (StoryboardError, OSError) as exc:
        media_root = None
        issues.append({"severity": "error", "code": "unsafe_media_root", "path": "media", "message": "Storyboarder can’t safely open the project’s image folder. Check that it is a regular folder inside the project."})
    if media_root and media_root.exists():
        for file in media_root.rglob("*"):
            relative = file.relative_to(service.root).as_posix()
            if file.is_symlink():
                issues.append({"severity": "error", "code": "symlink", "path": relative, "message": "An image path points to a linked file. Replace it with a regular image inside the project folder."})
            elif file.is_file() and relative not in known:
                issues.append({"severity": "warning", "code": "orphan_media", "path": relative, "message": "This image is in the project folder but not in the library. Import it from Image intake or move it after reviewing."})
    try:
        staging = safe_path(service.root, ".storyboarder/staging")
    except (StoryboardError, OSError) as exc:
        staging = None
        issues.append({"severity": "error", "code": "unsafe_staging_root", "path": ".storyboarder/staging", "message": "Storyboarder can’t safely open its temporary working folder. Check that it is a regular folder inside the project."})
    if staging and staging.exists():
        for file in staging.iterdir():
            issues.append({"severity": "warning", "code": "staging_file", "path": file.relative_to(service.root).as_posix(), "message": "An image import may still be in progress. Close open Storyboarder windows before clearing temporary files."})
    for job in snapshot["jobs"]:
        if job["status"] == "running":
            issues.append({"severity": "info", "code": "running_job", "job_id": job["id"], "message": "An image tool run is marked as running. If it stopped unexpectedly, cancel it before trying again."})
    project = service.project.summary()
    if service.project.manifest.get("title") != project["title"]:
        issues.append({"severity": "warning", "code": "manifest_hint_stale", "message": "The project folder’s saved title is out of date. Update the project title to refresh it."})
    return {"healthy": not any(i["severity"] == "error" for i in issues), "schema_version": version, "supported_schema_version": SCHEMA_VERSION, "database": ".storyboarder/storyboard.sqlite3", "project": str(service.root), "journal_mode": "wal", "integrity": integrity, "hashes_checked": hashes, "media_checked": len(snapshot["media"]), "migrations": migrations, "issues": issues}


def backup(service):
    output = safe_path(service.root, "exports/backups")
    output.mkdir(parents=True, exist_ok=True)
    name = "backup-" + now().replace(":", "").replace(".", "-") + "-" + uid()[:6] + ".zip"
    archive = output / name
    temp = Path(tempfile.mkdtemp(prefix="storyboarder-backup-"))
    try:
        # Hold a RESERVED writer lock while a second connection takes a SQLite backup.
        # Readers continue; authors wait. Media files are immutable once registered.
        with service.repo.transaction() as lock:
            snapshot_db = temp / ".storyboarder/storyboard.sqlite3"
            snapshot_db.parent.mkdir(parents=True)
            source = service.repo.connect()
            try:
                with sqlite3.connect(snapshot_db) as destination:
                    source.backup(destination)
            finally:
                source.close()
            copy_plan = []
            manifest_source = safe_path(service.root, "project.toml", must_exist=True)
            copy_plan.append((manifest_source, "project.toml", None))
            records = [dict(r) for r in lock.execute("SELECT * FROM media")]
            for media in records:
                src = safe_path(service.root, media["path"], must_exist=True)
                copy_plan.append((src, media["path"], media["sha256"]))
            jobs = safe_path(service.root, ".storyboarder/jobs")
            if jobs.is_dir():
                for file in jobs.rglob("*"):
                    if file.is_symlink():
                        raise UnsafePath("Backup refused a symbolic link in job storage.")
                    if file.is_file():
                        copy_plan.append((file, file.relative_to(service.root).as_posix(), None))
            planned_count = 1 + len(copy_plan) + 1  # database plus backup manifest
            planned_bytes = snapshot_db.stat().st_size + sum(src.stat().st_size for src, _, _ in copy_plan)
            if planned_count > MAX_BACKUP_FILES or planned_bytes > MAX_BACKUP_BYTES:
                raise StoryboardError("Backup exceeds the restore limit of 100,000 files or 10 GiB expanded data; no archive was created.")
            for src, relative, expected_hash in copy_plan:
                dst = safe_path(temp, relative)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
                if expected_hash and sha256(dst) != expected_hash:
                    raise StoryboardError("Backup stopped because managed media no longer matches its stored hash. Run doctor --hashes.")
        files = [{"path": f.relative_to(temp).as_posix(), "size": f.stat().st_size, "sha256": sha256(f)} for f in sorted(temp.rglob("*")) if f.is_file()]
        manifest = {"schema": "storyboarder.backup/v1", "project_id": service.project.id, "created_at": now(), "exclusions": ["rebuildable cache", "prior exports and backups", "staging files"], "files": files}
        json_file(temp / "backup.json", manifest)
        archive_files = [f for f in temp.rglob("*") if f.is_file()]
        total_bytes = sum(f.stat().st_size for f in archive_files)
        manifest_path = temp / "backup.json"
        if len(archive_files) > MAX_BACKUP_FILES or total_bytes > MAX_BACKUP_BYTES or manifest_path.stat().st_size > 20 * 1024 * 1024:
            raise StoryboardError("Backup exceeds the restore limits of 100,000 files, 10 GiB expanded data, or a 20 MiB manifest; no archive was created.")
        staging_archive = archive.with_suffix(".part")
        try:
            with zipfile.ZipFile(staging_archive, "w", zipfile.ZIP_DEFLATED) as z:
                for file in sorted(temp.rglob("*")):
                    if file.is_file():
                        z.write(file, file.relative_to(temp).as_posix())
            os.replace(staging_archive, archive)
        finally:
            staging_archive.unlink(missing_ok=True)
        return {"path": archive.relative_to(service.root).as_posix(), "size": archive.stat().st_size, "sha256": sha256(archive), "manifest": manifest, "files": [archive.relative_to(service.root).as_posix()]}
    finally:
        shutil.rmtree(temp)


def restore(archive, destination):
    destination = Path(destination).expanduser().absolute()
    if destination.is_symlink() or destination.exists():
        raise StoryboardError("Restore into a new folder. Existing folders and live projects are never replaced.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".storyboarder-restore-", dir=destination.parent))
    try:
        try:
            with zipfile.ZipFile(archive) as z:
                entries = z.infolist()
                if len(entries) > MAX_BACKUP_FILES or sum(e.file_size for e in entries) > MAX_BACKUP_BYTES:
                    raise StoryboardError("Backup exceeds the restore limit of 100,000 entries or 10 GiB expanded data.")
                seen = set()
                for entry in entries:
                    name = entry.filename
                    pure = PurePosixPath(name)
                    if name in seen or pure.is_absolute() or ".." in pure.parts or "\\" in name or ":" in name or "\x00" in name or stat.S_ISLNK(entry.external_attr >> 16):
                        raise UnsafePath("Backup contains a duplicate, unsafe path or symbolic link.")
                    seen.add(name)
                    safe_path(temp, name)
                if "backup.json" not in seen or ".storyboarder/storyboard.sqlite3" not in seen or "project.toml" not in seen:
                    raise StoryboardError("This is not a complete Storyboarder backup.")
                manifest_entry = z.getinfo("backup.json")
                if manifest_entry.file_size > 20 * 1024 * 1024:
                    raise StoryboardError("Backup manifest exceeds the 20 MiB limit.")
                manifest = json.loads(z.read("backup.json"))
                if not isinstance(manifest, dict) or manifest.get("schema") != "storyboarder.backup/v1":
                    raise StoryboardError("Unsupported backup contract.")
                if not isinstance(manifest.get("project_id"), str) or not manifest["project_id"] or not isinstance(manifest.get("files"), list):
                    raise StoryboardError("Backup manifest is missing its project identity or file list.")
                expected = {}
                for record in manifest["files"]:
                    if not isinstance(record, dict) or not isinstance(record.get("path"), str) or not isinstance(record.get("size"), int) or not isinstance(record.get("sha256"), str):
                        raise StoryboardError("Backup manifest contains an invalid file record.")
                    if record["path"] in expected:
                        raise StoryboardError("Backup manifest contains duplicate file records.")
                    expected[record["path"]] = record
                actual = {e.filename for e in entries if not e.is_dir()} - {"backup.json"}
                if set(expected) != actual:
                    raise StoryboardError("Backup manifest does not describe every archived file.")
                for entry in entries:
                    if entry.is_dir():
                        continue
                    dst = safe_path(temp, entry.filename)
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(entry) as src, dst.open("xb") as out:
                        shutil.copyfileobj(src, out, length=1024*1024)
                    if entry.filename != "backup.json":
                        record = expected[entry.filename]
                        if dst.stat().st_size != record["size"] or sha256(dst) != record["sha256"]:
                            raise StoryboardError(f"Backup checksum failed: {entry.filename}.")
        except (zipfile.BadZipFile, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise StoryboardError(f"Backup validation failed: {exc}") from exc
        project = Project(temp)
        if project.id != manifest["project_id"]:
            raise StoryboardError("Backup project identity does not match its manifest.")
        from .service import Service
        health = doctor(Service(project), hashes=True)
        if not health["healthy"]:
            raise StoryboardError("Restored project failed its health check; no destination was created.", health)
        (temp / "backup.json").unlink()
        for relative in ("exports/scenes", "exports/boards", "exports/backups", ".storyboarder/cache", ".storyboarder/staging"):
            safe_path(temp, relative).mkdir(parents=True, exist_ok=True)
        os.replace(temp, destination)
        return Project(destination).summary()
    finally:
        if temp.exists():
            shutil.rmtree(temp)
