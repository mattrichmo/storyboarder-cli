import asyncio
import json
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from prompt_toolkit.formatted_text import to_formatted_text
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.output import DummyOutput

import storyboarder.tui.app as tui_app
from storyboarder.application.documents import Documents
from storyboarder.application.source_workflows import SourceWorkflows
from storyboarder.commands.core import source_options, source_record
from storyboarder.domain.errors import NotFound
from storyboarder.tui.app import Desk
from test_documents import screenplay


async def render_tick():
    await asyncio.sleep(0.06)


def find_button_control(desk, label):
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
async def test_document_revise_form_uses_document_revision(service, screenplay, monkeypatch):
    imported = Documents(service).import_bytes(json.dumps(screenplay).encode(), 'source.json', 'screenjson')
    node = next(row for row in Documents(service).tree(imported['version']['id'])['items'] if row['node_type'] == 'action')
    captured = {}

    def execute_spy(_service, name, payload):
        assert name == 'document.revise'
        captured.update(payload)
        return {'ok': True}

    monkeypatch.setattr(tui_app, 'execute', execute_spy)
    with create_pipe_input() as pipe:
        desk = Desk(project=service.project, input=pipe, output=DummyOutput())
        app_task = asyncio.create_task(desk.app.run_async())

        async def choose_node(_title, _choices, _current=None, loader=None):
            page = await loader('Mara turns', 0)
            assert any(item['id'] == node['id'] for item in page['items'])
            return node['id']

        desk.choose = choose_node
        try:
            await render_tick()
            form = desk.spawn(desk.command_form('document.revise'))
            await render_tick()
            source_button = find_button_control(desk, 'Choose…')
            desk.app.layout.focus(source_button)
            pipe.send_text('\r')
            await render_tick()
            changes = next(control for control in desk.app.layout.find_all_controls()
                           if isinstance(control, BufferControl) and control.buffer.name == 'changes')
            changes.buffer.text = '{"text":{"en":"Revised from the TUI"}}'
            save = find_button_control(desk, 'Save / view')
            desk.app.layout.focus(save)
            pipe.send_text('\r')
            await asyncio.wait_for(form, timeout=4)
            assert captured['node_id'] == node['id']
            assert captured['revision'] == imported['document']['revision']
        finally:
            if not app_task.done(): desk.app.exit()
            await asyncio.wait_for(app_task, timeout=3)


def test_source_choices_are_bounded_and_revision_aware(service, screenplay, monkeypatch):
    imported = Documents(service).import_bytes(json.dumps(screenplay).encode(), 'source.json', 'screenjson')
    monkeypatch.setattr(service, 'state', lambda: (_ for _ in ()).throw(AssertionError('full state snapshot requested')))

    documents = source_options(service, 'documents', limit=1)
    assert documents['total'] == 1 and documents['items'][0]['id'] == imported['document']['id']
    nodes = source_options(service, 'document_nodes', query='Mara turns', limit=1)
    assert nodes['total'] == 1 and nodes['items'][0]['document_id'] == imported['document']['id']
    node_id = nodes['items'][0]['id']
    node = source_record(service, 'document_nodes', node_id)
    assert node['revision'] == imported['document']['revision']
    other_source = json.loads(json.dumps(screenplay))
    other_source['id'] = '00000000-0000-0000-0000-0000000000c8'
    other = Documents(service).import_bytes(json.dumps(other_source).encode(), 'second.json', 'screenjson')
    with pytest.raises(NotFound, match='different document'):
        source_record(service, 'document_nodes', node_id, {'document_id': other['document']['id']})
    with pytest.raises(NotFound, match='different document'):
        source_record(service, 'versions', imported['version']['id'], {'id': other['document']['id']})

    SourceWorkflows(service).archive(imported['document']['id'], imported['document']['revision'], True)
    SourceWorkflows(service).archive(other['document']['id'], other['document']['revision'], True)
    assert source_options(service, 'provenance_source', {'source_type': 'node'})['total'] == 0
    assert source_options(service, 'provenance_typed_endpoint', {'kind': 'node'})['total'] > 0


@pytest.mark.asyncio
async def test_escape_closes_only_the_top_dialog(service):
    with create_pipe_input() as pipe:
        desk = Desk(project=service.project, input=pipe, output=DummyOutput())
        app_task = asyncio.create_task(desk.app.run_async())
        try:
            await render_tick()
            outer = desk.spawn(desk.choose('Outer picker', [('outer', 'Outer item')]))
            await render_tick()
            inner = desk.spawn(desk.choose('Inner picker', [('inner', 'Inner item')]))
            await render_tick()
            assert desk.modal_depth == 2
            pipe.send_bytes(b'\x1b')
            await asyncio.wait_for(inner, timeout=3)
            await render_tick()
            assert desk.modal_depth == 1 and not outer.done()
            pipe.send_bytes(b'\x1b')
            await asyncio.wait_for(outer, timeout=3)
            await render_tick()
            assert desk.modal_depth == 0
        finally:
            if not app_task.done(): desk.app.exit()
            await asyncio.wait_for(app_task, timeout=3)


@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['create', 'restore'])
async def test_quit_waits_for_project_create_and_restore_workers(operation, monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def blocking_worker(*args):
        entered.set()
        release.wait(timeout=3)
        if operation == 'create': return SimpleNamespace(root=Path('/tmp/new-project'))
        return {'path': '/tmp/restored-project'}

    monkeypatch.setattr(tui_app.Project, 'create', blocking_worker)
    monkeypatch.setattr(tui_app, 'restore', blocking_worker)
    with create_pipe_input() as pipe:
        desk = Desk(input=pipe, output=DummyOutput())
        app_task = asyncio.create_task(desk.app.run_async())
        exits = Mock()
        app_exit = desk.app.exit
        def exit_spy(*args, **kwargs):
            exits(*args, **kwargs)
            return app_exit(*args, **kwargs)
        desk.app.exit = exit_spy

        async def simple_form(*args, **kwargs):
            if operation == 'create': return {'title': 'New project', 'path': '/tmp/new-project'}
            return {'archive': '/tmp/backup.zip', 'path': '/tmp/restored-project'}

        async def choose(*args, **kwargs): return 'yes'
        async def no_op(*args, **kwargs): return None

        desk.simple_form = simple_form
        desk.choose = choose
        desk.message_dialog = no_op
        desk.refresh = no_op
        desk.open_project = no_op
        try:
            await render_tick()
            action = desk.create_project() if operation == 'create' else desk.restore_backup()
            task = desk.spawn(action)
            assert await asyncio.to_thread(entered.wait, 2)
            assert desk.busy
            await desk.quit()
            exits.assert_not_called()
            release.set()
            await asyncio.wait_for(task, timeout=3)
            await render_tick()
            assert not desk.busy
        finally:
            release.set()
            if not app_task.done():
                desk.app.exit()
            await asyncio.wait_for(app_task, timeout=3)
