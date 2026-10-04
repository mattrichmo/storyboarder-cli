"""Authoring operations behind the shared Service facade.

Transactions remain in the application layer; UI adapters do not write SQL.
"""
from storyboarder.domain.errors import StoryboardError, InUse
from storyboarder.domain.models import uid, now, title, text, words, validate_fields, check_relation, check_role


class AuthoringOperations:
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
                if not isinstance(changes["fields"], dict):
                    raise StoryboardError("Authored fields must be a JSON object.")
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
            # Provenance and annotations are intentionally retained as history,
            # including retired links and resolved notes. The database guards
            # deletion on these references, so report them before attempting it.
            "provenance_links": ("SELECT id FROM provenance_edges WHERE (source_type='entity' AND source_id=?) OR (target_type='entity' AND target_id=?)", (record_id, record_id)),
            "annotations": ("SELECT id FROM annotations WHERE endpoint_type='entity' AND endpoint_id=?", (record_id,)),
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
