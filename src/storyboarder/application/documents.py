"""Immutable source documents, bounded tree queries, revisions and interchange."""
from __future__ import annotations

import copy
import difflib
import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid

from storyboarder.domain.documents import content_hash, decode_document, pointer_get
from storyboarder.domain.errors import StoryboardError, Conflict, NotFound
from storyboarder.domain.models import uid, now, title, text, dumps
from storyboarder.formats import parse
from storyboarder.media.files import safe_path, safe_name, sha256

SUMMARY_COLUMNS = 'n.id,n.version_id,n.logical_id,n.parent_id,n.node_type,n.position,n.title,substr(n.text,1,500) AS text,n.source_pointer,n.content_sha256,n.identity'


def page_bounds(limit, offset):
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise StoryboardError('Page size must be an integer from 1 to 1,000.')
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise StoryboardError('Page offset must be a nonnegative integer.')
    return limit, offset


def page(rows, total, limit, offset):
    return {'items': [dict(row) for row in rows], 'total': total, 'limit': limit, 'offset': offset,
            'next_offset': offset + len(rows) if offset + len(rows) < total else None,
            'truncated': offset + len(rows) < total}


class Documents:
    def __init__(self, service):
        self.service, self.repo, self.root = service, service.repo, service.root

    @staticmethod
    def _one(conn, table, record_id):
        if table not in ('documents', 'document_versions', 'document_nodes', 'source_artifacts'):
            raise ValueError('Unsupported document table')
        row = conn.execute(f'SELECT * FROM {table} WHERE id=?', (record_id,)).fetchone()
        if row is None:
            raise NotFound(f'Document record {record_id} is not in this project.')
        result = dict(row)
        for key in ('payload', 'warnings'):
            if key in result:
                result[key] = json.loads(result[key])
        return result

    def list(self, kind=None, query='', archived=False, limit=100, offset=0):
        page_bounds(limit, offset)
        if kind is not None and kind not in ('screenplay', 'edit'):
            raise StoryboardError('Choose screenplay or edit documents.')
        conditions, args = ['1=1' if archived else 'd.archived=0'], []
        if kind:
            conditions.append('d.kind=?'); args.append(kind)
        if query:
            conditions.append("d.title LIKE ? ESCAPE '\\'")
            args.append('%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%')
        where = ' AND '.join(conditions)
        with self.repo.transaction(False) as conn:
            total = conn.execute('SELECT count(*) FROM documents d WHERE ' + where, args).fetchone()[0]
            rows = conn.execute('SELECT d.*,v.number AS version_number,v.label AS version_label FROM documents d LEFT JOIN document_versions v ON d.current_version_id=v.id WHERE ' + where + ' ORDER BY d.updated_at DESC,d.id LIMIT ? OFFSET ?', (*args, limit, offset)).fetchall()
            return page(rows, total, limit, offset)

    def show(self, document_id):
        with self.repo.transaction(False) as conn:
            result = self._one(conn, 'documents', document_id)
            result['version_count'] = conn.execute('SELECT count(*) FROM document_versions WHERE document_id=?', (document_id,)).fetchone()[0]
            return result

    def version(self, version_id):
        with self.repo.transaction(False) as conn:
            result = self._one(conn, 'document_versions', version_id)
            result['source'] = self._one(conn, 'source_artifacts', result['source_artifact_id'])
            result['node_count'] = conn.execute('SELECT count(*) FROM document_nodes WHERE version_id=?', (version_id,)).fetchone()[0]
            return result

    def versions(self, document_id, limit=100, offset=0):
        page_bounds(limit, offset)
        with self.repo.transaction(False) as conn:
            self._one(conn, 'documents', document_id)
            total = conn.execute('SELECT count(*) FROM document_versions WHERE document_id=?', (document_id,)).fetchone()[0]
            rows = conn.execute('SELECT id,document_id,parent_version_id,number,label,format_version,content_sha256,created_at FROM document_versions WHERE document_id=? ORDER BY number DESC LIMIT ? OFFSET ?', (document_id, limit, offset)).fetchall()
            return page(rows, total, limit, offset)

    def node(self, node_id):
        with self.repo.transaction(False) as conn:
            result = self._one(conn, 'document_nodes', node_id)
            version = self._one(conn, 'document_versions', result['version_id'])
            document = self._one(conn, 'documents', version['document_id'])
            result['document_id'] = document['id']
            result['document_kind'] = document['kind']
            result['document_revision'] = document['revision']
            result['version_label'] = version['label']
            result['is_current'] = document['current_version_id'] == result['version_id']
            result['child_count'] = conn.execute('SELECT count(*) FROM document_nodes WHERE parent_id=?', (node_id,)).fetchone()[0]
            return result

    def children(self, version_id, parent_id=None, limit=100, offset=0):
        page_bounds(limit, offset)
        with self.repo.transaction(False) as conn:
            self._one(conn, 'document_versions', version_id)
            if parent_id and self._one(conn, 'document_nodes', parent_id)['version_id'] != version_id:
                raise StoryboardError('The selected parent belongs to another document version.')
            args = (version_id, parent_id)
            total = conn.execute('SELECT count(*) FROM document_nodes WHERE version_id=? AND parent_id IS ?', args).fetchone()[0]
            rows = conn.execute(f'SELECT {SUMMARY_COLUMNS},(SELECT count(*) FROM document_nodes c WHERE c.parent_id=n.id) AS child_count FROM document_nodes n WHERE n.version_id=? AND n.parent_id IS ? ORDER BY n.position,n.id LIMIT ? OFFSET ?', (*args, limit, offset)).fetchall()
            return page(rows, total, limit, offset)

    def tree(self, version_id, limit=1000, offset=0, query=''):
        page_bounds(limit, offset)
        with self.repo.transaction(False) as conn:
            self._one(conn, 'document_versions', version_id)
            if query:
                pattern = '%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
                condition = "n.version_id=? AND (n.title LIKE ? ESCAPE '\\' OR n.text LIKE ? ESCAPE '\\')"
                args = (version_id, pattern, pattern)
                total = conn.execute('SELECT count(*) FROM document_nodes n WHERE ' + condition, args).fetchone()[0]
                rows = conn.execute(f'SELECT {SUMMARY_COLUMNS},0 AS depth,(SELECT count(*) FROM document_nodes c WHERE c.parent_id=n.id) AS child_count FROM document_nodes n WHERE ' + condition + ' ORDER BY n.source_pointer LIMIT ? OFFSET ?', (*args, limit, offset)).fetchall()
            else:
                total = conn.execute('SELECT count(*) FROM document_nodes WHERE version_id=?', (version_id,)).fetchone()[0]
                rows = conn.execute(f'''WITH RECURSIVE tree(id,depth,ordering) AS (
                    SELECT id,0,printf('%09d',position) FROM document_nodes WHERE version_id=? AND parent_id IS NULL
                    UNION ALL SELECT n.id,t.depth+1,t.ordering||'/'||printf('%09d',n.position)
                    FROM document_nodes n JOIN tree t ON n.parent_id=t.id WHERE n.version_id=?)
                    SELECT {SUMMARY_COLUMNS},tree.depth,(SELECT count(*) FROM document_nodes c WHERE c.parent_id=n.id) AS child_count
                    FROM tree JOIN document_nodes n ON n.id=tree.id ORDER BY tree.ordering,n.id LIMIT ? OFFSET ?''', (version_id, version_id, limit, offset)).fetchall()
            return page(rows, total, limit, offset)

    def import_file(self, path, format='screenjson', document_id=None, revision=None, label='Imported draft'):
        path = Path(path).expanduser()
        if path.is_symlink() or not path.is_file():
            raise StoryboardError('Choose a regular screenplay or OTIO JSON file.')
        from storyboarder.domain.documents import MAX_DOCUMENT_BYTES
        if path.stat().st_size > MAX_DOCUMENT_BYTES:
            raise StoryboardError('Source documents may not exceed 20 MiB.')
        with path.open('rb') as handle:
            raw = handle.read(MAX_DOCUMENT_BYTES + 1)
        return self.import_bytes(raw, path.name, format, document_id, revision, label)

    def _artifact(self, conn, raw, filename):
        digest = hashlib.sha256(raw).hexdigest()
        found = conn.execute('SELECT * FROM source_artifacts WHERE sha256=?', (digest,)).fetchone()
        if found:
            source = dict(found)
            if sha256(safe_path(self.root, source['path'], must_exist=True)) != digest:
                raise StoryboardError('A managed document source was changed. Restore it before reusing it.')
            return source
        relative = f'sources/{digest}.json'
        destination = safe_path(self.root, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if sha256(destination) != digest:
                raise StoryboardError('An existing source path has different contents. Run project doctor.')
        else:
            fd, temporary = tempfile.mkstemp(prefix='.source-', dir=destination.parent)
            try:
                with os.fdopen(fd, 'wb') as handle:
                    handle.write(raw); handle.flush(); os.fsync(handle.fileno())
                os.replace(temporary, destination)
            finally:
                Path(temporary).unlink(missing_ok=True)
        source = {'id': uid(), 'path': relative, 'sha256': digest, 'original_name': safe_name(filename), 'size': len(raw), 'created_at': now()}
        conn.execute('INSERT INTO source_artifacts(id,path,sha256,original_name,size,created_at) VALUES(:id,:path,:sha256,:original_name,:size,:created_at)', source)
        return source

    def import_bytes(self, raw, filename, format='screenjson', document_id=None, revision=None, label='Imported draft'):
        parsed = parse(raw, format)
        label = title(label)
        checksum = content_hash(parsed.payload)
        with self.repo.transaction() as conn:
            document = self._one(conn, 'documents', document_id) if document_id else None
            if document is None and parsed.external_id:
                row = conn.execute('SELECT * FROM documents WHERE format=? AND external_id=?', (format, parsed.external_id)).fetchone()
                document = dict(row) if row else None
            if document:
                if document['archived'] or document['format'] != format:
                    raise StoryboardError('Restore this document and use its original interchange format.')
                if document['external_id'] and parsed.external_id != document['external_id']:
                    raise StoryboardError('This file has a different root identity. Import it as a separate document.')
                if revision is not None:
                    self.repo.check(document, revision)
                duplicate = conn.execute('SELECT id FROM document_versions WHERE document_id=? AND content_sha256=?', (document['id'], checksum)).fetchone()
                if duplicate:
                    version = self._one(conn, 'document_versions', duplicate[0])
                    artifact = self._artifact(conn, raw, filename)
                    conn.execute('INSERT OR IGNORE INTO document_imports VALUES(?,?,?)', (version['id'], artifact['id'], now()))
                    return {'document': document, 'version': version, 'unchanged': True, 'warnings': parsed.warnings}
                self.repo.check(document, revision)
            else:
                if document_id or revision is not None:
                    raise Conflict('The selected document is no longer available.')
                stamp = now()
                document = {'id': uid(), 'kind': parsed.kind, 'format': format, 'external_id': parsed.external_id,
                            'title': title(parsed.title), 'current_version_id': None, 'revision': 1,
                            'archived': 0, 'created_at': stamp, 'updated_at': stamp}
                conn.execute('INSERT INTO documents(id,kind,format,external_id,title,revision,created_at,updated_at) VALUES(:id,:kind,:format,:external_id,:title,:revision,:created_at,:updated_at)', document)
            artifact = self._artifact(conn, raw, filename)
            version_id = uid()
            number = conn.execute('SELECT coalesce(max(number),0)+1 FROM document_versions WHERE document_id=?', (document['id'],)).fetchone()[0]
            version = {'id': version_id, 'document_id': document['id'], 'parent_version_id': document['current_version_id'],
                       'number': number, 'label': label, 'format_version': parsed.format_version, 'content_sha256': checksum,
                       'source_artifact_id': artifact['id'], 'warnings': dumps(parsed.warnings), 'created_at': now()}
            conn.execute('INSERT INTO document_versions VALUES(:id,:document_id,:parent_version_id,:number,:label,:format_version,:content_sha256,:source_artifact_id,:warnings,:created_at)', version)
            node_ids = {node.logical_id: str(uuid.uuid5(uuid.UUID(version_id), node.logical_id)) for node in parsed.nodes}
            for node in parsed.nodes:
                conn.execute('INSERT INTO document_nodes VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', (
                    node_ids[node.logical_id], version_id, node.logical_id, node_ids.get(node.parent_logical_id), node.node_type,
                    node.position, node.title, node.text, node.pointer, dumps(node.payload), content_hash(node.payload), node.identity,
                ))
            conn.execute('INSERT INTO document_imports VALUES(?,?,?)', (version_id, artifact['id'], now()))
            conn.execute('UPDATE documents SET title=?,current_version_id=?,revision=revision+?,updated_at=? WHERE id=?',
                         (title(parsed.title), version_id, int(number > 1), now(), document['id']))
            self.repo.event(conn, 'document.version_created', document['id'], {'version_id': version_id, 'number': number, 'source_sha256': artifact['sha256']})
            return {'document': self._one(conn, 'documents', document['id']), 'version': self._one(conn, 'document_versions', version_id), 'unchanged': False, 'warnings': parsed.warnings}

    def source_bytes(self, version_id):
        version = self.version(version_id)
        source = version['source']
        path = safe_path(self.root, source['path'], must_exist=True)
        raw = path.read_bytes()
        if len(raw) != source['size'] or hashlib.sha256(raw).hexdigest() != source['sha256']:
            raise StoryboardError('The source document no longer matches its stored hash. Restore the original source.')
        return raw

    def export_payload(self, version_id, include_identities=False):
        version = self.version(version_id)
        payload = decode_document(self.source_bytes(version_id))
        if content_hash(payload) != version['content_sha256']:
            raise StoryboardError('Document content digest does not match the selected version.')
        if include_identities and self.show(version['document_id'])['format'] == 'otio':
            with self.repo.transaction(False) as conn:
                for row in conn.execute('SELECT logical_id,source_pointer FROM document_nodes WHERE version_id=?', (version_id,)):
                    pointer_get(payload, row['source_pointer']).setdefault('metadata', {}).setdefault('storyboarder', {})['id'] = row['logical_id']
        return payload

    def revise_node(self, node_id, changes, revision, label='Revised draft'):
        node = self.node(node_id)
        document = self.show(node['document_id'])
        self.repo.check(document, revision)
        if not node['is_current']:
            raise Conflict('This source belongs to an older draft. Open the current draft before editing.')
        if not isinstance(changes, dict) or not changes:
            raise StoryboardError('Provide a nonempty object of authored changes.')
        forbidden = {'id', 'scene', 'type', 'OTIO_SCHEMA', 'body', 'scenes', 'document', 'children', 'tracks'}
        if forbidden.intersection(changes):
            raise StoryboardError('Identity and tree structure require dedicated insert, move or remove operations.')
        if node['payload'].get('locked') and changes != {'locked': False}:
            raise StoryboardError('Unlock this screenplay element explicitly before editing it.')
        payload = self.export_payload(node['version_id'], include_identities=document['format'] == 'otio')
        target = pointer_get(payload, node['source_pointer'])
        target.update(copy.deepcopy(changes))
        return self.import_bytes((dumps(payload) + '\n').encode(), f'{document["title"]}.json', document['format'], document['id'], revision, label)

    def diff(self, before_id, after_id):
        before_version, after_version = self.version(before_id), self.version(after_id)
        if before_version['document_id'] != after_version['document_id']:
            raise StoryboardError('Compare two versions of the same document.')
        with self.repo.transaction(False) as conn:
            def records(version_id):
                rows = [dict(row) for row in conn.execute('SELECT * FROM document_nodes WHERE version_id=?', (version_id,))]
                by_id = {row['id']: row['logical_id'] for row in rows}
                return {row['logical_id']: {**row, 'payload': json.loads(row['payload']), 'parent_logical_id': by_id.get(row['parent_id'])} for row in rows}
            before, after = records(before_id), records(after_id)
        common = before.keys() & after.keys()
        changed, moved = [], []
        for logical in sorted(common):
            a, b = before[logical], after[logical]
            # Identity metadata is an export aid, not an editorial content change.
            def comparable(row):
                value = copy.deepcopy(row['payload'])
                if isinstance(value.get('metadata'), dict) and isinstance(value['metadata'].get('storyboarder'), dict):
                    value['metadata']['storyboarder'].pop('id', None)
                    if not value['metadata']['storyboarder']: value['metadata'].pop('storyboarder')
                return value
            aa, bb = comparable(a), comparable(b)
            if aa != bb:
                changed.append({'logical_id': logical, 'before': a, 'after': b, 'fields': sorted(k for k in aa.keys() | bb.keys() if aa.get(k) != bb.get(k))})
            if a['parent_logical_id'] != b['parent_logical_id']:
                moved.append({'logical_id': logical, 'before': a, 'after': b})
        for parent in {row['parent_logical_id'] for row in before.values()}:
            old = [key for key, row in sorted(before.items(), key=lambda pair: pair[1]['position']) if key in common and row['parent_logical_id'] == parent and after[key]['parent_logical_id'] == parent]
            new = [key for key, row in sorted(after.items(), key=lambda pair: pair[1]['position']) if key in common and row['parent_logical_id'] == parent and before[key]['parent_logical_id'] == parent]
            stable = set()
            for match in difflib.SequenceMatcher(a=old, b=new, autojunk=False).get_matching_blocks():
                stable.update(old[match.a:match.a + match.size])
            moved.extend({'logical_id': key, 'before': before[key], 'after': after[key]} for key in old if key not in stable)
        return {'before_version': before_version, 'after_version': after_version, 'changed': changed, 'moved': moved,
                'added': [after[key] for key in sorted(after.keys() - before.keys())],
                'removed': [before[key] for key in sorted(before.keys() - after.keys())],
                'identity_warning': any(row['identity'] != 'explicit' for row in [*before.values(), *after.values()])}
