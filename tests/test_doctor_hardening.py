import json
import hashlib
import sqlite3
import subprocess
import sys

from test_documents import documents, screenplay as screenplay_fixture


def corrupt_non_project_json(service):
    asset = service.create_entity('asset', 'Corrupted record', fields={'type': 'character'})
    with sqlite3.connect(service.repo.path) as connection:
        connection.execute('PRAGMA ignore_check_constraints=ON')
        connection.execute("UPDATE entities SET fields='{' WHERE id=?", (asset['id'],))
        connection.execute("INSERT INTO context_blocks(id, owner_id, key, operation, text) VALUES ('broken-link', 'missing-owner', 'note', 'append', 'retained')")
    return asset['id']


def test_doctor_preserves_sqlite_integrity_results_when_snapshot_json_is_invalid(service, image_factory):
    service.import_file(image_factory())
    asset_id = corrupt_non_project_json(service)

    result = service.doctor()

    assert result['healthy'] is False
    assert result['snapshot_available'] is False
    assert result['media_checked'] is None
    assert result['integrity'] == ['ok']
    codes = {issue['code'] for issue in result['issues']}
    assert 'foreign_keys' in codes
    assert 'snapshot_json' in codes
    assert 'orphan_media' not in codes
    with sqlite3.connect(service.repo.path) as connection:
        assert connection.execute('SELECT fields FROM entities WHERE id=?', (asset_id,)).fetchone()[0] == '{'


def test_cli_doctor_returns_structured_health_and_failure_exit_for_corrupt_json(service, image_factory):
    service.import_file(image_factory())
    corrupt_non_project_json(service)

    completed = subprocess.run(
        [sys.executable, '-m', 'storyboarder', 'doctor', '--project', str(service.root), '--json'],
        text=True,
        capture_output=True,
        timeout=20,
    )

    assert completed.returncode == 4
    result = json.loads(completed.stdout)
    assert result['healthy'] is False
    assert result['snapshot_available'] is False
    codes = {issue['code'] for issue in result['issues']}
    assert 'foreign_keys' in codes
    assert 'snapshot_json' in codes
    assert 'orphan_media' not in codes
    assert not completed.stderr


def test_cli_doctor_handles_corrupt_project_entity_without_unpacking_on_open(service):
    with sqlite3.connect(service.repo.path) as connection:
        connection.execute('PRAGMA ignore_check_constraints=ON')
        connection.execute("UPDATE entities SET fields='{' WHERE id=?", (service.project.id,))

    completed = subprocess.run(
        [sys.executable, '-m', 'storyboarder', 'doctor', '--project', str(service.root), '--json'],
        text=True,
        capture_output=True,
        timeout=20,
    )

    assert completed.returncode == 4
    result = json.loads(completed.stdout)
    codes = {issue['code'] for issue in result['issues']}
    assert 'snapshot_json' in codes
    assert 'project_summary_read' in codes
    assert not completed.stderr


def test_cli_doctor_reports_future_schema_without_migrating(service):
    with sqlite3.connect(service.repo.path) as connection:
        connection.execute('PRAGMA user_version=99')
    before = hashlib.sha256(service.repo.path.read_bytes()).hexdigest()

    completed = subprocess.run(
        [sys.executable, '-m', 'storyboarder', 'doctor', '--project', str(service.root), '--json'],
        text=True,
        capture_output=True,
        timeout=20,
    )

    assert completed.returncode == 4
    result = json.loads(completed.stdout)
    assert result['schema_version'] == 99
    assert 'migration_state' in {issue['code'] for issue in result['issues']}
    assert hashlib.sha256(service.repo.path.read_bytes()).hexdigest() == before
    assert not completed.stderr


def test_doctor_keeps_prior_findings_when_project_summary_fails(service):
    def fail_summary():
        raise sqlite3.DatabaseError('database damage')

    service.project.summary = fail_summary
    result = service.doctor()

    assert result['healthy'] is False
    assert 'project_summary_read' in {issue['code'] for issue in result['issues']}


def test_doctor_does_not_recreate_database_that_disappears_after_open(service):
    service.repo.path.unlink()

    result = service.doctor()

    assert result['healthy'] is False
    assert service.repo.path.exists() is False
    codes = {issue['code'] for issue in result['issues']}
    assert 'database_unreadable' in codes
    assert 'snapshot_read' in codes


def test_document_doctor_reports_malformed_source_artifact_field_types(service):
    imported = documents(service).import_bytes(json.dumps(screenplay_fixture.__wrapped__()).encode(), 'draft.json')
    artifact_id = imported['version']['source_artifact_id']
    with sqlite3.connect(service.repo.path) as connection:
        connection.execute('PRAGMA ignore_check_constraints=ON')
        connection.execute('DROP TRIGGER immutable_source_artifact_update')
        connection.execute(
            'UPDATE source_artifacts SET path=?, size=?, sha256=? WHERE id=?',
            (sqlite3.Binary(b'\xff'), 'invalid-size', sqlite3.Binary(b'not-a-hash'), artifact_id),
        )

    result = service.doctor()

    issue = next(issue for issue in result['issues'] if issue['code'] == 'document_source_integrity')
    assert issue['record_id'] == artifact_id
    assert issue['details']['invalid_fields'] == ['path', 'size', 'sha256']
    assert 'path' not in issue
    assert 'orphan_document_source' not in {item['code'] for item in result['issues']}
    json.dumps(result)


def test_cli_doctor_reports_unreadable_database_without_changing_it(service):
    damaged = b'This is not a SQLite database.'
    service.repo.path.write_bytes(damaged)
    completed = subprocess.run(
        [sys.executable, '-m', 'storyboarder', 'doctor', '--project', str(service.root), '--json'],
        text=True, capture_output=True, timeout=20,
    )
    assert completed.returncode == 4
    result = json.loads(completed.stdout)
    assert result['healthy'] is False
    assert result['snapshot_available'] is False
    assert 'database_integrity_check' in {issue['code'] for issue in result['issues']}
    assert service.repo.path.read_bytes() == damaged
    assert not completed.stderr
