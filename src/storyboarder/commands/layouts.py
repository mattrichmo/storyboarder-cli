"""Layouts command registrations; handlers use the application facade."""
from .core import ASSET_TYPES, F, ID, RELATION_RULES, register


register("canvas.graph", "View story connections", [F("mode", "View", "select", options=("story", "assets", "scene"), default="story"), F("query", "Search"), F("asset_type", "Item type", options=ASSET_TYPES), F("tag", "Tag"), F("relation", "Connection type", "select", options=RELATION_RULES), F("scene_id", "Scene", source="scenes"), F("sequence_id", "Sequence", source="sequences"), F("limit", "Maximum cards", type="integer", default=250)], lambda s, p: s.graph(**p), read_only=True)

register("canvas.neighbors", "See connected items", [ID()], lambda s, p: s.neighbors(p["id"]), read_only=True, page="connections")

register("canvas.save", "Save canvas arrangement", [F("name", required=True), F("mode", "View", "select", True, ("story", "assets", "scene")), F("positions", type="json", required=True), F("settings", type="json"), F("revision", "Existing layout revision", "integer"), F("layout_id", "Saved arrangement", "select", source="layouts")], lambda s, p: s.save_layout(p["name"], p["mode"], p["positions"], p.get("settings"), p.get("revision"), p.get("layout_id")))

register("canvas.show", "Show saved arrangement", [ID("layouts")], lambda s, p: s.get("layouts", p["id"]), read_only=True)
