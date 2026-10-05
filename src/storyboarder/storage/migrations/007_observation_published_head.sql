-- Once a version is published, its contract header must always retain a
-- pointer to a published version. Bootstrap still starts with NULL and the
-- first sealed version can still be published by the existing guards.
CREATE TRIGGER observation_contract_published_head_cannot_clear
BEFORE UPDATE OF current_version_id ON observation_contracts
WHEN OLD.current_version_id IS NOT NULL AND NEW.current_version_id IS NULL
BEGIN
 SELECT RAISE(ABORT,'A published observation contract head cannot be cleared');
END;
