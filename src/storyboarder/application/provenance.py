"""Explicit source lineage plus read-only projections of canonical relations.

Direction is consistently input -> output. Contextual correspondences are not
traversed as dependencies by impact analysis. Missing links never prove missing
footage or missing creative work.
"""
from __future__ import annotations

from collections import deque
import json

from storyboarder.domain.documents import content_hash
from storyboarder.domain.errors import StoryboardError, NotFound
from storyboarder.domain.models import uid, now, text, dumps
from .documents import Documents, page_bounds, page

TYPES = ('node', 'entity', 'frame', 'media', 'job', 'version', 'artifact')
RELATIONS = ('visualizes', 'appears-in', 'uses-reference', 'derived-from', 'corresponds-to')


def unpack(row):
    result = dict(row)
    for field in ('source_snapshot', 'target_snapshot', 'snapshot'):
        if field in result:
            result[field] = json.loads(result[field])
    return result


class Provenance:
    def __init__(self, service):
        self.service, self.repo = service, service.repo
        self.documents = Documents(service)

    def _endpoint(self, conn, kind, record_id):
        if kind not in TYPES:
            raise StoryboardError('Unsupported provenance endpoint type.')
        if kind in ('entity', 'frame', 'media', 'job'):
            table = {'entity': 'entities', 'frame': 'frames', 'media': 'media', 'job': 'jobs'}[kind]
            row = self.repo.get(conn, table, record_id)
            if kind == 'job':
                row = {k: row[k] for k in ('id', 'title', 'revision', 'status', 'target', 'shot_id', 'attempt', 'approved')}
            elif kind == 'frame':
                shot = self.repo.get(conn, 'entities', row['shot_id'])
                row['title'] = f"{shot['title']} · frame {row['version']}"
                # Frames have their own archived lifecycle state, and inherit
                # archive status from their parent shot for new-link checks.
                row['archived'] = bool(row['state'] == 'archived' or shot['archived'])
            elif kind == 'media':
                row['title'] = row['original_name']
        elif kind == 'node':
            node = Documents._one(conn, 'document_nodes', record_id)
            version = Documents._one(conn, 'document_versions', node['version_id'])
            document = Documents._one(conn, 'documents', version['document_id'])
            row = {k: v for k, v in node.items() if k not in ('payload', 'text')}
            row.update(document_id=document['id'], document_kind=document['kind'], version_label=version['label'], is_current=document['current_version_id'] == node['version_id'], archived=bool(document['archived']))
        elif kind == 'version':
            row = Documents._one(conn, 'document_versions', record_id)
            document = Documents._one(conn, 'documents', row['document_id'])
            row['title'] = f"{document['title']} · {row['label']}"
            # Versions and their nodes are immutable and inherit archive state
            # from the owning document.
            row['archived'] = bool(document['archived'])
            row.pop('warnings', None)
        else:
            row = Documents._one(conn, 'source_artifacts', record_id)
            row['title'] = row['original_name']
        return {**row, 'type': kind, 'key': f'{kind}:{record_id}', 'label': row.get('title', kind.title())}

    def endpoint(self, kind, record_id):
        with self.repo.transaction(False) as conn:
            return self._endpoint(conn, kind, record_id)

    @staticmethod
    def _semantics(source, target, relation):
        if relation not in RELATIONS:
            raise StoryboardError('Choose a supported provenance relationship.')
        if relation == 'visualizes':
            if not (source['type'] == 'node' and source.get('document_kind') == 'screenplay' and source.get('node_type') != 'screenplay' and target['type'] == 'entity' and target.get('kind') in ('scene', 'shot')):
                raise StoryboardError('Visualizes connects a screenplay scene or element to a storyboard scene or shot.')
        elif relation == 'appears-in':
            if not ((source['type'] == 'frame' or source['type'] == 'entity' and source.get('kind') == 'shot') and target['type'] == 'node' and target.get('document_kind') == 'edit' and target.get('node_type') == 'Clip'):
                raise StoryboardError('Appears-in connects a storyboard shot or frame to an editorial clip.')
        elif relation == 'uses-reference':
            if not ((source['type'] == 'media' or source['type'] == 'entity' and source.get('kind') == 'asset') and target['type'] == 'entity' and target.get('kind') in ('scene', 'shot')):
                raise StoryboardError('Uses-reference connects a media file or library asset to a storyboard scene or shot.')
        if source['key'] == target['key']:
            raise StoryboardError('An item cannot be its own source.')
        if source.get('archived') or target.get('archived'):
            raise StoryboardError('Restore archived items before making new provenance links.')

    def link(self, source_type, source_id, target_type, target_id, relation='corresponds-to', notes=''):
        notes = text(notes, max_length=10000)
        with self.repo.transaction() as conn:
            source, target = self._endpoint(conn, source_type, source_id), self._endpoint(conn, target_type, target_id)
            self._semantics(source, target, relation)
            existing = conn.execute('SELECT * FROM provenance_edges WHERE source_type=? AND source_id=? AND target_type=? AND target_id=? AND relation=? AND retired=0', (source_type, source_id, target_type, target_id, relation)).fetchone()
            if existing:
                return unpack(existing)
            if relation != 'corresponds-to':
                # Include canonical assignments, jobs and frames, not only authored links.
                pending, visited = [(target_type, target_id)], set()
                while pending:
                    endpoint = pending.pop()
                    if endpoint == (source_type, source_id):
                        raise StoryboardError('This source link would create a derivation cycle.')
                    if endpoint in visited:
                        continue
                    visited.add(endpoint)
                    if len(visited) > 2000:
                        raise StoryboardError('This lineage is too large to verify safely in one edit. Narrow the relationship scope.')
                    for edge in self._neighbors(conn, *endpoint, maximum=2000):
                        if edge['dependency'] and (edge['source_type'], edge['source_id']) == endpoint:
                            pending.append((edge['target_type'], edge['target_id']))
            row = {'id': uid(), 'source_type': source_type, 'source_id': source_id, 'target_type': target_type, 'target_id': target_id,
                   'relation': relation, 'source_snapshot': dumps(source), 'target_snapshot': dumps(target), 'notes': notes,
                   'retired': 0, 'revision': 1, 'created_at': now()}
            conn.execute('INSERT INTO provenance_edges VALUES(:id,:source_type,:source_id,:target_type,:target_id,:relation,:source_snapshot,:target_snapshot,:notes,:retired,:revision,:created_at)', row)
            self.repo.event(conn, 'provenance.linked', row['id'], {'source': source['key'], 'target': target['key'], 'relation': relation})
            return unpack(row)

    def show(self, edge_id):
        with self.repo.transaction(False) as conn:
            row = conn.execute('SELECT * FROM provenance_edges WHERE id=?', (edge_id,)).fetchone()
            if row is None:
                raise NotFound('This provenance link is not in the project.')
            return unpack(row)

    def retire(self, edge_id, revision):
        with self.repo.transaction() as conn:
            row = conn.execute('SELECT * FROM provenance_edges WHERE id=?', (edge_id,)).fetchone()
            if row is None:
                raise NotFound('This provenance link is not in the project.')
            self.repo.check(row, revision)
            conn.execute('UPDATE provenance_edges SET retired=1,revision=revision+1 WHERE id=?', (edge_id,))
            self.repo.event(conn, 'provenance.retired', edge_id)
            return unpack(conn.execute('SELECT * FROM provenance_edges WHERE id=?', (edge_id,)).fetchone())

    @staticmethod
    def _edge(prefix, key, source_type, source_id, target_type, target_id, label, dependency=True, **extra):
        return {'id': f'{prefix}:{key}', 'source': f'{source_type}:{source_id}', 'target': f'{target_type}:{target_id}',
                'source_type': source_type, 'source_id': source_id, 'target_type': target_type, 'target_id': target_id,
                'relation': label, 'derived': True, 'dependency': dependency, **extra}

    def _neighbors(self, conn, kind, record_id, maximum=500):
        rows = conn.execute('SELECT * FROM provenance_edges WHERE retired=0 AND ((source_type=? AND source_id=?) OR (target_type=? AND target_id=?)) ORDER BY id LIMIT ?', (kind, record_id, kind, record_id, maximum + 1)).fetchall()
        edges = [{**unpack(row), 'source': f"{row['source_type']}:{row['source_id']}", 'target': f"{row['target_type']}:{row['target_id']}", 'derived': False, 'dependency': row['relation'] != 'corresponds-to'} for row in rows]
        def add(*args, **kwargs):
            edges.append(self._edge(*args, **kwargs))
        if kind in ('entity', 'media'):
            condition = '(shot_id=? OR asset_id=?)' if kind == 'entity' else 'media_id=?'
            params = (record_id, record_id) if kind == 'entity' else (record_id,)
            for row in conn.execute('SELECT * FROM assignments WHERE ' + condition + ' LIMIT ?', (*params, maximum + 1)):
                add('assignment', row['id'], 'entity', row['asset_id'], 'entity', row['shot_id'], 'reference-assignment')
                if row['media_id']:
                    add('exact-media', row['id'], 'media', row['media_id'], 'entity', row['shot_id'], 'exact-reference-image')
        if kind in ('entity', 'media', 'frame'):
            column = {'entity': 'shot_id', 'media': 'media_id', 'frame': 'id'}[kind]
            for row in conn.execute(f'SELECT * FROM frames WHERE {column}=? LIMIT ?', (record_id, maximum + 1)):
                add('frame', row['id'], 'entity', row['shot_id'], 'frame', row['id'], 'frame-candidate')
                add('frame-image', row['id'], 'media', row['media_id'], 'frame', row['id'], 'image-bytes')
        if kind in ('job', 'frame', 'entity', 'media'):
            column = {'job': 'job_id', 'frame': 'frame_id', 'entity': 'entity_id', 'media': 'media_id'}[kind]
            for row in conn.execute(f'SELECT * FROM job_outputs WHERE {column}=? LIMIT ?', (record_id, maximum + 1)):
                target_type = 'frame' if row['frame_id'] else 'entity'
                target = row['frame_id'] or row['entity_id']
                if target:
                    add('generated', row['job_id'] + ':' + row['output_key'], 'job', row['job_id'], target_type, target, 'generated-output')
            if kind == 'entity':
                for row in conn.execute('SELECT id FROM jobs WHERE shot_id=? LIMIT ?', (record_id, maximum + 1)):
                    add('job-target', row['id'], 'entity', record_id, 'job', row['id'], 'generation-target')
            if kind == 'job':
                job = self.repo.get(conn, 'jobs', record_id)
                if job['shot_id']:
                    add('job-target', record_id, 'entity', job['shot_id'], 'job', record_id, 'generation-target')
                for media in job['request'].get('references', [])[:maximum]:
                    add('job-reference', record_id + ':' + media['id'], 'media', media['id'], 'job', record_id, 'pinned-image-input', sha256=media['sha256'])
        if kind == 'media':
            for pin in conn.execute('SELECT job_id,sha256 FROM job_media_pins WHERE media_id=? LIMIT ?', (record_id, maximum + 1)):
                add('job-media', pin['job_id'] + ':' + record_id, 'media', record_id, 'job', pin['job_id'], 'generation-reference', pinned_sha256=pin['sha256'])
        if kind in ('node', 'job'):
            column = 'node_id' if kind == 'node' else 'job_id'
            for row in conn.execute(f'SELECT * FROM job_source_pins WHERE {column}=? LIMIT ?', (record_id, maximum + 1)):
                add('job-source', row['job_id'] + ':' + row['node_id'], 'node', row['node_id'], 'job', row['job_id'], 'pinned-screenplay-input')
        if kind == 'node':
            node = Documents._one(conn, 'document_nodes', record_id)
            add('version-node', record_id, 'version', node['version_id'], 'node', record_id, 'source-version')
        elif kind == 'version':
            version = Documents._one(conn, 'document_versions', record_id)
            add('version-source', record_id, 'artifact', version['source_artifact_id'], 'version', record_id, 'imported-from')
            for row in conn.execute('SELECT id FROM document_nodes WHERE version_id=? ORDER BY source_pointer LIMIT ?', (record_id, maximum + 1)):
                add('version-node', row['id'], 'version', record_id, 'node', row['id'], 'source-version')
        elif kind == 'artifact':
            for row in conn.execute('SELECT id FROM document_versions WHERE source_artifact_id=? LIMIT ?', (record_id, maximum + 1)):
                add('version-source', row['id'], 'artifact', record_id, 'version', row['id'], 'imported-from')
        key = f'{kind}:{record_id}'
        return [edge for edge in edges if key in (edge['source'], edge['target'])]

    def trace(self, endpoint_type, endpoint_id, direction='upstream', max_depth=8, limit=200, lineage_only=False):
        if direction not in ('upstream', 'downstream', 'both'):
            raise StoryboardError('Choose upstream, downstream or both directions.')
        if isinstance(max_depth, bool) or not isinstance(max_depth, int) or not 1 <= max_depth <= 20:
            raise StoryboardError('Trace depth must be from 1 to 20.')
        page_bounds(limit, 0)
        limit = min(limit, 500)
        with self.repo.transaction(False) as conn:
            first = self._endpoint(conn, endpoint_type, endpoint_id)
            nodes, edges = {first['key']: first}, {}
            queue = deque([(endpoint_type, endpoint_id, 0)])
            visited = set()
            truncated = False
            while queue:
                kind, record_id, depth = queue.popleft()
                key = f'{kind}:{record_id}'
                if key in visited:
                    continue
                visited.add(key)
                neighbors = self._neighbors(conn, kind, record_id, limit)
                for edge in neighbors:
                    if lineage_only and not edge['dependency']:
                        continue
                    if direction == 'upstream' and edge['target'] != key or direction == 'downstream' and edge['source'] != key:
                        continue
                    if depth >= max_depth:
                        truncated = True
                        continue
                    other_key = edge['source'] if edge['target'] == key else edge['target']
                    other_kind, other_id = other_key.split(':', 1)
                    if other_key not in nodes:
                        if len(nodes) >= limit:
                            truncated = True
                            continue
                        nodes[other_key] = self._endpoint(conn, other_kind, other_id)
                        queue.append((other_kind, other_id, depth + 1))
                    edges[edge['id']] = edge
            return {'root': first['key'], 'direction': direction, 'nodes': list(nodes.values()), 'edges': list(edges.values()),
                    'truncated': truncated, 'limit': limit, 'max_depth': max_depth}

    def sources(self, entity_id):
        with self.repo.transaction(False) as conn:
            entity = self.service.entity(conn, entity_id, active=False)
            targets = [entity_id]
            if entity['kind'] == 'shot' and entity['parent_id']:
                targets.append(entity['parent_id'])
            marks = ','.join('?' for _ in targets)
            rows = conn.execute(f'''SELECT e.id AS edge_id,e.target_id,n.id AS node_id,n.version_id,n.logical_id,n.node_type,n.title,n.content_sha256,
                v.document_id,v.label AS version_label,d.current_version_id FROM provenance_edges e
                JOIN document_nodes n ON e.source_type='node' AND e.source_id=n.id
                JOIN document_versions v ON n.version_id=v.id JOIN documents d ON d.id=v.document_id
                WHERE e.retired=0 AND e.relation='visualizes' AND e.target_type='entity' AND e.target_id IN ({marks}) ORDER BY e.id''', targets).fetchall()
            return {'items': [{**dict(row), 'stale': row['version_id'] != row['current_version_id'], 'inherited': row['target_id'] != entity_id} for row in rows]}

    def pins(self, entity_id):
        result = []
        for source in self.sources(entity_id)['items']:
            node = self.documents.node(source['node_id'])
            with self.repo.transaction(False) as conn:
                rows = conn.execute('''WITH RECURSIVE subtree(id) AS (SELECT ? UNION ALL SELECT n.id FROM document_nodes n JOIN subtree s ON n.parent_id=s.id)
                                       SELECT n.logical_id,n.node_type,n.position,n.text,n.content_sha256 FROM subtree s JOIN document_nodes n ON n.id=s.id ORDER BY n.source_pointer''', (node['id'],)).fetchall()
            content = [dict(row) for row in rows]
            result.append({**source, 'node': {k: node[k] for k in ('id', 'logical_id', 'node_type', 'title', 'payload')}, 'content': content, 'scope_sha256': content_hash(content)})
        return result

    def impact(self, before_version, after_version, limit=300):
        difference = self.documents.diff(before_version, after_version)
        changed = [entry['before']['id'] for entry in difference['changed'] + difference['moved']] + [entry['id'] for entry in difference['removed']]
        affected, reasons = {}, {}
        roots = set(changed)
        # A link to a whole screenplay scene is an explicit scope link. Changes
        # inside that scope require review without turning every tree edge into a dependency.
        with self.repo.transaction(False) as conn:
            for record_id in changed:
                parent = Documents._one(conn, 'document_nodes', record_id).get('parent_id')
                while parent:
                    row = Documents._one(conn, 'document_nodes', parent)
                    if row['node_type'] == 'scene': roots.add(parent)
                    parent = row['parent_id']
        truncated = False
        for source in sorted(roots):
            traced = self.trace('node', source, 'downstream', limit=limit, lineage_only=True)
            truncated |= traced['truncated']
            for node in traced['nodes']:
                if node['key'] == f'node:{source}': continue
                if node['key'] not in affected and len(affected) >= limit:
                    truncated = True; continue
                affected[node['key']] = node
                reasons.setdefault(node['key'], []).append(source)
        return {'before_version_id': before_version, 'after_version_id': after_version, 'changed_sources': changed,
                'affected': list(affected.values()), 'reasons': reasons, 'truncated': truncated,
                'method': 'Potential review impact through explicit derivation and source-scope links; no automatic rewrite or approval revocation.'}

    def coverage(self, limit=100):
        page_bounds(limit, 0)
        reports = {}
        queries = {
            'screenplay_unlinked': '''SELECT n.id,n.title,n.node_type,v.document_id,n.version_id FROM document_nodes n JOIN document_versions v ON v.id=n.version_id JOIN documents d ON d.current_version_id=v.id
                WHERE d.archived=0 AND d.kind='screenplay' AND n.node_type IN ('action','dialogue')
                AND NOT EXISTS(SELECT 1 FROM provenance_edges e JOIN entities target ON target.id=e.target_id AND e.target_type='entity' AND target.archived=0
                    WHERE e.retired=0 AND e.relation='visualizes' AND e.source_type='node' AND (e.source_id=n.id OR e.source_id=n.parent_id))''',
            'edit_unlinked': '''SELECT n.id,n.title,n.node_type,v.document_id,n.version_id FROM document_nodes n JOIN document_versions v ON v.id=n.version_id JOIN documents d ON d.current_version_id=v.id
                WHERE d.archived=0 AND d.kind='edit' AND n.node_type='Clip' AND NOT EXISTS(SELECT 1 FROM provenance_edges e WHERE e.retired=0 AND e.relation='appears-in' AND e.target_type='node' AND e.target_id=n.id)''',
            'shots_without_sources': '''SELECT n.id,n.title,n.kind FROM entities n WHERE n.kind='shot' AND n.archived=0 AND NOT EXISTS(SELECT 1 FROM provenance_edges e WHERE e.retired=0 AND e.relation='visualizes' AND e.target_type='entity' AND (e.target_id=n.id OR e.target_id=n.parent_id))''',
            'shots_without_approved_frames': "SELECT n.id,n.title,n.kind FROM entities n WHERE n.kind='shot' AND n.archived=0 AND NOT EXISTS(SELECT 1 FROM frames f WHERE f.shot_id=n.id AND f.state='approved')",
            'approved_frames_without_edit_links': '''SELECT f.id,n.title,f.version,f.shot_id FROM frames f JOIN entities n ON n.id=f.shot_id WHERE f.state='approved' AND n.archived=0 AND NOT EXISTS(
                SELECT 1 FROM provenance_edges e JOIN document_nodes clip ON clip.id=e.target_id AND e.target_type='node' JOIN document_versions v ON v.id=clip.version_id JOIN documents d ON d.current_version_id=v.id
                WHERE e.retired=0 AND e.relation='appears-in' AND e.source_type='frame' AND e.source_id=f.id AND d.archived=0)''',
            'older_source_links': '''SELECT e.id,n.title,n.version_id,v.document_id,e.target_type,e.target_id FROM provenance_edges e JOIN document_nodes n ON e.source_type='node' AND n.id=e.source_id JOIN document_versions v ON v.id=n.version_id JOIN documents d ON d.id=v.document_id
                WHERE e.retired=0 AND e.relation='visualizes' AND n.version_id<>d.current_version_id''',
        }
        with self.repo.transaction(False) as conn:
            for name, query in queries.items():
                count = conn.execute('SELECT count(*) FROM (' + query + ')').fetchone()[0]
                rows = conn.execute(query + ' LIMIT ?', (limit,)).fetchall()
                reports[name] = page(rows, count, limit, 0)
        return {'counts': {key: value['total'] for key, value in reports.items()}, 'reports': reports,
                'method': 'Based on explicit source and clip links plus saved frame approvals. Missing links do not prove missing footage. Links to older source versions are retained and flagged for review.'}

    def annotate(self, endpoint_type, endpoint_id, content):
        value = text(content, 'Annotation', 10000)
        if not value: raise StoryboardError('Write a note before saving it.')
        with self.repo.transaction() as conn:
            endpoint = self._endpoint(conn, endpoint_type, endpoint_id)
            row = {'id': uid(), 'endpoint_type': endpoint_type, 'endpoint_id': endpoint_id, 'snapshot': dumps(endpoint),
                   'text': value, 'state': 'open', 'revision': 1, 'created_at': now(), 'updated_at': now()}
            conn.execute('INSERT INTO annotations VALUES(:id,:endpoint_type,:endpoint_id,:snapshot,:text,:state,:revision,:created_at,:updated_at)', row)
            conn.execute('INSERT INTO annotation_revisions VALUES(?,?,?,?,?)', (row['id'], 1, value, 'open', row['created_at']))
            self.repo.event(conn, 'annotation.created', row['id'])
            return unpack(row)

    def update_annotation(self, annotation_id, revision, content, state='open'):
        value = text(content, 'Annotation', 10000)
        if not value or state not in ('open', 'resolved'):
            raise StoryboardError('Use a nonempty note and an open or resolved state.')
        with self.repo.transaction() as conn:
            row = conn.execute('SELECT * FROM annotations WHERE id=?', (annotation_id,)).fetchone()
            if row is None: raise NotFound('The annotation is not in this project.')
            self.repo.check(row, revision)
            stamp = now()
            conn.execute('UPDATE annotations SET text=?,state=?,revision=revision+1,updated_at=? WHERE id=?', (value, state, stamp, annotation_id))
            conn.execute('INSERT INTO annotation_revisions VALUES(?,?,?,?,?)', (annotation_id, revision + 1, value, state, stamp))
            self.repo.event(conn, 'annotation.updated', annotation_id)
            return unpack(conn.execute('SELECT * FROM annotations WHERE id=?', (annotation_id,)).fetchone())

    def annotations(self, endpoint_type, endpoint_id, limit=100, offset=0):
        page_bounds(limit, offset)
        with self.repo.transaction(False) as conn:
            self._endpoint(conn, endpoint_type, endpoint_id)
            total = conn.execute('SELECT count(*) FROM annotations WHERE endpoint_type=? AND endpoint_id=?', (endpoint_type, endpoint_id)).fetchone()[0]
            rows = conn.execute('SELECT * FROM annotations WHERE endpoint_type=? AND endpoint_id=? ORDER BY updated_at DESC,id LIMIT ? OFFSET ?', (endpoint_type, endpoint_id, limit, offset)).fetchall()
            return page([unpack(row) for row in rows], total, limit, offset)
