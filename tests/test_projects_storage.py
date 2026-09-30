from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import sqlite3
import pytest
from storyboarder.application.projects import Project, Workspace, discover
from storyboarder.application.service import Service
from storyboarder.domain.errors import StoryboardError, Conflict, NotFound
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


def test_genuine_schema_one_upgrade_keeps_story_and_creates_preupgrade_backup(service):
    marker = service.create_entity('asset', 'Survives upgrade', tags=['kept'])
    with sqlite3.connect(service.repo.path) as conn:
        conn.execute('DROP TABLE job_outputs')
        conn.execute('DROP TABLE jobs')
        conn.execute('DELETE FROM schema_migrations WHERE version=2')
        conn.execute('PRAGMA user_version=1')
    reopened = Service(Project(service.root))
    assert reopened.get('entities', marker['id']) == marker
    assert Path(str(service.repo.path)+'.before-v2.bak').is_file()
    with reopened.repo.transaction(False) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 2
        assert conn.execute('SELECT count(*) FROM jobs').fetchone()[0] == 0
