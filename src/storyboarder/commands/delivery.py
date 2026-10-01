"""Delivery command registrations; handlers use the application facade."""
from .core import F, OWNER, register


register("composition.preview", "Preview storyboard", [OWNER], lambda s, p: s.compose(p["owner_id"]), read_only=True, page="composition")

register("export.bundle", "Create project handoff package", [OWNER, F("include_media", "Include reference images", "boolean", default=True)], lambda s, p: s.export_bundle(p["owner_id"], p.get("include_media", True)), page="composition")

register("export.board", "Export storyboard", [OWNER, F("format", "File format", "select", options=("html", "pdf", "png", "all"), default="all"), F("approved_only", "Use approved storyboard images only", "boolean")], lambda s, p: s.export_board(p["owner_id"], p.get("format", "all"), p.get("approved_only", False)), page="composition")

register("cache.rebuild", "Rebuild image previews", [], lambda s, p: s.cache(True), page="settings")

register("cache.clear", "Clear image previews", [], lambda s, p: s.cache(False), page="settings")
