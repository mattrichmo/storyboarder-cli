"""Authoring command registrations; handlers use the application facade."""
from .core import ASSET_TYPES, F, ID, PARENT, REV, authored_fields, create_handler, register, update_handler


for kind in ("asset", "sequence", "scene", "shot"):
    fields = [F("title", required=True)]
    if kind in PARENT:
        fields += [F("parent_id", "Parent " + PARENT[kind][:-1], required=True, source=PARENT[kind])]
    fields += [F("description", type="textarea"), *authored_fields(kind)]
    if kind == "asset":
        fields += [F("tags", "Tags (comma-separated)", "tags"), F("aliases", "Aliases (comma-separated)", "tags")]
    register(kind + ".create", "New " + ("library item" if kind == "asset" else kind), fields, create_handler(kind), page="library" if kind == "asset" else "outline")
    edits = [F(f.name, f.label, f.type, False, f.options, f.source, f.help) for f in fields if f.name != "parent_id"]
    register(kind + ".update", "Edit " + ("library item" if kind == "asset" else kind), [ID(kind + "s"), REV, *edits], update_handler(kind), page="library" if kind == "asset" else "editor")
    register(kind + ".list", "Find " + ("library items" if kind == "asset" else kind + "s"), [F("query", "Search"), F("tag", "Tag"), F("asset_type", "Item type", options=ASSET_TYPES), F("parent_id", "Place under"), F("archived", "Include archived", type="boolean"), F("limit", "Maximum results", type="integer", default=200), F("offset", "Start at", type="integer", default=0)], lambda s, p, k=kind: s.list_entities(kind=k, **p), read_only=True)
    register(kind + ".show", "View " + ("library item" if kind == "asset" else kind) + " details", [ID(kind+"s")], lambda s, p: s.get("entities", p["id"]), read_only=True)

register("project.update", "Edit project direction", [ID("projects"), REV, F("title"), F("description", type="textarea"), *authored_fields("project")], update_handler("project"), page="guide")

register("entity.update", "Edit item details", [ID(), REV, F("changes", "Changes", type="json", required=True)], lambda s, p: s.update_entity(p["id"], p["revision"], p["changes"]))

register("entity.usage", "See where an item is used", [ID()], lambda s, p: s.usage(p["id"]), read_only=True)

for action in ("archive", "restore", "delete"):
    register("entity." + action, action.title() + " item", [ID(), REV], lambda s, p, a=action: s.lifecycle(p["id"], p["revision"], a), destructive=action != "restore")

register("story.move", "Move or reorder a story item", [ID("story"), REV, F("position", "New position", "integer", True), F("parent_id", "Place under (optional)", source="parents")], lambda s, p: s.move(p["id"], p["revision"], p["position"], p.get("parent_id")), page="outline")

register("project.doctor", "Check project health", [F("hashes", "Check image contents", "boolean")], lambda s, p: s.doctor(p.get("hashes", False)), read_only=True, page="settings")

register("project.backup", "Back up project", [], lambda s, p: s.backup(), page="settings")

register("project.sync", "Update project title", [], lambda s, p: (s.project.sync_manifest() or s.project.summary()), page="settings")

for name, table in (("link", "links"), ("assignment", "assignments"), ("context", "context_blocks"), ("frame", "frames"), ("canvas", "layouts")):
    register(name + ".remove", "Remove " + {"context":"direction note","link":"connection","assignment":"shot reference","frame":"storyboard image","canvas":"saved layout"}.get(name,"item"), [ID(table), REV], lambda s, p, t=table: s.remove(t, p["id"], p["revision"]), destructive=True)
