"""Shared command catalog and form vocabulary; all handlers call application services.

HTTP exposes only this explicit allow-list, not arbitrary service methods or paths.
"""

from dataclasses import dataclass, field, asdict

from typing import Any, Callable

import json

from storyboarder.domain.errors import StoryboardError

from storyboarder.domain.models import ASSET_TYPES, ROLES, RELATION_RULES, FRAME_STATES, FIELD_MODELS

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
        record = s.get("entities", p["id"])
        if record["kind"] != kind:
            raise StoryboardError(f"Choose a {kind} for this command, not a {record['kind']}.")
        known = FIELD_MODELS[kind].model_fields
        changes = {k: v for k, v in p.items() if k in ("title", "description", "tags", "aliases")}
        changes["fields"] = {k: v for k, v in p.items() if k in known}
        return s.update_entity(p["id"], p["revision"], changes)
    return handler

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
            if f.default is not None and not f.required and not name.endswith(".update"):
                values[f.name] = f.default
                continue
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
