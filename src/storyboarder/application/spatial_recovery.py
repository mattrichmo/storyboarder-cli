"""Read-only spatial doctor and consistent portable recovery augmentation."""
from __future__ import annotations

from contextlib import closing
from io import BytesIO
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import zipfile

from storyboarder.domain.spatial import checked,canonical,SpatialBinding,SpatialReview,SpatialError,validate_binding,sha
from storyboarder.domain.errors import StoryboardError
from storyboarder.media.files import safe_path
from .spatial_plans import SpatialPlans,raw_hash,unpack


def inspect_connection(service,conn,*,check_reviews=True):
    plans=SpatialPlans(service);issues=[]
    def issue(code,record,exc):
        if len(issues)<500:issues.append({'severity':'error','code':code,'id':record,'message':str(exc)[:500]})
    for h in conn.execute('SELECT * FROM spatial_setups ORDER BY id'):
        try:
            if h['project_id']!=plans.project_id:raise SpatialError('Setup project identity mismatch.')
            versions=list(conn.execute('SELECT id,parent_version_id,number,sealed FROM spatial_setup_versions WHERE setup_id=? ORDER BY number',(h['id'],)))
            if not versions or h['current_version_id']!=versions[-1]['id'] or h['revision']!=len(versions):raise SpatialError('Missing, orphaned or incorrect setup head.')
            for i,v in enumerate(versions):
                if not v['sealed'] or v['number']!=i+1 or v['parent_version_id']!=(versions[i-1]['id'] if i else None):raise SpatialError('Unsealed or broken setup version chain.')
            for entry in versions:
                v=plans._version(conn,entry['id']);body=checked(v['payload_json'])
                if canonical(body)!=canonical(v['payload_json']):raise SpatialError('Stored payload is not normalized canonical data.')
                pins=plans._preserved(conn,v)
                if {p['scene_id'] for p in pins['scene']}!=set(body['scene_ids']):raise SpatialError('Scene JSON/pin mismatch.')
                assets=set()
                if body['location_asset_id']:assets.add((plans.project_id,'location',body['location_asset_id']))
                for group in ('instances','resources','cameras','lights','modifiers'):
                    for item in body[group]:
                        if item.get('asset_id'):assets.add((item['id'],'identity',item['asset_id']))
                        if item.get('reference_asset_id'):assets.add((item['id'],'reference',item['reference_asset_id']))
                if assets!={(p['owner_id'],p['role'],p['asset_id']) for p in pins['asset']}:raise SpatialError('Asset JSON/pin mismatch.')
                if {(p['id'],p['media_id'],p['media_sha256']) for p in body['floor_plans']}!={(p['owner_id'],p['media_id'],p['media_sha256']) for p in pins['media']}:raise SpatialError('Floor-plan JSON/pin mismatch.')
                if {(p['id'],p['kind']) for p in body['source_pins']}!={(p['pin_id'],p['source_kind']) for p in pins['source']}:raise SpatialError('Source JSON/pin mismatch.')
                if plans._basis(body,pins)!=v['basis_json']:raise SpatialError('Spatial basis differs from retained pins/physical semantics.')
        except (StoryboardError,KeyError,ValueError,TypeError) as exc:issue('spatial_integrity',h['id'],exc)
    for h in conn.execute('SELECT * FROM shot_spatial_bindings ORDER BY id'):
        try:
            shot=plans._entity(conn,h['shot_id'],'shot',False)
            versions=list(conn.execute('SELECT id,number,parent_version_id,sealed FROM shot_spatial_binding_versions WHERE binding_id=? ORDER BY number',(h['id'],)))
            if not versions or h['current_version_id']!=versions[-1]['id'] or h['revision']!=len(versions):raise SpatialError('Broken binding head.')
            for i,e in enumerate(versions):
                if not e['sealed'] or e['number']!=i+1 or e['parent_version_id']!=(versions[i-1]['id'] if i else None):raise SpatialError('Broken binding chain.')
                v=plans._binding_version(conn,e['id']);body=checked(v['binding_json'],SpatialBinding);basis=v['basis_json']
                setup=plans._version(conn,v['setup_version_id'])
                if body['setup_version_id']!=v['setup_version_id'] or basis['project_id']!=plans.project_id or basis['shot_id']!=h['shot_id']:raise SpatialError('Binding relational/basis identities differ.')
                if basis['setup_content_sha256']!=setup['content_sha256'] or basis['physical_sha256']!=setup['basis_json']['physical_sha256']:raise SpatialError('Binding exact setup hash mismatch.')
                validate_binding(body,setup['payload_json'],basis['parent_scene_id'],basis.get('shot_fields',{}).get('duration'))
                if e['id']==h['current_version_id'] and body['status']=='active' and shot['parent_id'] not in setup['payload_json']['scene_ids']:raise SpatialError('Current active binding scope mismatch.')
        except (StoryboardError,KeyError,ValueError,TypeError) as exc:issue('spatial_binding_integrity',h['id'],exc)
    last={}
    for r in conn.execute('SELECT * FROM observation_spatial_reviews ORDER BY shot_id,number'):
        try:
            if raw_hash(r['review_json'])!=r['content_sha256'] or raw_hash(r['basis_json'])!=r['basis_sha256']:raise SpatialError('Review hash mismatch.')
            body=checked(json.loads(r['review_json']),SpatialReview)
            previous=last.get(r['shot_id'])
            if r['number']!=(previous['number']+1 if previous else 1) or r['parent_review_id']!=(previous['id'] if previous else None):raise SpatialError('Broken review history.')
            last[r['shot_id']]=dict(r)
            if body['binding_version_id']!=r['binding_version_id'] or body['observation_version_id']!=r['observation_version_id']:raise SpatialError('Review JSON/pin mismatch.')
            binding=plans._binding_version(conn,r['binding_version_id']);header=plans._binding_header(conn,binding_id=binding['binding_id'])
            obs=conn.execute('SELECT v.*,c.shot_id FROM observation_contract_versions v JOIN observation_contracts c ON c.id=v.contract_id WHERE v.id=? AND sealed=1',(r['observation_version_id'],)).fetchone()
            if header['shot_id']!=r['shot_id'] or not obs or obs['shot_id']!=r['shot_id']:raise SpatialError('Review must pin same-shot v1/binding history.')
            basis=json.loads(r['basis_json'])
            if basis['binding_sha256']!=binding['content_sha256'] or basis['observation_content_sha256']!=obs['content_sha256'] or basis['observation_basis_sha256']!=obs['basis_sha256']:raise SpatialError('Review exact dependency hash mismatch.')
            if check_reviews:
                from .spatial_review import SpatialReviews
                status=SpatialReviews(service)._status(conn,unpack(r))
                if any(x['code']=='integrity_failure' for x in status['reasons']):raise SpatialError('Review dependency integrity failure.')
        except (StoryboardError,KeyError,ValueError,TypeError) as exc:issue('spatial_review_integrity',r['id'],exc)
    for receipt in conn.execute('SELECT * FROM spatial_import_receipts'):
        try:plans._file(receipt['original_path'],receipt['package_sha256'])
        except (StoryboardError,OSError) as exc:issue('spatial_import_original',receipt['id'],exc)
    return issues


def doctor(service):
    tables=('spatial_setups','spatial_setup_versions','shot_spatial_bindings','shot_spatial_binding_versions','observation_spatial_reviews','spatial_import_receipts')
    try:
        with service.repo.readonly_transaction() as conn:
            available={row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            missing=[table for table in tables if table not in available]
            if missing:
                issues=[{'severity':'error','code':'spatial_schema_incomplete','message':'Spatial project data could not be checked because required tables are missing. Preserve the project folder and inspect a verified backup.','details':{'missing_tables':missing}}]
                return {'schema':'storyboarder.spatial-health/v1','healthy':False,'issues':issues,'counts':{},'read_only':True,'issues_truncated':False}
            issues=inspect_connection(service,conn)
            counts={table:conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in tables}
            return {'schema':'storyboarder.spatial-health/v1','healthy':not issues,'issues':issues,'counts':counts,'read_only':True,'issues_truncated':len(issues)>=500}
    except Exception as exc:
        issues=[{'severity':'error','code':'spatial_database_unavailable','message':'Spatial project data could not be checked safely. Preserve the project folder and inspect a verified backup.','details':{'error_type':type(exc).__name__}}]
        return {'schema':'storyboarder.spatial-health/v1','healthy':False,'issues':issues,'counts':{},'read_only':True,'issues_truncated':False}


def backup(service):
    """Augment the existing consistent backup using its saved DB, not live refs.

The captured DB enumerates receipt originals. Later bytes are hash-checked;
publication of a newer setup cannot alter this backup's dependency closure.
"""
    from .recovery import backup as legacy_backup,MAX_BACKUP_BYTES,MAX_BACKUP_FILES
    result=legacy_backup(service)
    archive=safe_path(service.root,result['path'],must_exist=True)
    original_digest=result['sha256']
    temp=Path(tempfile.mkdtemp(prefix='spatial-backup-'))
    try:
        with zipfile.ZipFile(archive) as original:
            db=temp/'snapshot.sqlite3'
            with original.open('.storyboarder/storyboard.sqlite3') as inp,db.open('wb') as out:shutil.copyfileobj(inp,out)
            with closing(sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True)) as conn:
                receipts=conn.execute('SELECT original_path,package_sha256 FROM spatial_import_receipts ORDER BY original_path').fetchall()
            if not receipts:return result
            manifest=json.loads(original.read('backup.json'));existing={r['path'] for r in manifest['files']}
            additional={}
            for path,expected in receipts:
                if path in existing:continue
                file=safe_path(service.root,path,must_exist=True)
                if hashlib.sha256(file.read_bytes()).hexdigest()!=expected:raise SpatialError('An imported original changed during backup.',code='spatial_integrity')
                additional[path]=(file,expected)
                manifest['files'].append({'path':path,'size':file.stat().st_size,'sha256':expected})
            manifest['files'].sort(key=lambda r:r['path'])
            if len(manifest['files'])+1>MAX_BACKUP_FILES or sum(r['size'] for r in manifest['files'])>MAX_BACKUP_BYTES:raise SpatialError('Backup exceeds restore limits.')
            replacement=temp/'backup.zip'
            with zipfile.ZipFile(replacement,'w',zipfile.ZIP_DEFLATED) as out:
                for item in original.infolist():
                    if item.filename=='backup.json':continue
                    with original.open(item) as source,out.open(item.filename,'w') as dest:shutil.copyfileobj(source,dest)
                for name,(file,expected) in additional.items():
                    raw=file.read_bytes()
                    if hashlib.sha256(raw).hexdigest()!=expected:raise SpatialError('Import original changed while copying backup.')
                    out.writestr(name,raw)
                out.writestr('backup.json',canonical(manifest))
        if hashlib.sha256(archive.read_bytes()).hexdigest()!=original_digest:raise SpatialError('Backup was modified before augmentation; it was not replaced.')
        staged=archive.with_suffix('.spatial-part')
        try:shutil.copyfile(replacement,staged);os.replace(staged,archive)
        finally:staged.unlink(missing_ok=True)
        return result|{'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'size':archive.stat().st_size,'manifest':manifest}
    finally:shutil.rmtree(temp)


def restore(archive,destination):
    from .recovery import restore as legacy_restore
    from .service import Service
    from .projects import Project
    destination=Path(destination).expanduser().absolute()
    if destination.exists() or destination.is_symlink():raise SpatialError('Restore into a new destination, never over a live project.')
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=Path(tempfile.mkdtemp(prefix='.spatial-restore-',dir=destination.parent))
    try:
        staged=temporary/'project';legacy_restore(archive,staged)
        health=doctor(Service(Project(staged)))
        if not health['healthy']:raise SpatialError('Spatial restore failed integrity checks; no destination was created.',health,'spatial_integrity')
        os.rename(staged,destination)
        return Project(destination).summary()
    finally:shutil.rmtree(temporary)
