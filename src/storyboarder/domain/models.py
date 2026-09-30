"""Typed authoring contract. Unknown fields are errors, not hidden metadata."""
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from .errors import StoryboardError

ASSET_TYPES = ("character", "location", "prop", "reference")
ENTITY_KINDS = ("project", "asset", "sequence", "scene", "shot")
ROLES = ("subject", "setting-reference", "costume", "prop", "reference")
FRAME_STATES = ("draft", "selected", "approved", "archived")
RELATION_RULES = {
    "appears-at": ({"character", "prop", "reference"}, {"location"}),
    "alternate-view-of": (set(ASSET_TYPES), set(ASSET_TYPES)),
    "wears": ({"character"}, {"prop"}),
    "part-of": (set(ASSET_TYPES), set(ASSET_TYPES)),
    "related-to": (set(ASSET_TYPES), set(ASSET_TYPES)),
}


def uid():
    return str(uuid.uuid4())


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def text(value, label="Text", max_length=100000):
    if not isinstance(value, str) or len(value) > max_length or "\x00" in value:
        raise StoryboardError(f"{label} must be text under {max_length:,} characters without NUL bytes.")
    return value.strip()


def title(value):
    result = text(value, "Title", 240)
    if not result:
        raise StoryboardError("Give this record a title.")
    return result


def words(value):
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, list) or len(value) > 100:
        raise StoryboardError("Use a list of at most 100 plain-text tags or aliases.")
    if any(not isinstance(v, str) for v in value):
        raise StoryboardError("Tags and aliases must contain only plain text.")
    return sorted({text(v, "Tag or alias", 100) for v in value if v.strip()})


def slug(value):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", value or ""):
        raise StoryboardError("Folder name must be 1–64 lowercase letters, numbers or hyphens.")
    return value


class Fields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_max_length=100000, allow_inf_nan=False)
    notes: str = ""

    @field_validator("*", mode="before", check_fields=False)
    @classmethod
    def safe_authored_text(cls, value):
        if isinstance(value, str) and "\x00" in value:
            raise ValueError("Authored fields cannot contain NUL bytes.")
        return value


class Defaults(Fields):
    location_id: str | None = None
    time: str = ""
    framing: str = ""
    camera: str = ""
    constraints: str = ""


class ProjectFields(Defaults):
    premise: str = ""
    visual_style: str = ""


class AssetFields(Fields):
    type: Literal["character", "location", "prop", "reference"] = "reference"


class SequenceFields(Defaults):
    arc: str = ""
    tone: str = ""


class SceneFields(Defaults):
    summary: str = ""
    continuity: str = ""


class ShotFields(Defaults):
    number: str = ""
    action: str = ""
    dialogue: str = ""
    duration: float | None = Field(default=None, ge=0, le=86400)
    continuity: str = ""


FIELD_MODELS = {
    "project": ProjectFields, "asset": AssetFields, "sequence": SequenceFields,
    "scene": SceneFields, "shot": ShotFields,
}


def validate_fields(kind, values):
    try:
        return FIELD_MODELS[kind].model_validate(values).model_dump()
    except (ValidationError, KeyError) as exc:
        raise StoryboardError(f"Invalid {kind} fields: {exc}") from exc


def check_relation(source, target, relation):
    if source["id"] == target["id"]:
        raise StoryboardError("An asset cannot link to itself.")
    if relation not in RELATION_RULES:
        raise StoryboardError(f"Unknown relationship. Use: {', '.join(RELATION_RULES)}.")
    allowed_source, allowed_target = RELATION_RULES[relation]
    if source["kind"] != "asset" or target["kind"] != "asset":
        raise StoryboardError("Asset relationships require two asset endpoints. Use story move or shot assign instead.")
    a, b = source["fields"]["type"], target["fields"]["type"]
    if a not in allowed_source or b not in allowed_target:
        raise StoryboardError(f"'{relation}' cannot connect {a} → {b}; allowed sources: {', '.join(sorted(allowed_source))}; targets: {', '.join(sorted(allowed_target))}.")
    if relation == "alternate-view-of" and a != b:
        raise StoryboardError("Alternate views must have the same asset type.")


def check_role(asset, role):
    if role not in ROLES:
        raise StoryboardError(f"Unknown shot role. Use {', '.join(ROLES)}.")
    allowed = {"subject": {"character", "prop", "reference"}, "setting-reference": {"location", "reference"},
               "costume": {"prop", "reference"}, "prop": {"prop", "reference"}, "reference": set(ASSET_TYPES)}
    if asset["fields"]["type"] not in allowed[role]:
        raise StoryboardError(f"A {asset['fields']['type']} asset cannot be used as {role}.")
