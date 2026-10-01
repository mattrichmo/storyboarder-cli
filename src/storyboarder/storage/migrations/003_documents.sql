CREATE TABLE source_artifacts (
 id TEXT PRIMARY KEY, path TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL UNIQUE,
 original_name TEXT NOT NULL, size INTEGER NOT NULL CHECK(size > 0), created_at TEXT NOT NULL
);
CREATE TABLE documents (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('screenplay','edit')),
 format TEXT NOT NULL CHECK(format IN ('screenjson','otio')), external_id TEXT,
 title TEXT NOT NULL, current_version_id TEXT REFERENCES document_versions(id) DEFERRABLE INITIALLY DEFERRED,
 revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0), archived INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX document_external_identity ON documents(format,external_id) WHERE external_id IS NOT NULL;
CREATE TABLE document_versions (
 id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id),
 parent_version_id TEXT REFERENCES document_versions(id), number INTEGER NOT NULL CHECK(number > 0),
 label TEXT NOT NULL, format_version TEXT NOT NULL, content_sha256 TEXT NOT NULL,
 source_artifact_id TEXT NOT NULL REFERENCES source_artifacts(id),
 warnings TEXT NOT NULL CHECK(json_valid(warnings)), created_at TEXT NOT NULL,
 UNIQUE(document_id,number), UNIQUE(document_id,content_sha256)
);
CREATE TABLE document_nodes (
 id TEXT PRIMARY KEY, version_id TEXT NOT NULL REFERENCES document_versions(id),
 logical_id TEXT NOT NULL, parent_id TEXT REFERENCES document_nodes(id),
 node_type TEXT NOT NULL, position INTEGER NOT NULL CHECK(position >= 0),
 title TEXT NOT NULL, text TEXT NOT NULL DEFAULT '', source_pointer TEXT NOT NULL,
 payload TEXT NOT NULL CHECK(json_valid(payload)), content_sha256 TEXT NOT NULL,
 identity TEXT NOT NULL CHECK(identity IN ('explicit','inferred')),
 UNIQUE(version_id,logical_id), UNIQUE(version_id,source_pointer)
);
CREATE INDEX document_children ON document_nodes(version_id,parent_id,position,id);
CREATE INDEX document_node_kind ON document_nodes(version_id,node_type);
CREATE INDEX document_node_search ON document_nodes(version_id,title COLLATE NOCASE);
CREATE TABLE document_imports (
 version_id TEXT NOT NULL REFERENCES document_versions(id), artifact_id TEXT NOT NULL REFERENCES source_artifacts(id),
 created_at TEXT NOT NULL, PRIMARY KEY(version_id,artifact_id)
);
CREATE TRIGGER immutable_document_version_update BEFORE UPDATE ON document_versions BEGIN SELECT RAISE(ABORT,'Document versions are immutable'); END;
CREATE TRIGGER immutable_document_version_delete BEFORE DELETE ON document_versions BEGIN SELECT RAISE(ABORT,'Document versions are immutable'); END;
CREATE TRIGGER immutable_document_node_update BEFORE UPDATE ON document_nodes BEGIN SELECT RAISE(ABORT,'Document nodes are immutable'); END;
CREATE TRIGGER immutable_document_node_delete BEFORE DELETE ON document_nodes BEGIN SELECT RAISE(ABORT,'Document nodes are immutable'); END;
CREATE TRIGGER immutable_source_artifact_update BEFORE UPDATE ON source_artifacts BEGIN SELECT RAISE(ABORT,'Source artifacts are immutable'); END;
CREATE TRIGGER immutable_source_artifact_delete BEFORE DELETE ON source_artifacts BEGIN SELECT RAISE(ABORT,'Source artifacts are immutable'); END;
CREATE TRIGGER document_node_parent_scope BEFORE INSERT ON document_nodes WHEN NEW.parent_id IS NOT NULL BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM document_nodes WHERE id=NEW.parent_id AND version_id=NEW.version_id) THEN RAISE(ABORT,'Document parent belongs to another version') END;
END;
CREATE TRIGGER document_version_parent_scope BEFORE INSERT ON document_versions WHEN NEW.parent_version_id IS NOT NULL BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM document_versions WHERE id=NEW.parent_version_id AND document_id=NEW.document_id) THEN RAISE(ABORT,'Document parent version belongs to another document') END;
END;
CREATE TRIGGER document_current_version_scope BEFORE UPDATE OF current_version_id ON documents WHEN NEW.current_version_id IS NOT NULL BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM document_versions WHERE id=NEW.current_version_id AND document_id=NEW.id) THEN RAISE(ABORT,'Current version belongs to another document') END;
END;
