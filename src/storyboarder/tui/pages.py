"""First-class page definitions. Rendering is separate from the shared application core."""
from dataclasses import dataclass
import json
from .widgets import Row, clean


@dataclass(frozen=True)
class Page:
    key: str
    title: str
    subtitle: str
    actions: tuple[str, ...] = ()


PAGES = (
    Page('workspace', 'Workspace', 'Create, open, and switch between projects saved on this computer.'),
    Page('overview', 'Project overview', 'Recent changes, story progress, and project care.', ('sequence.create', 'project.doctor', 'project.backup')),
    Page('intake', 'Image intake', 'Review new images, add tags, and place them in your reference library.', ('media.import', 'intake.accept', 'intake.discard', 'media.tags')),
    Page('library', 'Reference library', 'Organize characters, locations, props, and other images.', ('asset.create', 'media.import', 'asset.update', 'asset.attach', 'asset.primary', 'asset.merge')),
    Page('connections', 'Connections', 'See how library items and shots are related.', ('link.create', 'link.remove', 'assignment.create')),
    Page('outline', 'Story outline', 'Arrange sequences, scenes, and shots in story order.', ('sequence.create', 'scene.create', 'shot.create', 'story.move')),
    Page('guide', 'Story guide', 'Set direction for the whole project, then add notes for a sequence, scene, or shot.', ('project.update', 'context.put', 'context.resolve', 'context.remove')),
    Page('editor', 'Scene & shot editor', 'Add action, dialogue, camera notes, continuity, and image references.', ('scene.create', 'shot.create', 'shot.update', 'assignment.create', 'assignment.update', 'assignment.remove')),
    Page('frames', 'Storyboard frames', 'Add, compare, select, and approve storyboard images.', ('frame.add', 'frame.attach', 'frame.state', 'frame.remove')),
    Page('composition', 'Board & exports', 'Review the storyboard and create files to share or hand off.', ('composition.preview', 'export.bundle', 'export.board')),
    Page('automation', 'Image tools', 'Run trusted tools and review their results before adding them to a project.', ('job.create', 'job.run', 'job.preview', 'job.approve', 'job.cancel', 'job.retry')),
    Page('coverage', 'Observation coverage', 'Pin exact screenplay sources to a shot, then review purpose, requirements, and basis.'),
    Page('settings', 'Project care', 'Check project health, manage images, back up, restore, and review archived items.', ('project.doctor', 'project.backup', 'cache.rebuild', 'cache.clear', 'entity.restore')),
)
PAGE_MAP = {p.key: p for p in PAGES}

LABELS = {
    'asset': 'Library item', 'context': 'Story direction', 'media': 'Image', 'asset_media': 'Library image',
    'record': 'Item', 'story': 'Story flow', 'assets': 'Reference map', 'scene': 'Scene', 'frame': 'Storyboard image',
    'order': 'Story order', 'relationship': 'Library connection', 'assignment': 'Shot reference', 'location_default': 'Default location',
    'children': 'Items inside', 'links': 'Connections', 'assignments': 'Shot references',
    'frames': 'Storyboard images', 'media_memberships': 'Library images', 'location_defaults': 'Shots using this location',
    'jobs': 'Image tool runs', 'generated_outputs': 'Generated results', 'context_blocks': 'Direction notes',
    'character': 'Character', 'location': 'Location', 'prop': 'Prop', 'reference': 'General reference',
    'pending': 'Needs review', 'accepted': 'Added', 'discarded': 'Removed from intake', 'queued': 'Ready to run',
    'running': 'In progress', 'succeeded': 'Complete', 'failed': 'Needs attention', 'cancelled': 'Stopped',
    'draft': 'Draft', 'selected': 'Selected', 'approved': 'Approved', 'archived': 'Archived',
    'subject': 'Subject', 'setting-reference': 'Location', 'costume': 'Wardrobe', 'reference': 'General reference',
    'append': 'Add to earlier notes', 'replace': 'Replace earlier notes', 'exclude': 'Hide earlier notes here',
    'visual_style': 'Visual style', 'premise': 'Story premise', 'arc': 'Sequence direction', 'location_id': 'Location',
    'camera': 'Camera plan', 'time': 'Time of day', 'framing': 'Framing', 'duration': 'Duration',
    'continuity': 'Continuity', 'constraints': 'Production notes', 'action': 'Action', 'dialogue': 'Dialogue',
    'summary': 'Summary', 'description': 'Description', 'tags': 'Tags', 'aliases': 'Also known as',
}


def human(value):
    return LABELS.get(str(value), str(value).replace('_', ' ').replace('-', ' ').title())


def operation_label(value):
    return {
        'append': 'Adds to earlier notes',
        'replace': 'Earlier direction replaced here',
        'exclude': 'Earlier direction hidden here',
    }.get(str(value), human(value))


def display_title(value):
    text = str(value or 'Untitled')
    if text.isupper() and '_' in text and all(part.isalnum() for part in text.split('_')):
        return ' '.join(part if part.isdigit() else part.title() for part in text.split('_'))
    return text


def defaults(record):
    if not record:
        return {}
    result = dict(record)
    result.update(record.get('fields', {}))
    if record.get('kind') and record.get('kind') != 'asset': result['owner_id'] = record.get('id')
    if record.get('kind') == 'shot': result['shot_id'] = record['id']
    if record.get('kind') == 'scene': result['parent_id'] = record['id']
    if record.get('kind') == 'sequence': result['parent_id'] = record['id']
    if record.get('kind') == 'asset':
        result['asset_id'] = result['source_id'] = record['id']
    if 'key' in record: result['content'] = record.get('text', '')
    return result


def entity_label(record):
    kind = record.get('fields', {}).get('type') if record.get('kind') == 'asset' else record.get('kind', 'item')
    order = f" {record['position']+1:02}" if kind in ('sequence', 'scene', 'shot') else ''
    return f"{human(kind)}{order} · {display_title(record.get('title'))}" + (' · Archived' if record.get('archived') else '')


def rows_for(page, state, projects=(), query='', anchor=None, neighbors=None):
    rows = []
    if page == 'workspace':
        rows = [Row(p['id'], p.get('title', 'Untitled project') + (' · Recent' if p.get('recent') else '') + (' · Unavailable' if not p.get('available', True) else ''), p.get('path', ''), p) for p in projects]
    elif state:
        entities = state['entities']
        by_id = {r['id']: r for r in entities}
        active = [r for r in entities if not r['archived']]
        if page == 'intake':
            media = {m['id']: m for m in state['media']}
            for r in sorted(state['intake'], key=lambda r: (r['state'] != 'pending', r['media_id'], r['created_at'])):
                m = media[r['media_id']]
                count = sum(i['media_id'] == r['media_id'] for i in state['intake'])
                rows.append(Row(r['id'], f"{human(r['state'])} · {r['original_name']}" + (f' · {count} identical imports' if count > 1 else ''), f"{m['format'].upper()} · {m['width']} × {m['height']} · tags: {', '.join(m['tags']) or 'none'}", r))
        elif page == 'frames':
            rows = [Row(f['id'], f"{human(f['state'])} · {by_id[f['shot_id']]['title']} / image {f['version']}", f['notes'] or 'Storyboard image', f) for f in sorted(state['frames'], key=lambda f: (f['shot_id'], -f['version']))]
            if not rows:
                rows = [Row(r['id'], entity_label(r), 'No storyboard images yet. Add an image to this shot.', r) for r in active if r['kind'] == 'shot']
        elif page == 'automation':
            rows = [Row(j['id'], f"{human('approved' if j['approved'] else j['status'])} · {j['title']}", f"{j['script']} · {human(j['target'])}", j) for j in state['jobs']]
        elif page == 'connections' and anchor and neighbors:
            rows = [Row(anchor, 'Selected · '+display_title(by_id[anchor]['title']), 'Enter to return to all connected items.', by_id[anchor])]
            for edge in neighbors['edges']:
                other = edge['target'] if edge['source'] == anchor else edge['source']
                if other not in by_id:
                    continue
                label = edge['label']
                if edge['kind'] == 'relationship': label = human(label)
                elif edge['kind'] == 'assignment':
                    role, _, image = label.partition(' · ')
                    label = human(role)+(' · Specific image selected' if image == 'specific image selected' else ' · No specific image selected')
                elif edge['kind'] == 'location_default': label = 'Location'
                rows.append(Row(other, ('→ ' if edge['source'] == anchor else '← ')+label+' · '+display_title(by_id[other]['title']), human(edge['kind']), by_id[other]))
        else:
            if page == 'library': items = [r for r in active if r['kind'] == 'asset']
            elif page == 'connections': items = [r for r in active if r['kind'] in ('asset', 'shot')]
            elif page in ('outline', 'editor'):
                items = []
                def visit(parent):
                    for r in sorted((e for e in active if e.get('parent_id') == parent and e['kind'] != 'asset'), key=lambda e: (e['position'], e['id'])):
                        if page != 'editor' or r['kind'] in ('scene', 'shot'): items.append(r)
                        visit(r['id'])
                visit(state['project']['id'])
            elif page in ('guide', 'composition'): items = [r for r in active if r['kind'] != 'asset']
            elif page == 'settings': items = [state['project']] + [r for r in entities if r['archived']]
            else: items = [state['project']] + [r for r in active if r['kind'] == 'sequence']
            for r in items:
                depth = {'sequence': 0, 'scene': 1, 'shot': 2}.get(r['kind'], 0) if page in ('outline', 'editor') else 0
                fields = r['fields']
                description = fields.get('action') or fields.get('summary') or fields.get('arc') or r['description'] or 'Add a description or direction note.'
                if r['kind'] == 'shot':
                    refs = sum(a['shot_id'] == r['id'] for a in state['assignments'])
                    description = f"{fields.get('framing') or 'Framing not set'} · {refs} references · {description}"
                if r['kind'] == 'asset': description = f"Tags: {', '.join(r['tags']) or 'None'} · Also known as: {', '.join(r['aliases']) or 'None'} · {description}"
                rows.append(Row(r['id'], '  '*depth+entity_label(r), str(description).replace('\n', ' ')[:240], r))
    q = query.casefold().strip()
    return [r for r in rows if not q or q in (r.label+' '+r.detail+' '+r.id).casefold()]


def context_text(context):
    out = ['Direction in effect', ' / '.join(display_title(r['title']) for r in context['chain']), '']
    for key, value in context['scalars'].items():
        out += [human(key)+': '+str(value.get('label', value['value'])), f"  {human(value['source']['kind'])} · {display_title(value['source']['title'])}", '']
    for key, entries in context['blocks'].items():
        out.append(human(key))
        for entry in entries:
            out += [entry['text'], f"  {human(entry['source']['kind'])} · {display_title(entry['source']['title'])}", '']
    for step in context['history']:
        if step['operation'] == 'append':
            continue
        out.append(f"{human(step['key'])}: {operation_label(step['operation'])} · {display_title(step['source']['title'])}")
    return '\n'.join(out)


def describe(record, state):
    if not record:
        return 'Choose an item with the arrow keys.\n\nEnter: open or follow a connection\nCtrl+E: edit\nCtrl+N: create\nCtrl+K: search actions\nF5: refresh\n\nSearch by title, tags, type, or status.'
    if 'kind' not in record:
        ignored = {'id', 'revision', 'created_at', 'updated_at', 'project_id', 'owner_id', 'source_id', 'target_id', 'shot_id', 'asset_id', 'media_id', 'parent_id'}
        out = [human(record.get('state') or record.get('status') or record.get('type') or 'Details'), '']
        for key, value in record.items():
            if key in ignored or value in (None, '', [], {}):
                continue
            if key in ('state', 'status', 'role', 'operation', 'target'):
                value = human(value)
            if isinstance(value, (dict, list)):
                continue
            out += [human(key), str(value), '']
        return clean('\n'.join(out))
    out = [entity_label(record), '', record.get('description', ''), '']
    for key, value in record.get('fields', {}).items():
        if value not in ('', None):
            if key == 'location_id': value = next((r['title'] for r in state['entities'] if r['id'] == value), value)
            out += [human(key), str(value), '']
    if record.get('tags'): out += ['Tags: '+', '.join(record['tags']), '']
    if record.get('aliases'): out += ['Also known as: '+', '.join(record['aliases']), '']
    by_id = {e['id']: e for e in state['entities']}
    if record.get('parent_id'): out += ['Part of: '+display_title(by_id[record['parent_id']]['title']), '']
    assignments = [a for a in state['assignments'] if record['id'] in (a['shot_id'], a['asset_id'])]
    if assignments: out += ['Used in shots']
    for a in assignments:
        image = next((m['original_name'] for m in state['media'] if m['id'] == a['media_id']), 'No specific image selected')
        out += [f"{display_title(by_id[a['shot_id']]['title'])} → {human(a['role'])} → {display_title(by_id[a['asset_id']]['title'])}", f"  {image}", '']
    memberships = [m for m in state['asset_media'] if m['asset_id'] == record['id']]
    if memberships: out += ['Library images']
    for m in memberships:
        media = next(r for r in state['media'] if r['id'] == m['media_id'])
        out += [('Cover image · ' if m['is_primary'] else '')+media['original_name'], '']
    for f in state['frames']:
        if f['shot_id'] == record['id']: out += [f"Storyboard image {f['version']} · {human(f['state'])}", f['notes'], '']
    for link in state['links']:
        if record['id'] in (link['source_id'], link['target_id']): out += [f"Connection · {display_title(by_id[link['source_id']]['title'])} → {human(link['relation'])} → {display_title(by_id[link['target_id']]['title'])}", '']
    return clean('\n'.join(out))
