"""Contexts command registrations; handlers use the application facade."""
from .core import F, OWNER, register


register("context.put", "Add or edit a direction note", [OWNER, F("key", "Topic", required=True), F("operation", "How it changes earlier direction", "select", True, ("append", "replace", "exclude"), default="append"), F("content", "Direction notes", "textarea"), F("revision", "Version check", "integer")], lambda s, p: s.put_context(p["owner_id"], p["key"], p.get("operation", "append"), p.get("content", ""), p.get("revision")), page="guide")

register("context.resolve", "Preview story direction", [OWNER], lambda s, p: s.compose(p["owner_id"])["context"], read_only=True, page="guide")
