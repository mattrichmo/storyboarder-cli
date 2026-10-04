"""Source pickers share bounded queries and current revision tokens across clients."""
import json
import uuid

from fastapi.testclient import TestClient

from storyboarder.api.server import create_app
from storyboarder.application.documents import Documents


def import_screenplay(service, name='Picker screenplay'):
    author_id = str(uuid.uuid4())
    payload = {
        'id': str(uuid.uuid4()), 'version': '1.0.0', 'lang': 'en',
        'charset': 'utf-8', 'dir': 'ltr', 'title': {'en': name},
        'authors': [{'id': author_id, 'given': 'Picker', 'family': 'Writer'}], 'characters': [],
        'document': {
            'cover': {'title': {'en': name}, 'authors': [author_id]},
            'scenes': [{
                'id': str(uuid.uuid4()), 'authors': [author_id],
                'heading': {'context': 'INT', 'setting': 'STATION', 'time': 'DAWN'},
                'body': [{'id': str(uuid.uuid4()), 'authors': [author_id], 'type': 'action',
                          'text': {'en': 'Mara turns the key.'}}],
            }],
        },
    }
    return Documents(service).import_bytes(json.dumps(payload).encode(), name + '.json', 'screenjson')


def picker_path(service, command, field):
    return f'/api/v1/projects/{service.project.id}/commands/{command}/fields/{field}/choices'


def test_source_picker_paging_search_and_revision(service):
    first = import_screenplay(service, 'First picker screenplay')
    second = import_screenplay(service, 'Second picker screenplay')
    with TestClient(create_app(service.root), base_url='http://127.0.0.1:7430') as client:
        path = picker_path(service, 'document.archive', 'document_id')
        page = client.get(path, params={'limit': 1}).json()
        assert len(page['items']) == 1
        assert page['total'] == 2
        assert page['next_offset'] == 1
        following = client.get(path, params={'limit': 1, 'offset': page['next_offset']}).json()
        assert {page['items'][0]['id'], following['items'][0]['id']} == {
            first['document']['id'], second['document']['id'],
        }
        found = client.get(path, params={'query': 'First picker'}).json()
        assert [row['id'] for row in found['items']] == [first['document']['id']]
        row = client.get(path + '/' + first['document']['id']).json()
        assert row['revision'] == first['document']['revision']
        node = next(n for n in Documents(service).tree(first['version']['id'])['items']
                    if n['node_type'] == 'action')
        record = client.get(picker_path(service, 'document.revise', 'node_id') + '/' + node['id']).json()
        assert record['document_id'] == first['document']['id']
        assert record['revision'] == first['document']['revision']
        version_path = picker_path(service, 'document.validate', 'version_id')
        assert client.get(version_path + '/' + first['version']['id'],
                          params={'values': json.dumps({'id': second['document']['id']})}).status_code == 404



def test_picker_grant_and_catalog_boundary(service):
    imported = import_screenplay(service)
    with TestClient(create_app(service.root), base_url='http://127.0.0.1:7430') as client:
        path = picker_path(service, 'document.archive', 'document_id')
        assert client.get(path.replace(service.project.id, str(uuid.uuid4()))).status_code == 404
        assert client.get(picker_path(service, 'unknown.action', 'document_id')).status_code == 404
        assert client.get(picker_path(service, 'document.import', 'document_id')).status_code == 404
        assert client.get(picker_path(service, 'document.archive', 'unknown_table')).status_code == 404
        assert client.get(path, params={'limit': 101}).status_code == 422
        for values in ('[]', 'not-json', '{"unknown":"value"}', '{"document_id":{}}'):
            assert client.get(path, params={'values': values}).status_code == 422
        assert client.get(path, headers={'Origin': 'https://example.com'}).status_code == 403
        assert client.get(path + '/' + imported['document']['id'], headers={'Host': 'example.com'}).status_code == 403
