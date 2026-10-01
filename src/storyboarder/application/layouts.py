"""Layouts operations behind the shared Service facade.

Transactions remain in the application layer; UI adapters do not write SQL.
"""
import math
from storyboarder.domain.errors import StoryboardError, Conflict
from storyboarder.domain.models import uid, now, title, dumps


class LayoutOperations:
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
