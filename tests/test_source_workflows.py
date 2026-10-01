"""Executable source -> board -> generation -> cut workflows, not UI-only mocks."""
import copy
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from storyboarder.api.server import create_app
from storyboarder.application.commands import execute
from storyboarder.application.documents import Documents
from storyboarder.application.provenance import Provenance
from storyboarder.automation.jobs import Jobs
from storyboarder.domain.errors import StoryboardError
from test_documents import screenplay, edit_payload, uid
from test_automation import register_sample


def test_cli_import_tree_jsonl_and_dry_run(service, screenplay, tmp_path):
    source = tmp_path / 'source.screenjson'; source.write_text(json.dumps(screenplay), encoding='utf-8')
    def cli(*args, input=None):
        return subprocess.run([sys.executable, '-m', 'storyboarder', '--project', str(service.root), *args], capture_output=True, text=True, input=input, timeout=10)
    preview = cli('screenplay', 'import', '--path', str(source), '--dry-run', '--json')
    assert preview.returncode == 0, preview.stderr
    assert json.loads(preview.stdout)['dry_run'] and Documents(service).list()['total'] == 0
    imported = cli('screenplay', 'import', '--path', str(source), '--json')
    assert imported.returncode == 0, imported.stderr
    document = json.loads(imported.stdout)['document']
    tree = cli('document', 'tree', '--document-id', document['id'], '--jsonl')
    assert tree.returncode == 0, tree.stderr
    rows = [json.loads(line) for line in tree.stdout.splitlines()]
    assert [r['node_type'] for r in rows] == ['screenplay', 'scene', 'action', 'character', 'dialogue']
    assert 'payload' not in rows[0]
    validate = cli('document', 'validate', '--id', document['id'], '--json')
    assert validate.returncode == 0 and json.loads(validate.stdout)['valid']


def test_catalog_source_link_and_document_annotation(story, screenplay):
    s=story['service']; d=Documents(s)
    imported=d.import_bytes(json.dumps(screenplay).encode(), 'source.json', 'screenjson')
    source=next(n for n in d.tree(imported['version']['id'])['items'] if n['node_type']=='action')
    result=execute(s, 'shot.link-source', {'shot_id': story['shot']['id'], 'node_id': source['id']})
    assert result['source_id']==source['id']
    assert execute(s, 'shot.sources', {'id': story['shot']['id']})['items'][0]['node_id']==source['id']
    note=execute(s, 'annotation.create', {'endpoint_type':'node','endpoint_id':source['id'], 'content':'Keep the original blocking.'})
    assert note['text']=='Keep the original blocking.'


def test_api_source_upload_revision_and_export_are_scoped(service, screenplay):
    app=create_app(project=service.project)
    with TestClient(app, base_url='http://127.0.0.1:7430') as c:
        token=c.get('/api/v1/session').json()['token']; c.headers['X-Storyboarder-Token']=token
        prefix=f'/api/v1/projects/{service.project.id}'
        raw=json.dumps(screenplay).encode()
        response=c.post(prefix+'/documents/upload',files={'file':('source.screenjson',raw,'application/json')},data={'format':'screenjson','label':'White'})
        assert response.status_code==201, response.text
        result=response.json(); document=result['document']; version=result['version']
        tree=c.get(prefix+f'/documents/{document["id"]}/tree?limit=2').json()
        assert tree['total']==5 and tree['next_offset']==2 and tree['truncated']
        all_nodes=c.get(prefix+f'/documents/{document["id"]}/tree').json()['items']
        node=next(n for n in all_nodes if n['node_type']=='action')
        response=c.post(prefix+'/commands/document.revise',json={'node_id':node['id'],'changes':{'text':{'en':'Revised action'}},'revision':document['revision'],'label':'Blue'})
        assert response.status_code==200,response.text
        assert c.post(prefix+'/commands/document.revise',json={'node_id':node['id'],'changes':{'text':{'en':'Lost'}},'revision':document['revision']}).status_code==409
        assert c.get(prefix+f'/versions/{version["id"]}/source').content==raw
        assert c.get('/api/v1/projects/not-this-project/documents').status_code==404
        assert c.post(prefix+'/commands/document.import',json={'path':'/etc/passwd','format':'screenjson'}).status_code in (403,422)


def test_api_document_upload_limit_is_checked_before_parsing():
    from storyboarder.api.limits import request_limit
    assert request_limit('/api/v1/projects/x/documents/upload')==21*1024*1024


def test_generation_pins_source_versions_and_reverse_media_usage(story, screenplay):
    s=story['service'];d=Documents(s);p=Provenance(s);register_sample()
    imported=d.import_bytes(json.dumps(screenplay).encode(),'source.json','screenjson')
    source=next(n for n in d.tree(imported['version']['id'])['items'] if n['node_type']=='scene')
    p.link('node',source['id'],'entity',story['shot']['id'],'visualizes')
    queued=Jobs(s).create('sample','frame',story['shot']['id'],'Candidate')
    pins=queued['request']['source_provenance']
    assert pins[0]['version_id']==imported['version']['id'] and len(pins[0]['scope_sha256'])==64
    assert any(n['key']=='job:'+queued['id'] for n in p.trace('node',source['id'],'downstream')['nodes'])
    assert any(n['key']=='job:'+queued['id'] for n in p.trace('media',story['exact']['id'],'downstream')['nodes'])
    # A new draft does not rewrite the queued request.
    node=next(n for n in d.tree(imported['version']['id'])['items'] if n['node_type']=='action')
    d.revise_node(node['id'],{'text':{'en':'A new action'}},imported['document']['revision'])
    assert s.get('jobs',queued['id'])['request']['source_provenance']==pins


def test_dependency_cycle_including_canonical_frame_is_rejected(story):
    s=story['service'];p=Provenance(s)
    frame=s.attach_frame(story['shot']['id'],story['exact']['id'])
    with pytest.raises(StoryboardError, match='cycle'):
        p.link('frame',frame['id'],'entity',story['shot']['id'],'derived-from')


@pytest.mark.parametrize('bad', ['text', {}, {'OTIO_SCHEMA':'TimeRange.1'}, 2])
def test_malformed_otio_ranges_are_domain_errors(service, edit_payload, bad):
    bad_payload=copy.deepcopy(edit_payload)
    bad_payload['tracks']['children'][0]['children'][0]['source_range']=bad
    with pytest.raises(StoryboardError):
        Documents(service).import_bytes(json.dumps(bad_payload).encode(),'bad.otio','otio')


def test_backup_closes_destination_connection(story, monkeypatch):
    # sqlite Connection.__exit__ commits, but does NOT close; Windows cannot unlink it.
    original=sqlite3.connect; connections=[]
    def connect(*args, **kwargs):
        conn=original(*args, **kwargs);connections.append(conn);return conn
    monkeypatch.setattr(sqlite3,'connect',connect)
    story['service'].backup()
    for conn in connections:
        with pytest.raises(sqlite3.ProgrammingError, match='closed'):
            conn.execute('SELECT 1')
