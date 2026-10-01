"""Media operations behind the shared Service facade.

Transactions remain in the application layer; UI adapters do not write SQL.
"""
from pathlib import Path
import os
from storyboarder.domain.errors import StoryboardError, Conflict, InUse
from storyboarder.domain.models import uid, now, title, text, words, validate_fields
from storyboarder.media.files import stage_file, safe_path, safe_name, EXTENSIONS, MAX_IMPORT_FILES, sha256


class MediaOperations:
    def import_file(self, path, original_name=None, original_path=None, frame_folder=None):
        media_id, intake_id = uid(), uid()
        staging = safe_path(self.root, f".storyboarder/staging/{media_id}.part")
        final = None
        committed = False
        try:
            info = stage_file(path, staging)
            name = safe_name(original_name or Path(path).name)
            with self.repo.transaction() as conn:
                existing = conn.execute("SELECT id FROM media WHERE sha256=?", (info["sha256"],)).fetchone()
                if existing:
                    media = self.repo.get(conn, "media", existing[0])
                    existing_path = safe_path(self.root, media["path"], must_exist=True)
                    if sha256(existing_path) != info["sha256"]:
                        raise StoryboardError("This image has changed since it was added. Restore the original or import a new copy.")
                else:
                    relative = f"media/{'frames' if frame_folder else 'items'}/{frame_folder or media_id}/{name}"
                    final = safe_path(self.root, relative)
                    final.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(staging, final)  # File is finalized before its DB reference is committed.
                    media = self.repo.insert(conn, "media", {"id": media_id, "path": relative, "original_name": name, **info, "created_at": now()})
                intake = self.repo.insert(conn, "intake", {"id": intake_id, "media_id": media["id"], "original_name": text(original_name or Path(path).name, max_length=300), "original_path": text(original_path or str(Path(path).expanduser().absolute()), max_length=4000), "duplicate": int(existing is not None), "created_at": now()})
                self.repo.event(conn, "media.imported", media["id"], {"duplicate": bool(existing), "intake_id": intake_id})
            committed = True
            return {"media": media, "intake": intake, "duplicate": bool(existing)}
        finally:
            staging.unlink(missing_ok=True)
            if final and not committed:
                final.unlink(missing_ok=True)

    def import_path(self, path, recursive=False):
        path = Path(path).expanduser()
        if not path.is_dir():
            return {"items": [self.import_file(path)], "errors": [], "skipped": []}
        candidates = sorted(path.rglob("*") if recursive else path.iterdir())
        candidates = [p for p in candidates if p.is_file() and not p.is_symlink()]
        if len(candidates) > MAX_IMPORT_FILES:
            raise StoryboardError(f"Import at most {MAX_IMPORT_FILES} files per batch. Split this folder into smaller batches.")
        result = {"items": [], "errors": [], "skipped": []}
        for candidate in candidates:
            if candidate.suffix.lower() not in EXTENSIONS:
                result["skipped"].append(str(candidate))
                continue
            try:
                result["items"].append(self.import_file(candidate))
            except StoryboardError as exc:
                result["errors"].append({"path": str(candidate), "error": exc.as_dict()})
        return result

    def attach_media(self, asset_id, media_id, primary=False, conn=None):
        if conn is None:
            with self.repo.transaction() as current:
                return self.attach_media(asset_id, media_id, primary, current)
        self.entity(conn, asset_id, "asset")
        self.repo.get(conn, "media", media_id)
        existing = conn.execute("SELECT id FROM asset_media WHERE asset_id=? AND media_id=?", (asset_id, media_id)).fetchone()
        if primary:
            conn.execute("UPDATE asset_media SET is_primary=0,revision=revision+1 WHERE asset_id=? AND is_primary=1", (asset_id,))
        if existing:
            if primary:
                conn.execute("UPDATE asset_media SET is_primary=1,revision=revision+1 WHERE id=?", (existing[0],))
            result = self.repo.get(conn, "asset_media", existing[0])
        else:
            first = not conn.execute("SELECT 1 FROM asset_media WHERE asset_id=?", (asset_id,)).fetchone()
            result = self.repo.insert(conn, "asset_media", {"id": uid(), "asset_id": asset_id, "media_id": media_id, "is_primary": int(primary or first)})
        self.repo.event(conn, "asset.media_attached", asset_id, {"media_id": media_id})
        return result

    def primary_media(self, membership_id, revision):
        with self.repo.transaction() as conn:
            row = self.repo.get(conn, "asset_media", membership_id)
            self.repo.check(row, revision)
            conn.execute("UPDATE asset_media SET is_primary=0,revision=revision+1 WHERE asset_id=? AND is_primary=1 AND id<>?", (row["asset_id"], membership_id))
            result = self.repo.update(conn, "asset_media", membership_id, revision, {"is_primary": 1})
            self.repo.event(conn, "asset.primary_changed", row["asset_id"], {"media_id": row["media_id"]})
            return result

    def detach_media(self, membership_id, revision):
        with self.repo.transaction() as conn:
            row = self.repo.get(conn, "asset_media", membership_id)
            self.repo.check(row, revision)
            if conn.execute("SELECT 1 FROM assignments WHERE asset_id=? AND media_id=?", (row["asset_id"], row["media_id"])).fetchone():
                raise InUse("This image is selected for a shot. Choose another image before removing it from this library item.")
            conn.execute("DELETE FROM asset_media WHERE id=?", (membership_id,))
            if row["is_primary"]:
                next_row = conn.execute("SELECT id FROM asset_media WHERE asset_id=? ORDER BY id LIMIT 1", (row["asset_id"],)).fetchone()
                if next_row:
                    conn.execute("UPDATE asset_media SET is_primary=1,revision=revision+1 WHERE id=?", (next_row[0],))
            self.repo.event(conn, "asset.media_detached", row["asset_id"])
            return {"id": membership_id, "deleted": True}

    def review_intake(self, intake_id, revision, state, asset_id=None, create_title=None, create_type="reference", tags=None):
        if state not in ("accepted", "discarded"):
            raise StoryboardError("Choose whether to add this image to the library or remove it from intake.")
        with self.repo.transaction() as conn:
            row = self.repo.get(conn, "intake", intake_id)
            self.repo.check(row, revision)
            if row["state"] != "pending":
                raise Conflict("This intake item has already been reviewed. Import it again to create a new review entry.")
            if state == "accepted":
                if asset_id and create_title:
                    raise StoryboardError("Choose an existing library item or create a new one, not both.")
                if create_title:
                    asset = self.repo.insert(conn, "entities", {"id": uid(), "kind": "asset", "title": title(create_title), "fields": validate_fields("asset", {"type": create_type}), "created_at": now(), "updated_at": now()})
                    asset_id = asset["id"]
                    self._metadata(conn, asset_id, tags or [], [])
                if asset_id:
                    self.attach_media(asset_id, row["media_id"], conn=conn)
                if tags is not None:
                    media = self.repo.get(conn, "media", row["media_id"])
                    self.repo.update(conn, "media", media["id"], media["revision"], {"tags": words(media["tags"] + words(tags))})
            result = self.repo.update(conn, "intake", intake_id, revision, {"state": state})
            self.repo.event(conn, "intake." + state, intake_id, {"asset_id": asset_id})
            return {**result, "asset_id": asset_id}

    def tag_media(self, media_id, revision, tags):
        with self.repo.transaction() as conn:
            result = self.repo.update(conn, "media", media_id, revision, {"tags": words(tags)})
            self.repo.event(conn, "media.tags_changed", media_id)
            return result
