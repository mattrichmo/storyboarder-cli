"""Small SQLite repository. Services own transactions; no interface owns SQL."""
from contextlib import closing, contextmanager
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import shutil
import tempfile
from filelock import FileLock, Timeout as FileLockTimeout
from storyboarder import SCHEMA_VERSION
from storyboarder.domain.models import now, dumps
from storyboarder.domain.errors import Conflict, NotFound, StoryboardError

JSON_COLUMNS = {"fields", "tags", "positions", "settings", "request", "result", "provenance", "details"}
TABLES = {"entities", "media", "intake", "asset_media", "links", "assignments", "context_blocks", "frames", "layouts", "jobs", "events"}


def unpack(row):
    if row is None:
        return None
    data = dict(row)
    for key in JSON_COLUMNS & data.keys():
        data[key] = json.loads(data[key])
    return data


def sql_statements(script):
    """Split only complete SQLite statements, including trigger bodies."""
    buffer = ""
    for char in script:
        buffer += char
        if char == ";" and sqlite3.complete_statement(buffer):
            yield buffer
            buffer = ""
    remainder = "\n".join(line for line in buffer.splitlines() if not line.strip().startswith("--"))
    if remainder.strip():
        raise StoryboardError("Migration contains an incomplete SQL statement.")


class Repository:
    def __init__(self, path):
        self.path = Path(path)

    def verify_initialized(self):
        """Read-only guard for opening an existing project database."""
        if not self.path.is_file() or self.path.stat().st_size == 0:
            raise StoryboardError("This project folder has no usable project data. Keep it intact and restore a verified backup; no new data was written.")
        conn = None
        try:
            conn = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)
            current = conn.execute("PRAGMA user_version").fetchone()[0]
            if current > SCHEMA_VERSION:
                raise StoryboardError(f"Project schema version {current} is newer than supported version {SCHEMA_VERSION}. Upgrade Storyboarder; no data was changed.")
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if current < 1 or "schema_migrations" not in tables:
                raise StoryboardError("The existing project database has no initialized Storyboarder schema. Preserve this folder and restore a verified backup; it was not changed.")
            applied = [row[0] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
            if applied and max(applied) > SCHEMA_VERSION:
                raise StoryboardError("The migration ledger contains a newer schema version. Upgrade Storyboarder or restore a verified backup; no data was changed.")
            if applied != list(range(1, current + 1)):
                raise StoryboardError("The existing project database has an incomplete migration ledger. Preserve this folder and restore a verified backup; it was not changed.")
        except sqlite3.DatabaseError as exc:
            raise StoryboardError("The existing project database could not be read. Preserve this folder and restore a verified backup; it was not changed.") from exc
        finally:
            if conn is not None:
                conn.close()

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    @contextmanager
    def transaction(self, write=True):
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield conn
            conn.commit()
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            raise StoryboardError(f"This operation conflicts with an existing record or reference: {exc}") from exc
        except sqlite3.OperationalError as exc:
            conn.rollback()
            raise StoryboardError(f"Database operation failed: {exc}. Retry after other edits finish; run project doctor if it persists.") from exc
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def readonly_transaction(self):
        """Open an existing project database without allowing SQLite to write to it."""
        if not self.path.is_file():
            raise StoryboardError("Project data is missing from this folder.")
        conn = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=10000")
        try:
            conn.execute("BEGIN")
            yield conn
            conn.commit()
        except sqlite3.DatabaseError as exc:
            conn.rollback()
            raise StoryboardError("Project data could not be read safely.") from exc
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _verify_preupgrade_backup(backup_path, expected_version, target_version, expected_project_id, migrations):
        """Accept only this project's intact backup at or before the current schema.

        An older same-project backup is valid after a partially completed upgrade:
        earlier numbered migrations commit separately, while this backup remains
        the original recovery point for the target release. A foreign or newer
        backup must stop migration and remain untouched.
        """
        if backup_path.is_symlink() or not backup_path.is_file():
            raise StoryboardError("A pre-upgrade backup path already exists but is not a regular file; preserve it and inspect it before upgrading.")
        try:
            with closing(sqlite3.connect(backup_path.resolve().as_uri() + "?mode=ro", uri=True)) as check:
                version = check.execute("PRAGMA user_version").fetchone()[0]
                if version < 1 or version >= target_version:
                    raise StoryboardError("The existing pre-upgrade backup is not an older supported schema; it was preserved and migration stopped.")
                if version > expected_version:
                    raise StoryboardError("The existing pre-upgrade backup is newer than this project database; it was preserved and migration stopped.")
                if check.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise StoryboardError("The existing pre-upgrade backup failed SQLite integrity checks; it was preserved and migration stopped.")
                tables = {row[0] for row in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if "schema_migrations" not in tables:
                    raise StoryboardError("The existing pre-upgrade backup has no migration ledger; it was preserved and migration stopped.")
                if "entities" not in tables:
                    raise StoryboardError("The existing pre-upgrade backup has no project identity; it was preserved and migration stopped.")
                project_ids = [row[0] for row in check.execute("SELECT id FROM entities WHERE kind='project' ORDER BY id")]
                if project_ids != [expected_project_id]:
                    raise StoryboardError("The existing pre-upgrade backup belongs to a different or invalid project identity; it was preserved and migration stopped.")
                applied = [row[0] for row in check.execute("SELECT version FROM schema_migrations ORDER BY version")]
                if applied != list(range(1, version + 1)):
                    raise StoryboardError("The existing pre-upgrade backup has an incomplete migration ledger; it was preserved and migration stopped.")
                for path in migrations:
                    migration_version = int(path.name.split("_", 1)[0])
                    if migration_version > version:
                        continue
                    found = check.execute("SELECT checksum FROM schema_migrations WHERE version=?", (migration_version,)).fetchone()
                    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
                    if not found or found[0] != checksum:
                        raise StoryboardError(f"The existing pre-upgrade backup has an invalid migration {migration_version} checksum; it was preserved and migration stopped.")
                return version
        except sqlite3.DatabaseError as exc:
            raise StoryboardError("The existing pre-upgrade backup is unreadable; it was preserved and migration stopped.") from exc

    @classmethod
    def _create_preupgrade_backup(cls, conn, backup_path, expected_version, target_version, migrations):
        """Install a consistent backup without ever replacing an existing one."""
        current_version = conn.execute("PRAGMA user_version").fetchone()[0]
        if current_version != expected_version:
            raise StoryboardError("The project database changed before its pre-upgrade backup could be checked; migration stopped.")
        project_ids = [row[0] for row in conn.execute("SELECT id FROM entities WHERE kind='project' ORDER BY id")]
        if len(project_ids) != 1:
            raise StoryboardError("The project database has no unique project identity; preserve it and repair or restore it before upgrading.")
        expected_project_id = project_ids[0]
        if backup_path.exists() or backup_path.is_symlink():
            cls._verify_preupgrade_backup(backup_path, expected_version, target_version, expected_project_id, migrations)
            return
        fd, temporary = tempfile.mkstemp(prefix=f".{backup_path.name}.", suffix=".tmp", dir=backup_path.parent)
        os.close(fd)
        created = False
        try:
            with closing(sqlite3.connect(temporary)) as destination:
                conn.backup(destination)
            # Hard-linking installs the finished file atomically where supported.
            try:
                os.link(temporary, backup_path)
                created = True
            except FileExistsError:
                cls._verify_preupgrade_backup(backup_path, expected_version, target_version, expected_project_id, migrations)
                return
            except OSError:
                # Some filesystems (including FAT variants) do not support hard
                # links. Create the destination exclusively so this fallback
                # still cannot replace a backup another process already made.
                try:
                    descriptor = os.open(backup_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                except FileExistsError:
                    cls._verify_preupgrade_backup(backup_path, expected_version, target_version, expected_project_id, migrations)
                    return
                except OSError as create_error:
                    raise StoryboardError(
                        f"Could not safely create the pre-upgrade backup ({create_error}); migration stopped."
                    ) from create_error
                created = True
                try:
                    with open(temporary, "rb") as source:
                        try:
                            destination = os.fdopen(descriptor, "wb")
                            descriptor = -1
                        except Exception:
                            os.close(descriptor)
                            descriptor = -1
                            raise
                        with destination:
                            shutil.copyfileobj(source, destination)
                            destination.flush()
                            os.fsync(destination.fileno())
                except Exception as copy_error:
                    if descriptor >= 0:
                        os.close(descriptor)
                    backup_path.unlink(missing_ok=True)
                    if isinstance(copy_error, OSError):
                        raise StoryboardError(
                            f"Could not write the pre-upgrade backup ({copy_error}); migration stopped."
                        ) from copy_error
                    raise
            try:
                found_version = cls._verify_preupgrade_backup(backup_path, expected_version, target_version, expected_project_id, migrations)
                if found_version != expected_version:
                    raise StoryboardError("The newly created pre-upgrade backup has an unexpected schema version.")
            except Exception:
                if created:
                    backup_path.unlink(missing_ok=True)
                raise
        finally:
            Path(temporary).unlink(missing_ok=True)

    def migrate(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # This lock covers the initial version read, backup creation, and all
        # migrations. SQLite transactions alone do not protect the gap before
        # migration 1 acquires its write lock, so separate launchers could both
        # take a backup and the later one could capture an already-upgraded DB.
        try:
            with FileLock(str(self.path) + ".migration.lock", timeout=10):
                conn = self.connect()
                try:
                    self._migrate_locked(conn)
                finally:
                    conn.close()
        except FileLockTimeout as exc:
            raise StoryboardError("Another Storyboarder process is migrating this project. Wait for it to finish, then retry.") from exc

    def _migrate_locked(self, conn):
        try:
            current = conn.execute("PRAGMA user_version").fetchone()[0]
            if current > SCHEMA_VERSION:
                raise StoryboardError(f"Project schema {current} is newer than supported schema {SCHEMA_VERSION}. Upgrade Storyboarder.")
            migrations = sorted(Path(__file__).with_name("migrations").glob("*.sql"))
            try:
                versions = [int(path.name.split("_", 1)[0]) for path in migrations]
            except ValueError as exc:
                raise StoryboardError("The installed migration set contains an invalid filename.") from exc
            supported = [version for version in versions if version <= SCHEMA_VERSION]
            if supported != list(range(1, SCHEMA_VERSION + 1)):
                raise StoryboardError(f"The installed migration set is incomplete for schema {SCHEMA_VERSION}; expected numbered migrations 1 through {SCHEMA_VERSION}.")
            if len(versions) != len(set(versions)):
                raise StoryboardError("The installed migration set contains duplicate version numbers.")
            if current:
                applied = [row[0] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
                if applied != list(range(1, current + 1)):
                    raise StoryboardError("Migration ledger and database version disagree. Restore a verified backup rather than editing migration history.")
                for path in migrations:
                    version = int(path.name.split("_", 1)[0])
                    if version <= current:
                        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
                        found = conn.execute("SELECT checksum FROM schema_migrations WHERE version=?", (version,)).fetchone()
                        if not found or found[0] != checksum:
                            raise StoryboardError(f"Migration {version} checksum changed. Restore the original migration file; do not rewrite project history.")
            if current and current < SCHEMA_VERSION:
                backup_path = Path(str(self.path) + f".before-v{SCHEMA_VERSION}.bak")
                self._create_preupgrade_backup(conn, backup_path, current, SCHEMA_VERSION, migrations)
            # Do not change database mode until its existing migration history
            # and pre-upgrade backup have both been checked.
            conn.execute("PRAGMA journal_mode=WAL")
            for path in migrations:
                version = int(path.name.split("_", 1)[0])
                if version > SCHEMA_VERSION:
                    continue
                sql = path.read_bytes().decode("utf-8")
                checksum = hashlib.sha256(sql.encode()).hexdigest()
                if version <= current:
                    found = conn.execute("SELECT checksum FROM schema_migrations WHERE version=?", (version,)).fetchone()
                    if not found or found[0] != checksum:
                        raise StoryboardError(f"Migration {version} checksum changed. Restore the original migration file; do not rewrite project history.")
                    continue
                # executescript is not used: its implicit COMMIT breaks atomic migrations.
                conn.execute("BEGIN IMMEDIATE")
                try:
                    # A second launcher may have migrated while this one waited on the lock.
                    if conn.execute("PRAGMA user_version").fetchone()[0] >= version:
                        conn.rollback()
                        continue
                    for statement in sql_statements(sql):
                        if statement.strip():
                            conn.execute(statement)
                    conn.execute("INSERT INTO schema_migrations VALUES (?,?,?,?)", (version, path.name, checksum, now()))
                    conn.execute(f"PRAGMA user_version={version}")
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
            final_version = conn.execute("PRAGMA user_version").fetchone()[0]
            if final_version != SCHEMA_VERSION:
                raise StoryboardError(f"Migration stopped at schema {final_version}; installed application requires schema {SCHEMA_VERSION}.")
        except sqlite3.OperationalError as exc:
            raise StoryboardError(f"Database migration failed: {exc}. Retry after other edits finish; run project doctor if it persists.") from exc

    def get(self, conn, table, record_id):
        assert table in TABLES
        row = unpack(conn.execute(f"SELECT * FROM {table} WHERE id=?", (record_id,)).fetchone())
        if not row:
            raise NotFound(f"{table.replace('_', ' ').title()} record {record_id} was not found. Reload this view.")
        if table == "entities":
            row["tags"] = [r[0] for r in conn.execute("SELECT tag FROM entity_tags WHERE entity_id=? ORDER BY tag", (record_id,))]
            row["aliases"] = [r[0] for r in conn.execute("SELECT name FROM aliases WHERE entity_id=? ORDER BY name", (record_id,))]
        return row

    def check(self, row, revision):
        if not isinstance(revision, int) or isinstance(revision, bool) or row["revision"] != revision:
            raise Conflict("This record changed in another interface. Reload it and reapply your edit.", {"id": row["id"], "expected": revision, "current_revision": row["revision"], "current": row})

    def insert(self, conn, table, data):
        assert table in TABLES
        data = {k: dumps(v) if k in JSON_COLUMNS and not isinstance(v, str) else v for k, v in data.items()}
        columns = ",".join(data)
        conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({','.join('?' for _ in data)})", tuple(data.values()))
        return self.get(conn, table, data["id"])

    def update(self, conn, table, record_id, revision, values):
        row = self.get(conn, table, record_id)
        self.check(row, revision)
        values = {k: dumps(v) if k in JSON_COLUMNS and not isinstance(v, str) else v for k, v in values.items()}
        values["revision"] = row["revision"] + 1
        if "updated_at" in row:
            values["updated_at"] = now()
        conn.execute(f"UPDATE {table} SET {','.join(k+'=?' for k in values)} WHERE id=?", (*values.values(), record_id))
        return self.get(conn, table, record_id)

    def event(self, conn, action, entity_id=None, details=None):
        conn.execute("INSERT INTO events(entity_id,action,details,created_at) VALUES (?,?,?,?)", (entity_id, action, dumps(details or {}), now()))

    def snapshot(self):
        with self.transaction(False) as conn:
            result = {}
            for table in sorted(TABLES - {"events"}):
                result[table] = [unpack(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY id")]
            tags, aliases = {}, {}
            for row in conn.execute("SELECT * FROM entity_tags ORDER BY tag"):
                tags.setdefault(row["entity_id"], []).append(row["tag"])
            for row in conn.execute("SELECT * FROM aliases ORDER BY name"):
                aliases.setdefault(row["entity_id"], []).append(row["name"])
            for entity in result["entities"]:
                entity["tags"], entity["aliases"] = tags.get(entity["id"], []), aliases.get(entity["id"], [])
            result["events"] = [unpack(r) for r in conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT 60")]
            return result
