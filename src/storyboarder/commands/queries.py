"""Queries command registrations; handlers use the application facade."""
from .core import F, register


LIST_LABELS = {
    "media": "List images", "intake": "List image intake", "link": "List connections",
    "assignment": "List shot references", "context": "List direction notes",
    "frame": "List storyboard images", "canvas": "List saved arrangements",
    "job": "List image requests",
}

for name, table in (("media", "media"), ("intake", "intake"), ("link", "links"), ("assignment", "assignments"), ("context", "context_blocks"), ("frame", "frames"), ("canvas", "layouts"), ("job", "jobs")):
    def list_handler(s, p, t=table):
        rows = s.repo.snapshot()[t]
        return [r for r in rows if all(r.get(k) == v for k, v in p.items() if v is not None)]
    filters = {"intake": [F("state", options=("pending", "accepted", "discarded"))], "frames": [F("shot_id", source="shots")], "context_blocks": [F("owner_id", source="story")], "assignments": [F("shot_id", source="shots")], "layouts": [F("mode", options=("story", "assets", "scene"))], "jobs": [F("status", options=("queued", "running", "succeeded", "failed", "cancelled"))]}.get(table, [])
    register(name + ".list", LIST_LABELS[name], filters, list_handler, read_only=True)
