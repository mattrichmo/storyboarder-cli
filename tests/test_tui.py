import asyncio
import pytest
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from prompt_toolkit.formatted_text import to_formatted_text
from prompt_toolkit.layout.controls import FormattedTextControl, BufferControl
from storyboarder.tui.app import Desk
from storyboarder.tui.pages import PAGES, rows_for
from storyboarder.application.service import Service

async def rendered():
    await asyncio.sleep(.07)

def find_button(desk,text):
    for control in desk.app.layout.find_all_controls():
        if isinstance(control,FormattedTextControl):
            try:plain=''.join(fragment[1] for fragment in to_formatted_text(control.text))
            except TypeError:continue
            if plain.strip().strip('<> ').strip()==text:return control
    raise AssertionError(f'Button not found: {text}')

@pytest.mark.asyncio
async def test_all_tui_pages_render_and_keyboard_can_author(story):
    with create_pipe_input() as pipe:
        desk=Desk(project=story['service'].project,input=pipe,output=DummyOutput())
        task=asyncio.create_task(desk.app.run_async())
        try:
            await rendered()
            for page in PAGES:
                desk.go(page.key)
                await rendered()
                assert not task.done(),f'Render failed on {page.key}'
                assert desk.page==page.key
            desk.go('library')
            form=desk.spawn(desk.command_form('asset.create',{'title':'Terminal asset','type':'character'}))
            await rendered()
            assert desk.modal_depth==1
            submit=find_button(desk,'Save / view')
            desk.app.layout.focus(submit)
            pipe.send_text('\r')
            await asyncio.wait_for(form,timeout=5)
            assert desk.service.list_entities('asset',query='Terminal asset')['total']==1
            assert desk.modal_depth==0
            # Ctrl+K opens the application action palette; cancellation restores focus.
            pipe.send_bytes(b'\x0b')
            await rendered()
            assert desk.modal_depth==1
            cancel=find_button(desk,'Cancel')
            desk.app.layout.focus(cancel);pipe.send_text('\r')
            await rendered()
            assert desk.modal_depth==0
        finally:
            if not task.done():desk.app.exit()
            await asyncio.wait_for(task,timeout=3)

@pytest.mark.asyncio
async def test_tui_workspace_switch_keeps_projects_isolated(workspace):
    first=workspace.create('One','one');second=workspace.create('Two','two')
    Service(first).create_entity('asset','Only One')
    with create_pipe_input() as pipe:
        desk=Desk(workspace=workspace,input=pipe,output=DummyOutput())
        task=asyncio.create_task(desk.app.run_async())
        try:
            await rendered();desk.go('workspace');await rendered()
            first_row=next(row for row in desk.records.rows if row.id==first.id)
            desk.select(first_row)
            await desk.open_project(first_row.record['path'])
            assert desk.service.project.id==first.id
            assert desk.service.list_entities('asset')['total']==1
            await desk.open_project(str(second.root))
            assert desk.service.project.id==second.id and desk.service.list_entities('asset')['total']==0
        finally:
            if not task.done():desk.app.exit()
            await asyncio.wait_for(task,timeout=3)


def test_same_named_pages_have_real_content(story):
    state=story['service'].state()
    for key in ('overview','intake','library','connections','outline','guide','editor','composition'):
        assert rows_for(key,state,[]), key
    assert any(p.key=='frames' for p in PAGES)
