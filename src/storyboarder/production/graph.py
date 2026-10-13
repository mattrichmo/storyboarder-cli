"""Referential and cross-vertical validation of exact production versions.

The resolver receives a transaction-local graph, including the entire staged batch.
No query or validation function mutates the database.
"""
from __future__ import annotations

from collections import deque

from .models import ProductionError, references


def key(ref):
    return ref['id'], ref['version']


def ref_for(record):
    return {'id': record['id'], 'version': record['version']}


class Graph:
    def __init__(self, heads, resolve):
        self.heads = heads
        self.resolve = resolve

    def require(self, ref, kinds=None, categories=None):
        record = self.resolve(*key(ref))
        if kinds and record['kind'] not in kinds:
            raise ProductionError('A production reference has the wrong record type.',
                                  {'reference': ref, 'expected': list(kinds), 'actual': record['kind']})
        if categories and record['data'].get('category') not in categories:
            raise ProductionError('An asset is used in an incompatible role.', {
                'reference': ref, 'expected_categories': list(categories),
                'actual': record['data'].get('category')})
        return record['data']

    def fragments(self, fragments):
        blocks = set()
        for f in fragments:
            script = self.require(f['script'], {'script'})
            scene = next((s for s in script['scenes'] if s['id'] == f['script_scene_id']), None)
            if scene is None:
                raise ProductionError('Script scene is absent from the pinned script version.', {'fragment': f})
            ids = {b['id'] for b in scene['blocks']}
            if set(f['block_ids']) - ids:
                raise ProductionError('Script coverage references removed or unrelated passages.',
                                      {'missing': sorted(set(f['block_ids']) - ids)})
            if f['disposition'] == 'planned':
                blocks.update(f['block_ids'] or ids)
        return blocks

    def validate(self, record):
        p, kind = record['data'], record['kind']
        for path, ref in references(p):
            self.require(ref)
            if self.heads[ref['id']]['archived']:
                raise ProductionError('New work cannot reference an archived production record.',
                                      {'path': path, 'reference': ref})
        if kind == 'asset' and p['portrays']:
            self.require(p['portrays'], {'asset'}, {'character'})
        if kind in ('scene', 'shot'):
            self.fragments(p['fragments'])
            for r in p['requirements'] + p.get('dressing', []):
                self.require(r['asset'], {'asset'})
        if kind == 'scene':
            if p['sequence']:
                self.require(p['sequence'], {'sequence'})
            if p['location']:
                self.require(p['location'], {'location'})
        if kind in ('action', 'camera_setup', 'lighting_setup', 'shot'):
            scene = self.require(p['scene'], {'scene'})
            if p.get('location'):
                location = self.require(p['location'], {'location'})
                if scene['location'] and p['location'] != scene['location']:
                    raise ProductionError('The setup and scene pin conflicting location revisions.')
            if p.get('action'):
                action = self.require(p['action'], {'action'})
                if action['scene'] != p['scene']:
                    raise ProductionError('The shot/setup and shared action must pin the same scene revision.')
                if p.get('location') and action['location'] != p['location']:
                    raise ProductionError('The setup and action must pin the same location revision.')
        if kind == 'action':
            mapped_blocks = self.fragments(scene['fragments'])
            for b in p['beats']:
                if set(b['block_ids']) - mapped_blocks:
                    raise ProductionError('An action beat references passages not planned by its scene.',
                                          {'beat_id': b['id'], 'unmapped': sorted(set(b['block_ids']) - mapped_blocks)})
            for i in p['instances']:
                self.require(i['asset'], {'asset'}, {'character','performer','prop','wardrobe','set_dressing','rig','grip','reference'})
                self.validate_target(i['facing'], p, location)
                self.validate_target(i['eyeline'], p, location)
            instances = {i['id']: i for i in p['instances']}
            for e in p['prop_events']:
                self.require(instances[e['instance_id']]['asset'], {'asset'}, {'prop','wardrobe','set_dressing'})
        if kind == 'camera_setup':
            if p['camera_asset']:
                self.require(p['camera_asset'], {'asset'}, {'camera'})
            if p['lens_asset']:
                self.require(p['lens_asset'], {'asset'}, {'lens'})
            action = self.require(p['action'], {'action'}) if p['action'] else None
            if action and p['keyframes'] and p['keyframes'][-1]['frame'] > action['duration_frames']:
                raise ProductionError('Camera move extends beyond the shared action.')
            self.validate_target(p['target'], action, location)
            self.validate_target(p['focus_target'], action, location)
        if kind == 'lighting_setup':
            action = self.require(p['action'], {'action'}) if p['action'] else None
            for f in p['fixtures']:
                self.require(f['asset'], {'asset'}, {'light'})
                for r in f['modifiers']:
                    self.require(r, {'asset'}, {'modifier'})
                for r in f['supports']:
                    self.require(r, {'asset'}, {'grip','rig'})
            if action and any(c['frame'] > action['duration_frames'] for c in p['cues']):
                raise ProductionError('Lighting cue extends beyond the shared action.')
        if kind == 'shot':
            action = self.require(p['action'], {'action'}) if p['action'] else None
            if action:
                if p['interval']['end'] > action['duration_frames']:
                    raise ProductionError('Shot interval extends beyond shared action.')
                beat_ids = {b['id'] for b in action['beats']}
                if set(p['beat_ids']) - beat_ids:
                    raise ProductionError('Shot references removed action beats.')
                instances = {i['id'] for i in action['instances']}
                for o in p['overrides']:
                    if o['instance_id'] not in instances:
                        raise ProductionError('Shot override references a missing instance.')
                    if o['keyframes'] and o['keyframes'][-1]['frame'] > action['duration_frames']:
                        raise ProductionError('Override keys extend beyond shared action.')
            for r in p['cameras'] + ([p['lighting']] if p['lighting'] else []):
                setup = self.require(r, {'lighting_setup'} if r == p['lighting'] else {'camera_setup'})
                if setup['scene'] != p['scene']:
                    raise ProductionError('A shot and its setups must pin the same scene revision.')
                if setup['action'] and setup['action'] != p['action']:
                    raise ProductionError('A shot and its timed setups must pin the same action revision.')
        if kind in ('panel', 'take'):
            shot = self.require(p['shot'], {'shot'})
            if kind == 'panel':
                if p['camera'] and p['camera'] not in shot['cameras']:
                    raise ProductionError('A storyboard panel camera must belong to its shot.')
                if p['action_frame'] is not None:
                    if not shot['interval'] or not shot['interval']['start'] <= p['action_frame'] < shot['interval']['end']:
                        raise ProductionError('Storyboard panel moment is outside its shot action interval.')
        if kind == 'animatic':
            for e in p['entries']:
                self.require(e['panel'], {'panel'})
        if kind == 'edit':
            from .evaluate import shot_duration_frames
            for e in p['entries']:
                shot = self.require(e['shot'], {'shot'})
                if shot['action']:
                    action = self.require(shot['action'], {'action'})
                    if e['shot_interval']['end'] > shot_duration_frames(shot, action):
                        raise ProductionError('Editorial selection exceeds its planned shot duration.')
                if e['take']:
                    take = self.require(e['take'], {'take'})
                    if take['shot'] != e['shot']:
                        raise ProductionError('Editorial take must belong to the selected planned shot revision.')
                if e['match_action_anchor']:
                    if not shot['action'] or e['match_action_anchor'] not in {b['id'] for b in self.require(shot['action'])['beats']}:
                        raise ProductionError('Match-action anchor must identify a beat in the shot action.')
        if kind == 'annotation':
            subject = self.require(p['subject'])
            if p['object_id']:
                ids = set()
                def collect(value):
                    if isinstance(value, dict):
                        if 'id' in value and 'version' not in value:
                            ids.add(value['id'])
                        for v in value.values():
                            collect(v)
                    elif isinstance(value, list):
                        for v in value:
                            collect(v)
                collect(subject)
                if p['object_id'] not in ids:
                    raise ProductionError('Annotation object is absent from the pinned subject revision.')
            if p['action_frame'] is not None:
                duration = subject.get('duration_frames')
                if subject['kind'] == 'shot' and subject['action']:
                    duration = self.require(subject['action'])['duration_frames']
                if duration is None or p['action_frame'] > duration:
                    raise ProductionError('Annotation time is outside its subject timeline.')

    @staticmethod
    def validate_target(target, action, location):
        if not target:
            return
        if target['instance_id'] and (not action or target['instance_id'] not in {i['id'] for i in action['instances']}):
            raise ProductionError('Target references an instance absent from the pinned action.')
        if target['mark_id'] and target['mark_id'] not in {m['id'] for m in location['marks']}:
            raise ProductionError('Target references a mark absent from the pinned location.')

    def closure(self, ref):
        """Bounded iterative exact-version traversal; safe for deep imported graphs."""
        queue, found = deque([ref]), {}
        while queue:
            current = queue.popleft()
            k = key(current)
            if k in found:
                continue
            if len(found) >= 25000:
                raise ProductionError('Dependency closure exceeds the supported 25,000 versions.')
            r = self.resolve(*k)
            found[k] = r
            queue.extend(child for _, child in references(r['data']))
        return found

    def stale(self, ref):
        """Distinguish pin drift from an actual change to covered script wording.

        An unrelated scene edit does not invalidate all shots in the screenplay.
        Exact source pins remain unchanged; the result explains the comparison.
        """
        issues, seen, queue = {}, set(), deque([(None, '', ref)])
        while queue:
            source, path, current = queue.popleft()
            rid, version = key(current)
            record = self.resolve(rid, version)
            head = self.heads[rid]
            if head['archived'] or head['selected_version'] != version:
                unaffected = False
                if record['kind'] == 'script' and head['selected_version'] and source and '/fragments/' in path:
                    parts = path.strip('/').split('/')
                    try:
                        fragment = source['data']
                        for part in parts[:-1]:
                            fragment = fragment[int(part)] if isinstance(fragment,list) else fragment[part]
                        newer = self.resolve(rid,head['selected_version'])['data']
                        unaffected = fragment_equivalent(fragment,record['data'],newer)
                    except (KeyError,IndexError,TypeError,ValueError):
                        unaffected = False
                reason = 'archived' if head['archived'] else 'unselected' if head['selected_version'] is None else 'unchanged_covered_content' if unaffected else 'revision_changed'
                detail = {'id':rid,'version':version,'selected_version':head['selected_version'],
                          'title':record['data']['title'],'reason':reason,
                          'needs_attention':not unaffected,'source_id':source['id'] if source else None,'path':path}
                previous = issues.get((rid,version))
                if previous is None or not previous['needs_attention']:
                    issues[(rid,version)] = detail
            if (rid,version) not in seen:
                seen.add((rid,version))
                queue.extend((record,p,child) for p,child in references(record['data']))
        return list(issues.values())

    def affected(self, ids, exclude=()):
        ids, exclude = set(ids), set(exclude)
        found = []
        for h in sorted(self.heads.values(), key=lambda x: x['id']):
            if h['archived'] or h['id'] in exclude:
                continue
            v = h['selected_version']
            if v is None:
                continue
            closure = self.closure({'id': h['id'], 'version': v})
            dependencies = [{'id': rid, 'version': version} for rid, version in closure if rid in ids and rid != h['id']]
            if dependencies:
                r = self.resolve(h['id'], v)
                found.append({'id': h['id'], 'kind': h['kind'], 'version': v, 'revision': h['revision'],
                              'title': r['data']['title'], 'dependencies': dependencies,
                              'stale': self.stale(ref_for(r))})
        return found


def fragment_equivalent(fragment, old_script, new_script):
    old = next((s for s in old_script['scenes'] if s['id']==fragment['script_scene_id']),None)
    new = next((s for s in new_script['scenes'] if s['id']==fragment['script_scene_id']),None)
    if not old or not new or old['heading'] != new['heading']:
        return False
    ids = set(fragment['block_ids'])
    def content(scene):
        return [(b['id'],b['type'],b['character'],b['text']) for b in scene['blocks'] if not ids or b['id'] in ids]
    return content(old)==content(new)
