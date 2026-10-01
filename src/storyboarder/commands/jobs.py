"""Jobs command registrations; handlers use the application facade."""
from .core import ASSET_TYPES, F, ID, REV, register
from storyboarder.automation.jobs import Jobs


register("job.create", "Prepare an image request", [F("script", "Image tool", required=True, source="scripts"), F("target", "Create", "select", True, ("asset", "frame"), default="asset"), F("shot_id", "Shot (for a storyboard image)", source="shots"), F("title", "Name for the result", required=True), F("asset_type", "Library item type", "select", options=ASSET_TYPES, default="reference"), F("prompt", "Instructions for the tool", "textarea")], lambda s, p: Jobs(s).create(p["script"], p.get("target", "asset"), p.get("shot_id"), p["title"], p.get("asset_type", "reference"), p.get("prompt", "")), page="automation")

for action in ("run", "cancel", "retry", "approve"):
    register("job." + action, {"run": "Run image tool", "cancel": "Stop image tool", "retry": "Run again", "approve": "Add reviewed results to project"}[action], [ID("jobs", label="Run"), REV], lambda s, p, a=action: getattr(Jobs(s), a)(p["id"], p["revision"]), page="automation", destructive=action in ("run", "cancel", "approve"))

register("job.preview", "Review image tool results", [ID("jobs", label="Image request")], lambda s, p: Jobs(s).preview(p["id"]), read_only=True, page="automation")
