from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import pytest
from storyboarder import SCHEMA_VERSION
from storyboarder.application.projects import Project, Workspace, WorkspaceConfigError, atomic_toml, discover
from storyboarder.application.service import Service
from storyboarder.domain.errors import StoryboardError, Conflict
from storyboarder.domain.models import slug, words


def test_two_projects_switch_move_and_discover(tmp_path, workspace):
    a = workspace.create('One', 'one')
    b = workspace.create('Two', 'two')
    marker = Service(a).create_entity('asset', 'Only in One')
    assert Service(b).list_entities('asset')['total'] == 0
    workspace.switch(a.id)
    assert workspace.current().id == a.id
    workspace.switch(b.id)
    assert workspace.current().id == b.id
    moved = tmp_path / 'moved'
    shutil.move(str(a.root), moved)
    opened = Project(moved)
    assert opened.id == a.id
    assert Service(opened).get('entities', marker['id'])['title'] == 'Only in One'
    assert Project(discover(moved / 'media')).id == a.id
    assert not next(p for p in workspace.list() if p['id'] == a.id)['available']


def test_current_project_manifest_uses_database_title(service):
    root = service.get('entities', service.project.id)
    service.update_entity(root['id'], root['revision'], {'title':'Renamed production'})
    assert Project(service.root).summary()['title'] == 'Renamed production'
    assert 'Renamed production' in (service.root/'project.toml').read_text()


def test_existing_nonempty_folder_not_overwritten(tmp_path):
    root=tmp_path/'occupied';root.mkdir();(root/'keep').write_text('Do not replace')
    with pytest.raises(StoryboardError): Project.create(root,'Occupied')
    assert (root/'keep').read_text() == 'Do not replace'


def test_missing_database_not_recreated(service):
    service.repo.path.unlink()
    with pytest.raises(StoryboardError): Project(service.root)
    assert not service.repo.path.exists()


def test_future_database_version_rejected(service):
    with sqlite3.connect(service.repo.path) as conn:
        conn.execute("INSERT INTO schema_migrations(version,name,checksum,applied_at) VALUES(99,'future','future','now')")
    with pytest.raises(StoryboardError, match='newer|future|upgrade|version'): Project(service.root)


def test_migration_checksum_tampering_rejected(service):
    with sqlite3.connect(service.repo.path) as conn:
        conn.execute("UPDATE schema_migrations SET checksum='tampered' WHERE version=1")
    with pytest.raises(StoryboardError, match='checksum|changed'): Project(service.root)


def test_transactions_rollback_all_changes(service):
    before=service.state()['entities']
    with pytest.raises(RuntimeError):
        with service.repo.transaction() as conn:
            conn.execute("UPDATE entities SET title='not committed'")
            raise RuntimeError('interrupt')
    assert service.state()['entities'] == before


def test_simultaneous_writes_detect_stale_revision(service):
    asset=service.create_entity('asset','Same revision')
    def edit(title):
        try: return service.update_entity(asset['id'],1,{'title':title})
        except Conflict: return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(edit,('First','Second')))
    assert results.count('conflict') == 1
    assert service.get('entities',asset['id'])['revision'] == 2


@pytest.mark.parametrize('name',['../x','/absolute','Upper','space here','', 'a'*65,'a_b','é'])
def test_invalid_slugs(name):
    with pytest.raises(StoryboardError):slug(name)


@pytest.mark.parametrize('value',[[1],['valid',None],{},[True],'x'*101])
def test_plain_tags_reject_invalid_values(value):
    with pytest.raises(StoryboardError):words(value)


def test_tags_and_aliases_normalize():
    assert words([' winter ', 'winter', '', 'morning']) == ['morning','winter']


def test_workspace_copy_keeps_identity_without_duplicate_navigation(workspace):
    first = workspace.create('Portable', 'original')
    copied = workspace.root / 'projects' / 'restored-copy'
    shutil.copytree(first.root, copied)
    assert Project(copied).id == first.id
    rows = workspace.list()
    assert len(rows) == 1
    assert rows[0]['path'] == str(first.root)
    assert rows[0]['duplicate_paths'] == [str(copied)]
    workspace.register(copied)
    rows = workspace.list()
    assert len(rows) == 1
    assert rows[0]['path'] == str(copied)
    assert workspace.current().root == copied


@pytest.mark.parametrize('old_version', [1, 2])
def test_genuine_legacy_upgrade_keeps_story_and_creates_preupgrade_backup(tmp_path, monkeypatch, old_version):
    import storyboarder.storage.repository as repository
    from storyboarder import SCHEMA_VERSION
    with monkeypatch.context() as legacy:
        legacy.setattr(repository, 'SCHEMA_VERSION', old_version)
        service = Service(Project.create(tmp_path / 'legacy', 'Legacy project'))
        marker = service.create_entity('asset', 'Survives upgrade', tags=['kept'])
    reopened = Service(Project(service.root))
    assert reopened.get('entities', marker['id']) == marker
    assert Path(str(service.repo.path)+f'.before-v{SCHEMA_VERSION}.bak').is_file()
    with reopened.repo.transaction(False) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION
        assert conn.execute('SELECT count(*) FROM jobs').fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM documents').fetchone()[0] == 0


def test_workspace_listing_does_not_upgrade_or_write_registered_external_project(tmp_path, monkeypatch):
    import storyboarder.storage.repository as repository

    external_root = tmp_path / 'external-project'
    with monkeypatch.context() as legacy:
        legacy.setattr(repository, 'SCHEMA_VERSION', SCHEMA_VERSION - 1)
        project = Project.create(external_root, 'Old external project')

    workspace = Workspace(tmp_path / 'workspace')
    workspace.init()
    atomic_toml(workspace.path, {
        'format_version': 1,
        'recent': project.id,
        'projects': [{'id': project.id, 'path': str(external_root)}],
    })
    before = {p.relative_to(external_root): p.read_bytes() for p in external_root.rglob('*') if p.is_file()}

    rows = workspace.list()
    from storyboarder.api.server import Launch
    browser_rows = Launch(workspace=workspace).projects()

    after = {p.relative_to(external_root): p.read_bytes() for p in external_root.rglob('*') if p.is_file()}
    row = next(p for p in rows if p['id'] == project.id)
    assert row['available'] is True
    assert row['browser_accessible'] is False
    assert browser_rows == []
    assert before == after
    assert not Path(str(project.repo.path) + f'.before-v{SCHEMA_VERSION}.bak').exists()
    with sqlite3.connect(project.repo.path) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION - 1


@pytest.mark.parametrize(('manifest', 'field'), [
    ("format_version = 1\nrecent = ''\nprojects = [42]\n", 'projects'),
    ("format_version = 1\nrecent = ''\n[[projects]]\nid = 'abc'\n", 'projects[0].path'),
    ("format_version = 1\nrecent = 7\nprojects = []\n", 'recent'),
    ("recent = ''\nprojects = []\n", 'format_version'),
])
def test_workspace_list_raises_structured_error_for_malformed_config(tmp_path, manifest, field):
    workspace = Workspace(tmp_path / 'workspace')
    workspace.root.mkdir()
    workspace.path.write_text(manifest)

    with pytest.raises(WorkspaceConfigError) as caught:
        workspace.list()

    assert caught.value.as_dict()['code'] == 'invalid_workspace_config'
    assert caught.value.as_dict()['details']['field'] == field


def test_concurrent_migration_preserves_a_preupgrade_backup(tmp_path, monkeypatch):
    import storyboarder.storage.repository as repository

    with monkeypatch.context() as legacy:
        legacy.setattr(repository, 'SCHEMA_VERSION', SCHEMA_VERSION - 1)
        project = Project.create(tmp_path / 'concurrent-legacy', 'Concurrent legacy')
    db_path = project.repo.path
    backup_path = Path(str(db_path) + f'.before-v{SCHEMA_VERSION}.bak')
    assert not backup_path.exists()

    gate = tmp_path / 'start-migration'
    code = (
        'import os, sys, time; from pathlib import Path; '
        'from storyboarder.storage.repository import Repository; '
        'db, gate = sys.argv[1:]; '
        'exec("while not Path(gate).exists(): time.sleep(0.005)"); '
        'Repository(db).migrate()'
    )
    env = os.environ.copy()
    src = str(Path(__file__).resolve().parents[1] / 'src')
    env['PYTHONPATH'] = src + os.pathsep + env.get('PYTHONPATH', '')
    children = [
        subprocess.Popen([sys.executable, '-c', code, str(db_path), str(gate)], env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for _ in range(2)
    ]
    gate.touch()
    outputs = [child.communicate(timeout=30) for child in children]
    assert [child.returncode for child in children] == [0, 0], outputs

    with sqlite3.connect(db_path) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION
    with sqlite3.connect(backup_path) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION - 1
        assert conn.execute('PRAGMA quick_check').fetchone()[0] == 'ok'


def test_existing_valid_preupgrade_backup_is_never_replaced(tmp_path, monkeypatch):
    import storyboarder.storage.repository as repository

    with monkeypatch.context() as legacy:
        legacy.setattr(repository, 'SCHEMA_VERSION', SCHEMA_VERSION - 1)
        project = Project.create(tmp_path / 'existing-backup-legacy', 'Legacy with backup')
    backup_path = Path(str(project.repo.path) + f'.before-v{SCHEMA_VERSION}.bak')
    shutil.copy2(project.repo.path, backup_path)
    original_backup = backup_path.read_bytes()

    Project(project.root)

    assert backup_path.read_bytes() == original_backup
    with sqlite3.connect(backup_path) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION - 1
        assert conn.execute('PRAGMA quick_check').fetchone()[0] == 'ok'


def test_foreign_preupgrade_backup_is_preserved_and_blocks_upgrade(tmp_path, monkeypatch):
    import storyboarder.storage.repository as repository

    with monkeypatch.context() as legacy:
        legacy.setattr(repository, 'SCHEMA_VERSION', SCHEMA_VERSION - 1)
        project = Project.create(tmp_path / 'current-project', 'Current project')
        foreign = Project.create(tmp_path / 'foreign-project', 'Different project')

    backup_path = Path(str(project.repo.path) + f'.before-v{SCHEMA_VERSION}.bak')
    shutil.copy2(foreign.repo.path, backup_path)
    original_database = project.repo.path.read_bytes()
    original_backup = backup_path.read_bytes()

    with pytest.raises(StoryboardError, match='different or invalid project identity'):
        Project(project.root)

    assert project.repo.path.read_bytes() == original_database
    assert backup_path.read_bytes() == original_backup
    with sqlite3.connect(project.repo.path) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION - 1


def test_preupgrade_backup_newer_than_current_database_blocks_upgrade(tmp_path, monkeypatch):
    import storyboarder.storage.repository as repository

    with monkeypatch.context() as legacy:
        legacy.setattr(repository, 'SCHEMA_VERSION', SCHEMA_VERSION - 2)
        project = Project.create(tmp_path / 'current-project', 'Current project')
    future_root = tmp_path / 'future-copy'
    shutil.copytree(project.root, future_root)
    with monkeypatch.context() as newer:
        newer.setattr(repository, 'SCHEMA_VERSION', SCHEMA_VERSION - 1)
        future = Project(future_root)

    backup_path = Path(str(project.repo.path) + f'.before-v{SCHEMA_VERSION}.bak')
    shutil.copy2(future.repo.path, backup_path)
    original_database = project.repo.path.read_bytes()
    original_backup = backup_path.read_bytes()

    with pytest.raises(StoryboardError, match='newer than this project database'):
        Project(project.root)

    assert project.repo.path.read_bytes() == original_database
    assert backup_path.read_bytes() == original_backup
    with sqlite3.connect(project.repo.path) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION - 2


def test_interrupted_upgrade_retry_keeps_older_same_project_backup(tmp_path, monkeypatch):
    import storyboarder.storage.repository as repository

    with monkeypatch.context() as legacy:
        legacy.setattr(repository, 'SCHEMA_VERSION', SCHEMA_VERSION - 2)
        project = Project.create(tmp_path / 'interrupted-upgrade', 'Interrupted upgrade')
    marker = Service(project).create_entity('asset', 'Kept through retry', tags=['preserved'])
    backup_path = Path(str(project.repo.path) + f'.before-v{SCHEMA_VERSION}.bak')
    shutil.copy2(project.repo.path, backup_path)
    original_backup = backup_path.read_bytes()
    migration = next(Path(repository.__file__).with_name('migrations').glob(f'{SCHEMA_VERSION:03d}_*.sql'))
    interrupted_migration = migration.read_bytes().decode('utf-8')
    real_statements = repository.sql_statements

    def interrupt_final_migration(script):
        if script == interrupted_migration:
            raise sqlite3.OperationalError('simulated interruption after earlier migrations committed')
        yield from real_statements(script)

    with monkeypatch.context() as interruption:
        interruption.setattr(repository, 'sql_statements', interrupt_final_migration)
        with pytest.raises(StoryboardError, match='migration failed'):
            Project(project.root)

    with sqlite3.connect(project.repo.path) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION - 1
    with sqlite3.connect(backup_path) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION - 2

    reopened = Project(project.root)
    assert Service(reopened).get('entities', marker['id'])['tags'] == ['preserved']
    assert backup_path.read_bytes() == original_backup


def test_preupgrade_backup_uses_exclusive_copy_when_hard_links_are_unsupported(tmp_path, monkeypatch):
    import storyboarder.storage.repository as repository

    with monkeypatch.context() as legacy:
        legacy.setattr(repository, 'SCHEMA_VERSION', SCHEMA_VERSION - 1)
        project = Project.create(tmp_path / 'no-hardlinks-legacy', 'Legacy without hard links')

    def no_hard_links(*_args, **_kwargs):
        raise OSError('hard links are unsupported')

    monkeypatch.setattr(repository.os, 'link', no_hard_links)
    Project(project.root)

    backup_path = Path(str(project.repo.path) + f'.before-v{SCHEMA_VERSION}.bak')
    with sqlite3.connect(backup_path) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION - 1
        assert conn.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
    with sqlite3.connect(project.repo.path) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION


def test_failed_exclusive_backup_copy_cleans_partial_file_and_stops_migration(tmp_path, monkeypatch):
    import storyboarder.storage.repository as repository

    with monkeypatch.context() as legacy:
        legacy.setattr(repository, 'SCHEMA_VERSION', SCHEMA_VERSION - 1)
        project = Project.create(tmp_path / 'failed-backup-copy', 'Legacy with failed backup')

    def no_hard_links(*_args, **_kwargs):
        raise OSError('hard links are unsupported')

    def copy_failure(*_args, **_kwargs):
        raise OSError('simulated full volume')

    monkeypatch.setattr(repository.os, 'link', no_hard_links)
    monkeypatch.setattr(repository.shutil, 'copyfileobj', copy_failure)
    backup_path = Path(str(project.repo.path) + f'.before-v{SCHEMA_VERSION}.bak')

    with pytest.raises(StoryboardError, match='write the pre-upgrade backup'):
        Project(project.root)

    assert not backup_path.exists()
    assert not list(backup_path.parent.glob(f'.{backup_path.name}.*.tmp'))
    with sqlite3.connect(project.repo.path) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION - 1


@pytest.mark.parametrize('backup_kind', ['corrupt', 'target_version'])
def test_invalid_preupgrade_backup_is_preserved_and_blocks_upgrade(tmp_path, monkeypatch, backup_kind):
    import storyboarder.storage.repository as repository

    with monkeypatch.context() as legacy:
        legacy.setattr(repository, 'SCHEMA_VERSION', SCHEMA_VERSION - 1)
        project = Project.create(tmp_path / f'invalid-backup-{backup_kind}', 'Legacy with invalid backup')
    backup_path = Path(str(project.repo.path) + f'.before-v{SCHEMA_VERSION}.bak')
    if backup_kind == 'corrupt':
        backup_path.write_bytes(b'not a SQLite database')
    else:
        shutil.copy2(project.repo.path, backup_path)
        with sqlite3.connect(backup_path) as conn:
            conn.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
    original_backup = backup_path.read_bytes()

    with pytest.raises(StoryboardError, match='backup'):
        Project(project.root)

    assert backup_path.read_bytes() == original_backup
    with sqlite3.connect(project.repo.path) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION - 1
