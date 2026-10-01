"""Provenance records explicit derivation, never guesses from visual positions."""
import importlib
import json

import pytest

from storyboarder.domain.errors import StoryboardError, Conflict
from test_documents import screenplay, edit_payload, uid, documents


def graph(service):
    return importlib.import_module('storyboarder.application.provenance').Provenance(service)


def source_node(service, screenplay):
    d = documents(service)
    imported = d.import_bytes(json.dumps(screenplay).encode(), 'source.json', format='screenjson')
    node = next(n for n in d.tree(imported['version']['id'])['items'] if n['logical_id'] == uid(4))
    return imported, node


def test_explicit_source_link_and_upstream_trace(story, screenplay):
    s = story['service']; p = graph(s)
    imported, node = source_node(s, screenplay)
    link = p.link('node', node['id'], 'entity', story['shot']['id'], 'visualizes')
    assert link['source_snapshot']['version_id'] == imported['version']['id']
    result = p.trace('entity', story['shot']['id'], 'upstream')
    assert any(n['id'] == node['id'] and n['type'] == 'node' for n in result['nodes'])
    assert any(n['id'] == story['exact']['id'] and n['type'] == 'media' for n in result['nodes'])
    # The canonical assignment is projected, not copied to the provenance table.
    with s.repo.transaction(False) as conn:
        assert conn.execute('SELECT count(*) FROM provenance_edges').fetchone()[0] == 1


def test_historical_links_do_not_repoint_on_new_draft(story, screenplay):
    s = story['service']; p = graph(s); d = documents(s)
    imported, node = source_node(s, screenplay)
    edge = p.link('node', node['id'], 'entity', story['shot']['id'], 'visualizes')
    later = d.revise_node(node['id'], {'text': {'en': 'Mara breaks the key.'}}, imported['document']['revision'], label='Blue')
    pinned = p.sources(story['shot']['id'])['items'][0]
    assert pinned['node_id'] == node['id']
    assert pinned['version_id'] == imported['version']['id']
    assert pinned['stale'] is True
    assert p.show(edge['id'])['source_id'] == node['id']
    assert later['version']['id'] != pinned['version_id']


def test_invalid_endpoints_and_semantic_directions_are_rejected(story, screenplay):
    s = story['service']; p = graph(s)
    _, node = source_node(s, screenplay)
    for args in [
        ('node', 'missing', 'entity', story['shot']['id'], 'visualizes'),
        ('entity', story['character']['id'], 'node', node['id'], 'visualizes'),
        ('node', node['id'], 'node', node['id'], 'corresponds-to'),
        ('node', node['id'], 'entity', story['character']['id'], 'appears-in'),
    ]:
        with pytest.raises(StoryboardError):
            p.link(*args)


def test_link_idempotency_and_retirement_keep_history(story, screenplay):
    s = story['service']; p = graph(s)
    _, node = source_node(s, screenplay)
    args = ('node', node['id'], 'entity', story['shot']['id'], 'visualizes')
    first = p.link(*args)
    assert p.link(*args)['id'] == first['id']
    retired = p.retire(first['id'], first['revision'])
    assert retired['retired']
    assert p.show(first['id'])['source_snapshot']['id'] == node['id']
    with pytest.raises(Conflict):
        p.retire(first['id'], first['revision'])
    assert not any(e.get('id') == first['id'] for e in p.trace('entity', story['shot']['id'], 'upstream')['edges'])


def test_derivation_cycle_is_not_allowed(story):
    s = story['service']; p = graph(s)
    a, b = story['character']['id'], story['prop']['id']
    p.link('entity', a, 'entity', b, 'derived-from')
    with pytest.raises(StoryboardError, match='cycle|loop'):
        p.link('entity', b, 'entity', a, 'derived-from')


def test_linked_entity_cannot_be_deleted(story, screenplay):
    s = story['service']; p = graph(s)
    _, node = source_node(s, screenplay)
    fresh = s.create_entity('asset', 'Linked reference')
    p.link('node', node['id'], 'entity', fresh['id'], 'corresponds-to')
    with pytest.raises(StoryboardError):
        s.lifecycle(fresh['id'], fresh['revision'], 'delete')


def test_impact_reaches_frames_and_current_edit(story, screenplay, edit_payload):
    s = story['service']; p = graph(s); d = documents(s)
    imported, node = source_node(s, screenplay)
    p.link('node', node['id'], 'entity', story['shot']['id'], 'visualizes')
    frame = s.attach_frame(story['shot']['id'], story['exact']['id'])
    edit = d.import_bytes(json.dumps(edit_payload).encode(), 'cut.otio', format='otio')
    clip = next(n for n in d.tree(edit['version']['id'])['items'] if n['node_type'] == 'Clip')
    p.link('frame', frame['id'], 'node', clip['id'], 'appears-in')
    later = d.revise_node(node['id'], {'text': {'en': 'Mara leaves.'}}, 1)
    impact = p.impact(imported['version']['id'], later['version']['id'])
    assert any(n['id'] == story['shot']['id'] for n in impact['affected'])
    assert any(n['id'] == frame['id'] for n in impact['affected'])
    assert any(n['id'] == clip['id'] for n in impact['affected'])


def test_coverage_distinguishes_missing_links_from_actual_screen_coverage(story, screenplay, edit_payload):
    s = story['service']; p = graph(s); d = documents(s)
    _, node = source_node(s, screenplay)
    p.link('node', node['id'], 'entity', story['shot']['id'], 'visualizes')
    edit = d.import_bytes(json.dumps(edit_payload).encode(), 'cut.otio', format='otio')
    report = p.coverage()
    assert report['counts']['screenplay_unlinked'] >= 1
    assert report['counts']['edit_unlinked'] == 1
    assert report['counts']['shots_without_approved_frames'] == 1
    assert 'explicit' in report['method'].lower()


def test_generation_source_pins_are_snapshots(story, screenplay):
    s = story['service']; p = graph(s); d = documents(s)
    imported, node = source_node(s, screenplay)
    p.link('node', node['id'], 'entity', story['shot']['id'], 'visualizes')
    pins = p.pins(story['shot']['id'])
    assert pins[0]['node_id'] == node['id'] and pins[0]['version_id'] == imported['version']['id']
    before = json.dumps(pins, sort_keys=True)
    d.revise_node(node['id'], {'text': {'en': 'Changed source.'}}, 1)
    assert json.dumps(pins, sort_keys=True) == before


def test_annotation_is_pinned_and_revision_checked(service, screenplay):
    p = graph(service)
    _, node = source_node(service, screenplay)
    note = p.annotate('node', node['id'], 'Keep the hand in frame.')
    assert note['endpoint_id'] == node['id']
    changed = p.update_annotation(note['id'], 1, 'Keep both hands in frame.', 'open')
    assert changed['revision'] == 2
    with pytest.raises(Conflict):
        p.update_annotation(note['id'], 1, 'Lost comment.', 'open')
    assert p.annotations('node', node['id'])['items'][0]['text'] == 'Keep both hands in frame.'
