-- Additive migration. Existing story, source, spatial and observation history is untouched.
CREATE TABLE production_clock (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    checkpoint INTEGER NOT NULL DEFAULT 0 CHECK(checkpoint>=0)
);
INSERT INTO production_clock(singleton,checkpoint) VALUES(1,0);
CREATE TABLE production_records (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('production','sequence','script','location','asset','scene','action','camera_setup','lighting_setup','shot','panel','animatic','edit','take','review','annotation','exception')),
    revision INTEGER NOT NULL CHECK(revision>=1),
    head_version INTEGER,
    selected_version INTEGER,
    archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(id,head_version) REFERENCES production_versions(record_id,number) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(id,selected_version) REFERENCES production_versions(record_id,number) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE production_versions (
    record_id TEXT NOT NULL REFERENCES production_records(id) ON DELETE RESTRICT,
    number INTEGER NOT NULL CHECK(number>=1),
    parent_number INTEGER,
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    sha256 TEXT NOT NULL CHECK(length(sha256)=64),
    created_at TEXT NOT NULL,
    PRIMARY KEY(record_id,number),
    FOREIGN KEY(record_id,parent_number) REFERENCES production_versions(record_id,number) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE production_refs (
    source_id TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    path TEXT NOT NULL,
    target_id TEXT NOT NULL,
    target_version INTEGER NOT NULL,
    PRIMARY KEY(source_id,source_version,path),
    FOREIGN KEY(source_id,source_version) REFERENCES production_versions(record_id,number) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(target_id,target_version) REFERENCES production_versions(record_id,number) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX production_refs_target ON production_refs(target_id,target_version);
CREATE INDEX production_records_kind ON production_records(kind,archived);
CREATE TABLE production_operations (
    id TEXT PRIMARY KEY,
    request_sha256 TEXT NOT NULL,
    checkpoint INTEGER NOT NULL UNIQUE,
    result_json TEXT NOT NULL CHECK(json_valid(result_json)),
    created_at TEXT NOT NULL
);
CREATE TABLE production_changes (
    checkpoint INTEGER NOT NULL,
    record_id TEXT NOT NULL REFERENCES production_records(id),
    operation TEXT NOT NULL,
    previous_version INTEGER,
    new_version INTEGER,
    PRIMARY KEY(checkpoint,record_id)
);
CREATE TRIGGER production_versions_immutable_update BEFORE UPDATE ON production_versions BEGIN
    SELECT RAISE(ABORT,'Production versions are immutable');
END;
CREATE TRIGGER production_versions_immutable_delete BEFORE DELETE ON production_versions BEGIN
    SELECT RAISE(ABORT,'Production history cannot be deleted; archive the record');
END;
CREATE TRIGGER production_refs_immutable_update BEFORE UPDATE ON production_refs BEGIN
    SELECT RAISE(ABORT,'Production version references are immutable');
END;
CREATE TRIGGER production_refs_immutable_delete BEFORE DELETE ON production_refs BEGIN
    SELECT RAISE(ABORT,'Production version references are immutable');
END;
CREATE TRIGGER production_operations_immutable_update BEFORE UPDATE ON production_operations BEGIN
    SELECT RAISE(ABORT,'Production retry receipts are immutable');
END;
CREATE TRIGGER production_operations_immutable_delete BEFORE DELETE ON production_operations BEGIN
    SELECT RAISE(ABORT,'Production retry receipts are immutable');
END;
-- Exact external identity pins prevent a legacy/media deletion from leaving hidden
-- dangling production references. Immutable history continues to own these pins.
CREATE TABLE production_media_pins (
 source_id TEXT NOT NULL,
 source_version INTEGER NOT NULL,
 media_id TEXT NOT NULL REFERENCES media(id) ON DELETE RESTRICT,
 PRIMARY KEY(source_id,source_version,media_id),
 FOREIGN KEY(source_id,source_version) REFERENCES production_versions(record_id,number) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE production_legacy_pins (
 source_id TEXT NOT NULL,
 source_version INTEGER NOT NULL,
 entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
 PRIMARY KEY(source_id,source_version,entity_id),
 FOREIGN KEY(source_id,source_version) REFERENCES production_versions(record_id,number) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
);
CREATE TRIGGER production_media_pins_immutable_update BEFORE UPDATE ON production_media_pins BEGIN
 SELECT RAISE(ABORT,'Production source pins are immutable');
END;
CREATE TRIGGER production_media_pins_immutable_delete BEFORE DELETE ON production_media_pins BEGIN
 SELECT RAISE(ABORT,'Production source pins are immutable');
END;
CREATE TRIGGER production_legacy_pins_immutable_update BEFORE UPDATE ON production_legacy_pins BEGIN
 SELECT RAISE(ABORT,'Production source pins are immutable');
END;
CREATE TRIGGER production_legacy_pins_immutable_delete BEFORE DELETE ON production_legacy_pins BEGIN
 SELECT RAISE(ABORT,'Production source pins are immutable');
END;
