"""Shared command catalog and form vocabulary; all handlers call application services.

HTTP exposes only this explicit allow-list, not arbitrary service methods or paths.
"""
from dataclasses import dataclass, field, asdict
from typing import Any, Callable
import json
from storyboarder.domain.errors import StoryboardError
from storyboarder.domain.models import ASSET_TYPES, ROLES, RELATION_RULES, FRAME_STATES, FIELD_MODELS
from storyboarder.automation.jobs import Jobs
from storyboarder.automation.registry import ScriptRegistry


@dataclass
class InputField:
    name: str
    label: str
    type: str = "text"
    required: bool = False
    options: list[str] = field(default_factory=list)
    source: str = ""
    help: str = ""
    default: Any = None


@dataclass
class Command:
    name: str
    label: str
    fields: list[InputField]
    handler: Callable
    page: str = ""
    destructive: bool = False
    browser: bool = True
    read_only: bool = False

    def public(self):
        return {"name": self.name, "label": self.label, "fields": [asdict(f) for f in self.fields], "page": self.page, "destructive": self.destructive, "browser": self.browser, "read_only": self.read_only}


COMMANDS: dict[str, Command] = {}

CHOICE_LABELS = {
    "assets": "Reference map", "scene": "Scene board", "story": "Story flow",
    "asset": "Library item", "frame": "Storyboard image", "append": "Add to earlier notes",
    "replace": "Replace earlier notes", "exclude": "Hide earlier notes here",
    "setting-reference": "Location", "subject": "Subject", "costume": "Wardrobe",
    "reference": "General reference", "same-person-as": "Same person as",
    "alternate-view-of": "Alternate view of", "appears-at": "Appears at",
    "part-of": "Part of", "inspired-by": "Inspired by", "related-to": "Related to",
    "wears": "Wears", "draft": "Draft", "selected": "Selected", "approved": "Approved",
    "archived": "Archived", "pending": "Needs review", "accepted": "Added",
    "discarded": "Removed from intake", "queued": "Ready to run", "running": "In progress",
    "succeeded": "Complete", "failed": "Needs attention", "cancelled": "Stopped",
}


def choice_label(value):
    value = str(value)
    return CHOICE_LABELS.get(value, value.replace("_", " ").replace("-", " ").title())


def F(name, label=None, type="text", required=False, options=(), source="", help="", default=None):
    return InputField(name, label or name.replace("_", " ").title(), type, required, list(options), source, help, default)


def register(name, label, fields, handler, **kwargs):
    COMMANDS[name] = Command(name, label, fields, handler, **kwargs)


def record_id(source="entities", name="id", label=None):
    labels = {"assets": "Library item", "media": "Image", "intake": "Imported image", "asset_media": "Library image", "frames": "Storyboard image", "assignments": "Shot reference", "context_blocks": "Direction note", "jobs": "Tool run", "layouts": "Saved arrangement", "links": "Connection", "story": "Story item"}
    return F(name, label or labels.get(source, "Choose item"), required=True, source=source)


ID = record_id
REV = F("revision", "Version check", "integer", True, help="Keeps a newer edit from being overwritten.")
OWNER = F("owner_id", "Apply direction to", required=True, source="story")
PARENT = {"scene": "sequences", "shot": "scenes"}
MULTILINE = {"description", "notes", "action", "dialogue", "continuity", "summary", "constraints", "premise", "visual_style", "arc", "tone", "camera"}


def authored_fields(kind):
    result = []
    for name in FIELD_MODELS[kind].model_fields:
        if name == "type":
            result.append(F(name, "Item type", "select", options=ASSET_TYPES, default="reference"))
        elif name == "location_id":
            result.append(F(name, "Location", source="locations", help="Leave blank to use the location set higher in the story."))
        elif name == "duration":
            result.append(F(name, "Duration (seconds)", "number"))
        else:
            result.append(F(name, type="textarea" if name in MULTILINE else "text"))
    return result


def create_handler(kind):
    def handler(s, p):
        known = FIELD_MODELS[kind].model_fields
        return s.create_entity(kind, p["title"], p.get("parent_id"), p.get("description", ""), {k: v for k, v in p.items() if k in known}, p.get("tags"), p.get("aliases"))
    return handler


def update_handler(kind):
    def handler(s, p):
        known = FIELD_MODELS[kind].model_fields
        changes = {k: v for k, v in p.items() if k in ("title", "description", "tags", "aliases")}
        changes["fields"] = {k: v for k, v in p.items() if k in known}
        return s.update_entity(p["id"], p["revision"], changes)
    return handler


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
register("media.import", "Import file or folder", [F("path", "File or folder path", required=True), F("recursive", "Include nested folders", "boolean")], lambda s, p: s.import_path(p["path"], p.get("recursive", False)), page="intake", browser=False)
register("media.tags", "Edit image tags", [ID("media"), REV, F("tags", "Tags (comma-separated)", "tags", True)], lambda s, p: s.tag_media(p["id"], p["revision"], p["tags"]), page="intake")
register("media.show", "View image details", [ID("media")], lambda s, p: s.get("media", p["id"]), read_only=True)
register("asset.attach", "Add image to library item", [F("asset_id", "Library item", required=True, source="assets"), F("media_id", "Image", required=True, source="media")], lambda s, p: s.attach_media(p["asset_id"], p["media_id"]), page="library")
register("asset.primary", "Set cover image", [ID("asset_media", label="Library image"), REV], lambda s, p: s.primary_media(p["id"], p["revision"]), page="library")
register("asset.detach", "Remove image from library item", [ID("asset_media", label="Library image"), REV], lambda s, p: s.detach_media(p["id"], p["revision"]), page="library", destructive=True)
register("asset.merge", "Combine library items", [F("source_id", "Item to combine", required=True, source="assets"), REV, F("target_id", "Keep this item", required=True, source="assets"), F("target_revision", "Version check", "integer", True)], lambda s, p: s.merge_assets(p["source_id"], p["revision"], p["target_id"], p["target_revision"]), page="library", destructive=True)
register("intake.accept", "Add image to library", [ID("intake", label="Imported image"), REV, F("asset_id", "Add to an existing item", source="assets"), F("create_title", "Or create a new item"), F("create_type", "New item type", "select", options=ASSET_TYPES, default="reference"), F("tags", "Tags (comma-separated)", "tags")], lambda s, p: s.review_intake(p["id"], p["revision"], "accepted", p.get("asset_id"), p.get("create_title"), p.get("create_type", "reference"), p.get("tags")), page="intake")
register("intake.discard", "Remove image from intake", [ID("intake", label="Imported image"), REV], lambda s, p: s.review_intake(p["id"], p["revision"], "discarded"), page="intake", destructive=True)
register("link.create", "Connect library items", [F("source_id", "First item", required=True, source="assets"), F("target_id", "Second item", required=True, source="assets"), F("relation", "How they are connected", "select", True, RELATION_RULES)], lambda s, p: s.create_link(p["source_id"], p["target_id"], p["relation"]), page="connections")
register("assignment.create", "Use a reference in a shot", [F("shot_id", "Shot", required=True, source="shots"), F("asset_id", "Library item", required=True, source="assets"), F("role", "How it appears in the shot", "select", True, ROLES, default="reference"), F("media_id", "Choose a specific image (optional)", source="asset_images", help="Choose an image from this library item. Leave blank if any of its images may be used.")], lambda s, p: s.assign(p["shot_id"], p["asset_id"], p.get("role", "reference"), p.get("media_id")), page="editor")
register("assignment.update", "Edit shot reference", [ID("assignments", label="Shot reference"), REV, F("role", "How it appears in the shot", "select", True, ROLES), F("media_id", "Choose a specific image", source="asset_images")], lambda s, p: s.update_assignment(p["id"], p["revision"], p["role"], p.get("media_id")), page="editor")
register("context.put", "Add or edit a direction note", [OWNER, F("key", "Topic", required=True), F("operation", "How it changes earlier direction", "select", True, ("append", "replace", "exclude"), default="append"), F("content", "Direction notes", "textarea"), F("revision", "Version check", "integer")], lambda s, p: s.put_context(p["owner_id"], p["key"], p.get("operation", "append"), p.get("content", ""), p.get("revision")), page="guide")
register("context.resolve", "Preview story direction", [OWNER], lambda s, p: s.compose(p["owner_id"])["context"], read_only=True, page="guide")
register("frame.add", "Add storyboard image from file", [F("shot_id", "Shot", required=True, source="shots"), F("path", "Image file", required=True), F("notes", "Notes", type="textarea")], lambda s, p: s.add_frame(p["shot_id"], p["path"], p.get("notes", "")), page="frames", browser=False)
register("frame.attach", "Use project image as storyboard frame", [F("shot_id", "Shot", required=True, source="shots"), F("media_id", "Image", required=True, source="media"), F("notes", "Notes", type="textarea")], lambda s, p: s.attach_frame(p["shot_id"], p["media_id"], p.get("notes", "")), page="frames")
register("frame.state", "Update storyboard image status", [ID("frames", label="Storyboard image"), REV, F("state", "Status", "select", True, FRAME_STATES)], lambda s, p: s.set_frame_state(p["id"], p["revision"], p["state"]), page="frames")
register("canvas.graph", "View story connections", [F("mode", "View", "select", options=("story", "assets", "scene"), default="story"), F("query", "Search"), F("asset_type", "Item type", options=ASSET_TYPES), F("tag", "Tag"), F("relation", "Connection type", "select", options=RELATION_RULES), F("scene_id", "Scene", source="scenes"), F("sequence_id", "Sequence", source="sequences"), F("limit", "Maximum cards", type="integer", default=250)], lambda s, p: s.graph(**p), read_only=True)
register("canvas.neighbors", "See connected items", [ID()], lambda s, p: s.neighbors(p["id"]), read_only=True, page="connections")
register("canvas.save", "Save canvas arrangement", [F("name", required=True), F("mode", "View", "select", True, ("story", "assets", "scene")), F("positions", type="json", required=True), F("settings", type="json"), F("revision", "Existing layout revision", "integer")], lambda s, p: s.save_layout(p["name"], p["mode"], p["positions"], p.get("settings"), p.get("revision")))
register("canvas.show", "Show saved arrangement", [ID("layouts")], lambda s, p: s.get("layouts", p["id"]), read_only=True)
register("composition.preview", "Preview storyboard", [OWNER], lambda s, p: s.compose(p["owner_id"]), read_only=True, page="composition")
register("export.bundle", "Create project handoff package", [OWNER, F("include_media", "Include reference images", "boolean", default=True)], lambda s, p: s.export_bundle(p["owner_id"], p.get("include_media", True)), page="composition")
register("export.board", "Export storyboard", [OWNER, F("format", "File format", "select", options=("html", "pdf", "png", "all"), default="all"), F("approved_only", "Use approved storyboard images only", "boolean")], lambda s, p: s.export_board(p["owner_id"], p.get("format", "all"), p.get("approved_only", False)), page="composition")
register("project.doctor", "Check project health", [F("hashes", "Check image contents", "boolean")], lambda s, p: s.doctor(p.get("hashes", False)), read_only=True, page="settings")
register("project.backup", "Back up project", [], lambda s, p: s.backup(), page="settings")
register("cache.rebuild", "Rebuild image previews", [], lambda s, p: s.cache(True), page="settings")
register("cache.clear", "Clear image previews", [], lambda s, p: s.cache(False), page="settings")
register("project.sync", "Update project title", [], lambda s, p: (s.project.sync_manifest() or s.project.summary()), page="settings")
register("job.create", "Prepare an image request", [F("script", "Image tool", required=True, source="scripts"), F("target", "Create", "select", True, ("asset", "frame"), default="asset"), F("shot_id", "Shot (for a storyboard image)", source="shots"), F("title", "Name for the result", required=True), F("asset_type", "Library item type", "select", options=ASSET_TYPES, default="reference"), F("prompt", "Instructions for the tool", "textarea")], lambda s, p: Jobs(s).create(p["script"], p.get("target", "asset"), p.get("shot_id"), p["title"], p.get("asset_type", "reference"), p.get("prompt", "")), page="automation")
for action in ("run", "cancel", "retry", "approve"):
    register("job." + action, {"run": "Run image tool", "cancel": "Stop image tool", "retry": "Run again", "approve": "Add reviewed results to project"}[action], [ID("jobs", label="Run"), REV], lambda s, p, a=action: getattr(Jobs(s), a)(p["id"], p["revision"]), page="automation", destructive=action in ("run", "cancel", "approve"))
register("job.preview", "Review image tool results", [ID("jobs", label="Image request")], lambda s, p: Jobs(s).preview(p["id"]), read_only=True, page="automation")
for name, table in (("link", "links"), ("assignment", "assignments"), ("context", "context_blocks"), ("frame", "frames"), ("canvas", "layouts")):
    register(name + ".remove", "Remove " + {"context":"direction note","link":"connection","assignment":"shot reference","frame":"storyboard image","canvas":"saved layout"}.get(name,"item"), [ID(table), REV], lambda s, p, t=table: s.remove(t, p["id"], p["revision"]), destructive=True)
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


def execute(service, name, payload=None, browser=False):
    if name not in COMMANDS:
        raise StoryboardError("That action is no longer available. Refresh the project and try again.")
    command = COMMANDS[name]
    if browser and not command.browser:
        raise StoryboardError("This file or folder action is available from the command line or TUI. In the app, use image upload instead.")
    payload = payload or {}
    if not isinstance(payload, dict):
        raise StoryboardError("The action could not be completed. Refresh the project and try again.")
    allowed = {f.name for f in command.fields}
    if set(payload) - allowed:
        raise StoryboardError("Some action details are out of date. Refresh the project and try again.")
    values = {}
    for f in command.fields:
        if f.name not in payload:
            if f.required:
                raise StoryboardError(f"{f.label} is required.")
            if f.default is not None and not name.endswith(".update"):
                values[f.name] = f.default
            continue
        value = payload[f.name]
        if value is None or value == "":
            if f.required and f.type != "tags":
                raise StoryboardError(f"{f.label} is required.")
            if f.type in ("integer", "number") or f.source:
                values[f.name] = None
                continue
        if f.type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
            raise StoryboardError(f"{f.label} must be an integer.")
        if f.type == "number" and (not isinstance(value, (int, float)) or isinstance(value, bool)):
            raise StoryboardError(f"{f.label} must be a number.")
        if f.type == "boolean" and not isinstance(value, bool):
            raise StoryboardError(f"{f.label} must be true or false.")
        if f.type == "json" and not isinstance(value, dict):
            raise StoryboardError(f"{f.label} has an invalid format. Review it and try again.")
        if f.type in ("text", "textarea", "select") and value is not None and not isinstance(value, str):
            raise StoryboardError(f"{f.label} must be text.")
        if f.options and value not in (None, "") and value not in f.options:
            raise StoryboardError(f"{f.label} must be one of: {', '.join(f.options)}.")
        values[f.name] = value
    return command.handler(service, values)


def options_for(source, state, values=None):
    values = values or {}
    entities = state.get("entities", [])
    by_id = {r["id"]: r for r in entities}
    if source == "scripts":
        return [(r["name"], r["name"] + " — " + r.get("description", "")) for r in ScriptRegistry().list()]
    kinds = {"assets": "asset", "sequences": "sequence", "scenes": "scene", "shots": "shot", "projects": "project"}
    if source in kinds:
        records = [r for r in entities if r["kind"] == kinds[source] and not r["archived"]]
    elif source == "locations":
        records = [r for r in entities if r["kind"] == "asset" and r["fields"]["type"] == "location" and not r["archived"]]
    elif source in ("story", "parents"):
        records = [r for r in entities if r["kind"] in (("project", "sequence", "scene") if source == "parents" else ("project", "sequence", "scene", "shot")) and not r["archived"]]
    else:
        records = state.get(source, entities if source == "entities" else [])
    if source == "asset_images":
        records = state["media"]
    if source == "asset_images" and values.get("asset_id"):
        allowed = {m["media_id"] for m in state.get("asset_media", []) if m["asset_id"] == values["asset_id"]}
        records = [r for r in records if r["id"] in allowed]
    result = []
    for record in records:
        label = record.get("title") or record.get("original_name") or record.get("name") or record.get("key")
        if source == "asset_media":
            media = next((m for m in state.get("media", []) if m["id"] == record["media_id"]), {})
            label = f"{by_id.get(record['asset_id'], {}).get('title', 'Library item')} / {media.get('original_name', 'Image')}" + (" · cover image" if record["is_primary"] else "")
        if source == "frames":
            label = f"{by_id.get(record['shot_id'], {}).get('title', 'Shot')} / image {record['version']} · {choice_label(record['state'])}"
        if source == "links":
            label = f"{by_id.get(record['source_id'], {}).get('title', 'Item')} → {choice_label(record['relation'])} → {by_id.get(record['target_id'], {}).get('title', 'Item')}"
        if source == "assignments":
            label = f"{by_id.get(record['shot_id'], {}).get('title', 'Shot')} → {choice_label(record['role'])} → {by_id.get(record['asset_id'], {}).get('title', 'Library item')}"
        result.append((record["id"], str(label or "Untitled item")))
    return result
