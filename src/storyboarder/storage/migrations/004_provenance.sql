CREATE TABLE provenance_edges (
 id TEXT PRIMARY KEY, source_type TEXT NOT NULL, source_id TEXT NOT NULL,
 target_type TEXT NOT NULL, target_id TEXT NOT NULL, relation TEXT NOT NULL,
 source_snapshot TEXT NOT NULL CHECK(json_valid(source_snapshot)),
 target_snapshot TEXT NOT NULL CHECK(json_valid(target_snapshot)),
 notes TEXT NOT NULL DEFAULT '', retired INTEGER NOT NULL DEFAULT 0 CHECK(retired IN (0,1)),
 revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0), created_at TEXT NOT NULL,
 CHECK(source_type <> target_type OR source_id <> target_id)
);
CREATE UNIQUE INDEX provenance_active_relation ON provenance_edges(source_type,source_id,target_type,target_id,relation) WHERE retired=0;
CREATE INDEX provenance_upstream ON provenance_edges(target_type,target_id,retired);
CREATE INDEX provenance_downstream ON provenance_edges(source_type,source_id,retired);
CREATE TABLE annotations (
 id TEXT PRIMARY KEY, endpoint_type TEXT NOT NULL, endpoint_id TEXT NOT NULL,
 snapshot TEXT NOT NULL CHECK(json_valid(snapshot)), text TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'open' CHECK(state IN ('open','resolved')),
 revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0), created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX annotation_endpoint ON annotations(endpoint_type,endpoint_id,state);
CREATE TABLE annotation_revisions (
 annotation_id TEXT NOT NULL REFERENCES annotations(id), revision INTEGER NOT NULL,
 text TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(annotation_id,revision)
);
CREATE TABLE job_source_pins (
 job_id TEXT NOT NULL REFERENCES jobs(id), node_id TEXT NOT NULL REFERENCES document_nodes(id),
 snapshot TEXT NOT NULL CHECK(json_valid(snapshot)), PRIMARY KEY(job_id,node_id)
);
CREATE INDEX pinned_source_jobs ON job_source_pins(node_id,job_id);
CREATE TRIGGER immutable_provenance_endpoints BEFORE UPDATE ON provenance_edges WHEN
 NEW.source_type<>OLD.source_type OR NEW.source_id<>OLD.source_id OR NEW.target_type<>OLD.target_type OR NEW.target_id<>OLD.target_id OR NEW.relation<>OLD.relation OR NEW.source_snapshot<>OLD.source_snapshot OR NEW.target_snapshot<>OLD.target_snapshot
 BEGIN SELECT RAISE(ABORT,'Provenance endpoints and snapshots are immutable'); END;
CREATE TRIGGER provenance_history_retained BEFORE DELETE ON provenance_edges BEGIN SELECT RAISE(ABORT,'Retire provenance links instead of deleting history'); END;
CREATE TRIGGER annotation_history_retained BEFORE DELETE ON annotation_revisions BEGIN SELECT RAISE(ABORT,'Annotation revisions are immutable'); END;
CREATE TRIGGER annotation_revision_immutable BEFORE UPDATE ON annotation_revisions BEGIN SELECT RAISE(ABORT,'Annotation revisions are immutable'); END;
CREATE TRIGGER source_pin_immutable BEFORE UPDATE ON job_source_pins BEGIN SELECT RAISE(ABORT,'Job source pins are immutable'); END;
CREATE TRIGGER source_pin_retained BEFORE DELETE ON job_source_pins BEGIN SELECT RAISE(ABORT,'Job source pins are immutable'); END;
CREATE TRIGGER provenance_entity_delete_guard BEFORE DELETE ON entities WHEN
 EXISTS(SELECT 1 FROM provenance_edges WHERE (source_type='entity' AND source_id=OLD.id) OR (target_type='entity' AND target_id=OLD.id)) OR EXISTS(SELECT 1 FROM annotations WHERE endpoint_type='entity' AND endpoint_id=OLD.id)
 BEGIN SELECT RAISE(ABORT,'This entity has retained provenance or annotations; archive it instead'); END;
CREATE TRIGGER provenance_frame_delete_guard BEFORE DELETE ON frames WHEN
 EXISTS(SELECT 1 FROM provenance_edges WHERE (source_type='frame' AND source_id=OLD.id) OR (target_type='frame' AND target_id=OLD.id)) OR EXISTS(SELECT 1 FROM annotations WHERE endpoint_type='frame' AND endpoint_id=OLD.id)
 BEGIN SELECT RAISE(ABORT,'This frame has retained provenance or annotations; archive it instead'); END;

CREATE TABLE job_media_pins (
 job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,
 media_id TEXT NOT NULL REFERENCES media(id) ON DELETE RESTRICT,
 sha256 TEXT NOT NULL,
 PRIMARY KEY(job_id,media_id)
);
CREATE INDEX job_media_reverse ON job_media_pins(media_id,job_id);
CREATE TRIGGER immutable_job_media_update BEFORE UPDATE ON job_media_pins BEGIN SELECT RAISE(ABORT,'Job media pins are immutable'); END;
CREATE TRIGGER immutable_job_media_delete BEFORE DELETE ON job_media_pins BEGIN SELECT RAISE(ABORT,'Job media pins are immutable'); END;
