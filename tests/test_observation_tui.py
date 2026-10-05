"""Human observation-contract page keeps exact pins and authored IDs stable."""
import asyncio
import copy
import json
from types import SimpleNamespace

import pytest
from prompt_toolkit.data_structures import Size
from prompt_toolkit.formatted_text import to_formatted_text
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.output import DummyOutput

import storyboarder.tui.app as tui_app
from storyboarder.application.documents import Documents
from storyboarder.application.observation_contracts import ObservationContracts
from storyboarder.domain.errors import Conflict
from storyboarder.tui.app import Desk
from storyboarder.tui.widgets import Row
from test_observation_planner import uid


@pytest.fixture
def imported_screenplay(story):
    author, char, scene_id = uid(99600), uid(99605), uid(99601)
    payload = {
        'id': uid(99602), 'version': '1.0.0', 'title': {'en': 'TUI source'},
        'lang': 'en', 'charset': 'utf-8', 'dir': 'ltr',
        'authors': [{'id': author, 'given': 'Test', 'family': 'Writer'}],
        'characters': [{'id': char, 'name': 'MARA'}],
        'document': {'cover': {'title': {'en': 'TUI source'}, 'authors': [author]},
                     'scenes': [{'id': scene_id, 'authors': [author],
                                 'heading': {'context': 'INT', 'setting': 'ROOM', 'time': 'DAY'},
                                 'body': [
                                     {'id': uid(99603), 'authors': [author], 'type': 'action',
                                      'text': {'en': 'A hand opens the door.'}},
                                     {'id': uid(99604), 'authors': [author], 'type': 'dialogue',
                                      'character': char, 'dual': False, 'text': {'en': 'We are here.'}},
                                 ]}]},
    }
    imported = Documents(story['service']).import_bytes(json.dumps(payload).encode(), 'tui-source.json', 'screenjson')
    nodes = Documents(story['service']).tree(imported['version']['id'])['items']
    return imported, {row['logical_id']: row for row in nodes}


class SizedDummyOutput(DummyOutput):
    def __init__(self, columns, rows):
        super().__init__()
        self.columns, self.rows = columns, rows

    def get_size(self):
        return Size(rows=self.rows, columns=self.columns)


async def render_tick():
    await asyncio.sleep(0.08)


def button_control(desk, label):
    for control in desk.app.layout.find_all_controls():
        if not isinstance(control, FormattedTextControl):
            continue
        try:
            text = ''.join(fragment[1] for fragment in to_formatted_text(control.text))
        except TypeError:
            continue
        if text.strip().strip('<> ').strip() == label:
            return control
    raise AssertionError(f'Button not found: {label}')


@pytest.mark.asyncio
@pytest.mark.parametrize('columns,rows', [(80, 24), (100, 30), (110, 35), (160, 50), (60, 20)])
async def test_observation_page_renders_at_supported_terminal_sizes(story, columns, rows):
    with create_pipe_input() as pipe:
        desk = Desk(project=story['service'].project, input=pipe,
                    output=SizedDummyOutput(columns, rows))
        task = asyncio.create_task(desk.app.run_async())
        try:
            desk.go('coverage')
            await render_tick()
            assert not task.done()
            assert desk.page == 'coverage'
            assert desk.detail.text
        finally:
            if not task.done():
                desk.app.exit()
            await asyncio.wait_for(task, timeout=3)


@pytest.mark.asyncio
async def test_coverage_page_is_keyboard_reachable(story):
    with create_pipe_input() as pipe:
        desk = Desk(project=story['service'].project, input=pipe, output=SizedDummyOutput(80, 24))
        task = asyncio.create_task(desk.app.run_async())
        try:
            await render_tick()
            desk.app.layout.focus(button_control(desk, 'Observation coverage'))
            pipe.send_text('\r')
            await render_tick()
            assert desk.page == 'coverage'
        finally:
            if not task.done():
                desk.app.exit()
            await asyncio.wait_for(task, timeout=3)


@pytest.mark.asyncio
async def test_first_human_plan_keeps_two_exact_source_pins_and_conflict_draft(story, imported_screenplay, monkeypatch):
    service = story['service']
    imported, nodes = imported_screenplay
    sources = [nodes[uid(99603)], nodes[uid(99604)]]
    with create_pipe_input() as pipe:
        desk = Desk(project=service.project, input=pipe, output=DummyOutput())
        desk.page = 'coverage'
        desk.build_page()
        desk.refresh = lambda: asyncio.sleep(0)
        desk.set_message = lambda message: setattr(desk, 'message', str(message))
        async def run_worker(function, *args, **kwargs): return function(*args, **kwargs)
        desk.run_worker = run_worker
        async def choose(title, choices, current=None, loader=None):
            if title == 'Choose the shot’s parent scene':
                return story['scene']['id']
            if title == 'Purpose basis':
                return 'direct'
            if title == 'Requirement priority':
                return 'must'
            if title == 'Requirement basis':
                return 'interpreted'
            if title == 'Add another exact source?':
                return 'yes' if title_counts[0] == 0 else 'no'
            raise AssertionError(f'unexpected picker: {title}')
        title_counts = [0]
        original_choose = choose
        async def numbered_choose(title, choices, current=None, loader=None):
            if title == 'Add another exact source?':
                value = 'yes' if title_counts[0] == 0 else 'no'
                title_counts[0] += 1
                return value
            return await original_choose(title, choices, current, loader)
        desk.choose = numbered_choose
        form_calls = []
        async def simple_form(title, fields, warning=''):
            form_calls.append(title)
            if title == 'Name the planned shot':
                return {'title': 'Two-beat shot'}
            if title == 'Describe this exact source':
                number = sum(name == title for name in form_calls)
                return {'purpose': f'Purpose {number}', 'communication': f'Visual read {number}'}
            if title == 'State the requirement':
                number = sum(name == title for name in form_calls)
                return {'statement': f'Requirement {number}'}
            raise AssertionError(f'unexpected form: {title}')
        desk.simple_form = simple_form
        source_iter = iter(sources)
        async def exact_source():
            node = next(source_iter)
            return {'document_id': imported['document']['id'], 'version_id': imported['version']['id'],
                    'node_id': node['id'], 'source_sha256': node['content_sha256'],
                    'node_type': node['node_type'], 'label': node['title']}
        desk._pick_exact_source = exact_source

        call = {'count': 0, 'payload': None}
        real_execute = tui_app.execute
        def fail_once(_service, name, payload):
            assert name == 'observation.create-group'
            call['count'] += 1
            call['payload'] = copy.deepcopy(payload)
            if call['count'] == 1:
                raise Conflict('Scene changed during authoring.')
            return real_execute(_service, name, payload)
        monkeypatch.setattr(tui_app, 'execute', fail_once)

        await desk.create_observation_plan()
        assert desk.observation_draft is not None
        item = call['payload']['request']['items'][0]
        assert item['expected_scene_revision'] == story['scene']['revision']
        assert len(item['source_edges']) == 2
        assert [edge['node_id'] for edge in item['source_edges']] == [node['id'] for node in sources]
        assert [edge['source_sha256'] for edge in item['source_edges']] == [node['content_sha256'] for node in sources]
        assert len({edge['edge_id'] for edge in item['source_edges']}) == 2
        saved_ids = (item['shot_id'], item['contract_id'],
                     tuple(edge['edge_id'] for edge in item['source_edges']),
                     tuple(intent['id'] for intent in item['contract']['script_intents']),
                     tuple(req['id'] for req in item['contract']['requirements']))

        first_payload = copy.deepcopy(call['payload'])
        await desk.retry_observation_draft()
        created = ObservationContracts(service).show(item['contract_id'])
        assert desk.observation_draft is None
        assert created['revision'] == 1
        assert {pin['node_id'] for pin in created['source_pins']} == {node['id'] for node in sources}
        assert call['payload'] == first_payload
        assert saved_ids == (item['shot_id'], item['contract_id'],
                             tuple(edge['edge_id'] for edge in item['source_edges']),
                             tuple(intent['id'] for intent in item['contract']['script_intents']),
                             tuple(req['id'] for req in item['contract']['requirements']))


@pytest.mark.asyncio
async def test_edit_one_requirement_keeps_other_contract_data_and_ids(story, monkeypatch):
    contract_id = uid(99500)
    shot_id = story['shot']['id']
    body = {
        'schema': 'storyboarder.observation-contract/v1',
        'source_pins': [{'edge_id': uid(99501), 'source_scope': 'direct-element'},
                        {'edge_id': uid(99502), 'source_scope': 'scene-context'}],
        'script_intents': [
            {'id': uid(99503), 'source_edge_id': uid(99501), 'source_scope': 'direct-element',
             'purpose': 'First purpose', 'communication': 'First visual read', 'basis': 'direct'},
            {'id': uid(99504), 'source_edge_id': uid(99502), 'source_scope': 'scene-context',
             'purpose': 'Second purpose', 'communication': 'Second visual read', 'basis': 'unknown'},
        ],
        'requirements': [
            {'id': uid(99505), 'priority': 'must', 'basis': 'interpreted',
             'source_edge_ids': [uid(99501)], 'statement': 'Old requirement statement'},
            {'id': uid(99506), 'priority': 'unknown', 'basis': 'unknown',
             'source_edge_ids': [uid(99502)], 'topic': 'Open continuity question'},
        ],
        'references': [uid(99507)],
        'continuity': [{'id': uid(99508), 'related_shot_ids': [shot_id], 'statement': 'Keep the arrival continuous.'}],
        'notes': 'Do not drop these saved notes.',
    }
    saved = {'id': contract_id, 'shot_id': shot_id, 'revision': 7,
             'contract': copy.deepcopy(body), 'version': {'id': uid(99509), 'number': 4}}
    monkeypatch.setattr(ObservationContracts, 'show', lambda _self, _contract_id: copy.deepcopy(saved))
    captured = {}
    def execute_spy(_service, name, payload):
        assert name == 'observation.revise'
        captured.update(copy.deepcopy(payload))
        return {'revision': 8}
    monkeypatch.setattr(tui_app, 'execute', execute_spy)
    with create_pipe_input() as pipe:
        desk = Desk(project=story['service'].project, input=pipe, output=DummyOutput())
        desk.page = 'coverage'
        desk.build_page()
        desk.selected = Row(contract_id, 'Test contract', '', {'id': contract_id})
        async def run_worker(function, *args, **kwargs): return function(*args, **kwargs)
        desk.run_worker = run_worker
        picks = iter([uid(99505), 'statement'])
        async def choose(*_args, **_kwargs): return next(picks)
        async def simple_form(_title, fields, warning=''): return {fields[0][0]: 'Edited requirement statement'}
        desk.choose, desk.simple_form = choose, simple_form
        desk.refresh = lambda: asyncio.sleep(0)
        desk.set_message = lambda message: setattr(desk, 'message', str(message))
        monkeypatch.setattr(tui_app, 'uuid', SimpleNamespace(
            uuid4=lambda: (_ for _ in ()).throw(AssertionError('render/edit regenerated an ID'))))

        await desk.edit_observation_field()
        updated = captured['contract']
        assert captured['revision'] == 7
        assert updated['requirements'][0]['statement'] == 'Edited requirement statement'
        assert updated['requirements'][0]['id'] == body['requirements'][0]['id']
        assert updated['requirements'][1] == body['requirements'][1]
        assert updated['script_intents'] == body['script_intents']
        assert updated['source_pins'] == body['source_pins']
        assert updated['references'] == body['references']
        assert updated['continuity'] == body['continuity']
        assert updated['notes'] == body['notes']
