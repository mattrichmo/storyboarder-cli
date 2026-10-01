"""Document history must preserve source bytes, stable identity and old story records."""
import copy
import importlib
import json
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from storyboarder.domain.errors import StoryboardError, Conflict


def documents(service):
    return importlib.import_module('storyboarder.application.documents').Documents(service)


def uid(n):
    return str(uuid.UUID(int=n))


@pytest.fixture
def screenplay():
    author, char, scene = uid(1), uid(2), uid(3)
    return {
        'id': uid(100), 'version': '1.0.0', 'title': {'en': 'Winter Station', 'fr': 'La gare'},
        'lang': 'en', 'charset': 'utf-8', 'dir': 'ltr',
        'authors': [{'id': author, 'given': 'Test', 'family': 'Writer'}],
        'characters': [{'id': char, 'name': 'MARA'}],
        'document': {'cover': {'title': {'en': 'Winter Station'}, 'authors': [author]},
                     'scenes': [{'id': scene, 'authors': [author],
                        'heading': {'context': 'INT', 'setting': 'STATION', 'time': 'DAWN'},
                        'meta': {'production': {'weather': 'snow'}},
                        'body': [
                            {'id': uid(4), 'authors': [author], 'type': 'action', 'text': {'en': 'Mara turns the key.', 'fr': 'Mara tourne la clé.'}},
                            {'id': uid(5), 'authors': [author], 'type': 'character', 'character': char},
                            {'id': uid(6), 'authors': [author], 'type': 'dialogue', 'character': char, 'dual': False, 'text': {'en': 'We stay.'}},
                        ]}]},
    }


@pytest.fixture
def edit_payload():
    return {
        'OTIO_SCHEMA': 'Timeline.1', 'name': 'Assembly', 'metadata': {},
        'tracks': {'OTIO_SCHEMA': 'Stack.1', 'name': 'tracks', 'metadata': {}, 'children': [
            {'OTIO_SCHEMA': 'Track.1', 'name': 'V1', 'kind': 'Video', 'metadata': {'storyboarder': {'id': uid(201)}}, 'children': [
                {'OTIO_SCHEMA': 'Clip.1', 'name': 'Station', 'metadata': {'storyboarder': {'id': uid(202)}},
                 'source_range': {'OTIO_SCHEMA': 'TimeRange.1',
                     'start_time': {'OTIO_SCHEMA': 'RationalTime.1', 'value': 12.0, 'rate': 24.0},
                     'duration': {'OTIO_SCHEMA': 'RationalTime.1', 'value': 96.0, 'rate': 24.0}},
                 'media_reference': {'OTIO_SCHEMA': 'ExternalReference.1', 'target_url': 'file:///originals/station.mov'}}]}]}}


def test_screenjson_import_retains_bytes_order_and_identity(service, screenplay):
    d = documents(service)
    raw = json.dumps(screenplay, ensure_ascii=False, indent=3).encode()
    imported = d.import_bytes(raw, 'winter.screenjson', format='screenjson')
    version = imported['version']
    assert imported['document']['kind'] == 'screenplay'
    assert d.export_payload(version['id']) == screenplay
    assert d.source_bytes(version['id']) == raw
    roots = d.children(version['id'])['items']
    scenes = d.children(version['id'], roots[0]['id'])['items']
    assert scenes[0]['logical_id'] == uid(3)
    elements = d.children(version['id'], scenes[0]['id'])['items']
    assert [n['node_type'] for n in elements] == ['action', 'character', 'dialogue']
    assert [n['logical_id'] for n in elements] == [uid(4), uid(5), uid(6)]
    assert all('payload' not in n for n in elements)
    assert d.node(elements[0]['id'])['payload']['text']['fr'] == 'Mara tourne la clé.'
    assert len(service.state()['entities']) == 1


def test_reimport_is_idempotent_even_with_different_json_whitespace(service, screenplay):
    d = documents(service)
    first = d.import_bytes(json.dumps(screenplay).encode(), 'a.json', format='screenjson')
    again = d.import_bytes(json.dumps(screenplay, indent=4).encode(), 'b.json', format='screenjson', document_id=first['document']['id'], revision=first['document']['revision'])
    assert again['unchanged']
    assert again['version']['id'] == first['version']['id']
    assert len(d.versions(first['document']['id'])['items']) == 1
    assert again['document']['revision'] == first['document']['revision']


def test_edit_creates_immutable_version_and_meaningful_diff(service, screenplay):
    d = documents(service)
    first = d.import_bytes(json.dumps(screenplay).encode(), 'draft.json', format='screenjson')
    v = first['version']['id']; doc = first['document']
    node = next(n for n in d.tree(v)['items'] if n['logical_id'] == uid(4))
    second = d.revise_node(node['id'], {'text': {'en': 'Mara leaves the key.', 'fr': 'Mara laisse la clé.'}}, doc['revision'], label='Blue')
    assert d.export_payload(v) == screenplay
    assert second['version']['id'] != v
    difference = d.diff(v, second['version']['id'])
    assert [r['logical_id'] for r in difference['changed']] == [uid(4)]
    assert not difference['added'] and not difference['removed']
    assert second['version']['parent_version_id'] == v
    with pytest.raises(Conflict):
        d.revise_node(node['id'], {'text': {'en': 'Stale'}}, doc['revision'], label='Lost')


def test_document_versions_and_nodes_reject_in_place_update(service, screenplay):
    d = documents(service)
    first = d.import_bytes(json.dumps(screenplay).encode(), 'draft.json', format='screenjson')
    with pytest.raises(StoryboardError, match='immutable'):
        with service.repo.transaction() as conn:
            conn.execute('UPDATE document_versions SET label=? WHERE id=?', ('Changed', first['version']['id']))
    with pytest.raises(StoryboardError, match='immutable'):
        with service.repo.transaction() as conn:
            conn.execute('DELETE FROM document_nodes WHERE version_id=?', (first['version']['id'],))


@pytest.mark.parametrize('bad', ['duplicate', 'character', 'scene', 'node-type', 'nonfinite'])
def test_invalid_screenjson_never_creates_document(service, screenplay, bad):
    d = documents(service)
    broken = copy.deepcopy(screenplay)
    body = broken['document']['scenes'][0]['body']
    if bad == 'duplicate': body[1]['id'] = body[0]['id']
    elif bad == 'character': body[2]['character'] = uid(999)
    elif bad == 'scene': body[0]['scene'] = uid(999)
    elif bad == 'node-type': body[0]['type'] = 'made-up'
    elif bad == 'nonfinite': body[0]['meta'] = {'n': float('nan')}
    with pytest.raises(StoryboardError):
        d.import_bytes(json.dumps(broken).encode(), 'bad.json', format='screenjson')
    assert not d.list()['items']


def test_otio_roundtrip_preserves_exact_rates_ranges_and_media_urls(service, edit_payload):
    d = documents(service)
    raw = json.dumps(edit_payload).encode()
    result = d.import_bytes(raw, 'cut.otio', format='otio')
    assert result['document']['kind'] == 'edit'
    assert d.export_payload(result['version']['id']) == edit_payload
    clip = next(n for n in d.tree(result['version']['id'])['items'] if n['node_type'] == 'Clip')
    assert clip['logical_id'] == uid(202)
    assert d.node(clip['id'])['payload']['source_range']['duration']['rate'] == 24
    assert d.source_bytes(result['version']['id']) == raw


def test_concurrent_revisions_have_one_winner(service, screenplay):
    d = documents(service)
    initial = d.import_bytes(json.dumps(screenplay).encode(), 'draft.json', format='screenjson')
    element = next(n for n in d.tree(initial['version']['id'])['items'] if n['logical_id'] == uid(4))
    def revise(word):
        try:
            return d.revise_node(element['id'], {'text': {'en': word}}, 1, label=word)
        except Conflict:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(revise, ['One', 'Two']))
    assert outcomes.count('conflict') == 1
    assert len(d.versions(initial['document']['id'])['items']) == 2


def test_tree_child_pagination_is_explicit(service, screenplay):
    d = documents(service)
    result = d.import_bytes(json.dumps(screenplay).encode(), 'draft.json', format='screenjson')
    scene = next(n for n in d.tree(result['version']['id'])['items'] if n['node_type'] == 'scene')
    first = d.children(result['version']['id'], scene['id'], limit=2)
    assert len(first['items']) == 2 and first['total'] == 3 and first['next_offset'] == 2
    assert len(d.children(result['version']['id'], scene['id'], offset=2, limit=2)['items']) == 1


def test_backup_restore_includes_document_sources(service, screenplay, tmp_path):
    from storyboarder.application.recovery import restore
    from storyboarder.application.service import Service
    d = documents(service)
    raw = json.dumps(screenplay).encode()
    result = d.import_bytes(raw, 'original.json', format='screenjson')
    saved = service.backup()
    restored = restore(service.root / saved['path'], tmp_path / 'restored-documents')
    fresh = Service(restored['path'])
    assert documents(fresh).source_bytes(result['version']['id']) == raw
    assert fresh.doctor(True)['healthy']


def test_source_tampering_is_reported_by_doctor(service, screenplay):
    d = documents(service)
    result = d.import_bytes(json.dumps(screenplay).encode(), 'original.json', format='screenjson')
    source = d.version(result['version']['id'])['source']
    (service.root / source['path']).write_bytes(b'changed')
    health = service.doctor(True)
    assert not health['healthy']
    assert any(issue['code'] == 'document_source_integrity' for issue in health['issues'])


def test_wrong_version_parent_is_rejected(service, screenplay):
    d = documents(service)
    first = d.import_bytes(json.dumps(screenplay).encode(), 'original.json', format='screenjson')
    node = next(n for n in d.tree(first['version']['id'])['items'] if n['node_type'] == 'action')
    second = d.revise_node(node['id'], {'text': {'en': 'Changed'}}, 1)
    with pytest.raises(StoryboardError):
        d.children(second['version']['id'], node['id'])


def test_empty_and_duplicate_json_keys_are_rejected(service):
    d = documents(service)
    for raw in (b'', b'{"id": 1, "id": 2}', b'[]'):
        with pytest.raises(StoryboardError):
            d.import_bytes(raw, 'broken.json')


def test_otio_negative_duration_is_rejected(service, edit_payload):
    d = documents(service)
    edit_payload['tracks']['children'][0]['children'][0]['source_range']['duration']['value'] = -1
    with pytest.raises(StoryboardError):
        d.import_bytes(json.dumps(edit_payload).encode(), 'broken.otio', format='otio')
