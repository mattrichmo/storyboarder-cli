"""Media command registrations; handlers use the application facade."""
from .core import ASSET_TYPES, F, ID, REV, register


register("media.import", "Import file or folder", [F("path", "File or folder path", required=True), F("recursive", "Include nested folders", "boolean")], lambda s, p: s.import_path(p["path"], p.get("recursive", False)), page="intake", browser=False)

register("media.tags", "Edit image tags", [ID("media"), REV, F("tags", "Tags (comma-separated)", "tags", True)], lambda s, p: s.tag_media(p["id"], p["revision"], p["tags"]), page="intake")

register("media.show", "View image details", [ID("media")], lambda s, p: s.get("media", p["id"]), read_only=True)

register("intake.accept", "Add image to library", [ID("intake", label="Imported image"), REV, F("asset_id", "Add to an existing item", source="assets"), F("create_title", "Or create a new item"), F("create_type", "New item type", "select", options=ASSET_TYPES, default="reference"), F("tags", "Tags (comma-separated)", "tags")], lambda s, p: s.review_intake(p["id"], p["revision"], "accepted", p.get("asset_id"), p.get("create_title"), p.get("create_type", "reference"), p.get("tags")), page="intake")

register("intake.discard", "Remove image from intake", [ID("intake", label="Imported image"), REV], lambda s, p: s.review_intake(p["id"], p["revision"], "discarded"), page="intake", destructive=True)
