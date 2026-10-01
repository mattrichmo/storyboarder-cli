"""Document workflow orchestration shared by the three interfaces."""
from pathlib import Path
import tempfile
import shutil

from storyboarder.domain.errors import StoryboardError
from storyboarder.domain.documents import MAX_DOCUMENT_BYTES, content_hash
from storyboarder.domain.models import dumps, now
from storyboarder.formats import parse
from storyboarder.media.files import safe_path, sha256
from storyboarder.rendering.exports import json_file, commit_export
from .documents import Documents


class SourceWorkflows:
    def __init__(self, service):
        self.service = service
        self.documents = Documents(service)

    def import_file(self, path, format, document_id=None, revision=None, label='Imported draft', dry_run=False):
        source = Path(path).expanduser()
        if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_DOCUMENT_BYTES:
            raise StoryboardError('Choose a regular source document no larger than 20 MiB.')
        with source.open('rb') as stream:
            raw = stream.read(MAX_DOCUMENT_BYTES + 1)
        if dry_run:
            parsed = parse(raw, format)
            return {'dry_run': True, 'valid': True, 'kind': parsed.kind, 'title': parsed.title,
                    'nodes': len(parsed.nodes), 'content_sha256': content_hash(parsed.payload), 'warnings': parsed.warnings}
        return self.documents.import_bytes(raw, source.name, format, document_id, revision, label)

    def tree(self, document_id, version_id=None, limit=1000, offset=0, query=''):
        document = self.documents.show(document_id)
        version_id = version_id or document['current_version_id']
        if self.documents.version(version_id)['document_id'] != document_id:
            raise StoryboardError('The selected draft belongs to another document.')
        return self.documents.tree(version_id, limit=limit, offset=offset, query=query)

    def validate(self, document_id, version_id=None):
        document = self.documents.show(document_id)
        version = self.documents.version(version_id or document['current_version_id'])
        if version['document_id'] != document_id:
            raise StoryboardError('The selected draft belongs to another document.')
        parsed = parse(self.documents.source_bytes(version['id']), document['format'])
        return {'valid': True, 'document_id': document_id, 'version_id': version['id'], 'format': document['format'],
                'node_count': len(parsed.nodes), 'content_sha256': content_hash(parsed.payload), 'warnings': parsed.warnings}

    def archive(self, document_id, revision, archived=True):
        with self.service.repo.transaction() as conn:
            document = Documents._one(conn, 'documents', document_id)
            self.service.repo.check(document, revision)
            conn.execute('UPDATE documents SET archived=?,revision=revision+1,updated_at=? WHERE id=?', (int(archived), now(), document_id))
            self.service.repo.event(conn, 'document.archived' if archived else 'document.restored', document_id)
            return Documents._one(conn, 'documents', document_id)

    def export(self, document_id, version_id=None, include_identities=False):
        document = self.documents.show(document_id)
        version = self.documents.version(version_id or document['current_version_id'])
        if version['document_id'] != document_id:
            raise StoryboardError('The selected draft belongs to another document.')
        payload = self.documents.export_payload(version['id'], include_identities)
        digest = content_hash({'version': version['id'], 'payload': payload})[:16]
        relative = f'exports/documents/{document_id[:8]}-{version["number"]}-{digest}'
        destination = safe_path(self.service.root, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        staged = Path(tempfile.mkdtemp(prefix='.document-', dir=destination.parent))
        try:
            extension = 'screenjson' if document['format'] == 'screenjson' else 'otio'
            json_file(staged / f'document.{extension}', payload)
            (staged / 'original.json').write_bytes(self.documents.source_bytes(version['id']))
            json_file(staged / 'version.json', {'document_id': document_id, 'version': version,
                'identity_metadata_added': bool(include_identities), 'media_files_included': False})
            manifest = {'schema': 'storyboarder.document-export/v1', 'document_id': document_id,
                        'version_id': version['id'], 'source_sha256': version['source']['sha256'],
                        'content_sha256': version['content_sha256'], 'files': [
                            {'path': f.name, 'size': f.stat().st_size, 'sha256': sha256(f)} for f in sorted(staged.iterdir())]}
            json_file(staged / 'manifest.json', manifest)
            commit_export(staged, destination, safe_path(self.service.root, relative + '.zip'))
            return {'path': relative, 'archive': relative + '.zip', 'manifest': manifest,
                    'files': [relative + f'/document.{extension}', relative + '/version.json', relative + '.zip']}
        finally:
            if staged.exists():
                shutil.rmtree(staged)
