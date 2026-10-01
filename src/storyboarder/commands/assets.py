"""Assets command registrations; handlers use the application facade."""
from .core import F, ID, RELATION_RULES, REV, ROLES, register


register("asset.attach", "Add image to library item", [F("asset_id", "Library item", required=True, source="assets"), F("media_id", "Image", required=True, source="media")], lambda s, p: s.attach_media(p["asset_id"], p["media_id"]), page="library")

register("asset.primary", "Set cover image", [ID("asset_media", label="Library image"), REV], lambda s, p: s.primary_media(p["id"], p["revision"]), page="library")

register("asset.detach", "Remove image from library item", [ID("asset_media", label="Library image"), REV], lambda s, p: s.detach_media(p["id"], p["revision"]), page="library", destructive=True)

register("asset.merge", "Combine library items", [F("source_id", "Item to combine", required=True, source="assets"), REV, F("target_id", "Keep this item", required=True, source="assets"), F("target_revision", "Version check", "integer", True)], lambda s, p: s.merge_assets(p["source_id"], p["revision"], p["target_id"], p["target_revision"]), page="library", destructive=True)

register("link.create", "Connect library items", [F("source_id", "First item", required=True, source="assets"), F("target_id", "Second item", required=True, source="assets"), F("relation", "How they are connected", "select", True, RELATION_RULES)], lambda s, p: s.create_link(p["source_id"], p["target_id"], p["relation"]), page="connections")

register("assignment.create", "Use a reference in a shot", [F("shot_id", "Shot", required=True, source="shots"), F("asset_id", "Library item", required=True, source="assets"), F("role", "How it appears in the shot", "select", True, ROLES, default="reference"), F("media_id", "Choose a specific image (optional)", source="asset_images", help="Choose an image from this library item. Leave blank if any of its images may be used.")], lambda s, p: s.assign(p["shot_id"], p["asset_id"], p.get("role", "reference"), p.get("media_id")), page="editor")

register("assignment.update", "Edit shot reference", [ID("assignments", label="Shot reference"), REV, F("role", "How it appears in the shot", "select", True, ROLES), F("media_id", "Choose a specific image", source="asset_images")], lambda s, p: s.update_assignment(p["id"], p["revision"], p["role"], p.get("media_id")), page="editor")
