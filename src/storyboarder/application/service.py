"""Stable application facade over domain-specific operation modules."""
from storyboarder.domain.errors import StoryboardError
from .projects import Project
from .authoring import AuthoringOperations
from .media import MediaOperations
from .assets import AssetOperations
from .contexts import ContextOperations
from .frames import FrameOperations
from .layouts import LayoutOperations
from .delivery import DeliveryOperations


class Service(AuthoringOperations, MediaOperations, AssetOperations, ContextOperations, FrameOperations, LayoutOperations, DeliveryOperations):
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
        where, args = (["1=1"], []) if archived else (["e.archived=0"], [])
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
