-- Versioned authored intent belongs to a storyboard shot, separate from ShotFields.
CREATE TABLE observation_contracts (
 id TEXT PRIMARY KEY,
 shot_id TEXT NOT NULL UNIQUE REFERENCES entities(id) ON DELETE RESTRICT,
 current_version_id TEXT REFERENCES observation_contract_versions(id) DEFERRABLE INITIALLY DEFERRED,
 revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0),
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);

CREATE TABLE observation_contract_versions (
 id TEXT PRIMARY KEY,
 contract_id TEXT NOT NULL REFERENCES observation_contracts(id) ON DELETE RESTRICT,
 parent_version_id TEXT REFERENCES observation_contract_versions(id) ON DELETE RESTRICT,
 number INTEGER NOT NULL CHECK(number > 0),
 schema_version INTEGER NOT NULL CHECK(schema_version = 1),
 contract_json TEXT NOT NULL CHECK(json_valid(contract_json)),
 content_sha256 TEXT NOT NULL,
 basis_json TEXT NOT NULL CHECK(json_valid(basis_json)),
 basis_sha256 TEXT NOT NULL,
 operation TEXT NOT NULL CHECK(operation IN ('create','revise','rebase')),
 sealed INTEGER NOT NULL DEFAULT 0 CHECK(sealed IN (0,1)),
 created_at TEXT NOT NULL,
 UNIQUE(contract_id,number)
);

CREATE TABLE observation_source_pins (
 version_id TEXT NOT NULL REFERENCES observation_contract_versions(id) ON DELETE RESTRICT,
 edge_id TEXT NOT NULL REFERENCES provenance_edges(id) ON DELETE RESTRICT,
 source_scope TEXT NOT NULL CHECK(source_scope IN ('direct-element','scene-context')),
 document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE RESTRICT,
 source_version_id TEXT NOT NULL REFERENCES document_versions(id) ON DELETE RESTRICT,
 node_id TEXT NOT NULL REFERENCES document_nodes(id) ON DELETE RESTRICT,
 logical_id TEXT NOT NULL,
 source_sha256 TEXT NOT NULL,
 scope_sha256 TEXT NOT NULL,
 document_sha256 TEXT NOT NULL,
 artifact_sha256 TEXT NOT NULL,
 source_snapshot TEXT NOT NULL CHECK(json_valid(source_snapshot)),
 edge_source_snapshot TEXT NOT NULL CHECK(json_valid(edge_source_snapshot)),
 edge_target_snapshot TEXT NOT NULL CHECK(json_valid(edge_target_snapshot)),
 created_at TEXT NOT NULL,
 PRIMARY KEY(version_id,edge_id)
);
CREATE INDEX observation_source_pin_edge ON observation_source_pins(edge_id,version_id);
CREATE INDEX observation_source_pin_node ON observation_source_pins(node_id,version_id);

-- References in v1 point to storyboard library assets. The FK preserves the
-- referenced identity without copying contract history into project snapshots.
CREATE TABLE observation_reference_pins (
 version_id TEXT NOT NULL REFERENCES observation_contract_versions(id) ON DELETE RESTRICT,
 reference_id TEXT NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
 snapshot_json TEXT NOT NULL CHECK(json_valid(snapshot_json)),
 created_at TEXT NOT NULL,
 PRIMARY KEY(version_id,reference_id)
);

CREATE TRIGGER observation_contract_shot_kind BEFORE INSERT ON observation_contracts BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM entities WHERE id=NEW.shot_id AND kind='shot')
   THEN RAISE(ABORT,'Observation contracts belong to storyboard shots') END;
END;
CREATE TRIGGER observation_contract_revision_initial BEFORE INSERT ON observation_contracts
 WHEN NEW.revision<>1 BEGIN SELECT RAISE(ABORT,'Observation contract revisions start at one'); END;
CREATE TRIGGER observation_contract_current_scope_insert BEFORE INSERT ON observation_contracts
 WHEN NEW.current_version_id IS NOT NULL BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM observation_contract_versions
   WHERE id=NEW.current_version_id AND contract_id=NEW.id AND sealed=1 AND number=1 AND parent_version_id IS NULL)
   THEN RAISE(ABORT,'Observation contract version belongs to another contract or is not sealed') END;
END;
CREATE TRIGGER observation_contract_shot_immutable BEFORE UPDATE OF shot_id ON observation_contracts
 WHEN NEW.shot_id<>OLD.shot_id BEGIN SELECT RAISE(ABORT,'Observation contract shot identity is stable'); END;
CREATE TRIGGER observation_contract_current_scope BEFORE UPDATE OF current_version_id ON observation_contracts
 WHEN NEW.current_version_id IS NOT NULL BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM observation_contract_versions
   WHERE id=NEW.current_version_id AND contract_id=NEW.id AND sealed=1)
   THEN RAISE(ABORT,'Observation contract version belongs to another contract or is not sealed') END;
END;
CREATE TRIGGER observation_contract_revision_guard BEFORE UPDATE OF current_version_id,revision ON observation_contracts
 WHEN NOT (
   (OLD.current_version_id IS NULL AND NEW.current_version_id IS NOT NULL AND NEW.revision=OLD.revision)
   OR
   (OLD.current_version_id IS NOT NULL AND NEW.current_version_id IS NOT OLD.current_version_id AND NEW.revision=OLD.revision+1)
 ) BEGIN SELECT RAISE(ABORT,'Observation contract revisions advance with new versions'); END;
CREATE TRIGGER observation_contract_next_version BEFORE UPDATE OF current_version_id ON observation_contracts
 WHEN NEW.current_version_id IS NOT NULL BEGIN
 SELECT CASE WHEN OLD.current_version_id IS NULL AND NOT EXISTS(
   SELECT 1 FROM observation_contract_versions WHERE id=NEW.current_version_id AND contract_id=NEW.id AND number=1 AND parent_version_id IS NULL
 ) THEN RAISE(ABORT,'The first observation contract version must have no parent') END;
 SELECT CASE WHEN OLD.current_version_id IS NOT NULL AND NOT EXISTS(
   SELECT 1 FROM observation_contract_versions next
   JOIN observation_contract_versions previous ON previous.id=OLD.current_version_id
   WHERE next.id=NEW.current_version_id AND next.contract_id=NEW.id
     AND next.parent_version_id=OLD.current_version_id AND next.number=previous.number+1
 ) THEN RAISE(ABORT,'Observation contract pointers must advance to the next child version') END;
END;
CREATE TRIGGER observation_contract_retained BEFORE DELETE ON observation_contracts
 BEGIN SELECT RAISE(ABORT,'Observation contract history is retained'); END;

CREATE TRIGGER observation_version_parent_scope BEFORE INSERT ON observation_contract_versions
 WHEN NEW.parent_version_id IS NOT NULL BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM observation_contract_versions
   WHERE id=NEW.parent_version_id AND contract_id=NEW.contract_id AND sealed=1)
   THEN RAISE(ABORT,'Observation parent version belongs to another contract or is not sealed') END;
END;
CREATE TRIGGER observation_version_insert_unsealed BEFORE INSERT ON observation_contract_versions
 WHEN NEW.sealed<>0 BEGIN SELECT RAISE(ABORT,'Observation contract versions must be created unsealed'); END;
CREATE TRIGGER observation_version_seal_once BEFORE UPDATE ON observation_contract_versions
 WHEN NOT (
   OLD.sealed=0 AND NEW.sealed=1
   AND NEW.id=OLD.id AND NEW.contract_id=OLD.contract_id AND NEW.parent_version_id IS OLD.parent_version_id
   AND NEW.number=OLD.number AND NEW.schema_version=OLD.schema_version
   AND NEW.contract_json=OLD.contract_json AND NEW.content_sha256=OLD.content_sha256
   AND NEW.basis_json=OLD.basis_json AND NEW.basis_sha256=OLD.basis_sha256
   AND NEW.operation=OLD.operation AND NEW.created_at=OLD.created_at
 ) BEGIN SELECT RAISE(ABORT,'Observation contract versions are immutable after sealing'); END;
CREATE TRIGGER observation_version_immutable_delete BEFORE DELETE ON observation_contract_versions
 BEGIN SELECT RAISE(ABORT,'Observation contract versions are immutable'); END;

-- Ordinary writes require active endpoints. Exact history restoration may
-- preserve a retired/archived endpoint only while the owning repository
-- connection has its short-lived restore gate enabled in one write transaction.
CREATE TRIGGER observation_source_pin_validate BEFORE INSERT ON observation_source_pins BEGIN
 SELECT CASE WHEN EXISTS(SELECT 1 FROM observation_contract_versions WHERE id=NEW.version_id AND sealed=1)
   THEN RAISE(ABORT,'Observation source pins cannot be added to a sealed version') END;
 SELECT CASE WHEN NOT EXISTS(
   SELECT 1
   FROM observation_contract_versions v
   JOIN observation_contracts c ON c.id=v.contract_id
   JOIN entities shot ON shot.id=c.shot_id AND shot.kind='shot'
     AND (shot.archived=0 OR observation_restore_authorized()=1)
   JOIN provenance_edges e ON e.id=NEW.edge_id AND e.relation='visualizes'
     AND (e.retired=0 OR observation_restore_authorized()=1)
   JOIN document_nodes n ON n.id=e.source_id
   JOIN document_versions dv ON dv.id=n.version_id
   JOIN documents d ON d.id=dv.document_id
     AND (d.archived=0 OR observation_restore_authorized()=1)
   JOIN source_artifacts artifact ON artifact.id=dv.source_artifact_id AND artifact.sha256=NEW.artifact_sha256
   WHERE v.id=NEW.version_id AND v.sealed=0
     AND e.source_type='node' AND e.target_type='entity'
     AND e.source_id=NEW.node_id
    AND n.version_id=NEW.source_version_id AND n.logical_id=NEW.logical_id
    AND n.identity='explicit' AND n.node_type<>'screenplay'
    AND n.content_sha256=NEW.source_sha256
     AND d.id=NEW.document_id AND d.kind='screenplay'
     AND dv.content_sha256=NEW.document_sha256
     AND json_extract(NEW.source_snapshot,'$.document_id')=d.id
     AND json_extract(NEW.source_snapshot,'$.document_version_id')=dv.id
     AND json_extract(NEW.source_snapshot,'$.node_id')=n.id
     AND json_extract(NEW.source_snapshot,'$.logical_id')=n.logical_id
     AND json_extract(NEW.source_snapshot,'$.source_sha256')=n.content_sha256
     AND json_extract(NEW.source_snapshot,'$.identity')=n.identity
     AND json_extract(NEW.edge_source_snapshot,'$.id')=n.id
     AND json_extract(NEW.edge_source_snapshot,'$.version_id')=dv.id
     AND json_extract(NEW.edge_source_snapshot,'$.logical_id')=n.logical_id
     AND json_extract(NEW.edge_source_snapshot,'$.content_sha256')=n.content_sha256
     AND json_extract(NEW.edge_target_snapshot,'$.id')=e.target_id
     AND (
       (e.target_id=c.shot_id AND NEW.source_scope='direct-element')
       OR
       (e.target_id=shot.parent_id AND NEW.source_scope='scene-context'
          AND EXISTS(SELECT 1 FROM entities scene WHERE scene.id=shot.parent_id AND scene.kind='scene'
            AND (scene.archived=0 OR observation_restore_authorized()=1)))
     )
 ) THEN RAISE(ABORT,'Observation source pin does not match an active exact screenplay edge') END;
END;
CREATE TRIGGER observation_source_pin_immutable_update BEFORE UPDATE ON observation_source_pins
 BEGIN SELECT RAISE(ABORT,'Observation source pins are immutable'); END;
CREATE TRIGGER observation_source_pin_immutable_delete BEFORE DELETE ON observation_source_pins
 BEGIN SELECT RAISE(ABORT,'Observation source pins are immutable'); END;
CREATE TRIGGER observation_reference_pin_validate BEFORE INSERT ON observation_reference_pins BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM observation_contract_versions WHERE id=NEW.version_id AND sealed=0)
   THEN RAISE(ABORT,'Observation version is sealed') END;
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM entities WHERE id=NEW.reference_id AND kind='asset'
   AND (archived=0 OR observation_restore_authorized()=1))
   THEN RAISE(ABORT,'Observation reference must be an active storyboard library asset') END;
END;
CREATE TRIGGER observation_reference_pin_immutable_update BEFORE UPDATE ON observation_reference_pins
 BEGIN SELECT RAISE(ABORT,'Observation references are immutable'); END;
CREATE TRIGGER observation_reference_pin_immutable_delete BEFORE DELETE ON observation_reference_pins
 BEGIN SELECT RAISE(ABORT,'Observation references are immutable'); END;
