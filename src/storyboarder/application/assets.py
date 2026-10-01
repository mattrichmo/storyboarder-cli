"""Assets operations behind the shared Service facade.

Transactions remain in the application layer; UI adapters do not write SQL.
"""
import json
from storyboarder.domain.errors import StoryboardError, InUse
from storyboarder.domain.models import uid, now, check_relation, check_role, dumps


class AssetOperations:
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
