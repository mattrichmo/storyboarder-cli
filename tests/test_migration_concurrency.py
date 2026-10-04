"""Migration backup regressions using spawned processes and explicit handoffs."""
import hashlib
import multiprocessing
from pathlib import Path
import sqlite3
import traceback

import pytest
from filelock import FileLock, Timeout

from storyboarder import SCHEMA_VERSION
from storyboarder.domain.errors import StoryboardError
import storyboarder.storage.repository as repository


def _migrate_worker(path, first, backup_started, second_waiting, resume_first, resume_second, errors):
    # These hooks preserve the real SQLite backup and OS lock. With the old code,
    # hold the second launcher's backup until the first upgrade completes.
    # With the fix, observe actual lock contention before releasing the first.
    class ObservedLock(FileLock):
        def acquire(self, *args, **kwargs):
            if not first:
                try:
                    return super().acquire(timeout=0)
                except Timeout:
                    second_waiting.set()
            return super().acquire(*args, **kwargs)

    class ObservedConnection(sqlite3.Connection):
        def backup(self, target, *args, **kwargs):
            if first:
                backup_started.set()
                assert resume_first.wait(20), 'First launcher was not released'
            else:
                second_waiting.set()
                assert resume_second.wait(20), 'Second launcher was not released'
            return super().backup(target, *args, **kwargs)

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None, factory=ObservedConnection)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA busy_timeout=10000')
        return conn

    repository.FileLock = ObservedLock
    repository.Repository.connect = connect
    try:
        repository.Repository(path).migrate()
    except BaseException:
        errors.put(traceback.format_exc())
        raise


def _legacy_database(tmp_path, monkeypatch, version):
    repo = repository.Repository(tmp_path / 'storyboard.sqlite3')
    with monkeypatch.context() as legacy:
        legacy.setattr(repository, 'SCHEMA_VERSION', version)
        repo.migrate()
    # User data independent of the application schema must survive both copies.
    with repo.transaction() as conn:
        conn.execute('CREATE TABLE backup_marker(value TEXT)')
        conn.execute("INSERT INTO backup_marker VALUES ('before upgrade')")
    return repo


def _assert_database(path, version):
    with sqlite3.connect(path) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert conn.execute('PRAGMA user_version').fetchone()[0] == version
        rows = conn.execute('SELECT version,name,checksum FROM schema_migrations ORDER BY version').fetchall()
        assert [row[0] for row in rows] == list(range(1, version + 1))
        for _, name, checksum in rows:
            migration = Path(repository.__file__).with_name('migrations') / name
            assert checksum == hashlib.sha256(migration.read_bytes()).hexdigest()
        assert conn.execute('SELECT value FROM backup_marker').fetchone()[0] == 'before upgrade'


@pytest.mark.parametrize('old_version', [1, SCHEMA_VERSION - 1])
def test_concurrent_migrations_preserve_preupgrade_backup(tmp_path, monkeypatch, old_version):
    repo = _legacy_database(tmp_path, monkeypatch, old_version)
    context = multiprocessing.get_context('spawn')
    backup_started, second_waiting, resume_first, resume_second = [context.Event() for _ in range(4)]
    errors = context.Queue()
    args = (backup_started, second_waiting, resume_first, resume_second, errors)
    first = context.Process(target=_migrate_worker, args=(repo.path, True, *args))
    second = context.Process(target=_migrate_worker, args=(repo.path, False, *args))
    started = []
    try:
        first.start()
        started.append(first)
        assert backup_started.wait(20), 'First launcher did not reach the snapshot'
        second.start()
        started.append(second)
        assert second_waiting.wait(20), 'Second launcher did not reach the contention/stale-read gate'
        resume_first.set()
        first.join(20)
        assert first.exitcode == 0, 'First launcher failed or hung'
        resume_second.set()
        second.join(20)
        assert second.exitcode == 0, 'Second launcher failed or hung'
    finally:
        resume_first.set()
        resume_second.set()
        for process in started:
            if process.is_alive():
                process.terminate()
            process.join(5)
        failures = []
        while not errors.empty():
            failures.append(errors.get())
        errors.close()
        errors.join_thread()
    assert not failures, '\n'.join(failures)
    backup = Path(str(repo.path) + f'.before-v{SCHEMA_VERSION}.bak')
    _assert_database(repo.path, SCHEMA_VERSION)
    _assert_database(backup, old_version)
    # A subsequent single-process open also leaves the rollback copy untouched.
    before = backup.read_bytes()
    repo.migrate()
    assert backup.read_bytes() == before


def test_failed_migration_rolls_back_and_releases_serialization_lock(tmp_path, monkeypatch):
    old_version = SCHEMA_VERSION - 1
    repo = _legacy_database(tmp_path, monkeypatch, old_version)

    def fail_after_write(sql):
        yield 'CREATE TABLE should_rollback(value TEXT);'
        raise RuntimeError('migration interrupted')

    with monkeypatch.context() as broken:
        broken.setattr(repository, 'sql_statements', fail_after_write)
        with pytest.raises(RuntimeError, match='migration interrupted'):
            repo.migrate()
    backup = Path(str(repo.path) + f'.before-v{SCHEMA_VERSION}.bak')
    _assert_database(repo.path, old_version)
    _assert_database(backup, old_version)
    with sqlite3.connect(repo.path) as conn:
        assert not conn.execute("SELECT name FROM sqlite_master WHERE name='should_rollback'").fetchall()
    # Retrying proves both locks were released; the real migration succeeds.
    repo.migrate()
    _assert_database(repo.path, SCHEMA_VERSION)
    _assert_database(backup, old_version)


@pytest.mark.parametrize('tamper', ['checksum', 'ledger'])
def test_legacy_history_rejection_does_not_overwrite_backup(tmp_path, monkeypatch, tamper):
    repo = _legacy_database(tmp_path, monkeypatch, SCHEMA_VERSION - 1)
    backup = Path(str(repo.path) + f'.before-v{SCHEMA_VERSION}.bak')
    backup.write_bytes(b'existing rollback copy')
    with repo.transaction() as conn:
        if tamper == 'checksum':
            conn.execute("UPDATE schema_migrations SET checksum='tampered' WHERE version=1")
        else:
            conn.execute('DELETE FROM schema_migrations WHERE version=1')
    with pytest.raises(StoryboardError, match='checksum|ledger'):
        repo.migrate()
    assert backup.read_bytes() == b'existing rollback copy'
    with sqlite3.connect(repo.path) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION - 1
