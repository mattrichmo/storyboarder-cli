"""All authoring workflows. CLI, TUI and API invoke this application layer."""
from pathlib import Path
import json
import math
import os
import shutil
import sqlite3
from storyboarder.domain.errors import StoryboardError, Conflict, InUse
from storyboarder.domain.models import (
    uid, now, title, text, words, validate_fields, check_relation, check_role,
    ASSET_TYPES, FRAME_STATES, dumps,
)
from storyboarder.media.files import stage_file, safe_path, safe_name, EXTENSIONS, MAX_IMPORT_FILES, thumbnail, sha256
from storyboarder.storage.repository import unpack
from .projects import Project


class Service:
    def __init__(self, project):
        self.project = project if isinstance(project, Project) else Project(project)
        self.root, self.repo = self.project.root, self.project.repo

    def entity(self, conn, entity_id, kind=None, active=True):
        row = self.repo.get(conn, "entities", entity_id)
        if kind and row["kind"] != kind:
            kind_copy = {"asset": "library item", "project": "project", "sequence": "sequence", "scene": "scene", "shot": "shot"}
            raise StoryboardError(f"Choose a {kind_copy.get(kind, kind)}, not a {kind_copy.get(row['kind'], row['kind'])}.")
        if active and row["archived"]:
            raise StoryboardError("This item is archived. Restore it before adding or changing connections.")
        return row

    def get(self, table, record_id):
        with self.repo.transaction(False) as conn:
            return self.repo.get(conn, table, record_id)

    def state(self):
        result = self.repo.snapshot()
        entities = result["entities"]
        by_id = {row["id"]: row for row in entities}

        def story_order(row):
            kind = row["kind"]
            if kind == "project":
                return (0, row["title"].casefold(), row["id"])
            if kind == "sequence":
                return (1, row["position"], row["title"].casefold(), row["id"])
            if kind == "scene":
                sequence = by_id.get(row.get("parent_id"), {})
                return (2, sequence.get("position", 0), row["position"], row["title"].casefold(), row["id"])
            if kind == "shot":
                scene = by_id.get(row.get("parent_id"), {})
                sequence = by_id.get(scene.get("parent_id"), {})
                return (3, sequence.get("position", 0), scene.get("position", 0), row["position"], row["title"].casefold(), row["id"])
            return (4, row["fields"].get("type", ""), row["title"].casefold(), row["id"])

        entities.sort(key=story_order)
        result["project"] = self.project.summary()
        return result

    def change_token(self):
        """Return the newest committed project event without materializing a full snapshot."""
        with self.repo.transaction(False) as conn:
            return {"event_id": conn.execute("SELECT coalesce(max(id),0) FROM events").fetchone()[0]}

    def list_entities(self, kind=None, query="", asset_type=None, tag=None, parent_id=None, archived=False, limit=200, offset=0):
        where, args = ["e.archived=?"], [int(archived)]
        if kind:
            where.append("e.kind=?")
            args.append(kind)
        if parent_id:
            where.append("e.parent_id=?")
            args.append(parent_id)
        if asset_type:
            where.append("json_extract(e.fields,'$.type')=?")
            args.append(asset_type)
        if tag:
            where.append("EXISTS(SELECT 1 FROM entity_tags t WHERE t.entity_id=e.id AND t.tag=?)")
            args.append(tag)
        if query:
            where.append("(e.title LIKE ? ESCAPE '\\' OR e.description LIKE ? ESCAPE '\\' OR EXISTS(SELECT 1 FROM aliases a WHERE a.entity_id=e.id AND a.name LIKE ? ESCAPE '\\'))")
            pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            args.extend([pattern] * 3)
        with self.repo.transaction(False) as conn:
            clause = " AND ".join(where)
            total = conn.execute("SELECT count(*) FROM entities e WHERE " + clause, args).fetchone()[0]
            rows = conn.execute("SELECT e.id FROM entities e WHERE " + clause + " ORDER BY e.position,e.title,e.id LIMIT ? OFFSET ?", (*args, min(max(int(limit), 1), 1000), max(int(offset), 0))).fetchall()
            return {"items": [self.entity(conn, r[0], active=False) for r in rows], "total": total, "offset": offset, "limit": limit}

    def _metadata(self, conn, entity_id, tags=None, aliases=None):
        if tags is not None:
            conn.execute("DELETE FROM entity_tags WHERE entity_id=?", (entity_id,))
            for tag in words(tags):
                conn.execute("INSERT OR IGNORE INTO tags VALUES (?)", (tag,))
                conn.execute("INSERT INTO entity_tags VALUES (?,?)", (entity_id, tag))
        if aliases is not None:
            conn.execute("DELETE FROM aliases WHERE entity_id=?", (entity_id,))
            for alias in words(aliases):
                conn.execute("INSERT INTO aliases VALUES (?,?)", (entity_id, alias))

    def _validate_location(self, conn, fields):
        if fields.get("location_id"):
            location = self.entity(conn, fields["location_id"], "asset")
            if location["fields"]["type"] != "location":
                raise StoryboardError("Choose an existing location from the reference library.")

    def create_entity(self, kind, title_value, parent_id=None, description="", fields=None, tags=None, aliases=None):
        if kind not in ("asset", "sequence", "scene", "shot"):
            raise StoryboardError("Create library items in Reference library. Add sequences, scenes, and shots in Story outline.")
        field_values = validate_fields(kind, fields or {})
        with self.repo.transaction() as conn:
            if kind == "sequence":
                parent_id = self.project.id
            elif kind == "asset":
                parent_id = None
            elif not parent_id:
                raise StoryboardError(f"Choose a parent {'sequence' if kind == 'scene' else 'scene'} first.")
            if parent_id:
                self.entity(conn, parent_id, {"sequence": "project", "scene": "sequence", "shot": "scene"}[kind])
            self._validate_location(conn, field_values)
            position = conn.execute("SELECT coalesce(max(position),-1)+1 FROM entities WHERE kind=? AND parent_id IS ?", (kind, parent_id)).fetchone()[0]
            row = self.repo.insert(conn, "entities", {"id": uid(), "kind": kind, "parent_id": parent_id, "position": position, "title": title(title_value), "description": text(description), "fields": field_values, "created_at": now(), "updated_at": now()})
            self._metadata(conn, row["id"], tags or [], aliases or [])
            self.repo.event(conn, kind + ".created", row["id"])
            return self.entity(conn, row["id"])

    def update_entity(self, record_id, revision, changes):
        if not isinstance(changes, dict):
            raise StoryboardError("Enter the item details in the expected format.")
        if unknown := set(changes) - {"title", "description", "fields", "tags", "aliases"}:
            raise StoryboardError("One or more item details are no longer supported. Refresh the project and try again.")
        with self.repo.transaction() as conn:
            row = self.entity(conn, record_id)
            self.repo.check(row, revision)
            values = {}
            for key in ("title", "description"):
                if key in changes:
                    values[key] = title(changes[key]) if key == "title" else text(changes[key])
            if "fields" in changes:
                values["fields"] = validate_fields(row["kind"], {**row["fields"], **changes["fields"]})
                self._validate_location(conn, values["fields"])
                if row["kind"] == "asset":
                    updated = {**row, "fields": values["fields"]}
                    for link in conn.execute("SELECT * FROM links WHERE source_id=? OR target_id=?", (record_id, record_id)):
                        source = updated if link["source_id"] == record_id else self.entity(conn, link["source_id"], active=False)
                        target = updated if link["target_id"] == record_id else self.entity(conn, link["target_id"], active=False)
                        check_relation(source, target, link["relation"])
                    for assignment in conn.execute("SELECT role FROM assignments WHERE asset_id=?", (record_id,)):
                        check_role(updated, assignment["role"])
                    if values["fields"]["type"] != "location" and conn.execute("SELECT 1 FROM entities WHERE json_extract(fields,'$.location_id')=? LIMIT 1", (record_id,)).fetchone():
                        raise InUse("This library item is used as a location in the story. Update those scenes before changing its type.")
            self.repo.update(conn, "entities", record_id, revision, values)
            self._metadata(conn, record_id, changes.get("tags"), changes.get("aliases"))
            self.repo.event(conn, row["kind"] + ".updated", record_id, {"fields": sorted(changes)})
            result = self.entity(conn, record_id)
        if result["kind"] == "project":
            self.project.sync_manifest()
        return result

    def usage(self, record_id, conn=None):
        if conn is None:
            with self.repo.transaction(False) as current:
                return self.usage(record_id, current)
        self.entity(conn, record_id, active=False)
        queries = {
            "children": ("SELECT id FROM entities WHERE parent_id=?", (record_id,)),
            "links": ("SELECT id FROM links WHERE source_id=? OR target_id=?", (record_id, record_id)),
            "assignments": ("SELECT id FROM assignments WHERE shot_id=? OR asset_id=?", (record_id, record_id)),
            "frames": ("SELECT id FROM frames WHERE shot_id=?", (record_id,)),
            "media_memberships": ("SELECT id FROM asset_media WHERE asset_id=?", (record_id,)),
            "location_defaults": ("SELECT id FROM entities WHERE json_extract(fields,'$.location_id')=?", (record_id,)),
            "jobs": ("SELECT id FROM jobs WHERE shot_id=?", (record_id,)),
            "generated_outputs": ("SELECT output_key FROM job_outputs WHERE entity_id=?", (record_id,)),
            "context_blocks": ("SELECT id FROM context_blocks WHERE owner_id=?", (record_id,)),
        }
        result = {name: [r[0] for r in conn.execute(sql, args)] for name, (sql, args) in queries.items()}
        result["can_delete"] = not any(result.values())
        return result

    def lifecycle(self, record_id, revision, action):
        if action not in ("archive", "restore", "delete"):
            raise StoryboardError("Choose whether to archive, restore, or delete this item.")
        with self.repo.transaction() as conn:
            row = self.entity(conn, record_id, active=False)
            self.repo.check(row, revision)
            if row["kind"] == "project":
                raise StoryboardError("Remove a project folder outside Storyboarder. Back up the folder before removing it.")
            usage = self.usage(record_id, conn)
            if action == "delete":
                if not usage["can_delete"]:
                    raise InUse("This item is still used in the story. Remove or change those connections, or archive the item instead.", usage)
                conn.execute("DELETE FROM entities WHERE id=?", (record_id,))
                result = {"id": record_id, "deleted": True}
            else:
                if action == "archive" and any(not self.entity(conn, child, active=False)["archived"] for child in usage["children"]):
                    raise InUse("Archive the scenes and shots inside this sequence first. This keeps active story content visible.", usage)
                if action == "restore" and row["parent_id"]:
                    self.entity(conn, row["parent_id"])
                result = self.repo.update(conn, "entities", record_id, revision, {"archived": int(action == "archive")})
            self.repo.event(conn, "record." + action, record_id)
            return result

    def move(self, record_id, revision, position, parent_id=None):
        if not isinstance(position, int) or position < 0:
            raise StoryboardError("Choose a position at the beginning or later in the story.")
        with self.repo.transaction() as conn:
            row = self.entity(conn, record_id)
            self.repo.check(row, revision)
            if row["kind"] not in ("sequence", "scene", "shot"):
                raise StoryboardError("Only sequences, scenes, and shots can be reordered.")
            new_parent = parent_id or row["parent_id"]
            self.entity(conn, new_parent, {"sequence": "project", "scene": "sequence", "shot": "scene"}[row["kind"]])
            siblings = [r[0] for r in conn.execute("SELECT id FROM entities WHERE parent_id=? AND kind=? AND id<>? ORDER BY position,id", (new_parent, row["kind"], record_id))]
            siblings.insert(min(position, len(siblings)), record_id)
            old_parent = row["parent_id"]
            for index, sibling in enumerate(siblings):
                conn.execute("UPDATE entities SET parent_id=?,position=?,revision=revision+1,updated_at=? WHERE id=?", (new_parent, index, now(), sibling))
            if old_parent != new_parent:
                for index, sibling in enumerate(conn.execute("SELECT id FROM entities WHERE parent_id=? AND kind=? ORDER BY position,id", (old_parent, row["kind"])).fetchall()):
                    conn.execute("UPDATE entities SET position=?,revision=revision+1,updated_at=? WHERE id=?", (index, now(), sibling[0]))
            self.repo.event(conn, "story.moved", record_id, {"parent_id": new_parent, "position": position})
            return self.entity(conn, record_id)

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

    def create_link(self, source_id, target_id, relation):
        with self.repo.transaction() as conn:
            source, target = self.entity(conn, source_id, "asset"), self.entity(conn, target_id, "asset")
            check_relation(source, target, relation)
            if relation == "part-of":
                found = conn.execute("WITH RECURSIVE reach(id) AS (SELECT ? UNION SELECT l.target_id FROM links l JOIN reach r ON l.source_id=r.id WHERE l.relation='part-of') SELECT 1 FROM reach WHERE id=?", (target_id, source_id)).fetchone()
                if found:
                    raise StoryboardError("This “part of” connection would create a loop. Choose a different connection.")
            result = self.repo.insert(conn, "links", {"id": uid(), "source_id": source_id, "target_id": target_id, "relation": relation})
            self.repo.event(conn, "relationship.created", result["id"])
            return result

    def assign(self, shot_id, asset_id, role="reference", media_id=None):
        with self.repo.transaction() as conn:
            self.entity(conn, shot_id, "shot")
            asset = self.entity(conn, asset_id, "asset")
            check_role(asset, role)
            self._check_exact_media(conn, asset_id, media_id)
            result = self.repo.insert(conn, "assignments", {"id": uid(), "shot_id": shot_id, "asset_id": asset_id, "role": role, "media_id": media_id})
            self.repo.event(conn, "shot.assigned", shot_id, {"assignment_id": result["id"]})
            return result

    def _check_exact_media(self, conn, asset_id, media_id):
        if media_id and not conn.execute("SELECT 1 FROM asset_media WHERE asset_id=? AND media_id=?", (asset_id, media_id)).fetchone():
            raise StoryboardError("Choose an image that belongs to this library item. A shot can only use an image from one of its selected references.")

    def update_assignment(self, assignment_id, revision, role, media_id=None):
        with self.repo.transaction() as conn:
            row = self.repo.get(conn, "assignments", assignment_id)
            asset = self.entity(conn, row["asset_id"], "asset")
            check_role(asset, role)
            self._check_exact_media(conn, row["asset_id"], media_id)
            result = self.repo.update(conn, "assignments", assignment_id, revision, {"role": role, "media_id": media_id})
            self.repo.event(conn, "shot.assignment_updated", row["shot_id"])
            return result

    def remove(self, table, record_id, revision):
        if table not in ("links", "assignments", "context_blocks", "layouts", "frames"):
            raise StoryboardError("Use Archive, Restore, or Delete for library items.")
        with self.repo.transaction() as conn:
            row = self.repo.get(conn, table, record_id)
            self.repo.check(row, revision)
            if table == "frames" and row["state"] == "approved":
                raise InUse("Archive an approved frame before removing it. The underlying media is retained.")
            if table == "frames" and conn.execute("SELECT 1 FROM job_outputs WHERE frame_id=?", (record_id,)).fetchone():
                raise InUse("This storyboard image is linked to an image tool result. Archive it instead of deleting it.")
            conn.execute(f"DELETE FROM {table} WHERE id=?", (record_id,))
            self.repo.event(conn, table + ".removed", record_id)
            return {"id": record_id, "deleted": True}

    def merge_assets(self, source_id, revision, target_id, target_revision):
        if source_id == target_id:
            raise StoryboardError("Choose two different library items to combine.")
        with self.repo.transaction() as conn:
            source, target = self.entity(conn, source_id, "asset"), self.entity(conn, target_id, "asset")
            self.repo.check(source, revision)
            self.repo.check(target, target_revision)
            if source["fields"]["type"] != target["fields"]["type"]:
                raise StoryboardError("Combine library items of the same type so their reference roles still make sense.")
            # Never silently choose between differing exact references for the same shot/role.
            for row in conn.execute("SELECT * FROM assignments WHERE asset_id=?", (source_id,)).fetchall():
                other = conn.execute("SELECT * FROM assignments WHERE shot_id=? AND asset_id=? AND role=?", (row["shot_id"], target_id, row["role"])).fetchone()
                if other and other["media_id"] != row["media_id"]:
                    raise InUse("Both library items use different images for the same role in a shot. Review that shot before combining them.")
            for member in conn.execute("SELECT * FROM asset_media WHERE asset_id=?", (source_id,)).fetchall():
                self.attach_media(target_id, member["media_id"], conn=conn)
            for row in conn.execute("SELECT * FROM assignments WHERE asset_id=?", (source_id,)).fetchall():
                other = conn.execute("SELECT id FROM assignments WHERE shot_id=? AND asset_id=? AND role=?", (row["shot_id"], target_id, row["role"])).fetchone()
                if other:
                    conn.execute("DELETE FROM assignments WHERE id=?", (row["id"],))
                else:
                    conn.execute("UPDATE assignments SET asset_id=?,revision=revision+1 WHERE id=?", (target_id, row["id"]))
            for row in conn.execute("SELECT * FROM links WHERE source_id=? OR target_id=?", (source_id, source_id)).fetchall():
                a = target_id if row["source_id"] == source_id else row["source_id"]
                b = target_id if row["target_id"] == source_id else row["target_id"]
                duplicate = conn.execute("SELECT 1 FROM links WHERE source_id=? AND target_id=? AND relation=? AND id<>?", (a, b, row["relation"], row["id"])).fetchone()
                if a == b or duplicate:
                    conn.execute("DELETE FROM links WHERE id=?", (row["id"],))
                else:
                    conn.execute("UPDATE links SET source_id=?,target_id=?,revision=revision+1 WHERE id=?", (a, b, row["id"]))
            # Replacing endpoints in part-of relationships can create a longer cycle.
            graph = {}
            for row in conn.execute("SELECT source_id,target_id FROM links WHERE relation='part-of'"):
                graph.setdefault(row[0], []).append(row[1])
            def visit(node, path):
                if node in path:
                    raise InUse("Combining these items would create a circular “part of” connection. Remove the conflicting connection first.")
                for other in graph.get(node, []):
                    visit(other, path | {node})
            for node in graph:
                visit(node, set())
            for row in conn.execute("SELECT id,fields FROM entities WHERE json_extract(fields,'$.location_id')=?", (source_id,)).fetchall():
                fields = json.loads(row["fields"])
                fields["location_id"] = target_id
                conn.execute("UPDATE entities SET fields=?,revision=revision+1,updated_at=? WHERE id=?", (dumps(fields), now(), row["id"]))
            conn.execute("DELETE FROM asset_media WHERE asset_id=?", (source_id,))
            self._metadata(conn, target_id, target["tags"] + source["tags"], target["aliases"] + source["aliases"] + [source["title"]])
            self.repo.update(conn, "entities", source_id, revision, {"archived": 1})
            result = self.repo.update(conn, "entities", target_id, target_revision, {})
            self.repo.event(conn, "asset.merged", target_id, {"source_id": source_id})
            return result

    def put_context(self, owner_id, key, operation="append", content="", revision=None):
        key = text(key, "Direction block name", 100)
        if not key:
            raise StoryboardError("Give this direction note a topic.")
        if operation not in ("append", "replace", "exclude"):
            raise StoryboardError("Choose whether to add to, replace, or hide earlier notes here.")
        with self.repo.transaction() as conn:
            owner = self.entity(conn, owner_id)
            if owner["kind"] == "asset":
                raise StoryboardError("Direction notes can be added to a project, sequence, scene, or shot.")
            existing = conn.execute("SELECT id FROM context_blocks WHERE owner_id=? AND key=?", (owner_id, key)).fetchone()
            if existing:
                result = self.repo.update(conn, "context_blocks", existing[0], revision, {"operation": operation, "text": text(content)})
            elif revision is not None:
                raise Conflict("This direction note is no longer available. Refresh the project and try again.")
            else:
                result = self.repo.insert(conn, "context_blocks", {"id": uid(), "owner_id": owner_id, "key": key, "operation": operation, "text": text(content)})
            self.repo.event(conn, "context.updated", owner_id, {"key": key, "operation": operation})
            return result

    def attach_frame(self, shot_id, media_id, notes="", provenance=None, conn=None):
        if conn is None:
            with self.repo.transaction() as current:
                return self.attach_frame(shot_id, media_id, notes, provenance, current)
        self.entity(conn, shot_id, "shot")
        self.repo.get(conn, "media", media_id)
        version = conn.execute("SELECT coalesce(max(version),0)+1 FROM frames WHERE shot_id=?", (shot_id,)).fetchone()[0]
        result = self.repo.insert(conn, "frames", {"id": uid(), "shot_id": shot_id, "media_id": media_id, "version": version, "state": "draft", "notes": text(notes), "provenance": provenance or {}, "created_at": now()})
        self.repo.event(conn, "frame.attached", shot_id, {"frame_id": result["id"], "version": version})
        return result

    def add_frame(self, shot_id, path, notes=""):
        with self.repo.transaction(False) as conn:
            self.entity(conn, shot_id, "shot")
        imported = self.import_file(path, frame_folder=uid())
        frame = self.attach_frame(shot_id, imported["media"]["id"], notes)
        self.review_intake(imported["intake"]["id"], imported["intake"]["revision"], "accepted")
        return frame

    def set_frame_state(self, frame_id, revision, state):
        if state not in FRAME_STATES:
            raise StoryboardError("Choose Draft, Selected, Approved, or Archived.")
        with self.repo.transaction() as conn:
            row = self.repo.get(conn, "frames", frame_id)
            self.repo.check(row, revision)
            self.entity(conn, row["shot_id"], "shot")
            if state in ("selected", "approved"):
                # Approved work is never silently demoted by selecting a new draft.
                current = conn.execute("SELECT * FROM frames WHERE shot_id=? AND state='approved' AND id<>?", (row["shot_id"], frame_id)).fetchone()
                if current:
                    raise InUse("Another storyboard image is already approved. Archive it or mark it as a draft before approving this one.")
                conn.execute("UPDATE frames SET state='draft',revision=revision+1 WHERE shot_id=? AND state='selected' AND id<>?", (row["shot_id"], frame_id))
            result = self.repo.update(conn, "frames", frame_id, revision, {"state": state})
            self.repo.event(conn, "frame." + state, row["shot_id"], {"frame_id": frame_id})
            return result

    def save_layout(self, name, mode, positions, settings=None, revision=None):
        if mode not in ("story", "assets", "scene"):
            raise StoryboardError("Choose Story flow, Reference map, or Scene board.")
        if not isinstance(positions, dict) or len(positions) > 20000:
            raise StoryboardError("This arrangement includes too many cards to save.")
        clean = {}
        for node, point in positions.items():
            if not isinstance(point, dict) or set(point) != {"x", "y"}:
                raise StoryboardError("Each card needs a valid horizontal and vertical position.")
            if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or abs(v) > 1_000_000 for v in point.values()):
                raise StoryboardError("Card positions must be within the canvas limits. Move the cards closer to the center and try again.")
            clean[str(node)] = point
        settings = settings or {}
        if not isinstance(settings, dict) or len(dumps(settings)) > 1_000_000:
            raise StoryboardError("The saved canvas arrangement is too large or incomplete. Refresh the canvas and try again.")
        if set(settings) - {"hidden", "collapsed", "viewport", "filters", "scene_id", "sequence_id"}:
            raise StoryboardError("This arrangement includes settings from a newer version. Refresh or update Storyboarder before saving it.")
        for field in ("hidden", "collapsed"):
            if field in settings and (not isinstance(settings[field], list) or not all(isinstance(x, str) for x in settings[field])):
                raise StoryboardError(f"The canvas could not read this card selection. Refresh and try again.")
        if "viewport" in settings:
            view = settings["viewport"]
            if not isinstance(view, dict) or set(view) != {"x", "y", "scale"} or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in view.values()) or not 0.15 <= view["scale"] <= 3:
                raise StoryboardError("The canvas view could not be saved. Adjust the view and try again.")
        with self.repo.transaction() as conn:
            existing = conn.execute("SELECT id FROM layouts WHERE name=? AND mode=?", (title(name), mode)).fetchone()
            values = {"positions": clean, "settings": settings}
            if existing:
                result = self.repo.update(conn, "layouts", existing[0], revision, values)
            elif revision is not None:
                raise Conflict("This saved arrangement was removed. Refresh the canvas before saving again.")
            else:
                result = self.repo.insert(conn, "layouts", {"id": uid(), "name": title(name), "mode": mode, **values, "updated_at": now()})
            self.repo.event(conn, "canvas.saved", result["id"], {"name": name, "mode": mode})
            return result

    def neighbors(self, record_id):
        snapshot = self.repo.snapshot()
        entities = {r["id"]: r for r in snapshot["entities"]}
        if record_id not in entities:
            self.get("entities", record_id)
        edges = []
        for row in snapshot["entities"]:
            if row["parent_id"] and (row["id"] == record_id or row["parent_id"] == record_id):
                edges.append({"id": "parent:" + row["id"], "source": row["parent_id"], "target": row["id"], "label": f"contains · {row['position']+1}", "kind": "order", "position": row["position"]})
        for table, kind, a, b, label in (("links", "relationship", "source_id", "target_id", "relation"), ("assignments", "assignment", "shot_id", "asset_id", "role")):
            for row in snapshot[table]:
                if record_id in (row[a], row[b]):
                    edges.append({**row, "source": row[a], "target": row[b], "label": row[label], "kind": kind})
        from storyboarder.rendering.composer import context
        record = entities[record_id]
        if record["kind"] != "asset":
            location = context(snapshot, record_id)["scalars"].get("location_id")
            target_id = location["value"] if location else None
            target = entities.get(target_id)
            if target and target["kind"] == "asset":
                edges.append({"id": f"location-default:{record_id}:{target_id}", "source": record_id, "target": target_id, "label": "default location", "kind": "location_default", "source_scope": location["source"]})
        elif record.get("fields", {}).get("type") == "location":
            for owner in snapshot["entities"]:
                if owner["kind"] != "asset" and owner.get("fields", {}).get("location_id") == record_id:
                    edges.append({"id": f"location-default:{owner['id']}:{record_id}", "source": owner["id"], "target": record_id, "label": f"default location · {owner['kind']}", "kind": "location_default", "source_scope": {"id": owner["id"], "kind": owner["kind"], "title": owner["title"]}})
        node_ids = {record_id} | {e[k] for e in edges for k in ("source", "target")}
        return {"nodes": [entities[n] for n in sorted(node_ids) if n in entities], "edges": edges}

    def graph(self, mode="story", query="", asset_type=None, tag=None, relation=None, scene_id=None, sequence_id=None, limit=250):
        if mode not in ("story", "assets", "scene"):
            raise StoryboardError("Choose Story flow, Reference map, or Scene board.")
        limit = min(max(int(limit), 1), 500)
        snapshot = self.repo.snapshot()
        entities = {r["id"]: r for r in snapshot["entities"] if not r["archived"]}
        if mode == "assets":
            nodes = [r for r in entities.values() if r["kind"] == "asset"]
        elif mode == "scene":
            if not scene_id:
                return {"nodes": [], "edges": [], "total": 0, "truncated": False, "mode": mode}
            nodes = [r for r in entities.values() if r["id"] == scene_id or (r["kind"] == "shot" and r["parent_id"] == scene_id)]
            shot_ids = {r["id"] for r in nodes}
            asset_ids = {a["asset_id"] for a in snapshot["assignments"] if a["shot_id"] in shot_ids}
            nodes += [r for r in entities.values() if r["id"] in asset_ids]
            from storyboarder.rendering.composer import context
            location = context(snapshot, scene_id)["scalars"].get("location_id")
            location_id = location["value"] if location else None
            if location_id and not any(r["id"] == location_id for r in nodes):
                location_record = next((r for r in snapshot["entities"] if r["id"] == location_id and r["kind"] == "asset"), None)
                if location_record:
                    nodes.append(location_record)
        else:
            nodes = [r for r in entities.values() if r["kind"] in ("sequence", "scene", "shot")]
            if sequence_id:
                scenes = {r["id"] for r in nodes if r["parent_id"] == sequence_id}
                nodes = [r for r in nodes if r["id"] == sequence_id or r["parent_id"] == sequence_id or r["parent_id"] in scenes]
        if query:
            q = query.casefold()
            nodes = [r for r in nodes if q in (r["title"] + " " + " ".join(r["aliases"]) + " " + r["description"]).casefold()]
        if asset_type:
            nodes = [r for r in nodes if r["fields"].get("type") == asset_type]
        if tag:
            nodes = [r for r in nodes if tag in r["tags"]]
        if relation:
            related = {r[k] for r in snapshot["links"] if r["relation"] == relation for k in ("source_id", "target_id")}
            nodes = [r for r in nodes if r["id"] in related]
        nodes.sort(key=lambda r: ({"sequence": 0, "scene": 1, "shot": 2, "asset": 3}[r["kind"]], r["parent_id"] or "", r["position"], r["title"], r["id"]))
        total = len(nodes)
        nodes = nodes[:limit]
        ids = {r["id"] for r in nodes}
        media = {r["id"]: r for r in snapshot["media"]}
        for row in nodes:
            members = [m for m in snapshot["asset_media"] if m["asset_id"] == row["id"]]
            preferred = next((f for f in snapshot["frames"] if f["shot_id"] == row["id"] and f["state"] in ("selected", "approved")), None)
            primary = next((m for m in members if m["is_primary"]), None)
            row["thumbnail_media_id"] = preferred["media_id"] if preferred else primary["media_id"] if primary else None
            row["reference_media_ids"] = [a["media_id"] for a in snapshot["assignments"] if a["shot_id"] == row["id"] and a["media_id"]]
            row["frame_state"] = preferred["state"] if preferred else None
            row["media_count"] = len(members)
            row["child_count"] = sum(1 for r in entities.values() if r["parent_id"] == row["id"])
            row["reference_count"] = sum(1 for a in snapshot["assignments"] if row["id"] in (a["asset_id"], a["shot_id"]))
            row["link_count"] = sum(1 for a in snapshot["links"] if row["id"] in (a["source_id"], a["target_id"]))
        edges = []
        for row in nodes:
            if row["parent_id"] in ids:
                edges.append({"id": "parent:" + row["id"], "source": row["parent_id"], "target": row["id"], "kind": "order", "label": f"{row['position'] + 1:02}", "position": row["position"]})
        for row in snapshot["links"]:
            if row["source_id"] in ids and row["target_id"] in ids and (not relation or row["relation"] == relation):
                edges.append({**row, "source": row["source_id"], "target": row["target_id"], "kind": "relationship", "label": row["relation"]})
        for row in snapshot["assignments"]:
            if row["shot_id"] in ids and row["asset_id"] in ids:
                edges.append({**row, "source": row["shot_id"], "target": row["asset_id"], "kind": "assignment", "label": row["role"] + (" · specific image selected" if row["media_id"] else " · no specific image selected")})
        if mode == "scene" and scene_id in ids and location and location_id in ids:
            edges.append({"id": f"location-default:{scene_id}:{location_id}", "source": scene_id, "target": location_id, "kind": "location_default", "label": "default location", "source_scope": location["source"]})
        return {"nodes": nodes, "edges": edges, "total": total, "truncated": total > limit, "mode": mode}

    def compose(self, owner_id):
        from storyboarder.rendering.composer import compose
        return compose(self.repo.snapshot(), owner_id, self.root)

    def export_bundle(self, owner_id, include_media=True):
        from storyboarder.rendering.exports import export_bundle
        return export_bundle(self, owner_id, include_media)

    def export_board(self, owner_id, format="html", approved_only=False):
        from storyboarder.rendering.boards import export_board
        return export_board(self, owner_id, format, approved_only)

    def doctor(self, hashes=False):
        from .recovery import doctor
        return doctor(self, hashes)

    def backup(self):
        from .recovery import backup
        return backup(self)

    def cache(self, rebuild=False):
        from storyboarder.media.files import clear_cache
        clear_cache(self.root)
        errors, count = [], 0
        if rebuild:
            for media in self.repo.snapshot()["media"]:
                try:
                    thumbnail(self.root, media)
                    count += 1
                except StoryboardError as exc:
                    errors.append({"media_id": media["id"], "message": str(exc)})
        return {"rebuilt": count, "cleared": True, "errors": errors}
