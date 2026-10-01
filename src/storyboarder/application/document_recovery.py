"""Document integrity checks shared by doctor and restore."""
from pathlib import Path

from storyboarder.domain.errors import StoryboardError
from storyboarder.media.files import safe_path, sha256


def document_health(service, hashes=False):
    issues = []
    with service.repo.transaction(False) as conn:
        artifacts = [dict(row) for row in conn.execute('SELECT * FROM source_artifacts')]
        invalid = conn.execute('''SELECT d.id FROM documents d LEFT JOIN document_versions v ON d.current_version_id=v.id
                                  WHERE v.id IS NULL OR v.document_id<>d.id''').fetchall()
        for row in invalid:
            issues.append({'severity': 'error', 'code': 'document_current_version', 'record_id': row['id'], 'message': 'The current draft pointer is missing or belongs to another document.'})
    known = {row['path'] for row in artifacts}
    for artifact in artifacts:
        try:
            file = safe_path(service.root, artifact['path'], must_exist=True)
            if file.stat().st_size != artifact['size'] or (hashes and sha256(file) != artifact['sha256']):
                raise StoryboardError('Stored source bytes changed.')
        except (StoryboardError, OSError):
            issues.append({'severity': 'error', 'code': 'document_source_integrity', 'record_id': artifact['id'],
                           'path': artifact['path'], 'message': 'A document source is missing, unsafe, or differs from its stored hash. Restore its original bytes.'})
    try:
        directory = safe_path(service.root, 'sources')
        if directory.exists():
            for item in directory.iterdir():
                relative = item.relative_to(service.root).as_posix()
                if item.is_symlink():
                    issues.append({'severity': 'error', 'code': 'source_symlink', 'path': relative, 'message': 'A document source cannot be a symbolic link.'})
                elif item.is_file() and relative not in known:
                    issues.append({'severity': 'warning', 'code': 'orphan_document_source', 'path': relative, 'message': 'An unregistered document source remains after an interrupted import. Review it before removal.'})
    except (StoryboardError, OSError):
        issues.append({'severity': 'error', 'code': 'source_directory', 'message': 'The document source directory is unsafe or unreadable.'})
    return issues
