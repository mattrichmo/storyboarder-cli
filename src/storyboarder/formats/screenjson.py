"""ScreenJSON 1.x core compatibility profile, independently implemented.

The published January 2026 schema uses closed allOf branches that reject their
own element fields under standard JSON Schema semantics. We validate a typed
core profile instead of silently patching that schema or claiming certification.
Ancillary metadata is preserved, never executed. See docs/FORMATS.md.
"""
import re
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator
from storyboarder.domain.documents import NodeDraft, ParsedDocument
from storyboarder.domain.errors import StoryboardError

UUID = Annotated[str, Field(pattern=r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')]
LANG = r'^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$'
LanguageMap = dict[Annotated[str, Field(pattern=LANG)], Annotated[str, Field(min_length=1, max_length=10000)]]


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)


class Person(Model):
    id: UUID
    given: str = Field(min_length=1, max_length=50)
    family: str = Field(min_length=1, max_length=50)
    meta: dict = Field(default_factory=dict)


class Character(Model):
    id: UUID
    name: str = Field(min_length=1, max_length=80)
    slug: str | None = None
    aliases: list[str] = Field(default_factory=list)
    desc: LanguageMap = Field(default_factory=dict)
    traits: list[str] = Field(default_factory=list)
    meta: dict = Field(default_factory=dict)


class Heading(Model):
    context: Literal['I/E', 'INT/EXT', 'EXT/INT', 'INT', 'EXT', 'POV']
    setting: str = Field(min_length=1, max_length=200)
    time: str = Field(min_length=2, max_length=40, pattern=r"^[A-Z0-9][A-Z0-9 .’'/-]{1,39}$")
    no: int | None = Field(default=None, ge=1)
    mods: list[str] = Field(default_factory=list)
    desc: LanguageMap = Field(default_factory=dict)
    meta: dict = Field(default_factory=dict)


class Element(Model):
    id: UUID
    authors: list[UUID] = Field(min_length=1)
    scene: UUID | None = None
    contributors: list[UUID] = Field(default_factory=list)
    access: list[str] = Field(default_factory=list)
    notes: list[dict] = Field(default_factory=list)
    charset: str | None = None
    dir: Literal['ltr', 'rtl'] | None = None
    css_class: str | None = Field(default=None, alias='class')
    dom: str | None = None
    encrypt: dict | None = None
    locked: bool = False
    omit: bool = False
    revisions: list[dict] = Field(default_factory=list)
    styles: list[str] = Field(default_factory=list)
    meta: dict = Field(default_factory=dict)


class TextElement(Element):
    type: Literal['action', 'parenthetical', 'general', 'transition']
    text: LanguageMap


class ShotElement(Element):
    type: Literal['shot']
    text: LanguageMap
    fov: float | None = Field(default=None, ge=0, le=360)
    perspective: Literal['2D', '3D'] = '2D'


class Cue(Element):
    type: Literal['character']
    character: UUID
    display: str | None = Field(default=None, min_length=1, max_length=120)


class Dialogue(Element):
    type: Literal['dialogue']
    character: UUID
    text: LanguageMap
    origin: Literal['V.O', 'V.O.', 'O.S', 'O.S.', 'O.C', 'O.C.', 'FILTER'] | None = None
    dual: bool = False


Body = Annotated[TextElement | ShotElement | Cue | Dialogue, Field(discriminator='type')]


class Scene(Model):
    id: UUID
    authors: list[UUID] = Field(min_length=1)
    heading: Heading
    body: list[Body]
    contributors: list[UUID] = Field(default_factory=list)
    cast: list[UUID] = Field(default_factory=list)
    animals: list[str] = Field(default_factory=list)
    extra: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    moods: list[str] = Field(default_factory=list)
    props: list[str] = Field(default_factory=list)
    sfx: list[str] = Field(default_factory=list)
    sounds: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    vfx: list[str] = Field(default_factory=list)
    wardrobe: list[str] = Field(default_factory=list)
    meta: dict = Field(default_factory=dict)


class Cover(Model):
    title: LanguageMap
    authors: list[UUID] = Field(min_length=1)
    sources: list[UUID] = Field(default_factory=list)
    extra: LanguageMap = Field(default_factory=dict)
    meta: dict = Field(default_factory=dict)


class Document(Model):
    cover: Cover
    scenes: list[Scene] = Field(min_length=1)
    layout: dict = Field(default_factory=dict)
    bookmarks: list[dict] = Field(default_factory=list)
    meta: dict = Field(default_factory=dict)


class ScreenJSON(Model):
    id: UUID
    version: str = Field(pattern=r'^1\.\d+\.\d+$')
    title: LanguageMap
    lang: str = Field(pattern=LANG)
    charset: str
    dir: Literal['ltr', 'rtl']
    authors: list[Person] = Field(min_length=1)
    document: Document
    characters: list[Character] = Field(default_factory=list)
    contributors: list[dict] = Field(default_factory=list)
    revisions: list[dict] = Field(default_factory=list)
    colors: list[dict] = Field(default_factory=list)
    sources: list[dict] = Field(default_factory=list)
    registrations: list[dict] = Field(default_factory=list)
    generator: dict | None = None
    locale: str | None = None
    encrypt: dict | None = None
    license: dict | None = None
    taggable: list[str] = Field(default_factory=list)
    genre: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    logline: LanguageMap = Field(default_factory=dict)
    analysis: dict = Field(default_factory=dict)

    @field_validator('charset')
    @classmethod
    def utf8(cls, value):
        if value.lower() not in ('utf-8', 'utf8'):
            raise ValueError('This adapter accepts UTF-8 ScreenJSON only.')
        return value


def text_value(value, language='en'):
    if isinstance(value, dict):
        return str(value.get(language) or next(iter(value.values()), ''))
    return str(value or '')


def parse_screenjson(payload):
    try:
        model = ScreenJSON.model_validate(payload)
    except ValidationError as exc:
        issues = [{'path': '/'.join(map(str, error['loc'])), 'message': error['msg']} for error in exc.errors()[:30]]
        raise StoryboardError('ScreenJSON does not match the supported 1.x core profile.', {'issues': issues}) from exc
    if model.encrypt or any(e.encrypt for scene in model.document.scenes for e in scene.body):
        raise StoryboardError('Encrypted screenplays must be decrypted externally before import.')
    canonical = lambda value: str(uuid.UUID(value))
    seen = set()
    def identity(value):
        result = canonical(value)
        if result in seen:
            raise StoryboardError(f'Duplicate ScreenJSON UUID: {value}')
        seen.add(result)
        return result
    root_id = identity(model.id)
    authors = {identity(person.id) for person in model.authors}
    characters = {identity(person.id): person.name for person in model.characters}
    scene_ids, element_scenes = set(), {}
    nodes = []
    root_payload = dict(payload)
    root_payload['document'] = {k: v for k, v in payload['document'].items() if k != 'scenes'}
    title = text_value(model.title, model.lang) or 'Untitled screenplay'
    nodes.append(NodeDraft(root_id, None, 'screenplay', 0, title, '', '', root_payload))
    def author_refs(values):
        if any(canonical(value) not in authors for value in values):
            raise StoryboardError('A screenplay author reference is missing from the author index.')
    author_refs(model.document.cover.authors)
    for i, scene in enumerate(model.document.scenes):
        scene_id = identity(scene.id)
        scene_ids.add(scene_id)
        author_refs(scene.authors)
        if any(canonical(value) not in characters for value in scene.cast):
            raise StoryboardError('A scene cast reference is missing from the character index.')
        heading = scene.heading
        label = f'{heading.context}. {heading.setting} — {heading.time}'
        raw_scene = payload['document']['scenes'][i]
        nodes.append(NodeDraft(scene_id, root_id, 'scene', i, label, label,
                               f'/document/scenes/{i}', {k: v for k, v in raw_scene.items() if k != 'body'}))
        for j, element in enumerate(scene.body):
            element_id = identity(element.id)
            element_scenes[element_id] = scene_id
            author_refs(element.authors)
            if element.scene and canonical(element.scene) != scene_id:
                raise StoryboardError('A scene element references a different owning scene.')
            character = getattr(element, 'character', None)
            if character and canonical(character) not in characters:
                raise StoryboardError('A dialogue or cue character is missing from the character index.')
            raw_element = raw_scene['body'][j]
            text = text_value(raw_element.get('text'), model.lang)
            if element.type == 'character':
                text = getattr(element, 'display', None) or characters[canonical(character)]
            nodes.append(NodeDraft(element_id, scene_id, element.type, j, (text[:120] or element.type.title()),
                                   text, f'/document/scenes/{i}/body/{j}', raw_element))
    for bookmark in model.document.bookmarks:
        try:
            sid, eid = canonical(bookmark['scene']), canonical(bookmark['element'])
            if sid not in scene_ids or element_scenes.get(eid) != sid:
                raise ValueError('Bookmark target is absent or belongs to another scene.')
        except (KeyError, ValueError, TypeError) as exc:
            raise StoryboardError(f'Invalid screenplay bookmark: {exc}') from exc
    warnings = [{'code': 'screenjson_core_profile', 'message': 'Core structure and author/character/scene references validated. Ancillary layout, analysis, revision and note payloads are preserved without full upstream-schema certification.'}]
    return ParsedDocument('screenplay', 'screenjson', model.version, title, root_id, payload, nodes, warnings)
