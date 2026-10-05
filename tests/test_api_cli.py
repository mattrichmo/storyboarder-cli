from pathlib import Path
import argparse
import json
import subprocess
import sys
import pytest
from fastapi.testclient import TestClient
from storyboarder.api.server import create_app
from storyboarder.application.projects import Project
from storyboarder.application.service import Service
from storyboarder.application.commands import COMMANDS
from storyboarder.cli.main import COMMAND_GROUP_HELP, CONVENIENCE_HELP, build_parser

@pytest.fixture
def client(workspace):
    app=create_app(workspace=workspace,port=7430)
    with TestClient(app,base_url='http://127.0.0.1:7430') as client:
        client.headers['X-Storyboarder-Token']=client.get('/api/v1/session').json()['token']
        yield client


def test_workspace_browser_project_creation_switching_shared_core(client,workspace):
    a=client.post('/api/v1/projects',json={'title':'First','slug':'first'})
    assert a.status_code==201,a.text
    first=a.json();second=client.post('/api/v1/projects',json={'title':'Second','slug':'second'}).json()
    assert client.post('/api/v1/active',json={'id':first['id']}).status_code==200
    assert workspace.current().id==first['id']
    created=client.post(f"/api/v1/projects/{first['id']}/commands/asset.create",json={'title':'Browser asset','type':'character'})
    assert created.status_code==200,created.text
    assert Service(workspace.current()).get('entities',created.json()['id'])['title']=='Browser asset'
    assert client.get(f"/api/v1/projects/{second['id']}/entities?kind=asset").json()['total']==0


@pytest.mark.parametrize('headers',[
 {'Host':'evil.example'}, {'Host':'127.0.0.1.evil.example:7430'},
 {'Origin':'https://evil.example'}, {'Sec-Fetch-Site':'cross-site'},
])
def test_host_origin_and_fetch_metadata_guard(client,headers):
    response=client.get('/api/v1/session',headers=headers)
    assert response.status_code==403


def test_launch_token_required_for_writes(client):
    response=client.post('/api/v1/projects',headers={'X-Storyboarder-Token':'wrong'},json={'title':'Denied','slug':'denied'})
    assert response.status_code==403
    assert client.get('/api/v1/projects').json()==[]


def test_unknown_external_project_inaccessible(client,workspace,tmp_path):
    external=Project.create(tmp_path/'external','External')
    workspace.register(external.root)
    assert client.get(f'/api/v1/projects/{external.id}/state').status_code==404
    assert all(p['id']!=external.id for p in client.get('/api/v1/projects').json())


def test_browser_creation_never_accepts_arbitrary_path(client):
    assert client.post('/api/v1/projects',json={'title':'Escape','slug':'../escape'}).status_code in (422,403)
    assert client.post('/api/v1/projects',json={'title':'Escape','slug':'escape','path':'/tmp/other'}).status_code==422


def test_api_revision_conflict_returns_current_record(client,workspace):
    project=workspace.create('Shared','shared')
    prefix=f'/api/v1/projects/{project.id}'
    asset=client.post(prefix+'/entities',json={'kind':'asset','title':'One'}).json()
    changed=client.patch(prefix+'/entities/'+asset['id'],json={'revision':1,'changes':{'title':'Two'}})
    assert changed.status_code==200
    conflict=client.patch(prefix+'/entities/'+asset['id'],json={'revision':1,'changes':{'title':'Three'}})
    assert conflict.status_code==409
    assert conflict.json()['error']['details']['current']['title']=='Two'


def test_multipart_import_exact_media_and_export_routes(client,workspace,image_factory):
    project=workspace.create('Images','images');prefix=f'/api/v1/projects/{project.id}'
    source=image_factory()
    response=client.post(prefix+'/upload',files={'file':('image.png',source.read_bytes(),'image/png')},data={'original_path':'local-folder/image.png'})
    assert response.status_code==201,response.text
    media=response.json()['media']
    assert client.get(prefix+'/media/'+media['id']).content==source.read_bytes()
    thumb=client.get(prefix+'/media/'+media['id']+'?size=160')
    assert thumb.status_code==200 and thumb.headers['content-type']=='image/jpeg'
    assert client.get(prefix+'/media/'+media['id']+'?size=999').status_code==422
    assert client.post(prefix+'/commands/media.import',json={'path':'/etc/passwd'}).status_code in (403,422)
    result=client.post(prefix+'/commands/export.bundle',json={'owner_id':project.id}).json()
    assert client.get(prefix+'/files/'+result['archive']).status_code==200
    assert client.get(prefix+'/files/.storyboarder/storyboard.sqlite3').status_code==403


def test_bounded_body_including_chunked_transfer(client):
    response=client.post('/api/v1/projects',content=(b'x'*65536 for _ in range(34)),headers={'Content-Type':'application/json'})
    assert response.status_code==413,response.text[:200]
    assert client.post('/api/v1/projects',content=b'{}',headers={'Content-Length':'-1'}).status_code==400


def test_packaged_frontend_no_remote_assets_and_security_headers(client):
    response=client.get('/')
    assert response.status_code==200
    assert 'http://' not in response.text and 'https://' not in response.text
    assert 'Content-Security-Policy' in response.headers
    assert client.get('/missing.js').status_code==404
    assert client.get('/api/v1/missing').status_code==404
    assert client.get('/api/v1/openapi.json').json()['info']['title']=='Storyboarder local API'


def cli(*args,cwd=None):
    return subprocess.run([sys.executable,'-m','storyboarder',*map(str,args)],cwd=cwd,text=True,capture_output=True,timeout=20)


def _leaf_parser(parser, group, action):
    group_subparsers = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    action_subparsers = next(
        a for a in group_subparsers.choices[group]._actions
        if isinstance(a, argparse._SubParsersAction)
    )
    return action_subparsers.choices[action]


def test_catalog_cli_help_shows_field_rules_and_all_commands_parse():
    parser = build_parser()
    catalog_groups = {name.split('.', 1)[0] for name in COMMANDS}
    assert catalog_groups <= COMMAND_GROUP_HELP.keys()
    root_help = parser.format_help()
    for description in (*COMMAND_GROUP_HELP.values(), *CONVENIENCE_HELP.values()):
        assert description in root_help
    for name, command in COMMANDS.items():
        group, action = name.split('.', 1)
        leaf = _leaf_parser(parser, group, action)
        help_text = leaf.format_help()
        named_args = [group, action]
        for field in command.fields:
            option = '--' + field.name.replace('_', '-')
            argument = leaf._option_string_actions[option]
            assert argument.default is argparse.SUPPRESS
            assert argument.choices == (field.options or None)
            assert option in help_text
            if field.required:
                assert '[required]' in argument.help
                if field.type != 'boolean':
                    if field.options:
                        value = field.options[0]
                    elif field.type in ('integer', 'number'):
                        value = '1'
                    elif field.type == 'json':
                        value = '{}'
                    else:
                        value = 'sample'
                    named_args.extend((option, value))
                else:
                    named_args.append(option)
            if field.default is not None:
                marker = '[default: ' + json.dumps(field.default, ensure_ascii=False) + ']'
                assert marker in argument.help

        # Payloads and named flags both remain valid ways to invoke every catalog command.
        assert parser.parse_args([group, action, '--payload', '{}']).command == name
        assert parser.parse_args(named_args).command == name


def test_bare_cli_noninteractive_help_not_tui():
    response=cli()
    assert response.returncode==0 and 'usage:' in response.stdout.lower()


def test_cli_create_edit_list_discover_and_stale_exit(tmp_path):
    root=tmp_path/'project'
    created=cli('project','create',root,'--title','CLI project','--json')
    assert created.returncode==0,created.stderr
    asset=cli('asset','create','--title','Caretaker','--type','character','--project',root,'--json')
    assert asset.returncode==0,asset.stderr
    record=json.loads(asset.stdout)
    updated=cli('asset','update','--id',record['id'],'--revision','1','--title','Mara','--json',cwd=root/'media')
    assert updated.returncode==0,updated.stderr
    stale=cli('asset','update','--id',record['id'],'--revision','1','--title','Lost update','--project',root,'--json')
    assert stale.returncode==3 and json.loads(stale.stdout or stale.stderr)['error']['code']=='revision_conflict'
    listed=cli('asset','list','--json',cwd=root)
    assert listed.returncode==0 and json.loads(listed.stdout)['items'][0]['title']=='Mara'
    assert cli('doctor','--hashes','--project',root,'--json').returncode==0
