"""Managed-media and explicit legacy-source integrity across both authoring models."""
from .models import ProductionError


def media_refs(value):
    if isinstance(value,dict):
        if set(value)=={'media_id','path','sha256','description'}:
            yield value
        else:
            for child in value.values():
                yield from media_refs(child)
    elif isinstance(value,list):
        for child in value:
            yield from media_refs(child)


def validate_external(conn,record):
    for ref in media_refs(record['data']):
        if ref['media_id']:
            row=conn.execute('SELECT path,sha256 FROM media WHERE id=?',(ref['media_id'],)).fetchone()
            if row is None:
                raise ProductionError('Managed-media prerequisite is missing. Import the media first, or restore a full project backup.',{'reference':ref})
            if ref['path'] and ref['path']!=row['path'] or ref['sha256'] and ref['sha256']!=row['sha256']:
                raise ProductionError('Managed-media ID, path and content hash disagree.',{'reference':ref})
    prov=record['data']['provenance']
    if prov['legacy_entity_id'] and not conn.execute('SELECT 1 FROM entities WHERE id=?',(prov['legacy_entity_id'],)).fetchone():
        raise ProductionError('Legacy source identity is absent. A graph package does not transfer legacy data; use a full project backup.',{'entity_id':prov['legacy_entity_id']})


def insert_external(conn,record):
    media={ref['media_id'] for ref in media_refs(record['data']) if ref['media_id']}
    for mid in sorted(media):
        conn.execute('INSERT INTO production_media_pins VALUES(?,?,?)',(record['id'],record['version'],mid))
    legacy=record['data']['provenance']['legacy_entity_id']
    if legacy:
        conn.execute('INSERT INTO production_legacy_pins VALUES(?,?,?)',(record['id'],record['version'],legacy))


def verify_external(conn,record):
    validate_external(conn,record)
    expected={ref['media_id'] for ref in media_refs(record['data']) if ref['media_id']}
    actual={r[0] for r in conn.execute('SELECT media_id FROM production_media_pins WHERE source_id=? AND source_version=?',(record['id'],record['version']))}
    legacy=record['data']['provenance']['legacy_entity_id']
    actual_legacy={r[0] for r in conn.execute('SELECT entity_id FROM production_legacy_pins WHERE source_id=? AND source_version=?',(record['id'],record['version']))}
    if expected!=actual or actual_legacy!=({legacy} if legacy else set()):
        raise ProductionError('External production pin index differs from immutable history.',{'id':record['id'],'version':record['version']})
