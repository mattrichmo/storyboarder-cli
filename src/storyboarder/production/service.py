"""Transactional, revision-pinned production mutations shared by CLI/API/viewer.

No lost-update fallback, no overwrite import, no implicit selection of agent proposals.
Receipts are checked before the checkpoint, so a lost response is safely retryable.
"""
from __future__ import annotations

import copy
import json

from storyboarder.domain.errors import Conflict, InUse, NotFound
from storyboarder.domain.models import dumps, now
from .models import Batch, MAX_OPERATIONS, MAX_PACKAGE_BYTES, MAX_RECORDS, ProductionError, decode, digest, parse_record, references
from .graph import Graph, ref_for
from .external import validate_external, insert_external


def size_check(value):
    try:
        encoded = dumps(value).encode('utf-8')
    except (ValueError, TypeError, RecursionError) as exc:
        raise ProductionError('Input must be finite JSON data.') from exc
    if len(encoded) > MAX_PACKAGE_BYTES:
        raise ProductionError('Production JSON exceeds the 32 MiB limit.')
    if b'\\u0000' in encoded:
        raise ProductionError('NUL characters are not allowed in production data.')


class ProductionService:
    def __init__(self, service):
        self.service, self.repo, self.root = service, service.repo, service.root

    @staticmethod
    def _clock(conn):
        return conn.execute('SELECT checkpoint FROM production_clock WHERE singleton=1').fetchone()[0]

    @staticmethod
    def _heads(conn):
        heads = {r['id']: dict(r) for r in conn.execute('SELECT * FROM production_records')}
        for h in heads.values():
            h['archived'] = bool(h['archived'])
        return heads

    @staticmethod
    def _version(conn, heads, rid, number):
        h = heads.get(rid)
        if not h:
            raise NotFound('Production record does not exist.', {'id': rid})
        v = conn.execute('SELECT * FROM production_versions WHERE record_id=? AND number=?', (rid, number)).fetchone()
        if v is None:
            raise NotFound('Pinned production version does not exist.', {'id': rid, 'version': number})
        return {**h, 'version': number, 'parent_version': v['parent_number'],
                'data': json.loads(v['payload_json']), 'sha256': v['sha256'], 'version_created_at': v['created_at'],
                'is_selected': h['selected_version'] == number}

    def _graph(self, conn, heads=None, staged=None):
        heads = heads if heads is not None else self._heads(conn)
        cache = dict(staged or {})
        cached_bytes = [sum(len(dumps(r['data']).encode('utf-8')) for r in cache.values())]
        def resolve(rid, version):
            k = rid, version
            if k not in cache:
                r = self._version(conn, heads, rid, version)
                cached_bytes[0] += len(dumps(r['data']).encode('utf-8'))
                if len(cache)>=25000 or cached_bytes[0]>128*1024*1024:
                    raise ProductionError('This graph evaluation exceeds 25,000 versions or 128 MiB. Narrow the query or split the production.')
                cache[k] = r
            return cache[k]
        return Graph(heads, resolve)

    def snapshot(self, mode='selected', include_archived=False, limit=500, offset=0, closure=False):
        if mode not in ('selected', 'head') or type(include_archived) is not bool or type(closure) is not bool:
            raise ProductionError('Choose selected/head with boolean archive/closure flags.')
        self._page(limit, offset)
        with self.repo.transaction(False) as conn:
            heads = self._heads(conn)
            graph = self._graph(conn, heads)
            active = [h for h in heads.values() if include_archived or not h['archived']]
            active.sort(key=lambda x: (x['kind'], x['id']))
            records, pinned = [], {}
            for h in active[offset:offset + limit]:
                version = h['head_version'] if mode == 'head' else h['selected_version'] or h['head_version']
                r = graph.resolve(h['id'], version)
                records.append(r)
                if closure:
                    pinned.update(graph.closure(ref_for(r)))
            result = {'format': 'storyboarder.production/v1', 'checkpoint': self._clock(conn),
                    'records': records, 'pinned_versions': list(pinned.values()),
                    'total': len(active), 'limit': limit, 'offset': offset,
                    'next_offset': offset + len(records) if offset + len(records) < len(active) else None,
                    'snapshot_sha256': digest([[h['id'], h['revision'], h['selected_version'], h['archived']]
                                               for h in sorted(heads.values(), key=lambda x: x['id'])])}
            size_check(result)
            return result

    @staticmethod
    def _page(limit, offset):
        if type(limit) is not int or not 1 <= limit <= MAX_RECORDS or type(offset) is not int or offset < 0:
            raise ProductionError('Page bounds must be integers: limit 1–5000 and offset >= 0.')

    def show(self, id, version=None):
        with self.repo.transaction(False) as conn:
            heads = self._heads(conn)
            h = heads.get(id)
            if not h:
                raise NotFound('Production record does not exist.', {'id': id})
            version = version if version is not None else h['selected_version'] or h['head_version']
            if type(version) is not int or version < 1:
                raise ProductionError('Version must be a positive integer.')
            graph = self._graph(conn, heads)
            record = graph.resolve(id, version)
            return {**record, 'stale_dependencies': graph.stale(ref_for(record)),
                    'dependencies': [{'path': path, **ref} for path, ref in references(record['data'])]}

    def history(self, id, limit=100, offset=0):
        self._page(limit, offset)
        with self.repo.transaction(False) as conn:
            heads = self._heads(conn)
            if id not in heads:
                raise NotFound('Production record does not exist.')
            total = conn.execute('SELECT count(*) FROM production_versions WHERE record_id=?', (id,)).fetchone()[0]
            rows = [dict(r) for r in conn.execute('SELECT record_id,number,parent_number,sha256,created_at FROM production_versions WHERE record_id=? ORDER BY number DESC LIMIT ? OFFSET ?', (id, limit, offset))]
            return {'header': heads[id], 'items': rows, 'total': total, 'offset': offset, 'limit': limit,
                    'next_offset': offset + len(rows) if offset + len(rows) < total else None}

    def _stage(self, conn, batch):
        if self._clock(conn) != batch['expected_checkpoint']:
            raise Conflict('Production changed since this batch was prepared; refresh and reconcile the draft.',
                           {'expected_checkpoint': batch['expected_checkpoint'], 'actual_checkpoint': self._clock(conn)})
        heads, staged, changes = self._heads(conn), {}, []
        stamp = now()
        for op in batch['operations']:
            h = heads.get(op['id'])
            actual = h['revision'] if h else 0
            if op['expected_revision'] != actual:
                raise Conflict('Record revision changed. The draft was not applied.',
                               {'id': op['id'], 'expected_revision': op['expected_revision'], 'actual_revision': actual})
            previous = h['selected_version'] if h else None
            if op['op'] == 'put':
                p = parse_record(op['data'])
                if h and h['kind'] != p['kind']:
                    raise ProductionError('A stable ID cannot change its record kind.')
                if h and h['archived']:
                    raise ProductionError('Restore archived records before editing them.')
                number = (h['head_version'] + 1) if h else 1
                parent = op['base_version'] if op['base_version'] else (h['head_version'] if h else None)
                if parent:
                    self._version(conn, heads, op['id'], parent)
                if not h:
                    h = {'id': op['id'], 'kind': p['kind'], 'revision': 0, 'head_version': None,
                         'selected_version': None, 'archived': False, 'created_at': stamp, 'updated_at': stamp}
                h = {**h, 'revision': actual + 1, 'head_version': number, 'updated_at': stamp}
                if op['select']:
                    h['selected_version'] = number
                heads[h['id']] = h
                staged[(h['id'], number)] = {**h, 'data': p, 'version': number, 'parent_version': parent,
                                            'sha256': digest(p), 'version_created_at': stamp,
                                            'is_selected': h['selected_version'] == number}
            else:
                if h is None:
                    raise NotFound('Production record does not exist.')
                h = {**h, 'revision': actual + 1, 'updated_at': stamp}
                if op['op'] == 'select':
                    if h['archived']:
                        raise ProductionError('Restore archived records before selecting a version.')
                    self._version(conn, heads, h['id'], op['version'])
                    h['selected_version'] = op['version']
                else:
                    h['archived'] = op['op'] == 'archive'
                heads[h['id']] = h
            changes.append({'id': h['id'], 'op': op['op'], 'revision': h['revision'],
                            'previous_selected_version': previous, 'selected_version': h['selected_version'],
                            'head_version': h['head_version'], 'archived': h['archived']})
        if len(heads) > MAX_RECORDS:
            raise ProductionError('Production exceeds the supported 5,000 record limit.')
        graph = self._graph(conn, heads, staged)
        # Revalidate every new/re-selected record in the same transaction. Existing stale
        # pinned work is retained, not rewritten or made impossible to inspect.
        for op in batch['operations']:
            h = heads[op['id']]
            if op['op'] in ('put', 'select', 'restore'):
                version = h['head_version'] if op['op'] == 'put' else h['selected_version'] or h['head_version']
                record = graph.resolve(h['id'], version)
                graph.validate(record)
                validate_external(conn, record)
        archived = {c['id'] for c in changes if c['op'] == 'archive'}
        if archived:
            for h in heads.values():
                if h['archived']:
                    continue
                for v in {h['head_version'], h['selected_version']} - {None}:
                    refs = {r['id'] for _, r in references(graph.resolve(h['id'], v)['data'])}
                    if refs & archived:
                        raise InUse('Archive blocked: active work still references this record.',
                                    {'dependent_id': h['id'], 'version': v, 'referenced_ids': sorted(refs & archived)})
        # An exact-version graph may refer to earlier versions of itself; a cycle between
        # newly constructed exact nodes, however, has no reproducible starting state.
        def acyclic(start):
            visiting, visited, stack = set(), set(), [(start, False)]
            while stack:
                k, exiting = stack.pop()
                if exiting:
                    visiting.discard(k); visited.add(k); continue
                if k in visiting:
                    raise ProductionError('Exact-version dependency cycle is not allowed.', {'reference': list(k)})
                if k in visited:
                    continue
                visiting.add(k); stack.append((k, True))
                children = [(r['id'], r['version']) for _, r in references(graph.resolve(*k)['data'])]
                stack.extend((child, False) for child in children)
        for k in staged:
            acyclic(k)
        vector = [[h['id'], h['revision'], h['selected_version'], h['archived']] for h in sorted(heads.values(), key=lambda x: x['id'])]
        result = {'checkpoint': batch['expected_checkpoint'] + 1, 'operation_id': batch['operation_id'],
                  'changes': changes, 'snapshot_sha256': digest(vector)}
        return heads, staged, changes, graph, result

    @staticmethod
    def _request(batch):
        return digest({k: v for k, v in batch.items() if k != 'preview_sha256'})

    def preview(self, batch):
        size_check(batch)
        batch = decode(Batch, batch)
        with self.repo.transaction(False) as conn:
            receipt = conn.execute('SELECT * FROM production_operations WHERE id=?', (batch['operation_id'],)).fetchone()
            if receipt:
                if receipt['request_sha256'] != self._request(batch):
                    raise Conflict('Idempotency key was already used for different changes.')
                return {**json.loads(receipt['result_json']), 'already_applied': True}
            heads, staged, changes, graph, result = self._stage(conn, batch)
            token = digest({'request': self._request(batch), 'result': result})
            affected = graph.affected([c['id'] for c in changes], exclude=[c['id'] for c in changes])
            return {**result, 'preview_sha256': token, 'valid': True, 'affected': affected,
                    'proposed_records': list(staged.values()), 'persisted': False}

    def apply(self, batch):
        size_check(batch)
        batch = decode(Batch, batch)
        request_hash = self._request(batch)
        with self.repo.transaction() as conn:
            receipt = conn.execute('SELECT * FROM production_operations WHERE id=?', (batch['operation_id'],)).fetchone()
            if receipt:
                if receipt['request_sha256'] != request_hash:
                    raise Conflict('Idempotency key was already used for different changes.')
                return {**json.loads(receipt['result_json']), 'replayed': True}
            heads, staged, changes, graph, result = self._stage(conn, batch)
            token = digest({'request': request_hash, 'result': result})
            if batch['preview_sha256'] and batch['preview_sha256'] != token:
                raise Conflict('Preview no longer matches this batch. Preview again without overwriting your draft.')
            stamp = now()
            for c in changes:
                h = heads[c['id']]
                conn.execute('''INSERT INTO production_records(id,kind,revision,head_version,selected_version,archived,created_at,updated_at)
                    VALUES(:id,:kind,:revision,:head_version,:selected_version,:archived,:created_at,:updated_at)
                    ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,head_version=excluded.head_version,
                    selected_version=excluded.selected_version,archived=excluded.archived,updated_at=excluded.updated_at''', h)
            for (rid, number), r in staged.items():
                conn.execute('INSERT INTO production_versions VALUES(?,?,?,?,?,?)',
                             (rid, number, r['parent_version'], dumps(r['data']), r['sha256'], r['version_created_at']))
                insert_external(conn, r)
                for path, ref in references(r['data']):
                    conn.execute('INSERT INTO production_refs VALUES(?,?,?,?,?)', (rid, number, path, ref['id'], ref['version']))
            for c in changes:
                conn.execute('INSERT INTO production_changes VALUES(?,?,?,?,?)',
                             (result['checkpoint'], c['id'], c['op'], c['previous_selected_version'], c['selected_version']))
            conn.execute('UPDATE production_clock SET checkpoint=? WHERE singleton=1', (result['checkpoint'],))
            conn.execute('INSERT INTO production_operations VALUES(?,?,?,?,?)',
                         (batch['operation_id'], request_hash, result['checkpoint'], dumps(result), stamp))
            self.repo.event(conn, 'production.batch', self.service.project.id,
                            {'checkpoint': result['checkpoint'], 'operation_id': batch['operation_id'], 'changes': changes})
            return {**result, 'replayed': False}

    def query(self, kind=None, text='', scene_id=None, script_block_id=None, include_proposals=False, limit=100, offset=0):
        from .models import MODELS
        self._page(limit, offset)
        if kind and kind not in MODELS:
            raise ProductionError('Unknown production kind.')
        if type(include_proposals) is not bool:
            raise ProductionError('include_proposals must be a boolean.')
        if not isinstance(text, str) or len(text) > 1000:
            raise ProductionError('Search text must be a string of at most 1,000 characters.')
        with self.repo.transaction(False) as conn:
            graph = self._graph(conn)
            rows = []
            for h in sorted(graph.heads.values(), key=lambda x: (x['kind'], x['id'])):
                if h['archived'] or kind and h['kind'] != kind or not include_proposals and not h['selected_version']:
                    continue
                r = graph.resolve(h['id'], h['selected_version'] or h['head_version'])
                p = r['data']
                if text.casefold() not in dumps(p).casefold():
                    continue
                if scene_id and p.get('scene', {}).get('id') != scene_id and r['id'] != scene_id:
                    continue
                if script_block_id:
                    direct = graph.fragments(p.get('fragments', []))
                    if p.get('action'):
                        a = graph.require(p['action'])
                        direct.update(bid for b in a['beats'] if b['id'] in p.get('beat_ids', []) for bid in b['block_ids'])
                    if script_block_id not in direct:
                        continue
                # A joined row follows exact dependencies, never current versions by accident.
                joins = {}
                for field in ('scene','sequence','location','action','lighting','shot','subject'):
                    value = p.get(field)
                    if isinstance(value, dict) and set(value) == {'id','version'}:
                        joined = graph.resolve(value['id'], value['version'])
                        joins[field] = {'id': joined['id'], 'version': joined['version'], 'title': joined['data']['title'], 'data': joined['data']}
                if p.get('cameras'):
                    joins['cameras'] = [graph.resolve(v['id'], v['version']) for v in p['cameras']]
                if p['kind'] == 'shot' and p['action']:
                    action = graph.require(p['action'])
                    joins['location'] = graph.resolve(action['location']['id'], action['location']['version'])
                    joins['beats'] = [b for b in action['beats'] if b['id'] in p['beat_ids']]
                    joins['script_fragments'] = p['fragments'] or graph.require(p['scene'])['fragments']
                rows.append({**r, 'joins': joins, 'stale_dependencies': graph.stale(ref_for(r))})
            items = rows[offset:offset+limit]
            return {'checkpoint': self._clock(conn), 'items': items, 'total': len(rows), 'limit': limit, 'offset': offset,
                    'next_offset': offset + len(items) if offset + len(items) < len(rows) else None}

    def impact(self, id):
        with self.repo.transaction(False) as conn:
            graph = self._graph(conn)
            if id not in graph.heads:
                raise NotFound('Production record does not exist.')
            return {'checkpoint': self._clock(conn), 'id': id, 'affected': graph.affected([id]),
                    'behavior': 'Exact pins stay intact. Review and explicitly repin affected records.'}

    def changes(self, since=0, limit=100, offset=0):
        self._page(limit, offset)
        if type(since) is not int or since < 0:
            raise ProductionError('Checkpoint must be a nonnegative integer.')
        with self.repo.transaction(False) as conn:
            total = conn.execute('SELECT count(*) FROM production_changes WHERE checkpoint>?', (since,)).fetchone()[0]
            rows = [dict(r) for r in conn.execute('SELECT * FROM production_changes WHERE checkpoint>? ORDER BY checkpoint,record_id LIMIT ? OFFSET ?', (since, limit, offset))]
            return {'checkpoint': self._clock(conn), 'items': rows, 'total': total, 'limit': limit, 'offset': offset,
                    'next_offset': offset + len(rows) if offset + len(rows) < total else None}

    def diff(self, id, from_version, to_version):
        from .scripts import compare_scripts
        if type(from_version) is not int or type(to_version) is not int or min(from_version,to_version)<1:
            raise ProductionError('Diff versions must be positive integers.')
        with self.repo.transaction(False) as conn:
            graph = self._graph(conn)
            a, b = graph.resolve(id, from_version), graph.resolve(id, to_version)
            changes = diff_values(a['data'], b['data'])
            result = {'id': id, 'from_version': from_version, 'to_version': to_version,
                      'from_sha256': a['sha256'], 'to_sha256': b['sha256'], 'changes': changes}
            if a['kind'] == 'script':
                result['script_changes'] = compare_scripts(a['data'], b['data'])
            return result

    def reconcile(self, replacements, ids, operation_id, expected_checkpoint, select=False):
        """Preview transitive pin changes only within explicitly chosen IDs.

        Content and blocking are not artistically revised by this operation. Exact
        reviews/exceptions may NOT be auto-repinned: they belong to the old work.
        """
        from .models import Ref, decode
        if not isinstance(replacements,list) or not 1<=len(replacements)<=100 or not isinstance(ids,list) or not 1<=len(ids)<=MAX_OPERATIONS or type(select) is not bool:
            raise ProductionError('Choose 1–100 exact replacement pairs, 1–500 record IDs, and a boolean selection policy.')
        if any(not isinstance(rid,str) for rid in ids) or len(set(ids))!=len(ids):
            raise ProductionError('Reconciliation IDs must be distinct strings.')
        mapping={}
        for pair in replacements:
            if not isinstance(pair,dict) or set(pair)!={'from','to'}:
                raise ProductionError('Each replacement needs exact from and to references.')
            old,new=decode(Ref,pair['from']),decode(Ref,pair['to'])
            if old['id']!=new['id'] or old==new or (old['id'],old['version']) in mapping:
                raise ProductionError('Replacement pins must change version on one stable ID and have unique sources.')
            mapping[old['id'],old['version']]=new
        with self.repo.transaction(False) as conn:
            if self._clock(conn)!=expected_checkpoint:
                raise Conflict('Production checkpoint changed before reconciliation.')
            graph=self._graph(conn)
            chosen=[]; excluded=[]
            for rid in ids:
                h=graph.heads.get(rid)
                if h is None or h['archived']:
                    raise NotFound('Reconciliation record is absent or archived.',{'id':rid})
                r=graph.resolve(rid,h['selected_version'] or h['head_version'])
                if r['kind'] in ('review','exception'):
                    excluded.append({'id':rid,'reason':'Review/exception acceptance stays pinned to the exact old work.'})
                else:
                    chosen.append(r)
            def replace(value):
                if isinstance(value,dict):
                    if set(value)=={'id','version'} and isinstance(value['id'],str) and type(value['version']) is int:
                        return copy.deepcopy(mapping.get((value['id'],value['version']),value))
                    return {k:replace(v) for k,v in value.items()}
                if isinstance(value,list):
                    return [replace(v) for v in value]
                return value
            changed=set()
            for _ in range(len(chosen)+1):
                before=len(changed)
                for r in chosen:
                    if replace(r['data'])!=r['data']:
                        changed.add(r['id'])
                        mapping[r['id'],r['version']]={'id':r['id'],'version':r['head_version']+1}
                if before==len(changed):
                    break
            ops=[{'op':'put','id':r['id'],'expected_revision':r['revision'],'base_version':r['version'],
                  'select':select,'data':replace(r['data'])} for r in chosen if r['id'] in changed]
            if not ops:
                return {'batch':None,'changed':False,'excluded':excluded,'message':'No matching pins in the chosen records.'}
            batch={'expected_checkpoint':expected_checkpoint,'operation_id':operation_id,'operations':ops}
        return {'batch':batch,'preview':self.preview(batch),'excluded':excluded,
                'behavior':'Only exact pins changed. Review the retained content and revise any action, timing or creative intent before accepting it.'}


def diff_values(a, b, path=''):
    if a == b:
        return []
    if isinstance(a,dict) and isinstance(b,dict):
        out = []
        for k in sorted(a.keys() | b.keys()):
            p = path+'/'+k
            if k not in a:
                out.append({'path':p,'change':'added','after':b[k]})
            elif k not in b:
                out.append({'path':p,'change':'removed','before':a[k]})
            else:
                out.extend(diff_values(a[k],b[k],p))
        return out
    return [{'path':path or '/', 'change':'changed','before':a,'after':b}]
