"""Inert native spatial packages with reviewed exact import or copy-as-new-root.

No third-party scene importer, executable SVG, external fetch, or live sync.
Exact import preserves canonical version and pin bytes; mappings and receipt
paths belong to a separate destination-local receipt, never those bytes.
"""
from __future__ import annotations

import base64
import binascii
from copy import deepcopy
from io import BytesIO
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import zipfile

from filelock import FileLock
from storyboarder import __version__
from storyboarder.domain.errors import StoryboardError, Conflict
from storyboarder.domain.models import now,uid
from storyboarder.domain.spatial import SpatialError,checked,canonical,sha,FRAME,SpatialBinding,SpatialReview,validate_binding
from storyboarder.media.files import safe_path,inspect_image,FORMATS,safe_name
from .spatial_plans import SpatialPlans,raw_hash,unpack
from .spatial_delivery import zip_bytes,publish

PACKAGE='storyboarder.spatial-package/v1'
MAX_COMPRESSED=100*1024*1024
MAX_EXPANDED=500*1024*1024
MAX_ENTRIES=2000
TABLES=('spatial_setups','spatial_setup_versions','spatial_version_scene_pins','spatial_version_asset_pins','spatial_version_media_pins','spatial_version_source_pins','shot_spatial_bindings','shot_spatial_binding_versions','observation_spatial_reviews')


def inert_json(raw):
    if len(raw)>80*1024*1024:raise SpatialError('Native package JSON exceeds 80 MiB.',code='spatial_limit_exceeded')
    def pairs(values):
        d={}
        for k,v in values:
            if k in d:raise ValueError('Duplicate JSON key')
            d[k]=v
        return d
    try:
        value=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Non-finite JSON')))
        stack=[(value,0)];count=0
        while stack:
            item,depth=stack.pop();count+=1
            if depth>64 or count>2_000_000:raise ValueError('Package nesting/count limit')
            if isinstance(item,dict):stack.extend((v,depth+1) for v in item.values())
            elif isinstance(item,list):stack.extend((v,depth+1) for v in item)
        return value
    except (ValueError,TypeError,RecursionError) as exc:raise SpatialError('Invalid native package JSON.',{'reason':str(exc)[:240]},'spatial_import_conflict') from exc


def decode(package=None,archive_base64=None):
    if (package is None)==(archive_base64 is None):raise SpatialError('Supply a package object or base64 ZIP, not both.')
    if archive_base64 is not None:
        if not isinstance(archive_base64,str) or len(archive_base64)>((MAX_COMPRESSED+2)//3)*4:raise SpatialError('Archive exceeds 100 MiB.',code='spatial_limit_exceeded')
        try:raw=base64.b64decode(archive_base64,validate=True)
        except (ValueError,binascii.Error) as exc:raise SpatialError('Archive base64 is malformed.') from exc
        if len(raw)>MAX_COMPRESSED:raise SpatialError('Archive exceeds 100 MiB.',code='spatial_limit_exceeded')
        files={}
        try:
            with zipfile.ZipFile(BytesIO(raw)) as z:
                infos=z.infolist()
                if len(infos)>MAX_ENTRIES or sum(i.file_size for i in infos)>MAX_EXPANDED:raise SpatialError('Archive expansion/count limit exceeded.',code='spatial_limit_exceeded')
                seen=set()
                for i in infos:
                    p=PurePosixPath(i.filename)
                    if i.filename in seen or p.is_absolute() or '..' in p.parts or '\\' in i.filename or ':' in i.filename or '\x00' in i.filename or stat.S_ISLNK(i.external_attr>>16) or i.flag_bits&1:
                        raise SpatialError('Unsafe archive path, duplicate, symlink or encrypted entry.',code='spatial_import_conflict')
                    seen.add(i.filename)
                    if i.file_size>max(i.compress_size,1)*100:raise SpatialError('Archive expansion ratio exceeds 100:1.',code='spatial_limit_exceeded')
                    if i.is_dir():continue
                    if i.filename!='package.json' and not i.filename.startswith('media/'):
                        raise SpatialError('Native archive contains an unsupported entry.',code='spatial_import_conflict')
                    files[i.filename]=z.read(i)
        except (zipfile.BadZipFile,RuntimeError,EOFError,NotImplementedError) as exc:raise SpatialError('Invalid or unsupported ZIP.') from exc
        if 'package.json' not in files:raise SpatialError('ZIP has no package.json.')
        package=inert_json(files.pop('package.json'))
    else:
        encoded=canonical(package).encode();package=inert_json(encoded);files={};raw=zip_bytes({'package.json':encoded})
    expected={'schema','producer','project_id','frame','time_unit','scope','tables','media','capabilities','extensions'}
    if not isinstance(package,dict) or set(package)!=expected or package['schema']!=PACKAGE or package['frame']!=FRAME or package['time_unit']!='microseconds':
        raise SpatialError('Unsupported package schema or coordinate/time convention.',code='spatial_import_conflict')
    if package['scope'] not in ('full-history','selected-with-history-closure','sparse-snapshot'):raise SpatialError('Unsupported package scope.')
    if not isinstance(package['extensions'],dict) or any(':' not in key for key in package['extensions']):raise SpatialError('Opaque extension keys must be namespaced.')
    if package['capabilities']!={'required':['spatial-plan/v1','exact-source-pins/v1'],'unsupported':[]}:
        raise SpatialError('Unknown required package capabilities block import.',code='spatial_import_conflict')
    if not isinstance(package['tables'],dict) or set(package['tables'])!=set(TABLES):raise SpatialError('Package table envelope is incomplete.')
    if any(not isinstance(rows,list) or len(rows)>10000 for rows in package['tables'].values()):raise SpatialError('Package row limit exceeded.',code='spatial_limit_exceeded')
    if not isinstance(package['media'],list) or len(package['media'])>MAX_ENTRIES-1:raise SpatialError('Package media limit exceeded.')
    from .spatial_plans import identity
    identity(package['project_id'])
    media_keys={'id','path','sha256','original_name','format','width','height','size','tags','revision','created_at'}
    media_ids=set();media_paths=set()
    for m in package['media']:
        if not isinstance(m,dict) or set(m)!={'package_path','record'} or not isinstance(m['record'],dict) or set(m['record'])!=media_keys:
            raise SpatialError('Unexpected media metadata fields.',code='spatial_import_conflict')
        record=m['record'];identity(record['id'])
        if record['id'] in media_ids or m['package_path'] in media_paths:raise SpatialError('Duplicate media identity/path.')
        media_ids.add(record['id']);media_paths.add(m['package_path'])
        if not isinstance(record['sha256'],str) or not __import__('re').fullmatch(r'[0-9a-f]{64}',record['sha256']):raise SpatialError('Invalid media hash.')
        if any(type(record[k]) is not int or record[k]<=0 for k in ('width','height','size','revision')) or record['width']*record['height']>80_000_000 or record['size']>100*1024*1024:raise SpatialError('Invalid or excessive media dimensions/size.')
        if record['format'] not in FORMATS or not isinstance(record['tags'],list) or any(not isinstance(t,str) or len(t)>240 for t in record['tags']):raise SpatialError('Unsupported media metadata.')
        if not isinstance(m['package_path'],str) or not isinstance(record['original_name'],str) or not isinstance(record['path'],str):raise SpatialError('Invalid media path metadata.')
    expectedfiles={m['package_path'] for m in package['media']}
    if set(files)-expectedfiles:raise SpatialError('Unlisted media in the archive.')
    for m in package['media']:
        p=m['package_path']
        if not p.startswith('media/') or PurePosixPath(p).name!=p.split('/')[-1] or '..' in PurePosixPath(p).parts:raise SpatialError('Invalid package media path.')
        if p in files and (len(files[p])!=m['record']['size'] or hashlib.sha256(files[p]).hexdigest()!=m['record']['sha256']):raise SpatialError('Package media hash mismatch.',code='spatial_integrity')
    return package,files,raw,hashlib.sha256(raw).hexdigest()


class SpatialTransfer:
    def __init__(self,service):
        self.s,self.repo=service,service.repo
        self.plans=SpatialPlans(service)

    def export(self,setup_id,scope='full-history',version_id=None):
        if scope not in ('full-history','selected-with-history-closure','sparse-snapshot'):raise SpatialError('Choose an explicit history scope.')
        with self.repo.transaction(False) as conn:
            selected=self.plans._show(conn,setup_id,version_id)['version']
            setup_versions={selected['id']}
            if scope=='full-history':setup_versions={r[0] for r in conn.execute('SELECT id FROM spatial_setup_versions WHERE setup_id=?',(setup_id,))}
            bindings=set();reviews=set()
            if scope!='sparse-snapshot':
                changed=True
                while changed:
                    before=(len(setup_versions),len(bindings),len(reviews))
                    for vid in list(setup_versions):
                        v=self.plans._version(conn,vid)
                        if v['parent_version_id']:setup_versions.add(v['parent_version_id'])
                        bindings.update(r[0] for r in conn.execute('SELECT id FROM shot_spatial_binding_versions WHERE setup_version_id=?',(vid,)))
                    for bid in list(bindings):
                        b=self.plans._binding_version(conn,bid);setup_versions.add(b['setup_version_id'])
                        if b['parent_version_id']:bindings.add(b['parent_version_id'])
                        reviews.update(r[0] for r in conn.execute('SELECT id FROM observation_spatial_reviews WHERE binding_version_id=?',(bid,)))
                    for rid in list(reviews):
                        r=conn.execute('SELECT * FROM observation_spatial_reviews WHERE id=?',(rid,)).fetchone();bindings.add(r['binding_version_id'])
                        if r['parent_review_id']:reviews.add(r['parent_review_id'])
                    changed=before!=(len(setup_versions),len(bindings),len(reviews))
                    if sum(before)>10000:raise SpatialError('History closure exceeds 10000 records.',code='spatial_limit_exceeded')
            tables={t:[] for t in TABLES}
            def rows(table,ids,column='id'):
                if not ids:return []
                out=[]
                for record_id in sorted(ids):out.extend(dict(r) for r in conn.execute(f'SELECT * FROM {table} WHERE {column}=?',(record_id,)))
                return out
            tables['spatial_setup_versions']=rows('spatial_setup_versions',setup_versions)
            tables['spatial_setup_versions'].sort(key=lambda r:(r['setup_id'],r['number']))
            headers={v['setup_id'] for v in tables['spatial_setup_versions']}
            tables['spatial_setups']=rows('spatial_setups',headers)
            for header in tables['spatial_setups']:
                versions=[v for v in tables['spatial_setup_versions'] if v['setup_id']==header['id']]
                last=max(versions,key=lambda v:v['number'])
                header.update(current_version_id=last['id'],revision=last['number'],title=json.loads(last['payload_json'])['setup_label'])
            for kind in ('scene','asset','media','source'):tables['spatial_version_'+kind+'_pins']=rows('spatial_version_'+kind+'_pins',setup_versions,'version_id')
            tables['shot_spatial_binding_versions']=rows('shot_spatial_binding_versions',bindings)
            tables['shot_spatial_binding_versions'].sort(key=lambda r:(r['binding_id'],r['number']))
            tables['shot_spatial_bindings']=rows('shot_spatial_bindings',{b['binding_id'] for b in tables['shot_spatial_binding_versions']})
            for header in tables['shot_spatial_bindings']:
                last=max((b for b in tables['shot_spatial_binding_versions'] if b['binding_id']==header['id']),key=lambda b:b['number'])
                header.update(current_version_id=last['id'],revision=last['number'])
            tables['observation_spatial_reviews']=rows('observation_spatial_reviews',reviews)
            tables['observation_spatial_reviews'].sort(key=lambda r:(r['shot_id'],r['number']))
            mediaids={p['media_id'] for p in tables['spatial_version_media_pins']}
            media=[]
            for mid in sorted(mediaids):
                record=dict(conn.execute('SELECT * FROM media WHERE id=?',(mid,)).fetchone())
                media.append({'record':record,'package_path':'media/'+record['sha256']+FORMATS[record['format']]})
            package={'schema':PACKAGE,'producer':{'application':'storyboarder','version':__version__},'project_id':self.plans.project_id,'frame':FRAME,'time_unit':'microseconds','scope':scope,'tables':tables,'media':media,'capabilities':{'required':['spatial-plan/v1','exact-source-pins/v1'],'unsupported':[]},'extensions':{}}
        files={'package.json':canonical(package).encode()}
        for m in media:
            record=m['record'];raw=safe_path(self.s.root,record['path'],must_exist=True).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=record['sha256']:raise SpatialError('Media changed during export.',code='spatial_integrity')
            files[m['package_path']]=raw
        raw=zip_bytes(files)
        if len(raw)>MAX_COMPRESSED:raise SpatialError('Native export exceeds 100 MiB; narrow the scope.',code='spatial_limit_exceeded')
        return publish(self.s,{'native-spatial.zip':raw,**files})|{'package_sha256':hashlib.sha256(raw).hexdigest(),'scope':scope}

    def _validate_rows(self,conn,p):
        tables=p['tables']
        for table,rows in tables.items():
            columns={r[1] for r in conn.execute(f'PRAGMA table_info({table})')}
            seen=set()
            for row in rows:
                if not isinstance(row,dict) or set(row)!=columns:raise SpatialError('Invalid native row shape.',{'table':table},'spatial_import_conflict')
                key=tuple(row[k] for k in ('id',) if k in row) or tuple(row[k] for k in ('version_id','owner_id','role','asset_id','scene_id','media_id','pin_id') if k in row)
                if key in seen:raise SpatialError('Duplicate native identity.',{'table':table},'spatial_import_conflict')
                seen.add(key)
        versions={v['id']:v for v in tables['spatial_setup_versions']}
        binding_versions={v['id']:v for v in tables['shot_spatial_binding_versions']}
        for table,field,model in [('spatial_setup_versions','payload_json',None),('shot_spatial_binding_versions','binding_json',SpatialBinding),('observation_spatial_reviews','review_json',SpatialReview)]:
            for row in tables[table]:
                if raw_hash(row[field])!=row['content_sha256'] or raw_hash(row['basis_json'])!=row['basis_sha256']:raise SpatialError('Imported immutable hash mismatch.',code='spatial_integrity')
                body=inert_json(row[field].encode());normalized=checked(body,model) if model else checked(body)
                if canonical(normalized)!=row[field]:raise SpatialError('Imported payload is not canonical.',code='spatial_integrity')
                if row['schema_version']!=(2 if table=='observation_spatial_reviews' else 1) or ('sealed' in row and row['sealed']!=1):raise SpatialError('Imported version is not sealed/supported.')
                if table=='spatial_setup_versions':
                    parent=versions.get(row['parent_version_id'])
                    if p['scope']!='sparse-snapshot' and ((row['number']==1 and row['parent_version_id'] is not None) or (row['number']>1 and (not parent or parent['setup_id']!=row['setup_id'] or parent['number']!=row['number']-1))):raise SpatialError('Missing setup parent closure.')
                if table=='shot_spatial_binding_versions':
                    parent=binding_versions.get(row['parent_version_id'])
                    if row['setup_version_id']!=body['setup_version_id'] or row['setup_version_id'] not in versions:raise SpatialError('Binding setup pin is missing/inconsistent.')
                    if (row['number']==1 and row['parent_version_id'] is not None) or (row['number']>1 and (not parent or parent['binding_id']!=row['binding_id'] or parent['number']!=row['number']-1)):raise SpatialError('Missing binding parent closure.')
                    basis=json.loads(row['basis_json']);setup=json.loads(versions[row['setup_version_id']]['payload_json'])
                    validate_binding(body,setup,basis['parent_scene_id'],basis.get('shot_fields',{}).get('duration'))
                if table=='observation_spatial_reviews' and (row['binding_version_id']!=body['binding_version_id'] or row['observation_version_id']!=body['observation_version_id']):raise SpatialError('Review JSON differs from relational pins.')
        return versions,binding_versions

    def _preview(self,conn,p,files,digest,mode,mappings):
        if mode not in ('exact','copy'):raise SpatialError('Choose exact or copy import.')
        if not isinstance(mappings,dict):raise SpatialError('Mappings must be an object.')
        versions,binding_versions=self._validate_rows(conn,p)
        conflicts=[];actions=[];dependencies=[]
        tables=p['tables']
        if mode=='exact' and p['scope']=='sparse-snapshot':conflicts.append({'code':'sparse_requires_copy','message':'Sparse snapshots are read-only or copy-as-new-root only.'})
        if mode=='exact' and p['project_id']!=self.plans.project_id:conflicts.append({'code':'project_identity','message':'Exact history requires the same project identity. Choose copy with explicit scene mappings.'})
        if mode=='copy':
            if len(tables['spatial_setups'])!=1:conflicts.append({'code':'copy_scope','message':'Import one selected setup as a copy at a time.'})
            if not mappings.get('new_setup_id'):conflicts.append({'code':'copy_identity','message':'Supply a new setup UUID.'})
            if conflicts:return {'conflicts':conflicts,'actions':[],'expected_basis_sha256':None}
            from .spatial_plans import identity
            identity(mappings['new_setup_id'])
            if conn.execute('SELECT 1 FROM spatial_setups WHERE id=?',(mappings['new_setup_id'],)).fetchone():conflicts.append({'code':'id_collision','id':mappings['new_setup_id']})
            selected=max(tables['spatial_setup_versions'],key=lambda v:v['number'])
            payload=deepcopy(json.loads(selected['payload_json']))
            for key in ('scene_ids',):
                payload[key]=[mappings.get('scenes',{}).get(x,x) for x in payload[key]]
            if payload['location_asset_id']:payload['location_asset_id']=mappings.get('assets',{}).get(payload['location_asset_id'],payload['location_asset_id'])
            for group in ('instances','resources','cameras','lights','modifiers'):
                for item in payload[group]:
                    for key in ('asset_id','reference_asset_id'):
                        if item.get(key):item[key]=mappings.get('assets',{}).get(item[key],item[key])
            for floor in payload['floor_plans']:floor['media_id']=mappings.get('media',{}).get(floor['media_id'],floor['media_id'])
            payload['origin']={'setup_id':selected['setup_id'],'version_id':selected['id']}
            payload['setup_label']=mappings.get('title',payload['setup_label']+' (copy)')
            try:
                payload=checked(payload);pins=self.plans._dependencies(conn,payload);dependencies=self.plans._basis(payload,pins)
            except StoryboardError as exc:conflicts.append(exc.as_dict());payload=None
            actions.append({'kind':'copy-new-root','setup_id':mappings['new_setup_id'],'source_version_id':selected['id']})
            token=sha({'protocol':'spatial-import/v1','project':self.plans.project_id,'package':digest,'mode':mode,'mappings':mappings,'dependencies':dependencies,'conflicts':conflicts})
            return {'conflicts':conflicts,'actions':actions,'expected_basis_sha256':token,'payload':payload}
        # Compare exact bytes and explicitly review every pointer advancement.
        for table,rows in tables.items():
            pk=[r[1] for r in sorted(conn.execute(f'PRAGMA table_info({table})').fetchall(),key=lambda r:r[5]) if r[5]]
            for row in rows:
                existing=conn.execute(f"SELECT * FROM {table} WHERE "+' AND '.join(k+'=?' for k in pk),tuple(row[k] for k in pk)).fetchone()
                if existing:
                    if table in ('spatial_setups','shot_spatial_bindings'):
                        dependencies.append({'table':table,'id':row['id'],'head':existing['current_version_id'],'revision':existing['revision']})
                        expected_owner='project_id' if table=='spatial_setups' else 'shot_id'
                        if existing[expected_owner]!=row[expected_owner]:conflicts.append({'code':'id_collision','table':table,'id':row['id']})
                    elif dict(existing)!=row:conflicts.append({'code':'id_collision','table':table,'id':row.get('id',row.get('version_id'))})
                else:actions.append({'kind':'insert','table':table,'id':row.get('id',row.get('version_id'))})
        for v in tables['spatial_setup_versions']:
            body=json.loads(v['payload_json'])
            for sid in body['scene_ids']:
                try:self.plans._entity(conn,sid,'scene',False)
                except StoryboardError as exc:conflicts.append(exc.as_dict())
        for pin in tables['spatial_version_asset_pins']:
            try:self.plans._entity(conn,pin['asset_id'],'asset',False)
            except StoryboardError as exc:conflicts.append(exc.as_dict())
            snapshot=inert_json(pin['snapshot_json'].encode())
            if sha(snapshot['semantic'])!=pin['semantic_sha256']:conflicts.append({'code':'asset_pin_hash'})
        for pin in tables['spatial_version_source_pins']:
            v=versions.get(pin['version_id'])
            if not v:conflicts.append({'code':'source_version_missing'});continue
            body=json.loads(v['payload_json']);declared=next((x for x in body['source_pins'] if x['id']==pin['pin_id']),None)
            if not declared:conflicts.append({'code':'source_pin_missing'});continue
            try:
                resolved=self.plans._source(conn,declared,body['scene_ids'],False)
                if resolved['semantic_sha256']!=pin['semantic_sha256'] or canonical(resolved['snapshot_json'])!=pin['snapshot_json']:conflicts.append({'code':'source_pin_mismatch'})
            except StoryboardError as exc:conflicts.append(exc.as_dict())
        for m in p['media']:
            record=m['record'];existing=conn.execute('SELECT * FROM media WHERE id=?',(record['id'],)).fetchone()
            if existing:
                if existing['sha256']!=record['sha256']:conflicts.append({'code':'media_id_collision','id':record['id']})
                else:self.plans._file(existing['path'],record['sha256'])
            elif m['package_path'] not in files:conflicts.append({'code':'media_missing','id':record['id']})
            elif conn.execute('SELECT 1 FROM media WHERE sha256=?',(record['sha256'],)).fetchone():conflicts.append({'code':'media_hash_identity_collision','id':record['id']})
        for h in tables['shot_spatial_bindings']:
            try:
                shot=self.plans._entity(conn,h['shot_id'],'shot',False)
                choice=mappings.get('shots',{}).get(h['shot_id'])
                if not choice or choice.get('shot_id')!=h['shot_id'] or choice.get('expected_revision')!=shot['revision']:
                    conflicts.append({'code':'shot_mapping_required','shot_id':h['shot_id'],'current_revision':shot['revision']})
                dependencies.append({'shot_id':h['shot_id'],'revision':shot['revision'],'parent_id':shot['parent_id']})
                final=binding_versions[h['current_version_id']];body=json.loads(final['binding_json'])
                if body['status']=='active':validate_binding(body,json.loads(versions[final['setup_version_id']]['payload_json']),shot['parent_id'],shot['fields'].get('duration'))
            except (StoryboardError,KeyError) as exc:conflicts.append({'code':'binding_scope','message':str(exc)})
        for review in tables['observation_spatial_reviews']:
            ov=conn.execute('SELECT v.*,c.shot_id FROM observation_contract_versions v JOIN observation_contracts c ON c.id=v.contract_id WHERE v.id=? AND v.sealed=1',(review['observation_version_id'],)).fetchone()
            if not ov or ov['shot_id']!=review['shot_id']:conflicts.append({'code':'v1_prerequisite_missing','id':review['observation_version_id']})
        token=sha({'protocol':'spatial-import/v1','project':self.plans.project_id,'package':digest,'mode':mode,'mappings':mappings,'dependencies':dependencies,'actions':actions,'conflicts':conflicts})
        return {'conflicts':conflicts[:200],'actions':actions[:500],'actions_truncated':len(actions)>500,'expected_basis_sha256':token,'dependency_prerequisites':'Exact documents/v1 observations and library assets must already exist; no source identities are invented.'}

    def preview(self,package=None,archive_base64=None,mode='exact',mappings=None):
        p,files,raw,digest=decode(package,archive_base64)
        with self.repo.transaction(False) as conn:
            result=self._preview(conn,p,files,digest,mode,mappings or {})
        return result|{'package_sha256':digest,'producer':p['producer'],'scope':p['scope'],'can_apply':not result['conflicts']}

    def apply(self,expected_basis_sha256,package=None,archive_base64=None,mode='exact',mappings=None):
        p,files,raw,digest=decode(package,archive_base64);mappings=mappings or {}
        created=[]
        lock=safe_path(self.s.root,'.storyboarder/spatial-import.lock')
        with FileLock(str(lock),timeout=10):
            try:
                with self.repo.transaction() as conn:
                    prior=conn.execute('SELECT * FROM spatial_import_receipts WHERE package_sha256=? AND mapping_json=?',(digest,canonical({'mode':mode,'mappings':mappings}))).fetchone()
                    if prior:return {'idempotent':True,'receipt':unpack(prior)}
                    preview=self._preview(conn,p,files,digest,mode,mappings)
                    self.plans._expect(expected_basis_sha256,preview['expected_basis_sha256'])
                    if preview['conflicts']:raise SpatialError('Resolve the preview conflicts before importing.',preview,'spatial_import_conflict',409)
                    def save(relative,content):
                        path=safe_path(self.s.root,relative);path.parent.mkdir(parents=True,exist_ok=True)
                        if path.exists():
                            if path.read_bytes()!=content:raise SpatialError('Import destination file differs; it was not overwritten.')
                            return
                        with path.open('xb') as out:out.write(content);out.flush();os.fsync(out.fileno())
                        created.append(path)
                    original='spatial-imports/'+digest+'/original.zip';save(original,raw)
                    imported={'setups':[],'bindings':[],'reviews':[]}
                    if mode=='copy':
                        payload=preview['payload'];pins=self.plans._dependencies(conn,payload)
                        header={'id':mappings['new_setup_id'],'project_id':self.plans.project_id,'current_version_id':None,'revision':1,'title':payload['setup_label'],'archived':0,'created_at':now(),'updated_at':now()}
                        self.plans._insert(conn,'spatial_setups',header)
                        result=self.plans._publish(conn,header,payload,pins,'import');imported['setups']=[result['header']['id']]
                    else:
                        for m in p['media']:
                            record=m['record']
                            if conn.execute('SELECT 1 FROM media WHERE id=?',(record['id'],)).fetchone():continue
                            content=files[m['package_path']]
                            temp_root=safe_path(self.s.root,'.storyboarder/staging');temp_root.mkdir(parents=True,exist_ok=True)
                            fd,name=tempfile.mkstemp(dir=temp_root,prefix='spatial-media-');os.close(fd)
                            try:
                                Path(name).write_bytes(content);verified=inspect_image(name)
                                if any(verified[k]!=record[k] for k in ('format','width','height','size','sha256')):raise SpatialError('Decoded media differs from its package metadata.')
                            finally:Path(name).unlink(missing_ok=True)
                            path='media/items/'+record['sha256']+FORMATS[record['format']];save(path,content)
                            self.repo.insert(conn,'media',{**record,'path':path,'original_name':safe_name(record['original_name'])})
                        tables=p['tables']
                        for header in tables['spatial_setups']:
                            if not conn.execute('SELECT 1 FROM spatial_setups WHERE id=?',(header['id'],)).fetchone():self.plans._insert(conn,'spatial_setups',header|{'current_version_id':None,'revision':1,'archived':0})
                        for v in sorted(tables['spatial_setup_versions'],key=lambda r:(r['setup_id'],r['number'])):
                            if conn.execute('SELECT 1 FROM spatial_setup_versions WHERE id=?',(v['id'],)).fetchone():continue
                            header=self.plans._header(conn,v['setup_id'])
                            if v['parent_version_id']!=header['current_version_id']:raise Conflict('Import would branch or rewind an existing setup. Choose copy.')
                            self.plans._insert(conn,'spatial_setup_versions',v|{'sealed':0})
                            for kind in ('scene','asset','media','source'):
                                for pin in tables['spatial_version_'+kind+'_pins']:
                                    if pin['version_id']==v['id']:
                                        columns=list(pin);conn.execute(f"INSERT INTO spatial_version_{kind}_pins ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",tuple(pin.values()))
                            conn.execute('UPDATE spatial_setup_versions SET sealed=1 WHERE id=?',(v['id'],))
                            archived=1 if v['operation']=='archive' else 0 if v['operation']=='unarchive' else header['archived']
                            conn.execute('UPDATE spatial_setups SET current_version_id=?,revision=?,title=?,archived=?,updated_at=? WHERE id=?',(v['id'],v['number'],json.loads(v['payload_json'])['setup_label'],archived,v['created_at'],v['setup_id']))
                            imported['setups'].append(v['id'])
                        for h in tables['shot_spatial_bindings']:
                            if not conn.execute('SELECT 1 FROM shot_spatial_bindings WHERE id=?',(h['id'],)).fetchone():self.plans._insert(conn,'shot_spatial_bindings',h|{'current_version_id':None,'revision':1})
                        for v in sorted(tables['shot_spatial_binding_versions'],key=lambda r:(r['binding_id'],r['number'])):
                            if conn.execute('SELECT 1 FROM shot_spatial_binding_versions WHERE id=?',(v['id'],)).fetchone():continue
                            h=self.plans._binding_header(conn,binding_id=v['binding_id'])
                            if v['parent_version_id']!=h['current_version_id']:raise Conflict('Import would branch or rewind an existing binding.')
                            self.plans._insert(conn,'shot_spatial_binding_versions',v|{'sealed':0});conn.execute('UPDATE shot_spatial_binding_versions SET sealed=1 WHERE id=?',(v['id'],))
                            conn.execute('UPDATE shot_spatial_bindings SET current_version_id=?,revision=?,updated_at=? WHERE id=?',(v['id'],v['number'],v['created_at'],v['binding_id']))
                            imported['bindings'].append(v['id'])
                        for r in sorted(tables['observation_spatial_reviews'],key=lambda r:(r['shot_id'],r['number'])):
                            if not conn.execute('SELECT 1 FROM observation_spatial_reviews WHERE id=?',(r['id'],)).fetchone():
                                columns=list(r);conn.execute(f"INSERT INTO observation_spatial_reviews ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",tuple(r.values()));imported['reviews'].append(r['id'])
                        # Immutable data is checked on this connection before commit.
                        from .spatial_recovery import inspect_connection
                        errors=inspect_connection(self.s,conn,check_reviews=False)
                        if errors:raise SpatialError('Imported history failed integrity checks.',{'issues':errors[:100]},'spatial_integrity')
                    receipt={'id':uid(),'package_sha256':digest,'original_path':original,'producer_json':p['producer'],'mapping_json':{'mode':mode,'mappings':mappings},'imported_records_json':imported,'created_at':now()}
                    self.plans._insert(conn,'spatial_import_receipts',receipt)
                    self.repo.event(conn,'spatial.import',self.plans.project_id,{'receipt_id':receipt['id'],'package_sha256':digest,'mode':mode})
                    return {'receipt':receipt,'imported':imported,'idempotent':False}
            except Exception:
                # The write transaction rolled back. Delete only files this call
                # exclusively created, and only if no committed row uses them.
                with self.repo.transaction(False) as conn:
                    for path in created:
                        rel=path.relative_to(self.s.root).as_posix()
                        used=conn.execute('SELECT 1 FROM media WHERE path=?',(rel,)).fetchone() or conn.execute('SELECT 1 FROM spatial_import_receipts WHERE original_path=?',(rel,)).fetchone()
                        if not used:path.unlink(missing_ok=True)
                raise
