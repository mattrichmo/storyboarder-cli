"""Strict, versioned metre/XYZ spatial authoring contract.

Pure validation/canonicalization only. No database, pixels, or camera prose is
an alternative authority. Python validates every publication and import.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import math
import re
from typing import Annotated, Generic, Literal, TypeVar, Union

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictBool, StrictInt, ValidationError, field_validator, model_validator
from storyboarder.domain.errors import StoryboardError

SCHEMA = "storyboarder.spatial-plan/v1"
FRAME = "rh-z-up-x-right-y-forward/v1"
EVALUATOR = "storyboarder.spatial-evaluator/v1"
MAX_BYTES = 8 * 1024 * 1024
MAX_TIME = 86_400_000_000


class SpatialError(StoryboardError):
    def __init__(self, message, details=None, code="spatial_invalid", status=422):
        super().__init__(message, details)
        self.code, self.status = code, status


def finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Enter a finite number, not text or a boolean.")
    return float(value) if value else 0.0


def canonical_uuid(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", value):
        raise ValueError("Use a canonical lowercase UUID.")
    return value


Finite = Annotated[float, BeforeValidator(finite)]
Coord = Annotated[Finite, Field(ge=-100_000, le=100_000)]
Positive = Annotated[Finite, Field(gt=0, le=100_000)]
Nonnegative = Annotated[Finite, Field(ge=0, le=100_000)]
UnitInterval = Annotated[Finite, Field(ge=0, le=1)]
SignedUnit = Annotated[Finite, Field(ge=-1, le=1)]
Spread = Annotated[Finite, Field(gt=0, lt=179)]
Kelvin = Annotated[Finite, Field(ge=1000, le=20000)]
Microseconds = Annotated[StrictInt, Field(ge=0, le=MAX_TIME)]
UUID = Annotated[str, BeforeValidator(canonical_uuid)]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Label = Annotated[str, Field(min_length=1, max_length=240)]
Note = Annotated[str, Field(max_length=4000)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False, populate_by_name=True)


class Vec3(StrictModel):
    x: Coord
    y: Coord
    z: Coord


class Quaternion(StrictModel):
    x: Finite
    y: Finite
    z: Finite
    w: Finite

    @model_validator(mode="after")
    def normalized(self):
        values = [self.x, self.y, self.z, self.w]
        norm = math.hypot(*values)
        if not math.isfinite(norm) or norm < 1e-12:
            raise ValueError("Quaternion norm must be at least 1e-12.")
        values = [v / norm for v in values] if abs(norm - 1.0) > 2e-15 else values
        sign = next((1 if v > 0 else -1 for v in [values[3], *values[:3]] if v != 0), 1)
        for key, value in zip(("x", "y", "z", "w"), values):
            object.__setattr__(self, key, 0.0 if value == 0 else value * sign)
        return self


class Pose(StrictModel):
    position: Vec3
    orientation: Quaternion


class Span(StrictModel):
    start_us: Microseconds
    end_us: Microseconds

    @model_validator(mode="after")
    def ordered(self):
        if self.end_us < self.start_us:
            raise ValueError("End precedes start.")
        return self


class Extents(StrictModel):
    width_m: Positive
    depth_m: Positive
    height_m: Positive


class PointTarget(StrictModel):
    kind: Literal["point"]
    point: Vec3


class MarkTarget(StrictModel):
    kind: Literal["mark"]
    mark_id: UUID
    offset_world: Vec3


class ItemTarget(StrictModel):
    kind: Literal["item"]
    item_id: UUID
    offset_world: Vec3


Target = Annotated[Union[PointTarget, MarkTarget, ItemTarget], Field(discriminator="kind")]
PositionValue = Annotated[Union[PointTarget, MarkTarget], Field(discriminator="kind")]


class Aim(StrictModel):
    target: Target
    roll_rad: Finite


class SourceClaim(StrictModel):
    pin_id: UUID
    basis: Literal["direct", "interpreted", "unknown"]
    note: Note


class Box(StrictModel):
    kind: Literal["box"]
    extents: Extents


class Capsule(StrictModel):
    kind: Literal["capsule"]
    radius_m: Positive
    height_m: Positive


class ActorProxy(StrictModel):
    kind: Literal["actor-proxy"]
    radius_m: Positive
    standing_height_m: Positive
    seated_height_m: Positive

    @model_validator(mode="after")
    def heights(self):
        if self.seated_height_m > self.standing_height_m:
            raise ValueError("Seated height cannot exceed standing height.")
        return self


Shape = Annotated[Union[Box, Capsule, ActorProxy], Field(discriminator="kind")]


class Instance(StrictModel):
    id: UUID
    kind: Literal["actor", "prop", "wall"]
    label: Label
    asset_id: UUID | None = None
    pose: Pose
    shape: Shape
    presence: Span | None = None
    eyeline: Aim | None = None
    posture: Literal["standing", "seated"] | None = None
    notes: Note
    source_claims: list[SourceClaim] = Field(max_length=128)

    @model_validator(mode="after")
    def actor_fields(self):
        if self.kind == "actor":
            if self.shape.kind != "actor-proxy" or self.posture is None:
                raise ValueError("Actors require an actor-proxy shape and explicit posture.")
        elif self.shape.kind == "actor-proxy" or self.posture is not None or self.eyeline is not None:
            raise ValueError("Actor-only fields are not valid on props or walls.")
        return self


class Mark(StrictModel):
    id: UUID
    label: Label
    position: Vec3


class Beat(StrictModel):
    id: UUID
    label: Label
    order: Annotated[StrictInt, Field(ge=0, le=9_007_199_254_740_991)]
    time_us: Microseconds | None


class Resource(StrictModel):
    id: UUID
    kind: Literal["camera", "light"]
    label: Label
    reference_asset_id: UUID | None = None


class Gate(StrictModel):
    x: Nonnegative
    y: Nonnegative
    width: Positive
    height: Positive


class Perspective(StrictModel):
    kind: Literal["perspective"]
    focal_length_mm: Positive
    sensor_width_mm: Positive
    sensor_height_mm: Positive
    active_gate_mm: Gate

    @model_validator(mode="after")
    def valid_gate(self):
        g = self.active_gate_mm
        if g.x + g.width > self.sensor_width_mm or g.y + g.height > self.sensor_height_mm:
            raise ValueError("The active gate must lie wholly inside the sensor.")
        return self


class Orthographic(StrictModel):
    kind: Literal["orthographic"]
    width_m: Positive
    aspect: Positive


Projection = Annotated[Union[Perspective, Orthographic], Field(discriminator="kind")]


class FramingTarget(StrictModel):
    target: Target
    ndc_x: SignedUnit
    ndc_y: SignedUnit
    roll_rad: Finite


class Camera(StrictModel):
    id: UUID
    label: Label
    resource_id: UUID | None = None
    reference_asset_id: UUID | None = None
    pose: Pose
    aim: Aim | None = None
    projection: Projection
    focus_distance_m: Positive | None = None
    coverage_display_distance_m: Positive
    framing_target: FramingTarget | None = None
    notes: Note


class RGB(StrictModel):
    mode: Literal["rgb"]
    srgb: list[UnitInterval] = Field(min_length=3, max_length=3)


class CCT(StrictModel):
    mode: Literal["cct"]
    kelvin: Kelvin


Color = Annotated[Union[RGB, CCT], Field(discriminator="mode")]


class Spot(StrictModel):
    kind: Literal["spot"]
    full_beam_angle_deg: Spread


class PointEmitter(StrictModel):
    kind: Literal["point"]


class Directional(StrictModel):
    kind: Literal["directional"]


class Area(StrictModel):
    kind: Literal["area"]
    planned_spread_deg: Spread


Emitter = Annotated[Union[Spot, PointEmitter, Directional, Area], Field(discriminator="kind")]


class Output(StrictModel):
    mode: Literal["schematic"]
    relative: UnitInterval


class Light(StrictModel):
    id: UUID
    label: Label
    resource_id: UUID | None = None
    reference_asset_id: UUID | None = None
    role: Literal["key", "fill", "rim", "practical", "other"]
    pose: Pose
    aim: Aim | None = None
    emitter: Emitter
    source_dimensions_m: Extents
    color: Color
    output: Output
    enabled: StrictBool
    modifier_ids: list[UUID] = Field(max_length=500)
    coverage_display_distance_m: Positive
    notes: Note


class Modifier(StrictModel):
    id: UUID
    label: Label
    kind: Literal["diffusion", "flag", "bounce", "negative-fill"]
    pose: Pose
    width_m: Positive
    height_m: Positive
    reference_asset_id: UUID | None = None
    notes: Note


T = TypeVar("T")


class Key(StrictModel, Generic[T]):
    id: UUID
    time_us: Microseconds
    value: T
    next: Literal["hold", "linear"]


class PositionTrack(StrictModel):
    id: UUID
    owner_id: UUID
    property: Literal["position"]
    keys: list[Key[PositionValue]] = Field(min_length=1, max_length=5000)


class OrientationTrack(StrictModel):
    id: UUID
    owner_id: UUID
    property: Literal["orientation"]
    keys: list[Key[Quaternion]] = Field(min_length=1, max_length=5000)


class AimTrack(StrictModel):
    id: UUID
    owner_id: UUID
    property: Literal["aim", "eyeline"]
    keys: list[Key[Aim]] = Field(min_length=1, max_length=5000)


class EnabledTrack(StrictModel):
    id: UUID
    owner_id: UUID
    property: Literal["light-enabled"]
    keys: list[Key[StrictBool]] = Field(min_length=1, max_length=5000)


class OutputTrack(StrictModel):
    id: UUID
    owner_id: UUID
    property: Literal["light-output"]
    keys: list[Key[UnitInterval]] = Field(min_length=1, max_length=5000)


class SpreadTrack(StrictModel):
    id: UUID
    owner_id: UUID
    property: Literal["light-spread"]
    keys: list[Key[Spread]] = Field(min_length=1, max_length=5000)


class PostureTrack(StrictModel):
    id: UUID
    owner_id: UUID
    property: Literal["actor-posture"]
    keys: list[Key[Literal["standing", "seated"]]] = Field(min_length=1, max_length=5000)


Track = Annotated[Union[PositionTrack, OrientationTrack, AimTrack, EnabledTrack, OutputTrack, SpreadTrack, PostureTrack], Field(discriminator="property")]


class Unscaled(StrictModel):
    status: Literal["unscaled"]
    reason: Note


class Approximate(StrictModel):
    status: Literal["approximate"]
    reason: Note
    metres_per_pixel: Positive


class Measured(StrictModel):
    status: Literal["measured"]
    projection: Literal["orthographic"]
    pixel_a: list[Nonnegative] = Field(min_length=2, max_length=2)
    pixel_b: list[Nonnegative] = Field(min_length=2, max_length=2)
    real_distance_m: Positive
    verified_by_user: StrictBool
    source_note: Note

    @model_validator(mode="after")
    def measured(self):
        if self.pixel_a == self.pixel_b or not self.verified_by_user:
            raise ValueError("Confirm orthographic measurement using two distinct image points.")
        return self


class ImageTransform(StrictModel):
    origin_world: Vec3
    rotation_rad: Finite


class FloorPlan(StrictModel):
    id: UUID
    media_id: UUID
    media_sha256: Sha256
    image_to_plan: ImageTransform
    calibration: Annotated[Union[Unscaled, Approximate, Measured], Field(discriminator="status")]


class DocumentPin(StrictModel):
    id: UUID
    kind: Literal["document-node"]
    document_id: UUID
    document_version_id: UUID
    node_id: UUID
    expected_source_sha256: Sha256
    expected_document_sha256: Sha256


class ObservationPin(StrictModel):
    id: UUID
    kind: Literal["observation-v1"]
    observation_version_id: UUID
    expected_content_sha256: Sha256
    expected_basis_sha256: Sha256


SourcePinInput = Annotated[Union[DocumentPin, ObservationPin], Field(discriminator="kind")]


class Scale(StrictModel):
    status: Literal["measured", "approximate", "unscaled"]
    note: Note


class Action(StrictModel):
    duration_us: Microseconds


class Origin(StrictModel):
    setup_id: UUID
    version_id: UUID


class SpatialPayload(StrictModel):
    schema_version: Literal[SCHEMA] = Field(alias="schema")
    frame: Literal[FRAME]
    length_unit: Literal["m"]
    setup_label: Label
    scene_ids: list[UUID] = Field(min_length=1, max_length=500)
    location_asset_id: UUID | None
    scale: Scale
    action: Action
    floor_plans: list[FloorPlan] = Field(max_length=32)
    instances: list[Instance] = Field(max_length=500)
    marks: list[Mark] = Field(max_length=1000)
    beats: list[Beat] = Field(max_length=1000)
    resources: list[Resource] = Field(max_length=500)
    cameras: list[Camera] = Field(max_length=200)
    lights: list[Light] = Field(max_length=200)
    modifiers: list[Modifier] = Field(max_length=500)
    tracks: list[Track] = Field(max_length=5000)
    source_pins: list[SourcePinInput] = Field(max_length=256)
    assumptions: list[Note] = Field(max_length=128)
    origin: Origin | None

    @model_validator(mode="after")
    def coherent(self):
        ids, tracks_by_owner = {}, {}
        duration = self.action.duration_us
        items = {i.id: i for i in [*self.instances, *self.cameras, *self.lights, *self.modifiers]}
        groups = ("instances", "marks", "beats", "resources", "cameras", "lights", "modifiers", "tracks", "floor_plans", "source_pins")
        for group in groups:
            for item in getattr(self, group):
                if item.id in ids:
                    raise ValueError(f"Duplicate ID {item.id}: {ids[item.id]} and {group}.")
                ids[item.id] = group
        total = len(self.instances) + len(self.cameras) + len(self.lights) + len(self.modifiers)
        if total > 500 or len(self.cameras) + len(self.lights) > 200 or sum(len(t.keys) for t in self.tracks) > 5000:
            raise ValueError("Spatial item, camera/light, or total key limit exceeded.")
        if len(self.scene_ids) != len(set(self.scene_ids)):
            raise ValueError("Repeated scene IDs.")
        marks, resources = {m.id for m in self.marks}, {r.id: r for r in self.resources}
        modifiers, pins = {m.id for m in self.modifiers}, {p.id for p in self.source_pins}

        def target(value, path):
            if value.kind == "mark" and value.mark_id not in marks:
                raise ValueError(f"{path}: missing mark {value.mark_id}.")
            if value.kind == "item" and value.item_id not in items:
                raise ValueError(f"{path}: missing target item {value.item_id}.")

        for instance in self.instances:
            if instance.presence and instance.presence.end_us > duration:
                raise ValueError(f"{instance.id}.presence exceeds action duration.")
            if instance.eyeline:
                target(instance.eyeline.target, f"{instance.id}.eyeline")
            if any(c.pin_id not in pins for c in instance.source_claims):
                raise ValueError(f"{instance.id}: source claim has no declared source pin.")
        for beat in self.beats:
            if beat.time_us is not None and beat.time_us > duration:
                raise ValueError(f"{beat.id}: beat exceeds action duration.")
        for item, kind in [*((c, "camera") for c in self.cameras), *((l, "light") for l in self.lights)]:
            if item.resource_id and (item.resource_id not in resources or resources[item.resource_id].kind != kind):
                raise ValueError(f"{item.id}: incorrect resource kind or missing resource.")
            if item.aim:
                target(item.aim.target, f"{item.id}.aim")
            if isinstance(item, Camera) and item.framing_target:
                if item.aim:
                    raise ValueError(f"{item.id}: choose aim or framing target, not both.")
                target(item.framing_target.target, f"{item.id}.framing_target")
            if isinstance(item, Light) and (len(set(item.modifier_ids)) != len(item.modifier_ids) or any(m not in modifiers for m in item.modifier_ids)):
                raise ValueError(f"{item.id}: missing or repeated modifier.")
        for track in self.tracks:
            owner = items.get(track.owner_id)
            if owner is None:
                raise ValueError(f"{track.id}: track owner does not exist or cannot own tracks.")
            prop = track.property
            key = (track.owner_id, prop)
            if key in tracks_by_owner:
                raise ValueError(f"Duplicate track for {key}.")
            tracks_by_owner[key] = track
            allowed = {"position", "orientation"}
            if isinstance(owner, (Light, Camera)):
                allowed.add("aim")
            if isinstance(owner, Instance) and owner.kind == "actor":
                allowed.update(("eyeline", "actor-posture"))
            if isinstance(owner, Light):
                allowed.update(("light-enabled", "light-output"))
                if owner.emitter.kind in ("spot", "area"):
                    allowed.add("light-spread")
            if prop not in allowed:
                raise ValueError(f"{track.id}: {prop} is not supported for this owner.")
            if isinstance(owner, (Light, Camera)):
                framing = isinstance(owner, Camera) and owner.framing_target
                if prop == "orientation" and (owner.aim or framing):
                    raise ValueError(f"{track.id}: orientation competes with aim/framing authority.")
                if prop == "aim" and (not owner.aim or framing):
                    raise ValueError(f"{track.id}: aim track requires static aim and forbids framing authority.")
            track.keys.sort(key=lambda k: (k.time_us, k.id))
            times = {}
            for index, k in enumerate(track.keys):
                if k.id in ids:
                    raise ValueError(f"Duplicate key ID {k.id}.")
                ids[k.id] = "key"
                if k.time_us in times:
                    raise ValueError(f"Equal-time keys {times[k.time_us]} and {k.id} on track {track.id}.")
                times[k.time_us] = k.id
                if k.time_us > duration:
                    raise ValueError(f"{k.id}: key exceeds action duration.")
                if prop in ("light-enabled", "actor-posture") and k.next != "hold":
                    raise ValueError(f"{k.id}: this property supports hold only.")
                if prop == "position":
                    target(k.value, f"{k.id}.value")
                if prop in ("aim", "eyeline"):
                    target(k.value.target, f"{k.id}.target")
                    if k.next == "linear" and index + 1 < len(track.keys):
                        a, b = k.value.target, track.keys[index + 1].value.target
                        if a.kind != b.kind or getattr(a, "mark_id", None) != getattr(b, "mark_id", None) or getattr(a, "item_id", None) != getattr(b, "item_id", None):
                            raise ValueError(f"{k.id}: changing target identity requires hold interpolation.")
        return self


class Instant(StrictModel):
    kind: Literal["instant"]
    time_us: Microseconds
    beat_id: UUID | None = None


class Interval(StrictModel):
    kind: Literal["interval"]
    start_us: Microseconds
    end_us: Microseconds
    start_beat_id: UUID | None = None
    end_beat_id: UUID | None = None

    @model_validator(mode="after")
    def nonempty(self):
        if self.end_us <= self.start_us:
            raise ValueError("An interval needs end > start; static plans use an instant.")
        return self


class NoMapping(StrictModel):
    kind: Literal["none"]


class LinearMapping(StrictModel):
    kind: Literal["linear"]
    shot_start_us: Microseconds
    shot_end_us: Microseconds
    action_start_us: Microseconds
    action_end_us: Microseconds

    @model_validator(mode="after")
    def forward(self):
        if self.shot_end_us <= self.shot_start_us or self.action_end_us < self.action_start_us:
            raise ValueError("Mapping needs increasing shot time and nondecreasing action time.")
        return self


class SpatialBinding(StrictModel):
    schema_version: Literal["storyboarder.spatial-binding/v1"] = Field(alias="schema")
    status: Literal["active", "detached"]
    setup_version_id: UUID
    camera_plan_id: UUID
    sample: Annotated[Union[Instant, Interval], Field(discriminator="kind")]
    time_mapping: Annotated[Union[NoMapping, LinearMapping], Field(discriminator="kind")]
    notes: Note


class Reviewed(StrictModel):
    blocking: StrictBool
    timing: StrictBool
    camera_coverage: StrictBool
    schematic_lighting: StrictBool


class Unresolved(StrictModel):
    id: UUID
    topic: Literal["blocking", "timing", "camera", "lighting"]
    statement: Note


class SpatialReview(StrictModel):
    schema_version: Literal["storyboarder.observation-contract/v2"] = Field(alias="schema")
    observation_version_id: UUID
    binding_version_id: UUID
    reviewed: Reviewed
    assumptions: list[Note] = Field(max_length=128)
    unresolved: list[Unresolved] = Field(max_length=256)
    notes: Note

    @model_validator(mode="after")
    def unique_ids(self):
        if len({x.id for x in self.unresolved}) != len(self.unresolved):
            raise ValueError("Repeated unresolved item ID.")
        return self


def canonical(value):
    """A single canonical encoder; never round persisted world coordinates."""
    if isinstance(value, BaseModel):
        value = value.model_dump(by_alias=True, exclude_none=True)
    def clean(obj):
        if isinstance(obj, dict):
            return {k: clean(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [clean(v) for v in obj]
        if isinstance(obj, float) and obj == 0:
            return 0.0
        return obj
    return json.dumps(clean(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def checked(value, model=SpatialPayload):
    try:
        encoded = canonical(value)
        if len(encoded.encode("utf-8")) > MAX_BYTES:
            raise SpatialError("Spatial payload exceeds 8 MiB.", code="spatial_limit_exceeded", status=413)
        parsed = model.model_validate(value)
        result = parsed.model_dump(by_alias=True, exclude_none=True)
        if model is SpatialPayload:
            # Required nullable fields are retained; absent optional fields stay absent.
            result["location_asset_id"] = parsed.location_asset_id
            result["origin"] = parsed.origin.model_dump() if parsed.origin else None
            for beat in result["beats"]:
                beat.setdefault("time_us", None)
            for group in ("instances", "marks", "resources", "cameras", "lights", "modifiers", "tracks", "floor_plans", "source_pins"):
                result[group].sort(key=lambda x: x["id"])
            result["beats"].sort(key=lambda x: (x["order"], x["id"]))
            result["scene_ids"].sort()
            for light in result["lights"]:
                light["modifier_ids"].sort()
        return result
    except ValidationError as exc:
        details = [{"path": ".".join(map(str, e["loc"])), "message": e["msg"]} for e in exc.errors()[:50]]
        raise SpatialError("Spatial details need attention.", {"errors": details}) from exc
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise SpatialError("Invalid or excessively nested spatial JSON.", {"reason": str(exc)[:500]}) from exc


def physical(value):
    """Display-only changes never masquerade as changed physical semantics."""
    omit = {"setup_label", "label", "notes", "note", "origin"}
    if isinstance(value, dict):
        return {k: physical(v) for k, v in value.items() if k not in omit}
    if isinstance(value, list):
        return [physical(v) for v in value]
    return value


def seconds_to_us(value):
    if isinstance(value, bool):
        raise SpatialError("Seconds must be a decimal number.")
    try:
        decimal = Decimal(str(value))
        if not decimal.is_finite() or decimal < 0 or decimal > 86400:
            raise ValueError()
        return int((decimal * 1_000_000).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    except (ValueError, ArithmeticError) as exc:
        raise SpatialError("Seconds must be between 0 and 86400.") from exc


def validate_binding(body, payload, shot_scene_id, shot_duration=None):
    body = checked(body, SpatialBinding)
    if shot_scene_id not in payload["scene_ids"]:
        raise SpatialError("The shot's scene is not in this exact setup version. Detach before moving.", code="spatial_scope_mismatch", status=409)
    if body["camera_plan_id"] not in {x["id"] for x in payload["cameras"]}:
        raise SpatialError("Choose a camera from the pinned setup version.", code="spatial_reference_missing")
    sample, duration = body["sample"], payload["action"]["duration_us"]
    start = sample.get("start_us", sample.get("time_us"))
    end = sample.get("end_us", sample.get("time_us"))
    if end > duration:
        raise SpatialError("The selected action exceeds setup duration.")
    beats = {b["id"]: b for b in payload["beats"]}
    for field, t in (("beat_id", start), ("start_beat_id", start), ("end_beat_id", end)):
        if field in sample and (sample[field] not in beats or beats[sample[field]]["time_us"] != t):
            raise SpatialError("A selected beat is missing, untimed, or not at the declared endpoint.")
    m = body["time_mapping"]
    if m["kind"] == "linear":
        if m["action_start_us"] < start or m["action_end_us"] > end:
            raise SpatialError("Action mapping must fit inside the selected action range.")
        if shot_duration is not None and m["shot_end_us"] > seconds_to_us(shot_duration):
            raise SpatialError("Shot mapping exceeds authored shot duration; duration was not changed.")
    return body
