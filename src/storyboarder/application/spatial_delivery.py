"""Immutable, opt-in delivery; legacy composition adapters remain unchanged."""
from __future__ import annotations

from io import BytesIO
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

from filelock import FileLock
from storyboarder.domain.spatial import canonical,sha,SpatialError
from storyboarder.media.files import safe_path
from storyboarder.storage.repository import SNAPSHOT_TABLES,unpack as unpack_legacy
from storyboarder.rendering.composer import compose
from storyboarder.rendering.spatial_diagrams import diagrams
from .spatial_plans import SpatialPlans


def zip_bytes(files):
    output=BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_STORED) as archive:
        for name,content in sorted(files.items()):
            info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.external_attr=0o100644<<16
            archive.writestr(info,content)
    return output.getvalue()


def publish(service,files,kind='scenes'):
    """Content-addressed directory promotion; edited existing exports are sacred."""
    manifest={'schema':'storyboarder.spatial-output-manifest/v1','files':[{'path':k,'sha256':hashlib.sha256(v).hexdigest(),'size':len(v)} for k,v in sorted(files.items())]}
    digest=sha(manifest)
    files=files|{'manifest.json':canonical(manifest).encode()}
    files=files|{'packet.zip':zip_bytes(files)}
    base=safe_path(service.root,'exports/'+kind);base.mkdir(parents=True,exist_ok=True)
    destination=safe_path(service.root,f'exports/{kind}/spatial-{digest}')
    staging_root=safe_path(service.root,'.storyboarder/staging');staging_root.mkdir(parents=True,exist_ok=True)
    lockpath=safe_path(service.root,'exports/.spatial-export.lock')
    with FileLock(str(lockpath),timeout=10):
        if destination.exists():
            actual={p.relative_to(destination).as_posix() for p in destination.rglob('*') if p.is_file()}
            if any(p.is_symlink() for p in destination.rglob('*')) or actual!=set(files):raise SpatialError('Existing spatial export was edited. It was not overwritten.')
            for name,content in files.items():
                if safe_path(destination,name,must_exist=True).read_bytes()!=content:raise SpatialError('Existing spatial export was edited. It was not overwritten.')
        else:
            temporary=Path(tempfile.mkdtemp(prefix='spatial-export-',dir=staging_root))
            try:
                for name,content in files.items():
                    path=safe_path(temporary,name);path.parent.mkdir(parents=True,exist_ok=True)
                    with path.open('xb') as handle:handle.write(content);handle.flush();os.fsync(handle.fileno())
                os.replace(temporary,destination)
            finally:
                if temporary.exists():shutil.rmtree(temporary)
    relative=destination.relative_to(service.root).as_posix()
    return {'schema':'storyboarder.spatial-output/v1','archive':relative+'/packet.zip','files':[relative+'/'+k for k in sorted(files)],'sha256':digest,'manifest':manifest}


def snapshot_on(conn):
    """The same bounded current-state shape, captured on the caller's transaction."""
    result={table:[unpack_legacy(r) for r in conn.execute(f'SELECT * FROM {table} ORDER BY id')] for table in sorted(SNAPSHOT_TABLES)}
    tags,aliases={},{}
    for row in conn.execute('SELECT * FROM entity_tags ORDER BY tag'):tags.setdefault(row['entity_id'],[]).append(row['tag'])
    for row in conn.execute('SELECT * FROM aliases ORDER BY name'):aliases.setdefault(row['entity_id'],[]).append(row['name'])
    for e in result['entities']:e['tags'],e['aliases']=tags.get(e['id'],[]),aliases.get(e['id'],[])
    result['events']=[unpack_legacy(r) for r in conn.execute('SELECT * FROM events ORDER BY id DESC LIMIT 60')]
    return result


def diagram_export(service,version_id=None,binding_version_id=None,times_us=None,target_plane_z_m=0.0,view_bounds=None,format='all'):
    plans=SpatialPlans(service)
    if bool(version_id)==bool(binding_version_id):raise SpatialError('Choose one exact setup version or binding version.')
    with service.repo.transaction(False) as conn:
        binding=plans._binding_version(conn,binding_version_id) if binding_version_id else None
        version=plans._version(conn,binding['setup_version_id'] if binding else version_id)
        pins=plans._preserved(conn,version)
        wrapper={'schema':'storyboarder.spatial-delivery/v1','setup':version,'pins':pins,'binding':binding,'composition':None,'reviews':[]}
        media=[]
        if binding:
            header=plans._binding_header(conn,binding_id=binding['binding_id'])
            state=snapshot_on(conn)
            wrapper['composition']=compose(state,header['shot_id'])
            wrapper['reviews']=[dict(r) for r in conn.execute('SELECT * FROM observation_spatial_reviews WHERE binding_version_id=? ORDER BY number',(binding['id'],))]
            required={m['id'] for m in wrapper['composition']['media']}
            media=[m for m in state['media'] if m['id'] in required]
            if times_us is None:
                sample=binding['binding_json']['sample'];times_us=[sample['time_us']] if sample['kind']=='instant' else [sample['start_us'],sample['end_us']]
        times_us=times_us if times_us is not None else [0]
    files=diagrams(version['payload_json'],version['id'],version['setup_id'],version['content_sha256'],times_us,target_plane_z_m,view_bounds,format)
    files['delivery.json']=canonical(wrapper).encode()
    for record in media:
        raw=safe_path(service.root,record['path'],must_exist=True).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=record['sha256']:raise SpatialError('Media changed during spatial export.',code='spatial_integrity')
        files['media/'+record['sha256']+Path(record['path']).suffix.lower()]=raw
    return publish(service,files,'boards')
