-- Exact historical context pins are restored against the parent scene saved
-- in that immutable version, never an arbitrary scene or the shot's new parent.
DROP TRIGGER IF EXISTS observation_source_pin_validate;
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
     AND json_extract(v.basis_json,'$.shot.shot_id')=c.shot_id
     AND EXISTS(SELECT 1 FROM json_each(v.contract_json,'$.source_pins') declared
       WHERE json_extract(declared.value,'$.edge_id')=NEW.edge_id
         AND json_extract(declared.value,'$.source_scope')=NEW.source_scope)
     AND json_extract(NEW.source_snapshot,'$.document_id')=d.id
     AND json_extract(NEW.source_snapshot,'$.document_version_id')=dv.id
     AND json_extract(NEW.source_snapshot,'$.document_sha256')=dv.content_sha256
     AND json_extract(NEW.source_snapshot,'$.artifact_sha256')=NEW.artifact_sha256
     AND json_extract(NEW.source_snapshot,'$.node_id')=n.id
     AND json_extract(NEW.source_snapshot,'$.logical_id')=n.logical_id
     AND json_extract(NEW.source_snapshot,'$.node_type')=n.node_type
     AND json_extract(NEW.source_snapshot,'$.identity')=n.identity
     AND json_extract(NEW.source_snapshot,'$.source_sha256')=n.content_sha256
     AND json_extract(NEW.source_snapshot,'$.scope_sha256')=NEW.scope_sha256
     AND json(json_extract(NEW.source_snapshot,'$.payload'))=json(n.payload)
     AND NEW.edge_source_snapshot=e.source_snapshot
     AND NEW.edge_target_snapshot=e.target_snapshot
     AND json_extract(NEW.edge_source_snapshot,'$.id')=n.id
     AND json_extract(NEW.edge_source_snapshot,'$.version_id')=dv.id
     AND json_extract(NEW.edge_source_snapshot,'$.logical_id')=n.logical_id
     AND json_extract(NEW.edge_source_snapshot,'$.content_sha256')=n.content_sha256
     AND json_extract(NEW.edge_target_snapshot,'$.id')=e.target_id
     AND (
       (e.target_id=c.shot_id AND NEW.source_scope='direct-element')
       OR
       (NEW.source_scope='scene-context'
          AND e.target_id=CASE WHEN observation_restore_authorized()=1
                               THEN json_extract(v.basis_json,'$.shot.parent_scene_id')
                               ELSE shot.parent_id END
          AND EXISTS(SELECT 1 FROM entities scene WHERE scene.id=e.target_id AND scene.kind='scene'
            AND (scene.archived=0 OR observation_restore_authorized()=1)))
     )
 ) THEN RAISE(ABORT,'Observation source pin does not match an active exact screenplay edge') END;
END;

-- Retain every identity referenced by any immutable contract version. The
-- service usage preflight provides actionable errors; triggers protect raw SQL.
CREATE TRIGGER observation_contract_owner_shot_retention BEFORE DELETE ON entities
 WHEN OLD.kind='shot' AND EXISTS(SELECT 1 FROM observation_contracts WHERE shot_id=OLD.id)
 BEGIN SELECT RAISE(ABORT,'Shot has retained observation contract history'); END;

CREATE TRIGGER observation_reference_asset_retention BEFORE DELETE ON entities
 WHEN OLD.kind='asset' AND EXISTS(SELECT 1 FROM observation_reference_pins WHERE reference_id=OLD.id)
 BEGIN SELECT RAISE(ABORT,'Asset has retained observation contract references'); END;

CREATE TRIGGER observation_continuity_shot_retention BEFORE DELETE ON entities
 WHEN OLD.kind='shot' AND EXISTS(
   SELECT 1
   FROM observation_contract_versions version,
        json_each(version.contract_json,'$.continuity') continuity,
        json_each(continuity.value,'$.related_shot_ids') related
   WHERE related.value=OLD.id
 ) BEGIN SELECT RAISE(ABORT,'Shot has retained observation continuity history'); END;
