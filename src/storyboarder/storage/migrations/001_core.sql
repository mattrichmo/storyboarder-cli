CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, checksum TEXT NOT NULL, applied_at TEXT NOT NULL);
CREATE TABLE entities (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('project','asset','sequence','scene','shot')),
 parent_id TEXT REFERENCES entities(id) ON DELETE RESTRICT,
 position INTEGER NOT NULL DEFAULT 0 CHECK(position >= 0), title TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '', fields TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(fields)),
 archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)), revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX entity_order ON entities(kind,parent_id,archived,position,id);
CREATE INDEX entity_search ON entities(title COLLATE NOCASE);
CREATE TABLE tags (name TEXT PRIMARY KEY);
CREATE TABLE entity_tags (entity_id TEXT REFERENCES entities(id) ON DELETE CASCADE, tag TEXT REFERENCES tags(name), PRIMARY KEY(entity_id,tag));
CREATE TABLE aliases (entity_id TEXT REFERENCES entities(id) ON DELETE CASCADE, name TEXT NOT NULL, PRIMARY KEY(entity_id,name));
CREATE TABLE media (
 id TEXT PRIMARY KEY, path TEXT UNIQUE NOT NULL, sha256 TEXT UNIQUE NOT NULL,
 original_name TEXT NOT NULL, format TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
 size INTEGER NOT NULL, tags TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(tags)),
 revision INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
);
CREATE TABLE intake (
 id TEXT PRIMARY KEY, media_id TEXT NOT NULL REFERENCES media(id) ON DELETE RESTRICT,
 original_name TEXT NOT NULL, original_path TEXT NOT NULL, duplicate INTEGER NOT NULL DEFAULT 0,
 state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','accepted','discarded')),
 revision INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
);
CREATE INDEX intake_queue ON intake(state,created_at);
CREATE TABLE asset_media (
 id TEXT PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
 media_id TEXT NOT NULL REFERENCES media(id) ON DELETE RESTRICT,
 is_primary INTEGER NOT NULL DEFAULT 0, revision INTEGER NOT NULL DEFAULT 1,
 UNIQUE(asset_id,media_id)
);
CREATE UNIQUE INDEX primary_reference ON asset_media(asset_id) WHERE is_primary=1;
CREATE TABLE links (
 id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
 target_id TEXT NOT NULL REFERENCES entities(id) ON DELETE RESTRICT, relation TEXT NOT NULL,
 revision INTEGER NOT NULL DEFAULT 1, UNIQUE(source_id,target_id,relation), CHECK(source_id <> target_id)
);
CREATE TABLE assignments (
 id TEXT PRIMARY KEY, shot_id TEXT NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
 asset_id TEXT NOT NULL REFERENCES entities(id) ON DELETE RESTRICT, role TEXT NOT NULL,
 media_id TEXT REFERENCES media(id) ON DELETE RESTRICT, revision INTEGER NOT NULL DEFAULT 1,
 UNIQUE(shot_id,asset_id,role)
);
CREATE TABLE context_blocks (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
 key TEXT NOT NULL, operation TEXT NOT NULL CHECK(operation IN ('append','replace','exclude')),
 text TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, UNIQUE(owner_id,key)
);
CREATE TABLE frames (
 id TEXT PRIMARY KEY, shot_id TEXT NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
 media_id TEXT NOT NULL REFERENCES media(id) ON DELETE RESTRICT, version INTEGER NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('draft','selected','approved','archived')),
 notes TEXT NOT NULL DEFAULT '', provenance TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(provenance)),
 revision INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, UNIQUE(shot_id,version)
);
CREATE UNIQUE INDEX preferred_frame ON frames(shot_id) WHERE state IN ('selected','approved');
CREATE TABLE layouts (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, mode TEXT NOT NULL CHECK(mode IN ('story','assets','scene')),
 positions TEXT NOT NULL CHECK(json_valid(positions)), settings TEXT NOT NULL CHECK(json_valid(settings)),
 revision INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL, UNIQUE(name,mode)
);
CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, entity_id TEXT, action TEXT NOT NULL, details TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL);
