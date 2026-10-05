"""Lifecycle preflight and archive policy for retained source history."""
import json

import pytest

from storyboarder.application.provenance import Provenance
from storyboarder.application.source_workflows import SourceWorkflows
from storyboarder.domain.errors import InUse, StoryboardError
from test_documents import documents, edit_payload, screenplay, uid


def source_node(service, payload):
    imported = documents(service).import_bytes(json.dumps(payload).encode(), 'source.json', format='screenjson')
    node = next(n for n in documents(service).tree(imported['version']['id'])['items'] if n['logical_id'] == uid(4))
    return imported, node


def test_entity_usage_reports_retained_annotations_and_all_provenance_history(service):
    provenance = Provenance(service)
    entity = service.create_entity('asset', 'Retained record')
    other = service.create_entity('asset', 'Connected record')
    annotation = provenance.annotate('entity', entity['id'], 'Keep this context with the record.')
    active = provenance.link('entity', entity['id'], 'entity', other['id'], 'corresponds-to')
    retired = provenance.link('entity', other['id'], 'entity', entity['id'], 'corresponds-to')
    provenance.retire(retired['id'], retired['revision'])

    usage = service.usage(entity['id'])
    assert usage['can_delete'] is False
    assert usage['annotations'] == [annotation['id']]
    assert set(usage['provenance_links']) == {active['id'], retired['id']}
    with pytest.raises(InUse) as caught:
        service.lifecycle(entity['id'], entity['revision'], 'delete')
    assert caught.value.details == usage
    assert service.get('entities', entity['id'])['id'] == entity['id']


def test_archived_document_state_blocks_new_node_and_version_links_but_keeps_history(story, screenplay):
    service = story['service']
    provenance = Provenance(service)
    imported, node = source_node(service, screenplay)
    existing = provenance.link('node', node['id'], 'entity', story['shot']['id'], 'visualizes')

    SourceWorkflows(service).archive(imported['document']['id'], imported['document']['revision'])

    assert provenance.endpoint('node', node['id'])['archived'] is True
    assert provenance.endpoint('version', imported['version']['id'])['archived'] is True
    assert provenance.show(existing['id'])['id'] == existing['id']
    historical = provenance.trace('entity', story['shot']['id'], 'upstream')
    source = next(item for item in historical['nodes'] if item['key'] == f"node:{node['id']}")
    assert source['archived'] is True

    second_shot = service.create_entity('shot', 'Another shot', story['scene']['id'])
    with pytest.raises(StoryboardError, match='archived'):
        provenance.link('node', node['id'], 'entity', second_shot['id'], 'visualizes')
    with pytest.raises(StoryboardError, match='archived'):
        provenance.link('version', imported['version']['id'], 'entity', second_shot['id'])


def test_archived_frame_state_and_archived_parent_shot_block_new_links(story, edit_payload):
    service = story['service']
    provenance = Provenance(service)
    imported = documents(service).import_bytes(json.dumps(edit_payload).encode(), 'cut.otio', format='otio')
    clip = next(n for n in documents(service).tree(imported['version']['id'])['items'] if n['node_type'] == 'Clip')

    frame = service.attach_frame(story['shot']['id'], story['exact']['id'])
    existing = provenance.link('frame', frame['id'], 'node', clip['id'], 'appears-in')
    service.set_frame_state(frame['id'], frame['revision'], 'archived')
    assert provenance.endpoint('frame', frame['id'])['archived'] is True
    assert provenance.show(existing['id'])['id'] == existing['id']
    historical = provenance.trace('node', clip['id'], 'upstream')
    source = next(item for item in historical['nodes'] if item['key'] == f"frame:{frame['id']}")
    assert source['archived'] is True

    another_frame = service.attach_frame(story['shot']['id'], story['first']['id'])
    shot = service.get('entities', story['shot']['id'])
    service.lifecycle(shot['id'], shot['revision'], 'archive')
    assert provenance.endpoint('frame', another_frame['id'])['archived'] is True
    with pytest.raises(StoryboardError, match='archived'):
        provenance.link('frame', another_frame['id'], 'node', clip['id'], 'appears-in')


def test_archived_shot_blocks_new_provenance_links_as_source_and_target(story):
    service = story['service']
    provenance = Provenance(service)
    archived_shot = story['shot']
    active_shot = service.create_entity('shot', 'Another angle', story['scene']['id'])
    service.lifecycle(archived_shot['id'], archived_shot['revision'], 'archive')

    with pytest.raises(StoryboardError, match='archived'):
        provenance.link('entity', archived_shot['id'], 'entity', active_shot['id'], 'corresponds-to')
    with pytest.raises(StoryboardError, match='archived'):
        provenance.link('entity', active_shot['id'], 'entity', archived_shot['id'], 'corresponds-to')
