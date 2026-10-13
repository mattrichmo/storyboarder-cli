"""Connected graph contracts, atomicity, revision impact, portability and CLI acceptance."""
import base64
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from uuid import uuid4
import zipfile

import pytest
from fastapi.testclient import TestClient
from storyboarder.api.server import create_app
from storyboarder.application.projects import Project
from storyboarder.application.service import Service
from storyboarder.application.recovery import backup, doctor, restore
from storyboarder.domain.errors import StoryboardError, Conflict, InUse
from storyboarder.production.example import example, SCRIPT
from storyboarder.production.service import ProductionService
from storyboarder.production.models import ProductionError, parse_record, digest, references
from storyboarder.production.evaluate import evaluate, convert_frames
from storyboarder.production.scripts import import_preview
from storyboarder.production.portability import export_package, import_package, validate_package
from storyboarder.production.outputs import packet, csv_text
from storyboarder.production.reports import report
from storyboarder.production.legacy import adopt_preview


def batch(cp, *ops):
    return dict(expected_checkpoint=cp, operation_id=str(uuid4()), operations=list(ops))


def put(r, **changes):
    data=deepcopy(r['data']); data.update(changes)
    return dict(op='put', id=r['id'], expected_revision=r['revision'], base_version=r['version'], select=True, data=data)


@pytest.fixture
def connected(service):
    p=ProductionService(service); e=example(service)
    p.apply(e['batch'])
    return service,p,e['ids']


def test_example_is_previewable_atomic_and_retry_safe(service):
    p=ProductionService(service); e=example(service)
    proof=p.preview(e['batch'])
    assert proof['valid'] and p.snapshot()['checkpoint']==0
    request={**e['batch'], 'preview_sha256':proof['preview_sha256']}
    result=p.apply(request)
    assert result['checkpoint']==1 and not result['replayed']
    assert p.apply(request)['replayed'] and p.snapshot()['total']==27
    changed=deepcopy(request); changed['operations'][0]['data']['title']='Not the same operation'
    with pytest.raises(Conflict): p.apply(changed)
    assert doctor(service,True)['healthy']


def test_typed_refs_atomic_rollback_and_no_partial_receipt(service):
    p=ProductionService(service); e=example(service)
    shot=next(o for o in e['batch']['operations'] if o['data']['kind']=='shot')
    shot['data']['cameras']=[dict(id=e['ids']['location'],version=1)]
    with pytest.raises(ProductionError): p.apply(e['batch'])
    assert p.snapshot()['total']==0
    with service.repo.readonly_transaction() as conn:
        assert conn.execute('SELECT count(*) FROM production_operations').fetchone()[0]==0


@pytest.mark.parametrize('bad', [float('nan'),float('inf'),True,'1.2'])
def test_pose_rejects_nonfinite_or_coerced_coordinates(bad):
    with pytest.raises(ProductionError):
        parse_record(dict(kind='location',title='Invalid',geometry=[dict(id=str(uuid4()),label='Wall',type='wall',pose=dict(position=dict(x=bad,y=0,z=0)),size=dict(x=1,y=1,z=1))]))


def test_unknown_fields_and_typestate():
    with pytest.raises(ProductionError): parse_record(dict(kind='asset',title='Bad',category='location'))
    with pytest.raises(ProductionError): parse_record(dict(kind='scene',title='Bad',unknown=True))
    with pytest.raises(ProductionError): parse_record(dict(kind='scene',title='Bad',planning='not_applicable'))
    assert list(references(dict(state=dict(id='serial',version='text'))))==[]


def test_alternatives_keep_selection_stable_and_stale_writes_fail(connected):
    _,p,ids=connected; old=p.show(ids['shot-master']); op=put(old,title='Alternate master');op['select']=False
    p.apply(batch(1,op))
    assert p.show(old['id'])['version']==1 and p.show(old['id'],2)['data']['title']=='Alternate master'
    assert p.snapshot(mode='head')['records']
    with pytest.raises(Conflict): p.apply(batch(1,put(old,title='Stale')))
    with pytest.raises(Conflict): p.apply(batch(2,put(old,title='Stale header')))
    p.apply(batch(2,dict(op='select',id=old['id'],expected_revision=2,version=2)))
    assert p.show(old['id'])['data']['title']=='Alternate master'
    assert p.history(old['id'])['total']==2
    assert p.show(old['id'],1)['sha256']==old['sha256']


def test_concurrent_checkpoints_only_one_writer_wins(connected):
    _,p,ids=connected;r=p.show(ids['shot-master'])
    requests=[batch(1,put(r,title=f'Writer {i}')) for i in range(2)]
    def apply(request):
        try: return p.apply(request)['checkpoint']
        except Conflict: return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(apply,requests))
    assert sorted(map(str,results))==['2','conflict']
    assert p.history(r['id'])['total']==2


def test_versions_and_receipts_are_immutable(connected):
    s,_,ids=connected
    for sql in ['DELETE FROM production_versions','UPDATE production_versions SET sha256=sha256','DELETE FROM production_operations','DELETE FROM production_refs']:
        with pytest.raises(StoryboardError):
            with s.repo.transaction() as conn: conn.execute(sql)
    assert ProductionService(s).show(ids['shot-master'])['version']==1


def test_archive_checks_dependencies_and_restore_keeps_history(connected):
    _,p,ids=connected
    with pytest.raises(InUse): p.apply(batch(1,dict(op='archive',id=ids['location'],expected_revision=1)))
    note=p.show(ids['note'])
    p.apply(batch(1,dict(op='archive',id=note['id'],expected_revision=1)))
    assert p.show(note['id'])['archived']
    p.apply(batch(2,dict(op='restore',id=note['id'],expected_revision=2)))
    assert not p.show(note['id'])['archived'] and p.show(note['id'])['sha256']==note['sha256']


def test_action_handoff_lighting_and_exact_camera_timing(connected):
    s,p,ids=connected
    before=evaluate(s,ids['shot-master'],frame=95); after=evaluate(s,ids['shot-master'],frame=96)
    key=lambda sample:next(i for i in sample['instances'] if i['id']==ids['key-instance'])
    assert key(before)['parent_id']==ids['mara-instance']
    assert key(after)['parent_id']==ids['leon-instance']
    assert after['seconds']==4 and after['cameras'][0]['model']=='rectilinear-pinhole'
    assert after['cameras'][0]['horizontal_fov_deg']>0
    assert evaluate(s,ids['shot-master'],frame=130)['fixtures'][0]['relative_intensity']!=before['fixtures'][0]['relative_intensity']
    with pytest.raises(ProductionError): evaluate(s,ids['action'],frame=-1)
    with pytest.raises(ProductionError): evaluate(s,ids['action'],frame=100000)
    assert p.query(kind='shot',scene_id=ids['scene'])['total']==2


def test_coverage_join_and_three_separate_readiness_dimensions(connected):
    s,p,ids=connected;r=report(s)
    assert r['structural']['valid'] and r['planning']['complete']
    assert not r['creative']['accepted']
    covered=next(x for x in r['coverage']['material'] if 'hands the key' in x['text'])
    rows=p.query(kind='shot',script_block_id=covered['block_id'])['items']
    assert len(rows)==2 and all(x['joins']['location']['version']==1 for x in rows)
    shot=p.show(ids['shot-insert']);p.apply(batch(1,put(shot,cameras=[])))
    r=report(s);assert r['structural']['valid'] and not r['planning']['complete']


def test_rational_time_mapping_does_not_hide_rounding():
    rate=dict(numerator=24000,denominator=1001);film=dict(numerator=24,denominator=1)
    assert convert_frames(24000,rate,film)['frames']==24024
    assert convert_frames(1,rate,film)['frames'] is None
    assert convert_frames(1,rate,film)['requires_rounding']
    assert convert_frames(1,rate,film,'floor')['frames']==1
    assert convert_frames(1,rate,film,'ceil')['frames']==2


def test_script_revision_reconciliation_retains_valid_work(connected):
    s,p,ids=connected; old=p.show(ids['script']); oldshot=p.show(ids['shot-master'])
    imported=import_preview(s,ids['script'],1,1,str(uuid4()),'revision.fountain',text=SCRIPT.replace('Keep it safe.','Bring it back.'),select=True)
    assert imported['persisted'] is False and imported['revision_diff']
    newscript=imported['batch']['operations'][0]['data']
    assert old['data']['scenes'][0]['id']==newscript['scenes'][0]['id']
    assert base64.b64decode(newscript['source_file']['bytes_base64']).decode().endswith('steps away.\n')
    p.apply(imported['batch'])
    assert p.show(ids['shot-master'])['sha256']==oldshot['sha256']
    impacted=p.impact(ids['script'])['affected']
    assert ids['shot-master'] in {x['id'] for x in impacted}
    chosen=[x['id'] for x in impacted if x['kind'] not in ('review','exception')]
    repair=p.reconcile([{'from':dict(id=ids['script'],version=1),'to':dict(id=ids['script'],version=2)}],chosen,str(uuid4()),2,select=True)
    assert repair['preview']['valid']
    p.apply(repair['batch'])
    assert p.show(ids['shot-master'])['version']==2
    assert p.show(ids['shot-master'],1)['sha256']==oldshot['sha256']
    assert p.show(ids['location'])['version']==1
    assert report(s)['structural']['valid']


def test_unchanged_script_wording_pin_drift_is_not_invalidated(connected):
    s,p,ids=connected;r=p.show(ids['script'])
    p.apply(batch(1,put(r,title='Same script, renamed')))
    stale=p.show(ids['shot-insert'])['stale_dependencies']
    assert stale and all(not x['needs_attention'] for x in stale)
    assert report(s)['planning']['complete']


@pytest.mark.parametrize('source', ['{}','{"scenes":[{}]}','{"scenes":[{"heading":3}]}','{"scenes":[{"heading":"INT. X","blocks":[null]}]}'])
def test_structured_import_invalid_input_is_machine_readable(service,source):
    with pytest.raises(ProductionError):
        import_preview(service,str(uuid4()),0,0,str(uuid4()),'bad.json',format='structured-json',text=source)


def test_graph_history_export_import_roundtrip(connected,tmp_path):
    s,p,ids=connected;p.apply(batch(1,put(p.show(ids['shot-master']),title='Second version')))
    exported=export_package(s); target=Service(Project.create(tmp_path/'target','Restored graph'))
    op=str(uuid4()); args=dict(package=exported,operation_id=op,expected_checkpoint=0)
    assert not import_package(target,**args)['persisted']
    import_package(target,**args,apply=True)
    assert export_package(target)['graph_sha256']==exported['graph_sha256']
    assert import_package(target,**args,apply=True)['replayed']
    with pytest.raises(Conflict): import_package(target,**{**args,'operation_id':str(uuid4()),'expected_checkpoint':1},apply=True)
    assert doctor(target,True)['healthy']


def test_package_tamper_is_rejected(connected):
    s,_,_=connected; package=export_package(s)
    package['graph']['versions'][0]['data']['title']='Tampered'
    with pytest.raises(ProductionError): validate_package(package)
    package['graph_sha256']=digest(package['graph'])
    with pytest.raises(ProductionError): validate_package(package)


def test_legacy_adoption_preserves_ids_and_media_pins(story):
    s=story['service'];p=ProductionService(s)
    preview=adopt_preview(s,0,str(uuid4()),select=True)
    assert preview['preview']['valid']
    p.apply(preview['batch'])
    assert p.show(story['shot']['id'])['data']['scene']['id']==story['scene']['id']
    assert not report(s)['planning']['complete']
    assert s.usage(story['character']['id'])['production_history']
    assert doctor(s,True)['healthy']


def test_packet_revision_stamps_and_escape(connected):
    s,p,ids=connected;p.apply(batch(1,put(p.show(ids['shot-master']),title='=Formula <script>bad</script>')))
    result=packet(s,include_pdf=True)
    archive=s.root/result['path'] if 'path' in result else s.root/next(x for x in result['files'] if x.endswith('packet.zip'))
    with zipfile.ZipFile(archive) as z:
        assert 'selection.json' in z.namelist() and 'review.pdf' in z.namelist()
        selection=json.loads(z.read('selection.json')); assert selection['checkpoint']==2
        assert b'<script>bad</script>' not in z.read('index.html')
        assert z.read('review.pdf').startswith(b'%PDF-')
    assert packet(s,include_pdf=True)['checkpoint']==2
    assert csv_text(['Title'],[['=cmd']]).splitlines()[1].startswith("'=cmd")


def test_cli_and_http_share_the_same_connected_plan(service,tmp_path):
    env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src')}
    def cli(*args,okay=True):
        result=subprocess.run([sys.executable,'-m','storyboarder','production',*args,'--project',str(service.root),'--json'],text=True,capture_output=True,env=env,timeout=30)
        if okay: assert result.returncode==0,result.stdout+result.stderr
        return json.loads(result.stdout or result.stderr)
    e=cli('example'); filename=tmp_path/'batch.json';filename.write_text(json.dumps(e['batch']))
    assert cli('apply','--batch','@'+str(filename))['checkpoint']==1
    assert cli('apply','--batch','@'+str(filename))['replayed']
    shot=e['ids']['shot-master']; script=e['ids']['script']
    before=cli('show','--id',shot)
    request=dict(id=script,expected_revision=1,expected_checkpoint=1,operation_id=str(uuid4()),filename='revision.fountain',text=SCRIPT.replace('Keep it safe.','Bring it back.'),select=True)
    filename.write_text(json.dumps(request)); changed=cli('script-import-preview','--payload','@'+str(filename))
    filename.write_text(json.dumps(changed['batch']));cli('apply','--batch','@'+str(filename))
    assert cli('show','--id',shot)['sha256']==before['sha256']
    affected=cli('impact','--id',script)['affected'];chosen=[r['id'] for r in affected if r['kind'] not in ('review','exception')]
    replacements=[{'from':dict(id=script,version=1),'to':dict(id=script,version=2)}]
    repair=cli('reconcile','--replacements',json.dumps(replacements),'--ids',json.dumps(chosen),'--operation-id',str(uuid4()),'--expected-checkpoint','2','--select')
    filename.write_text(json.dumps(repair['batch']));cli('apply','--batch','@'+str(filename))
    assert cli('show','--id',shot)['version']==2
    with TestClient(create_app(project=service.project),base_url='http://127.0.0.1:7430') as client:
        token=client.get('/api/v1/session').json()['token'];client.headers['X-Storyboarder-Token']=token
        url=f'/api/v1/projects/{service.project.id}/commands/production.evaluate'
        response=client.post(url,json=dict(id=shot,version=2,frame=96))
        assert response.status_code==200,response.text
        assert response.json()['source']['sha256']==cli('evaluate','--id',shot,'--version','2','--frame','96')['source']['sha256']
        client.headers['X-Storyboarder-Token']='wrong'
        assert client.post(url,json=dict(id=shot)).status_code==403


def test_additive_schema_eight_to_nine_preserves_original_records(tmp_path,monkeypatch):
    import storyboarder.storage.repository as repository
    with monkeypatch.context() as context:
        context.setattr(repository,'SCHEMA_VERSION',8)
        old=Service(Project.create(tmp_path/'old','Original eight'))
        scene=old.create_entity('sequence','Original sequence')
        with old.repo.readonly_transaction() as conn:
            assert conn.execute('PRAGMA user_version').fetchone()[0]==8
    upgraded=Service(Project(old.root))
    assert upgraded.get('entities',scene['id'])['title']=='Original sequence'
    assert ProductionService(upgraded).snapshot()['checkpoint']==0
    with upgraded.repo.readonly_transaction() as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0]==9
    assert doctor(upgraded)['healthy']


def test_backup_restores_portable_media_and_graph_exactly(connected,tmp_path):
    s,p,ids=connected
    media_path=s.root/'production-media/reference.txt';media_path.parent.mkdir();media_path.write_bytes(b'portable reference')
    asset=p.show(ids['key']);ref=dict(path='production-media/reference.txt',sha256=hashlib.sha256(media_path.read_bytes()).hexdigest())
    p.apply(batch(1,put(asset,references=[ref])))
    before=export_package(s)['graph_sha256']; saved=backup(s)
    restored_path=tmp_path/'restored';restore(s.root/saved['path'],restored_path)
    restored=Service(Project(restored_path))
    assert (restored.root/ref['path']).read_bytes()==media_path.read_bytes()
    assert export_package(restored)['graph_sha256']==before
    assert doctor(restored,True)['healthy']


def test_missing_media_and_checksum_mismatch_are_reported(connected):
    s,p,ids=connected;r=p.show(ids['key'])
    p.apply(batch(1,put(r,references=[dict(path='production-media/missing.png',sha256='0'*64)])))
    r=report(s,hashes=True)
    assert any('media' in issue['code'] for issue in r['issues'])
    with pytest.raises(StoryboardError): backup(s)


def test_exact_dependency_cycles_and_wrong_parent_types_are_rejected(service):
    p=ProductionService(service);a,b=str(uuid4()),str(uuid4())
    def op(id,target):return dict(op='put',id=id,expected_revision=0,select=True,data=dict(kind='asset',title=id,category='reference',provenance=dict(source_refs=[dict(id=target,version=1)])))
    with pytest.raises(ProductionError):p.apply(batch(0,op(a,b),op(b,a)))
    assert p.snapshot()['checkpoint']==0


def test_reconciliation_never_transfers_creative_acceptance(connected):
    s,p,ids=connected;rid=str(uuid4());shot=p.show(ids['shot-master'])
    p.apply(batch(1,dict(op='put',id=rid,expected_revision=0,select=True,data=dict(kind='review',title='Approved master',subject=dict(id=shot['id'],version=1),dimension='creative',decision='accepted',reviewer='Director',reason='Intent reviewed'))))
    p.apply(batch(2,put(shot,title='A changed master')))
    repair=p.reconcile([{'from':dict(id=shot['id'],version=1),'to':dict(id=shot['id'],version=2)}],[rid],str(uuid4()),3,select=True)
    assert repair['batch'] is None and repair['excluded'][0]['id']==rid
    assert p.show(rid)['data']['subject']['version']==1
    assert not report(s)['creative']['accepted']
