"""Small SQLite repository. Services own transactions; no interface owns SQL."""
from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
import sqlite3
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
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if current < 1 or "schema_migrations" not in tables:
                raise StoryboardError("The existing project database has no initialized Storyboarder schema. Preserve this folder and restore a verified backup; it was not changed.")
            applied = [row[0] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
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

    def migrate(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = self.connect()
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
            # Do not change database mode until its existing migration history is verified.
            conn.execute("PRAGMA journal_mode=WAL")
            if current and current < SCHEMA_VERSION:
                with sqlite3.connect(str(self.path) + f".before-v{SCHEMA_VERSION}.bak") as dest:
                    conn.backup(dest)
            for path in migrations:
                version = int(path.name.split("_", 1)[0])
                sql = path.read_text()
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
                    for statement in sql.split(";"):
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
        finally:
            conn.close()

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
