-- PROPOSED additive migration for exact base 4091c52076f8cc2cb39131e40cdf84caa362ae21.
-- Run through Storyboarder's migrator, not executescript against a live project.
-- Existing entities/document/media/observation table names verified in source excerpts.
CREATE TABLE spatial_setups (
 id TEXT PRIMARY KEY,
 project_id TEXT NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
 current_version_id TEXT REFERENCES spatial_setup_versions(id) DEFERRABLE INITIALLY DEFERRED,
 revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>0),
 title TEXT NOT NULL,
 archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE spatial_setup_versions (
 id TEXT PRIMARY KEY,
 setup_id TEXT NOT NULL REFERENCES spatial_setups(id) ON DELETE RESTRICT,
 parent_version_id TEXT REFERENCES spatial_setup_versions(id) ON DELETE RESTRICT,
 number INTEGER NOT NULL CHECK(number>0),
 schema_version INTEGER NOT NULL CHECK(schema_version=1),
 payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
 content_sha256 TEXT NOT NULL CHECK(length(content_sha256)=64),
 basis_json TEXT NOT NULL CHECK(json_valid(basis_json)),
 basis_sha256 TEXT NOT NULL CHECK(length(basis_sha256)=64),
 operation TEXT NOT NULL CHECK(operation IN ('create','revise','restore','duplicate','import','archive','unarchive')),
 sealed INTEGER NOT NULL DEFAULT 0 CHECK(sealed IN (0,1)),
 created_at TEXT NOT NULL,
 UNIQUE(setup_id,number)
);
CREATE TABLE spatial_version_scene_pins (
 version_id TEXT NOT NULL REFERENCES spatial_setup_versions(id) ON DELETE RESTRICT,
 scene_id TEXT NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
 PRIMARY KEY(version_id,scene_id)
);
CREATE TABLE spatial_version_asset_pins (
 version_id TEXT NOT NULL REFERENCES spatial_setup_versions(id) ON DELETE RESTRICT,
 owner_id TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('identity','reference','location')),
 asset_id TEXT NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
 asset_revision INTEGER NOT NULL CHECK(asset_revision>0),
 semantic_sha256 TEXT NOT NULL CHECK(length(semantic_sha256)=64),
 snapshot_json TEXT NOT NULL CHECK(json_valid(snapshot_json)),
 PRIMARY KEY(version_id,owner_id,role,asset_id)
);
CREATE TABLE spatial_version_media_pins (
 version_id TEXT NOT NULL REFERENCES spatial_setup_versions(id) ON DELETE RESTRICT,
 owner_id TEXT NOT NULL,
 media_id TEXT NOT NULL REFERENCES media(id) ON DELETE RESTRICT,
 media_sha256 TEXT NOT NULL CHECK(length(media_sha256)=64),
 PRIMARY KEY(version_id,owner_id,media_id)
);
CREATE TABLE spatial_version_source_pins (
 version_id TEXT NOT NULL REFERENCES spatial_setup_versions(id) ON DELETE RESTRICT,
 pin_id TEXT NOT NULL,
 source_kind TEXT NOT NULL CHECK(source_kind IN ('document-node','observation-v1')),
 document_id TEXT REFERENCES documents(id) ON DELETE RESTRICT,
 document_version_id TEXT REFERENCES document_versions(id) ON DELETE RESTRICT,
 node_id TEXT REFERENCES document_nodes(id) ON DELETE RESTRICT,
 observation_version_id TEXT REFERENCES observation_contract_versions(id) ON DELETE RESTRICT,
 semantic_sha256 TEXT NOT NULL CHECK(length(semantic_sha256)=64),
 snapshot_json TEXT NOT NULL CHECK(json_valid(snapshot_json)),
 CHECK((source_kind='document-node' AND document_id IS NOT NULL AND document_version_id IS NOT NULL AND node_id IS NOT NULL AND observation_version_id IS NULL)
    OR (source_kind='observation-v1' AND document_id IS NULL AND document_version_id IS NULL AND node_id IS NULL AND observation_version_id IS NOT NULL)),
 PRIMARY KEY(version_id,pin_id)
);
CREATE TABLE shot_spatial_bindings (
 id TEXT PRIMARY KEY,
 shot_id TEXT NOT NULL UNIQUE REFERENCES entities(id) ON DELETE RESTRICT,
 current_version_id TEXT REFERENCES shot_spatial_binding_versions(id) DEFERRABLE INITIALLY DEFERRED,
 revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>0),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE shot_spatial_binding_versions (
 id TEXT PRIMARY KEY,
 binding_id TEXT NOT NULL REFERENCES shot_spatial_bindings(id) ON DELETE RESTRICT,
 parent_version_id TEXT REFERENCES shot_spatial_binding_versions(id) ON DELETE RESTRICT,
 number INTEGER NOT NULL CHECK(number>0),
 setup_version_id TEXT NOT NULL REFERENCES spatial_setup_versions(id) ON DELETE RESTRICT,
 schema_version INTEGER NOT NULL CHECK(schema_version=1),
 binding_json TEXT NOT NULL CHECK(json_valid(binding_json)),
 content_sha256 TEXT NOT NULL CHECK(length(content_sha256)=64),
 basis_json TEXT NOT NULL CHECK(json_valid(basis_json)),
 basis_sha256 TEXT NOT NULL CHECK(length(basis_sha256)=64),
 operation TEXT NOT NULL CHECK(operation IN ('create','rebind','detach','restore','import')),
 sealed INTEGER NOT NULL DEFAULT 0 CHECK(sealed IN (0,1)),
 created_at TEXT NOT NULL,
 UNIQUE(binding_id,number)
);
-- An additive v2 envelope. It never replaces or rewrites v1 versions/heads.
-- Latest number is the v2 review head; no mutable head pointer is necessary.
CREATE TABLE observation_spatial_reviews (
 id TEXT PRIMARY KEY,
 shot_id TEXT NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
 parent_review_id TEXT REFERENCES observation_spatial_reviews(id) ON DELETE RESTRICT,
 number INTEGER NOT NULL CHECK(number>0),
 schema_version INTEGER NOT NULL CHECK(schema_version=2),
 observation_version_id TEXT NOT NULL REFERENCES observation_contract_versions(id) ON DELETE RESTRICT,
 binding_version_id TEXT NOT NULL REFERENCES shot_spatial_binding_versions(id) ON DELETE RESTRICT,
 review_json TEXT NOT NULL CHECK(json_valid(review_json)),
 content_sha256 TEXT NOT NULL CHECK(length(content_sha256)=64),
 basis_json TEXT NOT NULL CHECK(json_valid(basis_json)),
 basis_sha256 TEXT NOT NULL CHECK(length(basis_sha256)=64),
 created_at TEXT NOT NULL,
 UNIQUE(shot_id,number)
);
CREATE INDEX spatial_setup_project ON spatial_setups(project_id,archived,id);
CREATE INDEX spatial_asset_usage ON spatial_version_asset_pins(asset_id,version_id);
CREATE INDEX spatial_scene_usage ON spatial_version_scene_pins(scene_id,version_id);
CREATE INDEX spatial_media_usage ON spatial_version_media_pins(media_id,version_id);
CREATE INDEX spatial_source_node_usage ON spatial_version_source_pins(node_id,version_id);
CREATE INDEX spatial_source_observation_usage ON spatial_version_source_pins(observation_version_id,version_id);
CREATE INDEX spatial_binding_setup_usage ON shot_spatial_binding_versions(setup_version_id,binding_id);
CREATE TRIGGER spatial_setup_project_kind BEFORE INSERT ON spatial_setups BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM entities WHERE id=NEW.project_id AND kind='project')
 THEN RAISE(ABORT,'Spatial setup needs a project') END;
END;
CREATE TRIGGER spatial_binding_shot_kind BEFORE INSERT ON shot_spatial_bindings BEGIN
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM entities WHERE id=NEW.shot_id AND kind='shot')
 THEN RAISE(ABORT,'Spatial binding needs a shot') END;
END;

CREATE TRIGGER spatial_setups_bootstrap BEFORE INSERT ON spatial_setups
 WHEN NEW.revision<>1 OR NEW.current_version_id IS NOT NULL
 BEGIN SELECT RAISE(ABORT,'Bootstrap a spatial header without a head at revision one'); END;
CREATE TRIGGER spatial_setups_identity BEFORE UPDATE ON spatial_setups
 WHEN NEW.id<>OLD.id OR NEW.project_id<>OLD.project_id OR NEW.created_at<>OLD.created_at
 BEGIN SELECT RAISE(ABORT,'Spatial header identity is immutable'); END;
CREATE TRIGGER spatial_setups_advance BEFORE UPDATE ON spatial_setups BEGIN
 SELECT CASE WHEN NEW.current_version_id IS NULL OR NEW.current_version_id IS OLD.current_version_id
 THEN RAISE(ABORT,'Header updates require a new published version') END;
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM spatial_setup_versions v WHERE v.id=NEW.current_version_id AND v.setup_id=NEW.id AND v.sealed=1
 AND ((OLD.current_version_id IS NULL AND NEW.revision=OLD.revision AND v.number=1 AND v.parent_version_id IS NULL)
 OR (OLD.current_version_id IS NOT NULL AND NEW.revision=OLD.revision+1 AND v.parent_version_id=OLD.current_version_id
 AND v.number=(SELECT number+1 FROM spatial_setup_versions WHERE id=OLD.current_version_id))))
 THEN RAISE(ABORT,'Spatial head must advance to its sealed next child') END;
END;
CREATE TRIGGER spatial_setups_retain BEFORE DELETE ON spatial_setups
 BEGIN SELECT RAISE(ABORT,'Spatial history is retained'); END;
CREATE TRIGGER spatial_setup_versions_insert BEFORE INSERT ON spatial_setup_versions BEGIN
 SELECT CASE WHEN NEW.sealed<>0 THEN RAISE(ABORT,'Create spatial versions unsealed') END;
 SELECT CASE WHEN (NEW.parent_version_id IS NULL AND NEW.number<>1) OR
 (NEW.parent_version_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM spatial_setup_versions p
 WHERE p.id=NEW.parent_version_id AND p.setup_id=NEW.setup_id AND p.sealed=1 AND NEW.number=p.number+1))
 THEN RAISE(ABORT,'Spatial parent and sequence are invalid') END;
END;
CREATE TRIGGER spatial_setup_versions_seal_once BEFORE UPDATE ON spatial_setup_versions
 WHEN NOT(OLD.sealed=0 AND NEW.sealed=1 AND NEW.id IS OLD.id AND NEW.setup_id IS OLD.setup_id AND NEW.parent_version_id IS OLD.parent_version_id AND NEW.number IS OLD.number AND NEW.schema_version IS OLD.schema_version AND NEW.payload_json IS OLD.payload_json AND NEW.content_sha256 IS OLD.content_sha256 AND NEW.basis_json IS OLD.basis_json AND NEW.basis_sha256 IS OLD.basis_sha256 AND NEW.operation IS OLD.operation AND NEW.created_at IS OLD.created_at)
 BEGIN SELECT RAISE(ABORT,'Spatial versions only allow immutable sealing'); END;
CREATE TRIGGER spatial_setup_versions_retain BEFORE DELETE ON spatial_setup_versions
 BEGIN SELECT RAISE(ABORT,'Spatial versions are retained'); END;

CREATE TRIGGER shot_spatial_bindings_bootstrap BEFORE INSERT ON shot_spatial_bindings
 WHEN NEW.revision<>1 OR NEW.current_version_id IS NOT NULL
 BEGIN SELECT RAISE(ABORT,'Bootstrap a spatial header without a head at revision one'); END;
CREATE TRIGGER shot_spatial_bindings_identity BEFORE UPDATE ON shot_spatial_bindings
 WHEN NEW.id<>OLD.id OR NEW.shot_id<>OLD.shot_id OR NEW.created_at<>OLD.created_at
 BEGIN SELECT RAISE(ABORT,'Spatial header identity is immutable'); END;
CREATE TRIGGER shot_spatial_bindings_advance BEFORE UPDATE ON shot_spatial_bindings BEGIN
 SELECT CASE WHEN NEW.current_version_id IS NULL OR NEW.current_version_id IS OLD.current_version_id
 THEN RAISE(ABORT,'Header updates require a new published version') END;
 SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM shot_spatial_binding_versions v WHERE v.id=NEW.current_version_id AND v.binding_id=NEW.id AND v.sealed=1
 AND ((OLD.current_version_id IS NULL AND NEW.revision=OLD.revision AND v.number=1 AND v.parent_version_id IS NULL)
 OR (OLD.current_version_id IS NOT NULL AND NEW.revision=OLD.revision+1 AND v.parent_version_id=OLD.current_version_id
 AND v.number=(SELECT number+1 FROM shot_spatial_binding_versions WHERE id=OLD.current_version_id))))
 THEN RAISE(ABORT,'Spatial head must advance to its sealed next child') END;
END;
CREATE TRIGGER shot_spatial_bindings_retain BEFORE DELETE ON shot_spatial_bindings
 BEGIN SELECT RAISE(ABORT,'Spatial history is retained'); END;
CREATE TRIGGER shot_spatial_binding_versions_insert BEFORE INSERT ON shot_spatial_binding_versions BEGIN
 SELECT CASE WHEN NEW.sealed<>0 THEN RAISE(ABORT,'Create spatial versions unsealed') END;
 SELECT CASE WHEN (NEW.parent_version_id IS NULL AND NEW.number<>1) OR
 (NEW.parent_version_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM shot_spatial_binding_versions p
 WHERE p.id=NEW.parent_version_id AND p.binding_id=NEW.binding_id AND p.sealed=1 AND NEW.number=p.number+1))
 THEN RAISE(ABORT,'Spatial parent and sequence are invalid') END;
END;
CREATE TRIGGER shot_spatial_binding_versions_seal_once BEFORE UPDATE ON shot_spatial_binding_versions
 WHEN NOT(OLD.sealed=0 AND NEW.sealed=1 AND NEW.id IS OLD.id AND NEW.binding_id IS OLD.binding_id AND NEW.parent_version_id IS OLD.parent_version_id AND NEW.number IS OLD.number AND NEW.schema_version IS OLD.schema_version AND NEW.setup_version_id IS OLD.setup_version_id AND NEW.binding_json IS OLD.binding_json AND NEW.content_sha256 IS OLD.content_sha256 AND NEW.basis_json IS OLD.basis_json AND NEW.basis_sha256 IS OLD.basis_sha256 AND NEW.operation IS OLD.operation AND NEW.created_at IS OLD.created_at)
 BEGIN SELECT RAISE(ABORT,'Spatial versions only allow immutable sealing'); END;
CREATE TRIGGER shot_spatial_binding_versions_retain BEFORE DELETE ON shot_spatial_binding_versions
 BEGIN SELECT RAISE(ABORT,'Spatial versions are retained'); END;

CREATE TRIGGER spatial_version_scene_pins_unsealed BEFORE INSERT ON spatial_version_scene_pins
 WHEN NOT EXISTS(SELECT 1 FROM spatial_setup_versions WHERE id=NEW.version_id AND sealed=0)
 BEGIN SELECT RAISE(ABORT,'Pins require an unsealed spatial version'); END;
CREATE TRIGGER spatial_version_scene_pins_no_update BEFORE UPDATE ON spatial_version_scene_pins
 BEGIN SELECT RAISE(ABORT,'Spatial pins are immutable'); END;
CREATE TRIGGER spatial_version_scene_pins_no_delete BEFORE DELETE ON spatial_version_scene_pins
 BEGIN SELECT RAISE(ABORT,'Spatial pins are retained'); END;

CREATE TRIGGER spatial_version_asset_pins_unsealed BEFORE INSERT ON spatial_version_asset_pins
 WHEN NOT EXISTS(SELECT 1 FROM spatial_setup_versions WHERE id=NEW.version_id AND sealed=0)
 BEGIN SELECT RAISE(ABORT,'Pins require an unsealed spatial version'); END;
CREATE TRIGGER spatial_version_asset_pins_no_update BEFORE UPDATE ON spatial_version_asset_pins
 BEGIN SELECT RAISE(ABORT,'Spatial pins are immutable'); END;
CREATE TRIGGER spatial_version_asset_pins_no_delete BEFORE DELETE ON spatial_version_asset_pins
 BEGIN SELECT RAISE(ABORT,'Spatial pins are retained'); END;

CREATE TRIGGER spatial_version_media_pins_unsealed BEFORE INSERT ON spatial_version_media_pins
 WHEN NOT EXISTS(SELECT 1 FROM spatial_setup_versions WHERE id=NEW.version_id AND sealed=0)
 BEGIN SELECT RAISE(ABORT,'Pins require an unsealed spatial version'); END;
CREATE TRIGGER spatial_version_media_pins_no_update BEFORE UPDATE ON spatial_version_media_pins
 BEGIN SELECT RAISE(ABORT,'Spatial pins are immutable'); END;
CREATE TRIGGER spatial_version_media_pins_no_delete BEFORE DELETE ON spatial_version_media_pins
 BEGIN SELECT RAISE(ABORT,'Spatial pins are retained'); END;

CREATE TRIGGER spatial_version_source_pins_unsealed BEFORE INSERT ON spatial_version_source_pins
 WHEN NOT EXISTS(SELECT 1 FROM spatial_setup_versions WHERE id=NEW.version_id AND sealed=0)
 BEGIN SELECT RAISE(ABORT,'Pins require an unsealed spatial version'); END;
CREATE TRIGGER spatial_version_source_pins_no_update BEFORE UPDATE ON spatial_version_source_pins
 BEGIN SELECT RAISE(ABORT,'Spatial pins are immutable'); END;
CREATE TRIGGER spatial_version_source_pins_no_delete BEFORE DELETE ON spatial_version_source_pins
 BEGIN SELECT RAISE(ABORT,'Spatial pins are retained'); END;

CREATE TRIGGER spatial_scene_pin_kind BEFORE INSERT ON spatial_version_scene_pins
 WHEN NOT EXISTS(SELECT 1 FROM entities WHERE id=NEW.scene_id AND kind='scene')
 BEGIN SELECT RAISE(ABORT,'Scene pin must reference a scene'); END;
CREATE TRIGGER spatial_asset_pin_kind BEFORE INSERT ON spatial_version_asset_pins
 WHEN NOT EXISTS(SELECT 1 FROM entities WHERE id=NEW.asset_id AND kind='asset')
 BEGIN SELECT RAISE(ABORT,'Asset pin must reference a library asset'); END;
CREATE TRIGGER spatial_source_scope BEFORE INSERT ON spatial_version_source_pins BEGIN
 SELECT CASE WHEN NEW.source_kind='document-node' AND NOT EXISTS(
 SELECT 1 FROM document_nodes n JOIN document_versions v ON v.id=n.version_id
 WHERE n.id=NEW.node_id AND v.id=NEW.document_version_id AND v.document_id=NEW.document_id)
 THEN RAISE(ABORT,'Spatial source node is outside its declared document version') END;
 SELECT CASE WHEN NEW.source_kind='observation-v1' AND NOT EXISTS(
 SELECT 1 FROM observation_contract_versions WHERE id=NEW.observation_version_id AND sealed=1)
 THEN RAISE(ABORT,'Spatial observation source must be sealed') END;
END;
CREATE TRIGGER spatial_binding_setup_sealed BEFORE INSERT ON shot_spatial_binding_versions
 WHEN NOT EXISTS(SELECT 1 FROM spatial_setup_versions WHERE id=NEW.setup_version_id AND sealed=1)
 BEGIN SELECT RAISE(ABORT,'Bind an exact sealed setup version'); END;
CREATE TRIGGER observation_spatial_review_scope BEFORE INSERT ON observation_spatial_reviews BEGIN
 SELECT CASE WHEN NOT EXISTS(
 SELECT 1 FROM observation_contract_versions v JOIN observation_contracts c ON c.id=v.contract_id
 WHERE v.id=NEW.observation_version_id AND v.sealed=1 AND c.shot_id=NEW.shot_id)
 THEN RAISE(ABORT,'V2 review requires the same shot observation') END;
 SELECT CASE WHEN NOT EXISTS(
 SELECT 1 FROM shot_spatial_binding_versions v JOIN shot_spatial_bindings b ON b.id=v.binding_id
 WHERE v.id=NEW.binding_version_id AND v.sealed=1 AND b.shot_id=NEW.shot_id)
 THEN RAISE(ABORT,'V2 review requires the same shot binding') END;
 SELECT CASE WHEN (NEW.number=1 AND (NEW.parent_review_id IS NOT NULL OR EXISTS(SELECT 1 FROM observation_spatial_reviews WHERE shot_id=NEW.shot_id)))
 OR (NEW.number>1 AND NOT EXISTS(SELECT 1 FROM observation_spatial_reviews p WHERE p.id=NEW.parent_review_id
 AND p.shot_id=NEW.shot_id AND p.number=NEW.number-1
 AND p.number=(SELECT max(number) FROM observation_spatial_reviews WHERE shot_id=NEW.shot_id)))
 THEN RAISE(ABORT,'V2 review must append to its shot history') END;
END;
CREATE TRIGGER observation_spatial_review_no_update BEFORE UPDATE ON observation_spatial_reviews
 BEGIN SELECT RAISE(ABORT,'V2 reviews are immutable'); END;
CREATE TRIGGER observation_spatial_review_no_delete BEFORE DELETE ON observation_spatial_reviews
 BEGIN SELECT RAISE(ABORT,'V2 reviews are retained'); END;

-- Destination-local import receipts never rewrite exact imported version hashes.
CREATE TABLE spatial_import_receipts (
 id TEXT PRIMARY KEY,
 package_sha256 TEXT NOT NULL CHECK(length(package_sha256)=64),
 original_path TEXT NOT NULL,
 producer_json TEXT NOT NULL CHECK(json_valid(producer_json)),
 mapping_json TEXT NOT NULL CHECK(json_valid(mapping_json)),
 imported_records_json TEXT NOT NULL CHECK(json_valid(imported_records_json)),
 created_at TEXT NOT NULL
);
CREATE INDEX spatial_import_package ON spatial_import_receipts(package_sha256,id);
CREATE TRIGGER spatial_import_receipt_no_update BEFORE UPDATE ON spatial_import_receipts
 BEGIN SELECT RAISE(ABORT,'Spatial import receipts are immutable'); END;
CREATE TRIGGER spatial_import_receipt_no_delete BEFORE DELETE ON spatial_import_receipts
 BEGIN SELECT RAISE(ABORT,'Spatial import receipts are retained'); END;

-- Operation IDs provide response-loss lookup and reject duplicate publications.
CREATE UNIQUE INDEX spatial_operation_once ON events(json_extract(details,'$.operation_id'))
 WHERE action GLOB 'spatial.*' AND json_type(details,'$.operation_id')='text';
