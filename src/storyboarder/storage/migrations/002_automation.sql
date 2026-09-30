CREATE TABLE jobs (
 id TEXT PRIMARY KEY, status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','failed','cancelled')),
 script TEXT NOT NULL, target TEXT NOT NULL CHECK(target IN ('asset','frame')), shot_id TEXT REFERENCES entities(id) ON DELETE RESTRICT,
 title TEXT NOT NULL, asset_type TEXT NOT NULL DEFAULT 'reference', request TEXT NOT NULL CHECK(json_valid(request)),
 result TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(result)), attempt INTEGER NOT NULL DEFAULT 0,
 approved INTEGER NOT NULL DEFAULT 0, revision INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE job_outputs (
 job_id TEXT NOT NULL REFERENCES jobs(id), output_key TEXT NOT NULL, media_id TEXT NOT NULL REFERENCES media(id),
 entity_id TEXT REFERENCES entities(id), frame_id TEXT REFERENCES frames(id),
 PRIMARY KEY(job_id,output_key)
);
CREATE INDEX job_status ON jobs(status,created_at);
