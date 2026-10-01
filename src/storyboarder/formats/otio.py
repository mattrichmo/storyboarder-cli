"""Lossless OTIO JSON tree adapter; does not open referenced media or plug-ins.

Only the editorial hierarchy and its timing primitives are interpreted. Other
OTIO properties (effects, markers, media references, metadata) are retained.
"""
from collections import Counter
import json
import math
import uuid

from storyboarder.domain.documents import NodeDraft, ParsedDocument
from storyboarder.domain.errors import StoryboardError

STRUCTURES = {'Timeline': {1}, 'Stack': {1}, 'Track': {1}, 'Clip': {1, 2}, 'Gap': {1}, 'Transition': {1}}


def schema_type(value):
    try:
        name, version = value['OTIO_SCHEMA'].rsplit('.', 1)
        if name not in STRUCTURES or int(version) not in STRUCTURES[name]:
            raise ValueError('Unsupported editorial structure')
        return name
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise StoryboardError('Unsupported OTIO tree node. Use Timeline.1, Stack.1, Track.1, Clip.1/2, Gap.1 or Transition.1.') from exc


def rational(value, label):
    if not isinstance(value, dict) or value.get('OTIO_SCHEMA') != 'RationalTime.1':
        raise StoryboardError(f'{label} must be an OTIO RationalTime.1 value.')
    rate, amount = value.get('rate'), value.get('value')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (rate, amount)) or rate <= 0:
        raise StoryboardError(f'{label} requires a finite value and a positive frame rate.')
    return amount / rate


def validate_timing(value):
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            schema = item.get('OTIO_SCHEMA')
            if schema == 'RationalTime.1':
                rational(item, 'Time')
            elif schema == 'TimeRange.1':
                rational(item.get('start_time'), 'Range start')
                if rational(item.get('duration'), 'Range duration') < 0:
                    raise StoryboardError('Editorial duration cannot be negative.')
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)


def parse_otio(payload):
    if schema_type(payload) != 'Timeline':
        raise StoryboardError('Import an OTIO Timeline.1 root, not a media collection.')
    validate_timing(payload)
    if not isinstance(payload.get('tracks'), dict) or schema_type(payload['tracks']) != 'Stack':
        raise StoryboardError('An OTIO timeline needs a tracks Stack.')
    drafts, warnings, seen = [], [], set()
    occurrences = Counter()
    def visit(item, parent, position, pointer, depth):
        if depth > 48:
            raise StoryboardError('OTIO editorial nesting exceeds 48 levels.')
        kind = schema_type(item)
        name = item.get('name', '')
        if not isinstance(name, str):
            raise StoryboardError('OTIO node names must be text.')
        metadata = item.get('metadata', {})
        if not isinstance(metadata, dict):
            raise StoryboardError('OTIO metadata must be an object.')
        namespace = metadata.get('storyboarder', {})
        if not isinstance(namespace, dict):
            raise StoryboardError('OTIO metadata.storyboarder must be an object.')
        explicit = namespace.get('id')
        if explicit:
            try:
                logical_id = str(uuid.UUID(explicit))
            except (TypeError, ValueError, AttributeError) as exc:
                raise StoryboardError('OTIO metadata.storyboarder.id must be a UUID.') from exc
            identity = 'explicit'
        else:
            # Names/media references are hints, not universal OTIO identities. Warnings
            # remain visible in comparisons; no identity is inferred from timing.
            hint = json.dumps([kind, name, item.get('media_reference'), item.get('media_references')], sort_keys=True)
            occurrences[hint] += 1
            logical_id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'storyboarder:otio:' + hint + ':' + str(occurrences[hint])))
            identity = 'inferred'
        if logical_id in seen:
            raise StoryboardError(f'Duplicate OTIO structural identity: {logical_id}')
        seen.add(logical_id)
        own = {k: v for k, v in item.items() if k not in ('tracks', 'children')}
        label = name.strip() or kind
        text = ''
        if item.get('source_range') is not None:
            source_range = item['source_range']
            if not isinstance(source_range, dict) or source_range.get('OTIO_SCHEMA') != 'TimeRange.1':
                raise StoryboardError('source_range must be an OTIO TimeRange.1 object or null.')
            validate_timing(source_range)
            duration = source_range['duration']
            text = f"{duration['value']:g} frames @ {duration['rate']:g} fps"
        drafts.append(NodeDraft(logical_id, parent, kind, position, label, text, pointer, own, identity))
        if kind == 'Timeline':
            visit(item['tracks'], logical_id, 0, '/tracks', depth + 1)
        elif kind in ('Track', 'Stack'):
            children = item.get('children', [])
            if not isinstance(children, list):
                raise StoryboardError('OTIO children must be an ordered list.')
            if kind == 'Track' and item.get('kind', 'Video') not in ('Video', 'Audio'):
                raise StoryboardError('This adapter supports Video and Audio tracks.')
            for i, child in enumerate(children):
                if not isinstance(child, dict) or schema_type(child) == 'Timeline':
                    raise StoryboardError('Invalid OTIO composition child.')
                visit(child, logical_id, i, pointer + f'/children/{i}', depth + 1)
        elif 'children' in item or 'tracks' in item:
            raise StoryboardError(f'{kind} cannot contain editorial child nodes.')
        if kind == 'Transition':
            for field in ('in_offset', 'out_offset'):
                if rational(item.get(field), field) < 0:
                    raise StoryboardError('Transition offsets cannot be negative.')
        return logical_id
    root = visit(payload, None, 0, '', 0)
    inferred = sum(node.identity != 'explicit' for node in drafts)
    if inferred:
        warnings.append({'code': 'inferred_otio_identity', 'count': inferred,
                         'message': 'Some OTIO objects have no metadata.storyboarder.id. Matching uses name/media hints; renames and repeated clips may require manual relinking. Export with identity metadata before external revision when possible.'})
    warnings.append({'code': 'otio_json_scope', 'message': 'OTIO JSON hierarchy and timing validated. Effects, markers and media references are preserved, not rendered or resolved.'})
    return ParsedDocument('edit', 'otio', payload['OTIO_SCHEMA'], payload.get('name') or 'Untitled edit',
                          root if drafts[0].identity == 'explicit' else None, payload, drafts, warnings)
