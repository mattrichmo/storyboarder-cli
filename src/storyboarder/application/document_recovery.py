"""Document integrity checks shared by doctor and restore."""
from pathlib import Path
import sqlite3

from storyboarder.domain.errors import StoryboardError
from storyboarder.media.files import safe_path, sha256


def document_health(service, hashes=False):
    issues = []
    artifacts = []
    database_readable = False
    connection = None
    try:
        connection = sqlite3.connect(service.repo.path.resolve().as_uri() + '?mode=ro', uri=True)
        connection.row_factory = sqlite3.Row
        artifacts = [dict(row) for row in connection.execute('SELECT * FROM source_artifacts')]
        invalid = connection.execute('''SELECT d.id FROM documents d LEFT JOIN document_versions v ON d.current_version_id=v.id
                                        WHERE v.id IS NULL OR v.document_id<>d.id''').fetchall()
        for row in invalid:
            issues.append({'severity': 'error', 'code': 'document_current_version', 'record_id': _record_id(row['id']), 'message': 'The current draft pointer is missing or belongs to another document.'})
        database_readable = True
    except sqlite3.DatabaseError as exc:
        issues.append({'severity': 'error', 'code': 'document_database_check', 'message': 'Document integrity records could not be read. Preserve the project folder and restore a verified backup.', 'details': {'error_type': type(exc).__name__}})
    finally:
        if connection is not None:
            connection.close()
    known = {row['path'] for row in artifacts if isinstance(row.get('path'), str)}
    registry_complete = all(isinstance(row.get('path'), str) for row in artifacts)
    for artifact in artifacts:
        record_id = _record_id(artifact.get('id'))
        path = artifact.get('path')
        size = artifact.get('size')
        digest = artifact.get('sha256')
        invalid_fields = []
        if not isinstance(path, str) or not path:
            invalid_fields.append('path')
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            invalid_fields.append('size')
        if not isinstance(digest, str) or len(digest) != 64 or any(char not in '0123456789abcdef' for char in digest.lower()):
            invalid_fields.append('sha256')
        if invalid_fields:
            issue = {'severity': 'error', 'code': 'document_source_integrity', 'record_id': record_id,
                     'message': 'A document source record contains invalid path, size, or hash data. Restore its original bytes.'}
            if isinstance(path, str):
                issue['path'] = path
            issue['details'] = {'invalid_fields': invalid_fields}
            issues.append(issue)
            continue
        try:
            file = safe_path(service.root, path, must_exist=True)
            if file.stat().st_size != size or (hashes and sha256(file) != digest):
                raise StoryboardError('Stored source bytes changed.')
        except (StoryboardError, OSError, TypeError, ValueError):
            issues.append({'severity': 'error', 'code': 'document_source_integrity', 'record_id': record_id,
                           'path': path, 'message': 'A document source is missing, unsafe, or differs from its stored hash. Restore its original bytes.'})
    try:
        directory = safe_path(service.root, 'sources')
        if directory.exists():
            for item in directory.iterdir():
                relative = item.relative_to(service.root).as_posix()
                if item.is_symlink():
                    issues.append({'severity': 'error', 'code': 'source_symlink', 'path': relative, 'message': 'A document source cannot be a symbolic link.'})
                elif database_readable and registry_complete and item.is_file() and relative not in known:
                    issues.append({'severity': 'warning', 'code': 'orphan_document_source', 'path': relative, 'message': 'An unregistered document source remains after an interrupted import. Review it before removal.'})
    except (StoryboardError, OSError):
        issues.append({'severity': 'error', 'code': 'source_directory', 'message': 'The document source directory is unsafe or unreadable.'})
    return issues


def _record_id(value):
    if value is None:
        return None
    return value if isinstance(value, (str, int, float)) else repr(value)
