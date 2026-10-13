"""Strict, inspectable production contracts; geometry is metres, right-handed Z-up.

A Ref always pins a record *version*. Labels, ordering, selected versions, and
mutable header revisions are deliberately different things. No provider required.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
from datetime import date
from typing import Annotated, Literal, Union

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, TypeAdapter, ValidationError, model_validator

from storyboarder.domain.errors import StoryboardError
from storyboarder.domain.models import dumps
from storyboarder.domain.spatial import canonical_uuid, finite

MAX_PACKAGE_BYTES = 32 * 1024 * 1024
MAX_RECORDS = 5000
MAX_OPERATIONS = 500
FRAME = 'rh-z-up-x-right-y-forward/v1'
UUID = Annotated[str, BeforeValidator(canonical_uuid)]
Number = Annotated[float, BeforeValidator(finite)]
Positive = Annotated[Number, Field(gt=0, le=1e8)]
Nonnegative = Annotated[Number, Field(ge=0, le=1e8)]
Frame = Annotated[int, Field(ge=0, le=100_000_000)]
Label = Annotated[str, Field(min_length=1, max_length=240)]
Note = Annotated[str, Field(max_length=20000)]
Sha = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
Kind = Literal['production', 'sequence', 'script', 'location', 'asset', 'scene', 'action',
               'camera_setup', 'lighting_setup', 'shot', 'panel', 'animatic', 'edit', 'take',
               'review', 'annotation', 'exception']


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False, str_max_length=20000)


class ProductionError(StoryboardError):
    code = 'production_invalid'


def decode(model, value):
    try:
        return model.model_validate(value).model_dump(mode='json')
    except ValidationError as exc:
        raise ProductionError('Production data failed validation.', {
            'issues': json.loads(exc.json(include_url=False, include_input=False))}) from exc


def digest(value):
    return hashlib.sha256(dumps(value).encode('utf-8')).hexdigest()


class Ref(Model):
    id: UUID
    version: Annotated[int, Field(ge=1)]


class Rate(Model):
    numerator: Annotated[int, Field(ge=1, le=240000)] = 24
    denominator: Annotated[int, Field(ge=1, le=10000)] = 1

    @model_validator(mode='after')
    def reasonable(self):
        if not 1 <= self.numerator / self.denominator <= 240:
            raise ValueError('Supported rates are 1–240 fps, including rational rates such as 24000/1001.')
        return self


class Aspect(Model):
    width: Positive = 16.0
    height: Positive = 9.0


class Vec3(Model):
    x: Annotated[Number, Field(ge=-100000, le=100000)] = 0.0
    y: Annotated[Number, Field(ge=-100000, le=100000)] = 0.0
    z: Annotated[Number, Field(ge=-100000, le=100000)] = 0.0


class Size(Model):
    x: Positive
    y: Positive
    z: Positive


class Pose(Model):
    position: Vec3 = Field(default_factory=Vec3)
    # +Y is forward; positive yaw turns toward -X, as in the existing spatial frame.
    yaw_deg: Annotated[Number, Field(ge=-360000, le=360000)] = 0.0
    pitch_deg: Annotated[Number, Field(ge=-90, le=90)] = 0.0
    roll_deg: Annotated[Number, Field(ge=-180, le=180)] = 0.0


class Interval(Model):
    start: Frame = 0
    end: Frame

    @model_validator(mode='after')
    def ordered(self):
        if self.end <= self.start:
            raise ValueError('Intervals are half-open [start,end); end must be after start.')
        return self


class TimeMap(Model):
    action_start: Frame
    shot_start: Frame = 0
    # action frames advanced per shot frame; rates are also applied by the evaluator.
    speed_numerator: Annotated[int, Field(ge=1, le=1000)] = 1
    speed_denominator: Annotated[int, Field(ge=1, le=1000)] = 1


class Provenance(Model):
    origin: Literal['human', 'agent', 'import', 'legacy'] = 'human'
    author: Note = ''
    rationale: Note = ''
    assumptions: list[Note] = Field(default_factory=list, max_length=100)
    questions: list[Note] = Field(default_factory=list, max_length=100)
    source_refs: list[Ref] = Field(default_factory=list, max_length=100)
    legacy_entity_id: UUID | None = None
    legacy_entity_revision: Annotated[int, Field(ge=1)] | None = None

    @model_validator(mode='after')
    def complete_legacy_pin(self):
        if (self.legacy_entity_id is None)!=(self.legacy_entity_revision is None):
            raise ValueError('A legacy source pin needs both its identity and revision.')
        return self


class Orders(Model):
    narrative: Annotated[int, Field(ge=0)] | None = None
    shooting: Annotated[int, Field(ge=0)] | None = None
    editorial: Annotated[int, Field(ge=0)] | None = None


class Applicability(Model):
    state: Literal['required', 'not_applicable', 'intentionally_unplanned'] = 'required'
    reason: Note = ''

    @model_validator(mode='after')
    def reason_required(self):
        if self.state != 'required' and not self.reason.strip():
            raise ValueError('An applicability exception requires a reason.')
        return self


class Record(Model):
    title: Label
    applicability: dict[Literal['location','geometry','action','cameras','camera_asset','lighting','fixtures','instances','beats','purpose'], Applicability] = Field(default_factory=dict)
    label: Annotated[str, Field(max_length=80)] = ''
    notes: Note = ''
    orders: Orders = Field(default_factory=Orders)
    planning: Literal['planned', 'not_applicable', 'intentionally_unplanned'] = 'planned'
    planning_reason: Note = ''
    responsibility: Note = ''
    next_action: Note = ''
    constraints: list[Note] = Field(default_factory=list, max_length=100)
    provenance: Provenance = Field(default_factory=Provenance)

    @model_validator(mode='after')
    def explicit_exceptions(self):
        if not self.title.strip():
            raise ValueError('A nonblank title is required.')
        if self.planning != 'planned' and not self.planning_reason.strip():
            raise ValueError('Not-applicable or intentionally-unplanned records need a reason.')
        return self


class Production(Record):
    kind: Literal['production']
    production_type: Literal['short', 'feature', 'episode', 'commercial', 'music_video', 'documentary', 'other'] = 'short'
    display_units: Literal['m', 'cm', 'ft'] = 'm'
    frame_rate: Rate = Field(default_factory=Rate)
    aspect_ratio: Aspect = Field(default_factory=Aspect)
    coordinate_frame: Literal['rh-z-up-x-right-y-forward/v1'] = FRAME
    # Storage always uses metres, even when the interface displays feet.
    storage_units: Literal['m'] = 'm'


class Sequence(Record):
    kind: Literal['sequence']
    objective: Note = ''


class SourcePosition(Model):
    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(ge=0)]
    line: Annotated[int, Field(ge=1)] = 1

    @model_validator(mode='after')
    def ordered(self):
        if self.end < self.start:
            raise ValueError('Source positions are Unicode code-point offsets, end-exclusive.')
        return self


class ScriptBlock(Model):
    id: UUID
    type: Literal['action', 'dialogue', 'character', 'parenthetical', 'transition', 'note', 'lyric']
    text: Annotated[str, Field(max_length=100000)]
    character: Annotated[str, Field(max_length=240)] = ''
    source: SourcePosition | None = None


class ScriptScene(Model):
    id: UUID
    heading: Label
    number: Annotated[str, Field(max_length=80)] = ''
    source: SourcePosition | None = None
    blocks: list[ScriptBlock] = Field(default_factory=list, max_length=5000)


class SourceFile(Model):
    name: Label
    format: Literal['fountain', 'structured-json', 'screenjson']
    encoding: Literal['utf-8'] = 'utf-8'
    # The original bytes live in the immutable version and portable package, not a temp file.
    bytes_base64: Annotated[str, Field(max_length=4 * 1024 * 1024)]
    sha256: Sha

    @model_validator(mode='after')
    def original_bytes(self):
        try:
            raw = base64.b64decode(self.bytes_base64, validate=True)
        except ValueError as exc:
            raise ValueError('Source bytes must be valid base64.') from exc
        if len(raw) > 2 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != self.sha256:
            raise ValueError('Original script bytes exceed 2 MiB or fail their SHA-256 check.')
        raw.decode('utf-8-sig')
        return self


class ImportIssue(Model):
    code: Label
    message: Note
    line: Annotated[int, Field(ge=1)] | None = None
    candidates: list[UUID] = Field(default_factory=list, max_length=100)


class Script(Record):
    kind: Literal['script']
    source_file: SourceFile | None = None
    scenes: list[ScriptScene] = Field(default_factory=list, max_length=2000)
    import_issues: list[ImportIssue] = Field(default_factory=list, max_length=1000)
    wording_status: Literal['imported', 'authored', 'amended'] = 'authored'

    @model_validator(mode='after')
    def identities(self):
        ids = [s.id for s in self.scenes] + [b.id for s in self.scenes for b in s.blocks]
        unique(ids, 'Script scene and passage IDs')
        if self.wording_status == 'imported' and self.source_file is None:
            raise ValueError('Imported wording requires preserved source bytes.')
        return self


class MediaRef(Model):
    media_id: UUID | None = None
    path: Annotated[str, Field(max_length=1000)] = ''
    sha256: Sha | None = None
    description: Note = ''

    @model_validator(mode='after')
    def portable(self):
        from pathlib import PurePosixPath
        if self.path:
            p = PurePosixPath(self.path)
            if p.is_absolute() or '..' in p.parts or '\\' in self.path or ':' in self.path or '\x00' in self.path:
                raise ValueError('Media paths must be portable project-relative paths, never URLs or parent traversal.')
            if not self.path.startswith(('media/', 'sources/', 'production-media/')):
                raise ValueError('Portable media belongs under media/, sources/ or production-media/.')
            if self.sha256 is None:
                raise ValueError('Portable media paths require a content hash.')
        if not self.path and self.media_id is None:
            raise ValueError('Reference a managed media ID or a portable path plus SHA-256.')
        return self


class Geometry(Model):
    id: UUID
    label: Label
    type: Literal['room', 'wall', 'door', 'window', 'floor', 'stairs', 'obstacle', 'mesh_proxy']
    pose: Pose = Field(default_factory=Pose)
    size: Size
    quality: Literal['measured', 'estimated', 'unknown'] = 'unknown'
    solid: bool = True
    mesh: MediaRef | None = None
    notes: Note = ''


class Mark(Model):
    id: UUID
    label: Label
    type: Literal['mark', 'entrance', 'exit', 'zone', 'equipment'] = 'mark'
    position: Vec3
    radius_m: Nonnegative = 0.0


class FloorPlan(Model):
    media: MediaRef
    calibration: Literal['measured', 'estimated', 'unscaled'] = 'unscaled'
    metres_per_pixel: Positive | None = None
    origin_pixel_x: Nonnegative = 0.0
    origin_pixel_y: Nonnegative = 0.0
    origin_world: Vec3 = Field(default_factory=Vec3)
    rotation_deg: Number = 0.0
    calibration_note: Note = ''

    @model_validator(mode='after')
    def scaled(self):
        if self.calibration != 'unscaled' and self.metres_per_pixel is None:
            raise ValueError('A calibrated floor plan needs metres_per_pixel.')
        if self.calibration == 'unscaled' and self.metres_per_pixel is not None:
            raise ValueError('Do not imply scale for an unscaled reference.')
        return self


class Location(Record):
    kind: Literal['location']
    location_type: Literal['physical', 'constructed', 'virtual'] = 'physical'
    coordinate_frame: Literal['rh-z-up-x-right-y-forward/v1'] = FRAME
    dimension_quality: Literal['measured', 'estimated', 'unknown'] = 'unknown'
    geometry: list[Geometry] = Field(default_factory=list, max_length=1000)
    marks: list[Mark] = Field(default_factory=list, max_length=1000)
    floor_plans: list[FloorPlan] = Field(default_factory=list, max_length=20)
    references: list[MediaRef] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def identities(self):
        unique([g.id for g in self.geometry] + [m.id for m in self.marks], 'Location object IDs')
        return self


AssetCategory = Literal['character', 'performer', 'prop', 'wardrobe', 'set_dressing', 'camera', 'lens',
                        'light', 'modifier', 'grip', 'rig', 'sound', 'reference']


class Specifications(Model):
    sensor_width_mm: Positive | None = None
    sensor_height_mm: Positive | None = None
    focal_length_mm: Positive | None = None
    min_focal_length_mm: Positive | None = None
    max_focal_length_mm: Positive | None = None
    wattage: Nonnegative | None = None
    beam_angle_deg: Annotated[Number, Field(gt=0, lt=180)] | None = None
    color_kelvin: Annotated[int, Field(ge=1000, le=20000)] | None = None
    manufacturer: Note = ''
    model: Note = ''
    specifications_note: Note = ''


class Asset(Record):
    kind: Literal['asset']
    category: AssetCategory
    dimensions: Size | None = None
    dimension_quality: Literal['measured', 'estimated', 'unknown'] = 'unknown'
    portrays: Ref | None = None
    owner: Note = ''
    specifications: Specifications = Field(default_factory=Specifications)
    reference_points: dict[Label, Vec3] = Field(default_factory=dict, max_length=30)
    references: list[MediaRef] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def portrayal(self):
        if self.portrays and self.category != 'performer':
            raise ValueError('Only a performer portrays a story character.')
        return self


class Fragment(Model):
    script: Ref
    script_scene_id: UUID
    block_ids: list[UUID] = Field(default_factory=list, max_length=1000)
    disposition: Literal['planned', 'omitted', 'deferred', 'intentionally_unfilmed'] = 'planned'
    reason: Note = ''

    @model_validator(mode='after')
    def intention(self):
        unique(self.block_ids, 'Covered passage IDs')
        if self.disposition != 'planned' and not self.reason.strip():
            raise ValueError('Omitted, deferred or intentionally unfilmed material requires a reason.')
        return self


class Requirement(Model):
    asset: Ref
    quantity: Annotated[int, Field(ge=1, le=10000)] = 1
    role: Note = ''
    state: dict[Label, Note] = Field(default_factory=dict, max_length=50)


class Scene(Record):
    kind: Literal['scene']
    sequence: Ref | None = None
    fragments: list[Fragment] = Field(default_factory=list, max_length=500)
    purpose: Note = ''
    unscripted_objectives: list[Note] = Field(default_factory=list, max_length=100)
    story_location: Note = ''
    location: Ref | None = None
    interior_exterior: Literal['INT', 'EXT', 'INT/EXT', 'unknown'] = 'unknown'
    story_time: Note = ''
    shoot_date: Annotated[str, Field(max_length=10)] | None = None
    environment: list[Note] = Field(default_factory=list, max_length=100)
    requirements: list[Requirement] = Field(default_factory=list, max_length=500)
    dressing: list[Requirement] = Field(default_factory=list, max_length=500)
    # Action and shot records point here; no reverse version pin that would form a cycle.

    @model_validator(mode='after')
    def date_format(self):
        if self.shoot_date:
            date.fromisoformat(self.shoot_date)
        return self


class Target(Model):
    instance_id: UUID | None = None
    mark_id: UUID | None = None
    point: Vec3 | None = None
    offset: Vec3 = Field(default_factory=Vec3)

    @model_validator(mode='after')
    def exactly_one(self):
        if sum(v is not None for v in (self.instance_id, self.mark_id, self.point)) != 1:
            raise ValueError('A target references exactly one instance, mark, or world point.')
        return self


class Keyframe(Model):
    frame: Frame
    pose: Pose
    interpolation: Literal['linear', 'hold'] = 'linear'


class Instance(Model):
    id: UUID
    label: Label
    asset: Ref
    pose: Pose = Field(default_factory=Pose)
    parent_id: UUID | None = None
    attachment: Note = ''
    facing: Target | None = None
    eyeline: Target | None = None
    presence: Interval | None = None
    state: dict[Label, Note] = Field(default_factory=dict, max_length=50)
    keyframes: list[Keyframe] = Field(default_factory=list, max_length=2000)

    @model_validator(mode='after')
    def keys(self):
        sorted_frames(self.keyframes)
        return self


class Beat(Model):
    id: UUID
    label: Label
    interval: Interval
    block_ids: list[UUID] = Field(default_factory=list, max_length=1000)
    start_anchor: Note = ''
    end_anchor: Note = ''
    purpose: Note = ''


class PropEvent(Model):
    frame: Frame
    instance_id: UUID
    type: Literal['placed', 'carried', 'handoff', 'removed', 'state']
    from_instance_id: UUID | None = None
    to_instance_id: UUID | None = None
    pose: Pose | None = None
    state: dict[Label, Note] = Field(default_factory=dict, max_length=50)

    @model_validator(mode='after')
    def handoff(self):
        if self.type == 'handoff' and (self.from_instance_id is None or self.to_instance_id is None):
            raise ValueError('Handoffs identify both the giving and receiving instance.')
        if self.type == 'placed' and self.pose is None:
            raise ValueError('Placed props require an explicit world pose.')
        if self.type == 'carried' and self.to_instance_id is None:
            raise ValueError('Carried props require a carrier.')
        return self


class Action(Record):
    kind: Literal['action']
    scene: Ref
    location: Ref
    frame_rate: Rate = Field(default_factory=Rate)
    duration_frames: Annotated[int, Field(ge=1, le=100_000_000)]
    beats: list[Beat] = Field(default_factory=list, max_length=1000)
    instances: list[Instance] = Field(default_factory=list, max_length=1000)
    prop_events: list[PropEvent] = Field(default_factory=list, max_length=2000)
    alternative: Note = ''

    @model_validator(mode='after')
    def timeline(self):
        unique([b.id for b in self.beats] + [i.id for i in self.instances], 'Action object IDs')
        instances = {i.id: i for i in self.instances}
        for i in self.instances:
            if i.presence and i.presence.end > self.duration_frames:
                raise ValueError('Instance presence extends beyond the action.')
            if i.keyframes and i.keyframes[-1].frame > self.duration_frames:
                raise ValueError('Keyframe lies beyond the action duration.')
            seen = {i.id}
            parent = i.parent_id
            while parent:
                if parent not in instances or parent in seen:
                    raise ValueError('Instance parenting must be acyclic and reference this action.')
                seen.add(parent)
                parent = instances[parent].parent_id
            for target in (i.facing, i.eyeline):
                if target and target.instance_id and target.instance_id not in instances:
                    raise ValueError('Facing/eyeline target is not in this action.')
        for beat in self.beats:
            if beat.interval.end > self.duration_frames:
                raise ValueError('A beat extends beyond the action.')
        parents = {i.id: i.parent_id for i in self.instances}
        events = sorted(self.prop_events, key=lambda x: x.frame)
        for event in events:
            if event.frame > self.duration_frames or event.instance_id not in instances:
                raise ValueError('Prop event is outside the action or references a missing instance.')
            for other in (event.from_instance_id, event.to_instance_id):
                if other and other not in instances:
                    raise ValueError('Prop event carrier is not in this action.')
            if event.type == 'handoff' and parents[event.instance_id] != event.from_instance_id:
                raise ValueError('Handoff giver does not currently own/carry this prop.')
            if event.type in ('carried', 'handoff', 'placed', 'removed'):
                parents[event.instance_id] = event.to_instance_id if event.type in ('carried', 'handoff') else None
            for node in parents:
                seen = {node}
                parent = parents[node]
                while parent:
                    if parent in seen:
                        raise ValueError('A prop event would create an attachment cycle.')
                    seen.add(parent)
                    parent = parents[parent]
        return self


class CameraSetup(Record):
    kind: Literal['camera_setup']
    scene: Ref
    location: Ref
    action: Ref | None = None
    camera_asset: Ref | None = None
    lens_asset: Ref | None = None
    pose: Pose = Field(default_factory=Pose)
    target: Target | None = None
    sensor_width_mm: Positive = 36.0
    sensor_height_mm: Positive = 24.0
    focal_length_mm: Positive = 50.0
    aspect_ratio: Aspect = Field(default_factory=Aspect)
    fit: Literal['horizontal', 'vertical'] = 'horizontal'
    motion: Literal['static', 'handheld', 'dolly', 'tracking', 'crane', 'rig', 'other'] = 'static'
    keyframes: list[Keyframe] = Field(default_factory=list, max_length=2000)
    focus_target: Target | None = None
    focus_distance_m: Positive | None = None
    safe_area: Annotated[Number, Field(ge=0.5, le=1)] = 0.9
    approximation: Literal['rectilinear-pinhole'] = 'rectilinear-pinhole'

    @model_validator(mode='after')
    def keys(self):
        sorted_frames(self.keyframes)
        if self.keyframes and self.action is None:
            raise ValueError('A timed camera move requires an exact action time base.')
        for target in (self.target, self.focus_target):
            if target and target.instance_id and not self.action:
                raise ValueError('An instance target requires an exact action version.')
        ratio = self.aspect_ratio.width / self.aspect_ratio.height
        if self.fit == 'horizontal' and self.sensor_width_mm / ratio > self.sensor_height_mm + 1e-8:
            raise ValueError('Horizontal-fit crop exceeds the sensor; use vertical fit.')
        if self.fit == 'vertical' and self.sensor_height_mm * ratio > self.sensor_width_mm + 1e-8:
            raise ValueError('Vertical-fit crop exceeds the sensor; use horizontal fit.')
        return self


class Fixture(Model):
    id: UUID
    label: Label
    asset: Ref
    role: Literal['key', 'fill', 'backlight', 'practical', 'environment', 'other'] = 'key'
    pose: Pose = Field(default_factory=Pose)
    type: Literal['point', 'spot', 'area', 'directional', 'practical'] = 'spot'
    beam_angle_deg: Annotated[Number, Field(gt=0, lt=180)] = 45.0
    color_kelvin: Annotated[int, Field(ge=1000, le=20000)] = 5600
    relative_intensity: Annotated[Number, Field(ge=0, le=1)] = 1.0
    enabled: bool = True
    modifiers: list[Ref] = Field(default_factory=list, max_length=20)
    supports: list[Ref] = Field(default_factory=list, max_length=20)
    notes: Note = ''


class LightCue(Model):
    frame: Frame
    fixture_id: UUID
    enabled: bool
    relative_intensity: Annotated[Number, Field(ge=0, le=1)]


class LightingSetup(Record):
    kind: Literal['lighting_setup']
    scene: Ref
    location: Ref
    action: Ref | None = None
    fixtures: list[Fixture] = Field(default_factory=list, max_length=500)
    cues: list[LightCue] = Field(default_factory=list, max_length=2000)
    intended_look: Note = ''
    preview_model: Literal['geometric-symbolic'] = 'geometric-symbolic'

    @model_validator(mode='after')
    def timeline(self):
        unique([f.id for f in self.fixtures], 'Fixture IDs')
        ids = {f.id for f in self.fixtures}
        if self.cues and not self.action:
            raise ValueError('Lighting cues require an action time base.')
        unique([(c.frame, c.fixture_id) for c in self.cues], 'Fixture cue times')
        for cue in self.cues:
            if cue.fixture_id not in ids:
                raise ValueError('Cue references a missing fixture.')
        return self


class Override(Model):
    instance_id: UUID
    pose: Pose | None = None
    keyframes: list[Keyframe] = Field(default_factory=list, max_length=1000)
    reason: Label

    @model_validator(mode='after')
    def keys(self):
        sorted_frames(self.keyframes)
        return self


class Shot(Record):
    kind: Literal['shot']
    scene: Ref
    shot_type: Literal['master', 'single', 'two_shot', 'insert', 'cutaway', 'POV', 'pickup', 'other'] = 'master'
    purpose: Note = ''
    subject: Note = ''
    framing: Note = ''
    composition: Note = ''
    fragments: list[Fragment] = Field(default_factory=list, max_length=500)
    action: Ref | None = None
    beat_ids: list[UUID] = Field(default_factory=list, max_length=1000)
    interval: Interval | None = None
    frame_rate: Rate = Field(default_factory=Rate)
    time_map: TimeMap | None = None
    handles_before: Frame = 0
    handles_after: Frame = 0
    cameras: list[Ref] = Field(default_factory=list, max_length=30)
    lighting: Ref | None = None
    overrides: list[Override] = Field(default_factory=list, max_length=500)
    requirements: list[Requirement] = Field(default_factory=list, max_length=500)
    alternative_group: Note = ''
    axis_start: Vec3 | None = None
    axis_end: Vec3 | None = None
    screen_direction: Literal['left_to_right', 'right_to_left', 'neutral', 'unknown'] = 'unknown'

    @model_validator(mode='after')
    def action_bounds(self):
        if self.action is None and (self.interval or self.beat_ids or self.overrides or self.time_map):
            raise ValueError('Shot timing, beats and overrides require a pinned shared action.')
        if self.action and self.interval is None:
            raise ValueError('A shot observing action needs an action interval.')
        unique(self.beat_ids, 'Shot beat IDs')
        unique([(r.id, r.version) for r in self.cameras], 'Shot cameras')
        unique([r.instance_id for r in self.overrides], 'Shot override instances')
        if (self.axis_start is None) != (self.axis_end is None):
            raise ValueError('An axis needs both endpoints.')
        if self.axis_start and self.axis_start == self.axis_end:
            raise ValueError('An axis must have length.')
        if self.time_map and self.interval and self.time_map.action_start != self.interval.start:
            raise ValueError('Time-map action_start must match the photographed interval.')
        return self


class Point2(Model):
    x: Annotated[Number, Field(ge=0, le=1)]
    y: Annotated[Number, Field(ge=0, le=1)]


class Stroke(Model):
    points: list[Point2] = Field(min_length=2, max_length=5000)
    color: Annotated[str, Field(pattern=r'^#[0-9a-fA-F]{6}$')] = '#1c302c'
    width: Annotated[Number, Field(gt=0, le=0.1)] = 0.005


class Panel(Record):
    kind: Literal['panel']
    shot: Ref
    camera: Ref | None = None
    action_frame: Frame | None = None
    duration_frames: Annotated[int, Field(ge=1, le=100_000_000)] = 24
    artwork: MediaRef | None = None
    drawing: list[Stroke] = Field(default_factory=list, max_length=1000)
    dialogue: Note = ''
    annotation: Note = ''


class AnimaticEntry(Model):
    panel: Ref
    duration_frames: Annotated[int, Field(ge=1, le=100_000_000)]
    audio: MediaRef | None = None
    audio_cue: Note = ''


class Animatic(Record):
    kind: Literal['animatic']
    frame_rate: Rate = Field(default_factory=Rate)
    entries: list[AnimaticEntry] = Field(default_factory=list, max_length=5000)


class EditEntry(Model):
    shot: Ref
    shot_interval: Interval
    transition: Literal['cut', 'dissolve', 'fade'] = 'cut'
    transition_frames: Frame = 0
    match_action_anchor: UUID | None = None
    take: Ref | None = None


class Edit(Record):
    kind: Literal['edit']
    frame_rate: Rate = Field(default_factory=Rate)
    entries: list[EditEntry] = Field(default_factory=list, max_length=5000)


class Take(Record):
    kind: Literal['take']
    shot: Ref
    slate: Label
    captured_at: Note = ''
    frame_rate: Rate = Field(default_factory=Rate)
    duration_frames: Frame | None = None
    source_timecode: Annotated[str, Field(max_length=80)] = ''
    media: list[MediaRef] = Field(default_factory=list, max_length=100)
    observation: Note = ''


class Review(Record):
    kind: Literal['review']
    subject: Ref
    decision: Literal['accepted', 'changes_requested', 'not_applicable']
    dimension: Literal['structural', 'planning', 'creative']
    reviewer: Label
    reason: Label
    dependencies: list[Ref] = Field(default_factory=list, max_length=500)


class Annotation(Record):
    kind: Literal['annotation']
    subject: Ref
    object_id: UUID | None = None
    action_frame: Frame | None = None
    body: Note
    author: Label
    resolved: bool = False


class ExceptionRecord(Record):
    kind: Literal['exception']
    subject: Ref
    check_code: Label
    reason: Label
    reviewer: Label
    dependencies: list[Ref] = Field(default_factory=list, max_length=500)


RecordData = Annotated[Union[Production, Sequence, Script, Location, Asset, Scene, Action, CameraSetup,
                             LightingSetup, Shot, Panel, Animatic, Edit, Take, Review, Annotation,
                             ExceptionRecord], Field(discriminator='kind')]
ADAPTER = TypeAdapter(RecordData)
MODELS = {name: model for name, model in zip(
    ('production','sequence','script','location','asset','scene','action','camera_setup','lighting_setup',
     'shot','panel','animatic','edit','take','review','annotation','exception'),
    (Production,Sequence,Script,Location,Asset,Scene,Action,CameraSetup,LightingSetup,Shot,Panel,Animatic,Edit,Take,Review,Annotation,ExceptionRecord))}


def unique(values, label):
    if len(values) != len(set(values)):
        raise ValueError(label + ' must be unique.')


def sorted_frames(keys):
    frames = [k.frame for k in keys]
    if frames != sorted(set(frames)):
        raise ValueError('Keyframes must have unique, ascending frame numbers.')


def parse_record(value):
    try:
        return ADAPTER.validate_python(value).model_dump(mode='json')
    except ValidationError as exc:
        raise ProductionError('Production record failed validation.', {
            'issues': json.loads(exc.json(include_url=False, include_input=False))}) from exc


def references(value, path=''):
    """Only structural exact refs are edges. No guessing IDs from prose or source bytes."""
    if isinstance(value, dict):
        if set(value) == {'id', 'version'} and isinstance(value['id'],str) and type(value['version']) is int:
            yield path, value
        else:
            for key, child in value.items():
                yield from references(child, f'{path}/{key}')
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from references(child, f'{path}/{index}')


def schema():
    return {'format': 'storyboarder.production/v1', 'record': ADAPTER.json_schema(),
            'batch': Batch.model_json_schema(), 'kinds': list(MODELS),
            'conventions': {'coordinates': FRAME, 'storage_units': 'metres',
                'rotation': 'degrees; +Y forward; yaw about +Z, pitch upward; relative children use parent-local pose',
                'intervals': 'half-open [start,end), integer action frames',
                'frame_rates': 'rational; no drop-frame timecode interpretation',
                'selection': 'explicit; new proposals never replace selected versions by default',
                'limits': {'records': MAX_RECORDS, 'operations_per_batch': MAX_OPERATIONS,
                           'json_bytes': MAX_PACKAGE_BYTES}}}


class Put(Model):
    op: Literal['put']
    id: UUID
    expected_revision: Annotated[int, Field(ge=0)]
    base_version: Annotated[int, Field(ge=1)] | None = None
    select: bool = False
    data: RecordData


class Select(Model):
    op: Literal['select']
    id: UUID
    expected_revision: Annotated[int, Field(ge=1)]
    version: Annotated[int, Field(ge=1)]


class Archive(Model):
    op: Literal['archive', 'restore']
    id: UUID
    expected_revision: Annotated[int, Field(ge=1)]


Operation = Annotated[Union[Put, Select, Archive], Field(discriminator='op')]


class Batch(Model):
    expected_checkpoint: Annotated[int, Field(ge=0)]
    operation_id: UUID
    operations: list[Operation] = Field(min_length=1, max_length=MAX_OPERATIONS)
    preview_sha256: Sha | None = None

    @model_validator(mode='after')
    def single_change_per_record(self):
        unique([o.id for o in self.operations], 'Changed record IDs within one atomic batch')
        return self
