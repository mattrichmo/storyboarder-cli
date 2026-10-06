"""Full-screen authoring desk. All mutations call application.commands.execute."""
from __future__ import annotations
import asyncio
import copy
from contextlib import asynccontextmanager
import json
import os
import uuid
import webbrowser
from pathlib import Path
from prompt_toolkit.application import Application
from prompt_toolkit.layout import Layout, HSplit, VSplit, Window, FloatContainer, Float, DynamicContainer, ConditionalContainer, ScrollablePane
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension as D
from prompt_toolkit.widgets import Button, Dialog, TextArea, Label, Frame, RadioList, Checkbox, Box
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.bindings.focus import focus_next, focus_previous
from prompt_toolkit.styles import Style
from prompt_toolkit.completion import PathCompleter
from prompt_toolkit.output import ColorDepth
from PIL import Image, ImageOps
from storyboarder.application.projects import Project, Workspace, discover
from storyboarder.application.service import Service
from storyboarder.application.observation_contracts import ObservationContracts
from storyboarder.application.commands import COMMANDS, execute, options_for, source_options, source_record
from storyboarder.application.recovery import restore
from storyboarder.domain.errors import StoryboardError, Conflict
from storyboarder.media.files import safe_path, thumbnail
from storyboarder.rendering.composer import markdown
from .pages import PAGES, PAGE_MAP, defaults, rows_for, describe, context_text, human
from .widgets import Row, RecordList, clean

STYLE = Style.from_dict({
    '': 'bg:#f5f4ed #2f372d', 'header': 'bg:#e3e8dd #30432d bold',
    'footer': 'bg:#e3e8dd #4c6046', 'muted': '#65725f', 'title': '#2c422a bold',
    'nav': 'bg:#ebece3 #40523a', 'nav.selected': 'bg:#d6e1ce #263d24 bold',
    'list.selected': 'bg:#d9e5d0 #263c25 bold', 'list.row': 'bg:#fcfbf6 #34402e',
    'record-list': 'bg:#fcfbf6 #34402e', 'detail': 'bg:#f8f8f0 #364331',
    'button': 'bg:#eeeee5 #3f5538', 'button.focused': 'bg:#405d36 #ffffff bold',
    'text-area': 'bg:#fffef8 #2e392a', 'text-area.prompt': '#596d50',
    'dialog': 'bg:#f9f8f0 #293b22', 'dialog.body': 'bg:#f9f8f0 #293b22',
    'dialog frame.label': 'bg:#f9f8f0 #30452b bold', 'dialog shadow': 'bg:#8b9681',
    'frame.border': '#b4c1a9', 'frame.label': '#4c6142',
    'radio-selected': 'bg:#dce6d5 #263d23', 'checkbox-checked': '#3c6630 bold',
    'error': 'bg:#f6e9df #8b3c2c', 'warning': '#805d29',
    'scrollbar.background': 'bg:#e9ede2', 'scrollbar.button': 'bg:#a1b595',
})

PAGED_CHOICES = {
    'documents', 'document_nodes', 'versions', 'provenance_edges', 'annotations',
    'provenance_endpoints', 'provenance_source', 'provenance_target', 'provenance_typed_endpoint',
}


class Desk:
    def __init__(self, project=None, workspace=None, *, input=None, output=None):
        self.workspace = Workspace(workspace) if isinstance(workspace, (str, Path)) else workspace
        project = Project(project) if isinstance(project, (str, Path)) else project
        self.service = Service(project) if project else None
        if not self.service and self.workspace:
            try:
                current = self.workspace.current()
                if current: self.service = Service(current)
            except StoryboardError: pass
        self.state = self.service.state() if self.service else None
        self.projects = self.workspace.list() if self.workspace else ([self.service.project.summary() | {'available': True}] if self.service else [])
        self.page = 'overview' if self.service else 'workspace'
        self.message = 'Ready. Choose a page. Ctrl+K searches actions.'
        self.selected: Row | None = None
        self.anchor = None
        self.neighbors = None
        self.thumbnail_fragments = []
        self.show_thumbnails = os.environ.get('STORYBOARDER_NO_THUMBNAILS') != '1'
        self.compare_ids = []
        self.observation_rows = []
        self.observation_draft = None
        self.modal_depth = 0
        self._busy_operations = set()
        self._busy_workers = set()
        self._modal_entries = []
        self.pending_tasks = set()
        self.search = TextArea(multiline=False, height=1, prompt='Find on this page: ', style='class:text-area', name='page-search')
        self.search.buffer.on_text_changed += lambda _: self.rebuild_rows()
        self.detail = TextArea(text='', read_only=True, scrollbar=True, wrap_lines=True, style='class:detail', name='record-detail')
        self.records = RecordList([], self.select, self.enter)
        self.toolbar = HSplit([])
        self.page_body = HSplit([])
        self.build_page()
        self.nav_buttons = []
        for page in PAGES:
            button = Button(page.title, handler=lambda key=page.key: self.go(key), width=26)
            self.nav_buttons.append(button)
        nav = HSplit([Label('  STORYBOARDER', style='class:title'), Label('  Local production desk\n', style='class:muted'), *self.nav_buttons,
                      Window(height=1), Button('Search actions  Ctrl+K', handler=lambda: self.spawn(self.palette()), width=26),
                      Button('Keyboard help  F1', handler=lambda: self.spawn(self.help()), width=26)])
        main = HSplit([
            Window(FormattedTextControl(lambda: [('class:header', '  STORYBOARDER  /  '+(self.state['project']['title'] if self.state else 'Workspace')+'  /  '+PAGE_MAP[self.page].title)]), height=1, style='class:header'),
            VSplit([ConditionalContainer(Box(nav, padding=1, width=29, style='class:nav'),
                                         Condition(lambda: self._terminal_columns() >= 80)),
                    ConditionalContainer(Window(width=1, char='│', style='class:frame.border'),
                                         Condition(lambda: self._terminal_columns() >= 80)),
                    DynamicContainer(lambda: self.page_body)]),
            Window(FormattedTextControl(lambda: [('class:footer', '  '+clean(self.message))]), height=2, wrap_lines=True, style='class:footer'),
            Window(FormattedTextControl([('class:footer', '  Tab focus  ↑↓ choose  Enter inspect  Ctrl+E edit  Ctrl+N new  Ctrl+K actions  F5 reload  Ctrl+Q quit')]), height=1, style='class:footer')
        ])
        self.root = FloatContainer(main, floats=[])
        keys = KeyBindings()
        keys.add('tab')(focus_next)
        keys.add('s-tab')(focus_previous)
        main_only = Condition(lambda: self.modal_depth == 0)
        @keys.add('c-q', filter=main_only)
        def quit_app(event): self.spawn(self.quit())
        @keys.add('c-c', filter=main_only)
        def interrupt(event): self.spawn(self.quit())
        @keys.add('c-k', filter=main_only)
        def actions(event): self.spawn(self.palette())
        @keys.add('f1', filter=main_only)
        def help_(event): self.spawn(self.help())
        @keys.add('f5', filter=main_only)
        def refresh(event): self.spawn(self.refresh())
        @keys.add('c-e', filter=main_only)
        def edit(event): self.edit_selected()
        @keys.add('c-n', filter=main_only)
        def create(event): self.create_default()
        @keys.add('c-f', filter=main_only)
        def search(event): event.app.layout.focus(self.search)
        @keys.add('escape', filter=Condition(lambda: bool(self._modal_entries)))
        def close_top_dialog(event):
            _, cancel_modal = self._modal_entries[-1]
            cancel_modal()
        for key, page in [('c-p', 'workspace'), ('c-l', 'library'), ('c-o', 'outline'), ('f6', 'connections')]:
            keys.add(key, filter=main_only)(lambda event, name=page: self.go(name))
        self.app = Application(layout=Layout(self.root, focused_element=self.records.control), key_bindings=keys,
                               style=STYLE, full_screen=True, mouse_support=True, input=input, output=output,
                               color_depth=ColorDepth.TRUE_COLOR if os.environ.get('COLORTERM') in ('truecolor', '24bit') else None)

    def spawn(self, coroutine):
        task = self.app.create_background_task(coroutine)
        self.pending_tasks.add(task)
        task.add_done_callback(self.pending_tasks.discard)
        return task

    @property
    def busy(self):
        return bool(self._busy_operations or self._busy_workers)

    @asynccontextmanager
    async def busy_operation(self):
        token = object()
        self._busy_operations.add(token)
        self.app.invalidate()
        try:
            yield
        finally:
            self._busy_operations.discard(token)
            self.app.invalidate()

    def _worker_finished(self, task):
        self._busy_workers.discard(task)
        self.app.invalidate()

    async def run_worker(self, function, *args, **kwargs):
        """Track blocking work until its thread finishes, even if its caller is cancelled."""
        worker = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
        self._busy_workers.add(worker)
        worker.add_done_callback(self._worker_finished)
        self.app.invalidate()
        try:
            return await asyncio.shield(worker)
        finally:
            if worker.done():
                self._worker_finished(worker)

    def set_message(self, message):
        self.message = str(message)
        if hasattr(self, 'app'): self.app.invalidate()

    def go(self, key):
        if self.modal_depth: return
        if key != 'workspace' and not self.service:
            self.set_message('Create or open a project from Workspace first.')
            return
        self.page, self.anchor, self.neighbors = key, None, None
        self.search.text = ''
        self.build_page()
        if hasattr(self, 'app'):
            self.app.layout.focus(self.records.control)
            self.app.invalidate()
        if key == 'coverage':
            self.spawn(self.refresh_observation_rows())

    def build_page(self):
        page = PAGE_MAP[self.page]
        if self.page == 'coverage':
            self.build_coverage_page(page)
            return
        buttons = []
        if self.page == 'workspace':
            buttons = [Button('New project', handler=lambda: self.spawn(self.create_project())), Button('Open path', handler=lambda: self.spawn(self.open_path())), Button('Refresh', handler=lambda: self.spawn(self.refresh()))]
        else:
            for name in page.actions:
                command = COMMANDS[name]
                buttons.append(Button(command.label[:30], handler=lambda n=name: self.launch_action(n), width=min(34, len(command.label)+4)))
            if self.page == 'settings': buttons.append(Button('Restore backup', handler=lambda: self.spawn(self.restore_backup())))
            if self.page in ('library', 'intake', 'frames', 'editor'):
                buttons.append(Button('View image', handler=lambda: self.spawn(self.view_image())))
            if self.page == 'frames': buttons.append(Button('Compare images', handler=lambda: self.spawn(self.compare_frame())))
            if self.page == 'connections': buttons.append(Button('All items', handler=self.reset_connections))
        button_rows = [VSplit(buttons[i:i+3], padding=1, height=1) for i in range(0, len(buttons), 3)]
        thumb = ConditionalContainer(Window(FormattedTextControl(lambda: self.thumbnail_fragments), height=10), Condition(lambda: bool(self.thumbnail_fragments) and self.show_thumbnails))
        self.page_body = HSplit([
            Box(HSplit([Label(page.title, style='class:title'), Label(page.subtitle, style='class:muted'), Window(height=1), self.search, Window(height=1), *button_rows]), padding=1, padding_bottom=0),
            Box(VSplit([Frame(self.records, title='Story items · ↑↓ / Enter', width=D(weight=1, min=25)),
                        Frame(HSplit([thumb, self.detail]), title='Selected item', width=D(weight=1, min=25))], padding=1), padding=1)
        ])
        self.rebuild_rows()

    def _terminal_columns(self):
        try:
            return self.app.output.get_size().columns
        except (AttributeError, ValueError):
            return 80

    def build_coverage_page(self, page):
        buttons = [
            Button('Plan shot + contract', handler=lambda: self.spawn(self.create_observation_plan())),
            Button('Contract for existing shot', handler=lambda: self.spawn(self.create_existing_shot_contract())),
            Button('Show exact pins', handler=lambda: self.spawn(self.show_observation())),
            Button('Validate', handler=lambda: self.spawn(self.validate_observation())),
            Button('Edit one field', handler=lambda: self.spawn(self.edit_observation_field())),
            Button('Diff versions', handler=lambda: self.spawn(self.diff_observation())),
            Button('Rebase preview', handler=lambda: self.spawn(self.rebase_observation())),
            Button('Refresh list', handler=lambda: self.spawn(self.refresh_observation_rows())),
            Button('Coverage JSON', handler=lambda: self.launch_action('observation.coverage')),
            Button('Advanced group JSON', handler=lambda: self.launch_action('observation.create-group')),
        ]
        standard_observation_forms = {
            'observation.create', 'observation.show', 'observation.list', 'observation.revise',
            'observation.validate', 'observation.rebase-preview', 'observation.rebase', 'observation.diff',
            'observation.coverage', 'observation.create-group',
        }
        for name, command in COMMANDS.items():
            if command.page == 'coverage' and not command.browser and name not in standard_observation_forms:
                buttons.append(Button(command.label[:28], handler=lambda n=name: self.launch_action(n)))
        if self.observation_draft:
            buttons += [Button('Retry saved draft', handler=lambda: self.spawn(self.retry_observation_draft())),
                        Button('Discard saved draft', handler=self.discard_observation_draft)]
        columns = 3 if self._terminal_columns() >= 150 else 2 if self._terminal_columns() >= 100 else 1
        button_rows = [VSplit(buttons[index:index + columns], padding=1, height=1)
                       for index in range(0, len(buttons), columns)]
        draft_status = Label(self._observation_draft_label(), style='class:warning') if self.observation_draft else Window(height=0)
        controls = Box(HSplit([Label(page.title, style='class:title'), Label(page.subtitle, style='class:muted'),
                               draft_status, self.search, *button_rows]), padding=1, padding_bottom=0)
        list_frame = Frame(self.records, title='Contracts · revision · source state', width=D(weight=1, min=25))
        detail_frame = Frame(self.detail, title='Selected contract', width=D(weight=1, min=25))
        if self._terminal_columns() >= 115:
            records = VSplit([list_frame, detail_frame], padding=1)
        else:
            records = HSplit([list_frame, detail_frame], padding=1)
        self.page_body = HSplit([controls, ScrollablePane(HSplit([records]), show_scrollbar=True)])
        self.rebuild_rows()

    def _observation_draft_label(self):
        if not self.observation_draft:
            return ''
        kind = self.observation_draft.get('kind', 'plan')
        if kind == 'group':
            item = self.observation_draft['payload']['request']['items'][0]
            return f"Saved draft · {item['title']} · exact source pins retained · scene revision {item['expected_scene_revision']}"
        if kind == 'create_existing':
            return (f"Saved contract draft · shot {self.observation_draft['shot_id']} · "
                    f"shot revision {self.observation_draft['expected_shot_revision']} · "
                    f"{len(self.observation_draft['contract']['source_pins'])} exact pins retained")
        if kind == 'rebase':
            pins = self.observation_draft['contract']['source_pins']
            return (f"Saved rebase review · contract {self.observation_draft['contract_id']} · "
                    f"header revision {self.observation_draft['revision']} · {len(pins)} exact pins retained")
        return f"Saved edit draft · contract {self.observation_draft['contract_id']} · header revision {self.observation_draft['revision']}"

    async def refresh_observation_rows(self):
        if not self.service:
            return
        try:
            result = await self.run_worker(lambda: ObservationContracts(self.service).list(limit=500))
            self.observation_rows = [Row(item['id'],
                                         f"{item['shot_title']} · contract r{item['revision']} · v{item['version_number']}",
                                         f"{item['content_sha256']} · {'archived' if item.get('shot_archived') else 'active'}", item)
                                     for item in result['items']]
            self.rebuild_rows()
        except (StoryboardError, OSError) as exc:
            self.set_message(str(exc))

    def discard_observation_draft(self):
        self.observation_draft = None
        self.build_page()
        self.set_message('Saved observation draft discarded.')

    def _selected_contract_id(self):
        if self.selected and self.page == 'coverage':
            return self.selected.record['id']
        self.set_message('Select an observation contract first.')
        return None

    @staticmethod
    def _observation_scope_label(source_scope):
        return 'Scene context' if source_scope == 'scene-context' else 'Direct shot link'

    @staticmethod
    def _format_observation_show(record):
        pins = []
        for pin in record['source_pins']:
            details = dict(pin)
            details['relationship_label'] = Desk._observation_scope_label(pin['source_scope'])
            details['screenplay_node_kind'] = pin.get('source_node_type', 'unknown')
            pins.append(details)
        sections = [f"Contract {record['id']} · header revision {record['revision']}",
                    f"Shot {record['shot_id']} · version {record['version']['number']} · {record['version']['id']}",
                    f"Version hash {record['version']['content_sha256']} · basis hash {record['version']['basis_sha256']}",
                    f"Validation: {record['validation']['status']} · basis current: {record['validation']['basis_current']}",
                    '', 'Purpose and requirements', json.dumps({
                        'script_intents': record['contract']['script_intents'],
                        'requirements': record['contract']['requirements'],
                    }, ensure_ascii=False, indent=2), '', 'Exact source pins (document/version/node/hash/edge)',
                    json.dumps(pins, ensure_ascii=False, indent=2), '', 'Saved history',
                    json.dumps(record['history'], ensure_ascii=False, indent=2)]
        return '\n'.join(sections)

    async def show_observation(self):
        contract_id = self._selected_contract_id()
        if not contract_id:
            return
        try:
            record = await self.run_worker(ObservationContracts(self.service).show, contract_id)
            await self.message_dialog('Observation contract · exact pins', self._format_observation_show(record))
        except (StoryboardError, OSError) as exc:
            await self.message_dialog('Observation contract unavailable', str(exc))

    async def validate_observation(self):
        contract_id = self._selected_contract_id()
        if not contract_id:
            return
        try:
            result = await self.run_worker(ObservationContracts(self.service).validate, contract_id)
            await self.message_dialog('Observation validation',
                                      json.dumps(result, ensure_ascii=False, indent=2))
        except (StoryboardError, OSError) as exc:
            await self.message_dialog('Validation failed', str(exc))

    async def diff_observation(self):
        contract_id = self._selected_contract_id()
        if not contract_id:
            return
        try:
            record = await self.run_worker(ObservationContracts(self.service).show, contract_id)
            versions = record['history']
            if len(versions) < 2:
                await self.message_dialog('No earlier version', 'Create a revision before comparing contract versions.')
                return
            choices = [(item['id'], f"Version {item['number']} · {item['operation']} · {item['created_at']}") for item in versions]
            before = await self.choose('Earlier contract version', choices[:-1])
            if not before:
                return
            after = await self.choose('Later contract version', choices)
            if not after:
                return
            result = await self.run_worker(ObservationContracts(self.service).diff, contract_id, before, after)
            await self.message_dialog('Observation contract difference', json.dumps(result, ensure_ascii=False, indent=2))
        except (StoryboardError, OSError) as exc:
            await self.message_dialog('Could not compare versions', str(exc))

    async def edit_observation_field(self):
        contract_id = self._selected_contract_id()
        if not contract_id:
            return
        try:
            saved = await self.run_worker(ObservationContracts(self.service).show, contract_id)
            body = copy.deepcopy(saved['contract'])
            components = []
            for item in body['script_intents']:
                components.append((item['id'], f"Purpose · {item['purpose']} · intent {item['id']}"))
            for item in body['requirements']:
                label = item.get('statement') or item.get('topic') or ''
                components.append((item['id'], f"{item['priority']} requirement · {label} · {item['id']}"))
            if not components:
                await self.message_dialog('Nothing to edit', 'This contract has no purpose or requirement rows yet.')
                return
            component_id = await self.choose('Choose one purpose or requirement', components)
            if not component_id:
                return
            intent = next((item for item in body['script_intents'] if item['id'] == component_id), None)
            requirement = next((item for item in body['requirements'] if item['id'] == component_id), None)
            if intent:
                prop = await self.choose('Choose one purpose field', [('purpose', 'Purpose'), ('communication', 'How it should read visually'), ('basis', 'Basis label')])
                if not prop:
                    return
                if prop == 'basis':
                    value = await self.choose('Purpose basis', [('direct', 'Directly stated'), ('interpreted', 'Interpreted'), ('unknown', 'Unknown')], intent['basis'])
                    if value is None:
                        return
                    intent[prop] = value
                else:
                    values = await self.simple_form('Edit one purpose field', [(prop, 'New ' + ('purpose' if prop == 'purpose' else 'visual communication'), intent[prop])])
                    if values is None:
                        return
                    intent[prop] = values[prop]
            else:
                current_text_key = 'topic' if requirement['priority'] == 'unknown' else 'statement'
                properties = [('priority', 'Priority'), ('basis', 'Basis label'), (current_text_key, 'Topic' if current_text_key == 'topic' else 'Requirement statement')]
                prop = await self.choose('Choose one requirement field', properties)
                if not prop:
                    return
                if prop == 'priority':
                    value = await self.choose('Requirement priority', [('must', 'Must include'), ('prefer', 'Prefer'), ('unknown', 'Unknown / open question')], requirement['priority'])
                    if value is None:
                        return
                    old_key = 'topic' if requirement['priority'] == 'unknown' else 'statement'
                    new_key = 'topic' if value == 'unknown' else 'statement'
                    content = requirement.pop(old_key)
                    requirement['priority'] = value
                    requirement[new_key] = content
                elif prop == 'basis':
                    value = await self.choose('Requirement basis', [('direct', 'Directly stated'), ('interpreted', 'Interpreted'), ('unknown', 'Unknown')], requirement['basis'])
                    if value is None:
                        return
                    requirement[prop] = value
                else:
                    values = await self.simple_form('Edit one requirement field', [(prop, 'New ' + prop, requirement[prop])])
                    if values is None:
                        return
                    requirement[prop] = values[prop]
            payload = {'contract_id': contract_id, 'revision': saved['revision'], 'contract': body}
            self.observation_draft = {'kind': 'revise', **copy.deepcopy(payload)}
            await self._apply_observation_draft()
        except (StoryboardError, OSError) as exc:
            await self.message_dialog('Contract edit was not saved', str(exc))

    async def rebase_observation(self):
        draft = self.observation_draft
        contract_id = (draft['contract_id'] if draft and draft.get('kind') == 'rebase'
                       else self._selected_contract_id())
        if not contract_id:
            return
        try:
            if draft and draft.get('kind') == 'rebase' and draft['contract_id'] == contract_id:
                saved = await self.run_worker(ObservationContracts(self.service).show, contract_id)
                if saved['revision'] != draft['revision']:
                    diff_text = ''
                    previous_version_id = draft.get('saved_version_id')
                    current_version_id = saved['version']['id']
                    if previous_version_id and previous_version_id != current_version_id:
                        diff = await self.run_worker(ObservationContracts(self.service).diff,
                                                      contract_id, previous_version_id, current_version_id)
                        diff_text = '\n\nSaved version diff:\n' + json.dumps(diff, ensure_ascii=False, indent=2)
                    await self.message_dialog(
                        'Contract revision changed',
                        f"The retained rebase draft uses header revision {draft['revision']}; the current contract is at revision {saved['revision']}.\n\nCurrent saved version:\n{self._format_observation_show(saved)}{diff_text}\n\nThe draft still holds its original exact pins until you explicitly reload.",
                    )
                    decision = await self.choose('Reload this saved version and review a new rebase?', [
                        ('yes', 'Reload current body and pins'), ('no', 'Keep the old draft')], 'no')
                    if decision != 'yes':
                        return
                    body = copy.deepcopy(saved['contract'])
                    revision = saved['revision']
                    saved_version_id = current_version_id
                else:
                    body = copy.deepcopy(draft['contract'])
                    revision = draft['revision']
                    saved_version_id = draft.get('saved_version_id', saved['version']['id'])
            else:
                saved = await self.run_worker(ObservationContracts(self.service).show, contract_id)
                body = copy.deepcopy(saved['contract'])
                revision = saved['revision']
                saved_version_id = saved['version']['id']

            if body['source_pins']:
                pin_action = await self.choose('Keep exact pins or retarget one?', [
                    ('keep', 'Keep these exact source pins'),
                    ('retarget', 'Retarget one pin to another linked exact source'),
                    ('cancel', 'Cancel rebase review')], 'keep')
                if pin_action == 'retarget':
                    updated_body = await self._retarget_rebase_pin(saved['shot_id'], body, saved)
                    if updated_body is None:
                        return
                    body = updated_body
                elif pin_action != 'keep':
                    return

            preview = await self.run_worker(execute, self.service, 'observation.rebase-preview', {
                'contract_id': contract_id, 'contract': body})
            await self.message_dialog('Review authored basis changes', self._format_rebase_preview(preview))
            decision = await self.choose('Rebase this exact contract body and pin set?', [
                ('yes', 'Save with this reviewed basis'), ('no', 'Keep current version')], 'no')
            if decision != 'yes':
                return
            self.observation_draft = {
                'kind': 'rebase', 'contract_id': contract_id, 'revision': revision,
                'saved_version_id': saved_version_id, 'contract': body,
                'expected_basis_sha256': preview['expected_basis_sha256'],
            }
            await self._apply_observation_draft()
        except (StoryboardError, OSError) as exc:
            await self.message_dialog('Could not review contract rebase', str(exc))

    async def _retarget_rebase_pin(self, shot_id, body, saved):
        shot = await self.run_worker(self.service.get, 'entities', shot_id)
        source_result = await self.run_worker(execute, self.service, 'shot.sources', {'id': shot_id})
        documents, linked = {}, {}
        for edge in source_result['items']:
            if edge['inherited']:
                if edge['target_id'] != shot['parent_id']:
                    continue
                scope = 'scene-context'
            else:
                if edge['target_id'] != shot_id:
                    continue
                scope = 'direct-element'
            node = await self.run_worker(source_record, self.service, 'document_nodes', edge['node_id'], {
                'document_id': edge['document_id'], 'version_id': edge['version_id']})
            if node.get('identity') != 'explicit' or node.get('content_sha256') != edge['content_sha256']:
                continue
            document = documents.get(edge['document_id'])
            if document is None:
                document = await self.run_worker(source_record, self.service, 'documents', edge['document_id'])
                documents[edge['document_id']] = document
            if document.get('kind') != 'screenplay' or document.get('archived'):
                continue
            linked[edge['edge_id']] = {
                'edge_id': edge['edge_id'], 'source_scope': scope,
                'document_id': edge['document_id'], 'version_id': edge['version_id'],
                'node_id': edge['node_id'], 'source_sha256': edge['content_sha256'],
                'node_type': edge['node_type'], 'document_title': document['title'],
                'title': edge['title'], 'stale': edge['stale'],
            }

        current_pin_ids = {pin['edge_id'] for pin in body['source_pins']}
        saved_pins = {pin['edge_id']: pin for pin in saved['source_pins']}

        def detail(pin):
            edge_id = pin['edge_id']
            found = saved_pins.get(edge_id) or linked.get(edge_id) or {}
            return {
                'edge_id': edge_id,
                'source_scope': pin.get('source_scope', found.get('source_scope', 'unknown')),
                'document_id': found.get('document_id', '<unavailable>'),
                'version_id': found.get('source_version_id', found.get('version_id', '<unavailable>')),
                'node_id': found.get('node_id', '<unavailable>'),
                'source_sha256': found.get('source_sha256', found.get('content_sha256', '<unavailable>')),
            }

        pin_choices = [(pin['edge_id'], self._rebase_pin_description(detail(pin)))
                       for pin in body['source_pins']]
        old_edge_id = await self.choose('Choose the exact contract pin to retarget', pin_choices)
        if not old_edge_id:
            return None
        old_pin = next(pin for pin in body['source_pins'] if pin['edge_id'] == old_edge_id)
        old_detail = detail(old_pin)
        candidates = [source for edge_id, source in linked.items()
                      if edge_id != old_edge_id and edge_id not in current_pin_ids]
        if not candidates:
            await self.message_dialog(
                'No replacement exact links',
                'This shot has no other active, explicitly identified screenplay visualizes edge to itself or its current parent scene. Link the exact source first, then review the rebase again.',
            )
            return None
        choices = [(source['edge_id'], self._rebase_pin_description(source) +
                    (' · older exact source version' if source['stale'] else ' · current source version'))
                   for source in candidates]
        new_edge_id = await self.choose('Choose another already-linked exact source', choices)
        if not new_edge_id:
            return None
        new_pin = linked[new_edge_id]
        await self.message_dialog(
            'Confirm exact source retarget',
            'Current pin:\n' + self._rebase_pin_description(old_detail) +
            '\n\nReplacement pin:\n' + self._rebase_pin_description(new_pin) +
            '\n\nThe replacement is already linked to this shot. Matching uses the exact edge ID; no source is chosen by title, order, or latest-version status.',
        )
        decision = await self.choose('Retarget this exact source pin?', [
            ('yes', 'Retarget to this exact linked source'), ('no', 'Keep current pin')], 'no')
        if decision != 'yes':
            return None

        revised = copy.deepcopy(body)
        for pin in revised['source_pins']:
            if pin['edge_id'] == old_edge_id:
                pin['edge_id'] = new_edge_id
                pin['source_scope'] = new_pin['source_scope']
                break
        for intent in revised['script_intents']:
            if intent['source_edge_id'] == old_edge_id:
                intent['source_edge_id'] = new_edge_id
                intent['source_scope'] = new_pin['source_scope']
        for requirement in revised['requirements']:
            if old_edge_id in requirement['source_edge_ids']:
                requirement['source_edge_ids'] = list(dict.fromkeys(
                    new_edge_id if edge_id == old_edge_id else edge_id
                    for edge_id in requirement['source_edge_ids']))
        return revised

    @staticmethod
    def _rebase_pin_description(pin):
        return (f"{Desk._observation_scope_label(pin['source_scope'])} · "
                f"doc {pin['document_id']} · version {pin['version_id']} · "
                f"node {pin['node_id']} · hash {pin['source_sha256']} · edge {pin['edge_id']}")

    @staticmethod
    def _format_rebase_preview(preview):
        lines = [
            f"Contract {preview['contract_id']} · header revision {preview['revision']}",
            f"Saved basis SHA-256: {preview['saved_basis_sha256']}",
            f"Current basis SHA-256: {preview['current_basis_sha256']}",
            f"Basis changed: {'yes' if preview['basis_changed'] else 'no'}",
            f"Validation: {preview['validation_context']['status']}",
            '', 'Exact source pins retained in the proposed body:',
        ]
        lines.extend(f"  {pin['edge_id']} · {pin['source_scope']}" for pin in preview['requested_source_pins'])
        lines += ['', 'Saved and current values:']
        if preview['changes']:
            for change in preview['changes']:
                before = json.dumps(change['saved_value'], ensure_ascii=False, sort_keys=True)
                after = json.dumps(change['current_value'], ensure_ascii=False, sort_keys=True)
                lines.append(f"  {change['path']}: {before} → {after}")
        else:
            lines.append('  No supported basis fields changed.')
        if preview['changes_truncated']:
            lines.append('  Additional basis changes were omitted from this bounded preview.')
        lines += ['', 'Rebase review token:', preview['expected_basis_sha256'],
                  'The save is checked against this token. A changed basis keeps the draft for another explicit review.']
        return '\n'.join(lines)

    async def retry_observation_draft(self):
        if not self.observation_draft:
            return
        await self._apply_observation_draft()

    async def _apply_observation_draft(self):
        draft = self.observation_draft
        if not draft:
            return
        try:
            if draft['kind'] == 'group':
                result = await self.run_worker(execute, self.service, 'observation.create-group', draft['payload'])
                self.set_message(f"Created shot {result['items'][0]['shot_id']} and its exact observation contract.")
            elif draft['kind'] == 'create_existing':
                result = await self.run_worker(execute, self.service, 'observation.create', {
                    'shot_id': draft['shot_id'],
                    'expected_shot_revision': draft['expected_shot_revision'],
                    'contract': draft['contract'],
                })
                self.set_message(f"Created observation contract {result['id']} at revision {result['revision']}.")
            elif draft['kind'] == 'rebase':
                result = await self.run_worker(execute, self.service, 'observation.rebase', {
                    'contract_id': draft['contract_id'], 'revision': draft['revision'],
                    'contract': draft['contract'],
                    'expected_basis_sha256': draft['expected_basis_sha256'],
                })
                self.set_message(f"Saved contract rebase {result['revision']} with the reviewed basis and exact pins.")
            else:
                result = await self.run_worker(execute, self.service, 'observation.revise', {
                    'contract_id': draft['contract_id'], 'revision': draft['revision'], 'contract': draft['contract']})
                self.set_message(f"Saved contract revision {result['revision']} with the existing IDs and source pins.")
            self.observation_draft = None
            await self.refresh()
        except (StoryboardError, OSError) as exc:
            self.set_message('Draft retained with exact IDs, revisions, and pins. ' + str(exc))
            self.build_page()

    async def _pick_exact_source(self):
        async def pick(source, title, values=None, *, exact_nodes=False):
            async def load(query, offset):
                page = await self.run_worker(source_options, self.service, source, values or {}, query, 100, offset)
                if exact_nodes:
                    page['items'] = [item for item in page['items']
                                     if item.get('identity') == 'explicit' and item.get('node_type') != 'screenplay']
                return page
            selected = await self.choose(title, [], loader=load)
            if not selected:
                return None
            return await self.run_worker(source_record, self.service, source, selected, values or {})

        document = await pick('documents', 'Choose a screenplay document', {'kind': 'screenplay'})
        if not document:
            return None
        if document.get('kind') != 'screenplay' or document.get('archived'):
            await self.message_dialog('Choose an active screenplay', 'Observation links require an active screenplay document.')
            return None
        version = await pick('versions', 'Choose the exact screenplay version', {'document_id': document['id']})
        if not version:
            return None
        node = await pick('document_nodes', 'Choose an explicitly identified scene or element',
                          {'document_id': document['id'], 'version_id': version['id']}, exact_nodes=True)
        if not node:
            return None
        return {'document_id': document['id'], 'version_id': version['id'], 'node_id': node['id'],
                'source_sha256': node['content_sha256'], 'node_type': node['node_type'],
                'label': node.get('label') or node.get('title') or node['id']}

    async def create_observation_plan(self):
        if not self.service or not self.state:
            return
        scenes = [(item['id'], f"{item['title']} · scene revision {item['revision']}")
                  for item in self.state['entities'] if item['kind'] == 'scene' and not item['archived']]
        scene_id = await self.choose('Choose the shot’s parent scene', scenes)
        if not scene_id:
            return
        scene = next(item for item in self.state['entities'] if item['id'] == scene_id)
        title_values = await self.simple_form('Name the planned shot', [('title', 'Shot title', '')],
                                              f"Expected scene revision {scene['revision']} is captured now. A later scene edit will keep this draft and return a conflict.")
        if not title_values:
            return
        edges, intents, requirements = [], [], []
        while True:
            source = await self._pick_exact_source()
            if not source:
                if not edges:
                    return
                break
            scope = 'scene-context' if source['node_type'] == 'scene' else 'direct-element'
            scope_label = self._observation_scope_label(scope)
            self.set_message(f"Exact source selected: {source['document_id']} / {source['version_id']} / {source['node_id']} · {source['source_sha256']} · {source['node_type']} · {scope_label}")
            fields = await self.simple_form('Describe this exact source', [
                ('purpose', 'Purpose', ''), ('communication', 'How the visual should read', '')],
                f"Pinned source: {source['document_id']} · version {source['version_id']} · node {source['node_id']} · hash {source['source_sha256']}\nScreenplay node kind: {source['node_type']} · Relationship: {scope_label}")
            if not fields:
                return
            intent_basis = await self.choose('Purpose basis', [('direct', 'Directly stated'), ('interpreted', 'Interpreted'), ('unknown', 'Unknown')], 'unknown')
            if intent_basis is None:
                return
            priority = await self.choose('Requirement priority', [('must', 'Must include'), ('prefer', 'Prefer'), ('unknown', 'Unknown / open question')], 'must')
            if priority is None:
                return
            req_basis = await self.choose('Requirement basis', [('direct', 'Directly stated'), ('interpreted', 'Interpreted'), ('unknown', 'Unknown')], 'unknown')
            if req_basis is None:
                return
            field_name = 'topic' if priority == 'unknown' else 'statement'
            req_form = await self.simple_form('State the requirement', [(field_name, 'Open question topic' if priority == 'unknown' else 'Requirement statement', '')])
            if not req_form:
                return
            edge_id = str(uuid.uuid4())
            edges.append({'edge_id': edge_id, 'document_id': source['document_id'], 'version_id': source['version_id'],
                          'node_id': source['node_id'], 'source_sha256': source['source_sha256'],
                          'source_scope': scope})
            intents.append({'id': str(uuid.uuid4()), 'source_edge_id': edge_id, 'source_scope': edges[-1]['source_scope'],
                            'purpose': fields['purpose'], 'communication': fields['communication'], 'basis': intent_basis})
            requirement = {'id': str(uuid.uuid4()), 'priority': priority, 'basis': req_basis,
                           'source_edge_ids': [edge_id], field_name: req_form[field_name]}
            requirements.append(requirement)
            more = await self.choose('Add another exact source?', [('yes', 'Add another source link'), ('no', 'Finish this shot')], 'no')
            if more != 'yes':
                break
        if not edges:
            return
        shot_id, contract_id = str(uuid.uuid4()), str(uuid.uuid4())
        item = {'shot_id': shot_id, 'contract_id': contract_id, 'scene_id': scene_id,
                'expected_scene_revision': scene['revision'], 'title': title_values['title'], 'description': '',
                'fields': {}, 'source_edges': edges,
                'contract': {'schema': 'storyboarder.observation-contract/v1',
                             'source_pins': [{'edge_id': edge['edge_id'], 'source_scope': edge['source_scope']} for edge in edges],
                             'script_intents': intents, 'requirements': requirements,
                             'references': [], 'continuity': [], 'notes': ''}}
        self.observation_draft = {'kind': 'group', 'payload': {'request': {'items': [item]}}}
        await self._apply_observation_draft()

    async def create_existing_shot_contract(self):
        if not self.service or not self.state:
            return
        shots = [(item['id'], f"{item['title']} · shot revision {item['revision']}")
                 for item in self.state['entities'] if item['kind'] == 'shot' and not item['archived']]
        shot_id = await self.choose('Choose an existing storyboard shot', shots)
        if not shot_id:
            return
        try:
            shot = await self.run_worker(self.service.get, 'entities', shot_id)
            if shot['kind'] != 'shot' or shot['archived']:
                await self.message_dialog('Choose an active shot', 'Restore the selected shot before creating a contract.')
                return
            source_result = await self.run_worker(execute, self.service, 'shot.sources', {'id': shot_id})
            candidates, documents = [], {}
            for edge in source_result['items']:
                if edge['inherited']:
                    if edge['target_id'] != shot['parent_id']:
                        continue
                    scope = 'scene-context'
                else:
                    if edge['target_id'] != shot_id:
                        continue
                    scope = 'direct-element'
                node = await self.run_worker(source_record, self.service, 'document_nodes', edge['node_id'], {
                    'document_id': edge['document_id'], 'version_id': edge['version_id']})
                if node.get('identity') != 'explicit' or node.get('content_sha256') != edge['content_sha256']:
                    continue
                document = documents.get(edge['document_id'])
                if document is None:
                    document = await self.run_worker(source_record, self.service, 'documents', edge['document_id'])
                    documents[edge['document_id']] = document
                if document.get('kind') != 'screenplay' or document.get('archived'):
                    continue
                candidates.append({**edge, 'source_scope': scope, 'document_title': document['title'],
                                   'identity': node['identity']})
            if not candidates:
                await self.message_dialog(
                    'No exact screenplay links',
                    'This shot has no active, explicitly identified screenplay visualizes edges to itself or its parent scene. Link an exact source first, then create the contract.',
                )
                return

            choices = []
            by_edge = {}
            for edge in candidates:
                by_edge[edge['edge_id']] = edge
                scope_label = self._observation_scope_label(edge['source_scope'])
                stale = ' · older exact source version' if edge['stale'] else ''
                choices.append((edge['edge_id'],
                                f"{scope_label} · {edge['node_type']} · {edge['title']} · "
                                f"doc {edge['document_id']} · version {edge['version_id']} · "
                                f"node {edge['node_id']} · hash {edge['content_sha256']} · edge {edge['edge_id']}{stale}"))

            selected_edges, intents = [], []
            available = list(choices)
            while available and len(selected_edges) < 128:
                selection = await self.choose('Select an existing exact source link or finish',
                                              [*available, ('finish', 'Finish source selection')], 'finish')
                if not selection or selection == 'finish':
                    break
                edge = by_edge[selection]
                fields = await self.simple_form('Describe this exact shot source', [
                    ('purpose', 'Purpose', ''), ('communication', 'How it should read visually', '')],
                    f"Shot revision captured: {shot['revision']}\n{self._observation_scope_label(edge['source_scope'])} · screenplay node kind {edge['node_type']}\nExact document/version/node/hash/edge: {edge['document_id']} / {edge['version_id']} / {edge['node_id']} / {edge['content_sha256']} / {edge['edge_id']}")
                if not fields:
                    return
                basis = await self.choose('Purpose basis', [
                    ('direct', 'Directly stated'), ('interpreted', 'Interpreted'), ('unknown', 'Unknown')], 'unknown')
                if basis is None:
                    return
                selected_edges.append(edge)
                intents.append({
                    'id': str(uuid.uuid4()), 'source_edge_id': edge['edge_id'],
                    'source_scope': edge['source_scope'], 'purpose': fields['purpose'],
                    'communication': fields['communication'], 'basis': basis,
                })
                available = [(value, label) for value, label in available if value != selection]
                if not available:
                    break
                more = await self.choose('Add another exact source link?', [
                    ('yes', 'Choose another source link'), ('no', 'Finish source selection')], 'no')
                if more != 'yes':
                    break
            if len(selected_edges) == 128 and available:
                self.set_message('This contract has reached the 128 exact source-pin limit.')
            if not selected_edges:
                return

            requirements = []
            while await self.choose('Add a requirement?', [
                    ('yes', 'Add requirement'), ('no', 'Finish contract')], 'no') == 'yes':
                priority = await self.choose('Requirement priority', [
                    ('must', 'Must include'), ('prefer', 'Prefer'), ('unknown', 'Unknown / open question')], 'must')
                if priority is None:
                    return
                basis = await self.choose('Requirement basis', [
                    ('direct', 'Directly stated'), ('interpreted', 'Interpreted'), ('unknown', 'Unknown')], 'unknown')
                if basis is None:
                    return
                field_name = 'topic' if priority == 'unknown' else 'statement'
                content = await self.simple_form('State this requirement', [(
                    field_name, 'Open question topic' if priority == 'unknown' else 'Requirement statement', '')])
                if not content:
                    return
                mapping_choices = [(edge['edge_id'],
                                    f"{self._observation_scope_label(edge['source_scope'])} · {edge['node_type']} · {edge['title']} · {edge['edge_id']}")
                                   for edge in selected_edges]
                mapping = await self.choose('Choose an exact source for this requirement', [
                    *mapping_choices, ('all', 'All selected source links'), ('none', 'No exact source mapping')], 'none')
                if mapping is None:
                    return
                source_edge_ids = ([edge['edge_id'] for edge in selected_edges] if mapping == 'all'
                                   else [] if mapping == 'none' else [mapping])
                requirements.append({
                    'id': str(uuid.uuid4()), 'priority': priority, 'basis': basis,
                    'source_edge_ids': source_edge_ids, field_name: content[field_name],
                })

            body = {
                'schema': 'storyboarder.observation-contract/v1',
                'source_pins': [{'edge_id': edge['edge_id'], 'source_scope': edge['source_scope']}
                                for edge in selected_edges],
                'script_intents': intents, 'requirements': requirements,
                'references': [], 'continuity': [], 'notes': '',
            }
            self.observation_draft = {
                'kind': 'create_existing', 'shot_id': shot_id,
                'expected_shot_revision': shot['revision'], 'contract': body,
            }
            await self._apply_observation_draft()
        except (StoryboardError, OSError) as exc:
            await self.message_dialog('Could not create the shot contract', str(exc))

    def rebuild_rows(self):
        previous = self.selected.id if self.selected else None
        if self.page == 'coverage':
            query = self.search.text.casefold().strip()
            self.records.rows = [row for row in self.observation_rows
                                 if not query or query in (row.label + ' ' + row.detail + ' ' + row.id).casefold()]
        else:
            self.records.rows = rows_for(self.page, self.state, self.projects, self.search.text, self.anchor, self.neighbors)
        self.records.index = next((i for i, r in enumerate(self.records.rows) if r.id == previous), 0)
        self.select(self.records.selected)
        if hasattr(self, 'app'): self.app.invalidate()

    def select(self, row):
        self.selected = row
        self.thumbnail_fragments = []
        if self.page == 'coverage':
            if row:
                record = row.record
                shot = next((item for item in self.state['entities'] if item['id'] == record['shot_id']), None)
                parent = next((item for item in self.state['entities'] if shot and item['id'] == shot.get('parent_id')), None)
                self.detail.text = (f"{record.get('shot_title', 'Shot')}\n\n"
                                    f"Contract revision: {record['revision']} · Version {record.get('version_number', '?')}\n"
                                    f"Header ID: {record['id']}\nShot ID: {record['shot_id']}\n"
                                    f"Current version ID: {record.get('current_version_id')}\n"
                                    f"Source hash: {record.get('content_sha256')}\n"
                                    f"Scene: {parent.get('title', parent['id']) if parent else 'Unavailable'}\n\n"
                                    "Choose Show to inspect exact pins, basis, and saved history.\n"
                                    "Validate checks the saved declarations against current source and shot context.")
            else:
                self.detail.text = ('No observation contracts yet. Choose “Plan shot + contract” to create a new shot with exact links, '
                                    'or “Contract for existing shot” to use exact screenplay links already connected to a shot.')
            self.detail.buffer.cursor_position = 0
            return
        if self.page == 'workspace':
            self.detail.text = (row.record.get('title','Untitled project')+'\n\n'+row.record.get('description','')+'\n\nSaved at: '+row.record.get('path','')) if row else 'No projects here yet.\n\nCreate a project folder or open one from this computer.\n\nThe workspace helps you switch between projects; each project keeps its own story and images together.'
        elif row and self.state:
            record = row.record
            self.detail.text = describe(record, self.state)
            if self.page in ('guide', 'composition') and record.get('kind') != 'asset':
                try:
                    document = self.service.compose(record['id'])
                    self.detail.text = clean(context_text(document['context']) if self.page == 'guide' else markdown(document))
                except StoryboardError as exc: self.detail.text = str(exc)
            elif self.page == 'overview' and record['id'] == self.service.project.id:
                counts = self.state['project']['counts']
                recent = '\n'.join(f"  {e['created_at'][:10]} {COMMANDS.get(e['action']).label if COMMANDS.get(e['action']) else human(e['action'])}" for e in self.state['events'][:14])
                summary = ' · '.join(f"{human(key)}: {value}" for key,value in counts.items())
                self.detail.text = describe(record, self.state)+'\nProject contents\n'+summary+'\n\nRecent changes\n'+recent
            self.update_thumbnail(record)
        else:
            self.detail.text = describe(None, self.state)
        self.detail.buffer.cursor_position = 0

    def update_thumbnail(self, record):
        if not self.show_thumbnails or not self.service: return
        media_id = self.media_id(record)
        if not media_id: return
        try:
            media = next(m for m in self.state['media'] if m['id'] == media_id)
            path = thumbnail(self.service.root, media, 160)
            with Image.open(path) as image:
                image = ImageOps.contain(image.convert('RGB'), (34, 16))
                backdrop = Image.new('RGB', (34, 16), (242, 244, 233))
                backdrop.paste(image, ((34-image.width)//2, (16-image.height)//2))
                fragments = [('class:muted', ' Preview · original file unchanged\n')]
                for y in range(0, 16, 2):
                    fragments.append(('', ' '))
                    for x in range(34):
                        top, bottom = backdrop.getpixel((x,y)), backdrop.getpixel((x,y+1))
                        fragments.append(('fg:#%02x%02x%02x bg:#%02x%02x%02x' % (*top, *bottom), '▀'))
                    fragments.append(('', '\n'))
                self.thumbnail_fragments = fragments
        except (StoryboardError, OSError, StopIteration):
            self.thumbnail_fragments = [('class:warning', ' Preview unavailable. Open Project care to check the project files.\n')]

    def media_id(self, record):
        if record.get('media_id'): return record['media_id']
        if record.get('kind') == 'asset':
            members = [m for m in self.state['asset_media'] if m['asset_id'] == record['id']]
            primary = next((m for m in members if m['is_primary']), members[0] if members else None)
            return primary['media_id'] if primary else None
        if record.get('kind') == 'shot':
            preferred = next((f for f in self.state['frames'] if f['shot_id'] == record['id'] and f['state'] in ('selected', 'approved')), None)
            if preferred: return preferred['media_id']
            assignment = next((a for a in self.state['assignments'] if a['shot_id'] == record['id'] and a['media_id']), None)
            return assignment['media_id'] if assignment else None
        return None

    def enter(self, row):
        if self.page == 'workspace': self.spawn(self.open_project(row.record['path']))
        elif self.page == 'connections':
            if row.id == self.anchor: self.reset_connections()
            else:
                self.anchor = row.id
                self.neighbors = self.service.neighbors(row.id)
                self.rebuild_rows()
                self.set_message('Use the arrow keys to follow connections. Select the current item to return to all items.')
        elif self.page == 'intake': self.launch_action('intake.accept')
        elif self.page == 'frames' and row.record.get('shot_id'): self.launch_action('frame.state')
        elif self.page == 'automation': self.launch_action('job.preview')
        elif self.page == 'composition': self.launch_action('composition.preview')
        else: self.edit_selected()

    def reset_connections(self):
        self.anchor = self.neighbors = None
        self.rebuild_rows()

    def edit_selected(self):
        if not self.selected or not self.service: return
        record = self.selected.record
        if record.get('kind'): self.launch_action(record['kind']+'.update')
        elif 'shot_id' in record and 'version' in record: self.launch_action('frame.state')
        elif 'state' in record and 'original_path' in record: self.launch_action('intake.accept')
        elif 'script' in record: self.launch_action('job.preview')
        else: self.set_message('Use Ctrl+K to choose an action for this item.')

    def create_default(self):
        name = {'intake':'media.import','library':'asset.create','connections':'link.create','outline':'sequence.create','guide':'context.put','editor':'shot.create','frames':'frame.add','composition':'export.bundle','automation':'job.create','overview':'sequence.create'}.get(self.page)
        if self.page == 'workspace': self.spawn(self.create_project())
        elif name: self.launch_action(name)

    def launch_action(self, name):
        if not self.service:
            self.set_message('Open a project before running an authoring action.')
            return
        initial = defaults(self.selected.record if self.selected else self.state['project'])
        if name == 'project.update': initial = defaults(self.state['project'])
        if name in ('scene.create', 'shot.create'):
            kind = 'sequence' if name == 'scene.create' else 'scene'
            if not self.selected or self.selected.record.get('kind') != kind: initial.pop('parent_id', None)
        if name.endswith('.create'):
            initial.pop('title', None)
            for key in ('description', 'action', 'dialogue', 'notes', 'fields', 'type', 'tags', 'aliases'): initial.pop(key, None)
        if name == 'media.tags' and self.selected:
            media_id = self.media_id(self.selected.record)
            record = next((m for m in self.state['media'] if m['id'] == media_id), None)
            if record: initial = defaults(record)
        if name == 'assignment.update' and 'asset_id' in initial: initial['asset_id'] = initial['asset_id']
        self.spawn(self.command_form(name, initial))

    async def refresh(self):
        if self.busy:
            self.set_message('A project action is still running. Its status will appear when it finishes.')
            return
        try:
            if self.service: self.state = await self.run_worker(self.service.state)
            if self.workspace: self.projects = await self.run_worker(self.workspace.list)
            if self.anchor: self.neighbors = await self.run_worker(self.service.neighbors, self.anchor)
            if self.page == 'coverage': await self.refresh_observation_rows()
            self.rebuild_rows()
            self.set_message('Project refreshed. Unsaved edits are unchanged.')
        except (StoryboardError, OSError) as exc:
            self.set_message(str(exc))

    async def show_dialog(self, dialog, future, focus=None, on_escape=None):
        previous = self.app.layout.current_window
        floating = Float(content=dialog)
        def default_cancel():
            if not future.done(): future.set_result(None)
        entry = (future, on_escape or default_cancel)
        self.root.floats.append(floating)
        self._modal_entries.append(entry)
        self.modal_depth += 1
        self.app.layout.focus(focus or dialog)
        self.app.invalidate()
        try:
            return await future
        finally:
            if floating in self.root.floats: self.root.floats.remove(floating)
            if entry in self._modal_entries: self._modal_entries.remove(entry)
            self.modal_depth -= 1
            try: self.app.layout.focus(previous)
            except ValueError: self.app.layout.focus(self.records.control)
            self.app.invalidate()

    async def message_dialog(self, title, text):
        future = asyncio.get_running_loop().create_future()
        body = TextArea(text=clean(text), read_only=True, scrollbar=True, wrap_lines=True, height=D(min=6, max=26, preferred=18))
        close = lambda: future.set_result(None) if not future.done() else None
        dialog = Dialog(title=title, body=body, buttons=[Button('Close', handler=close)], width=D(preferred=94, max=110))
        await self.show_dialog(dialog, future, body)

    async def choose(self, title, choices, current=None, loader=None):
        future = asyncio.get_running_loop().create_future()
        search = TextArea(multiline=False, height=1, prompt='Find: ')
        original = list(choices)
        radios = RadioList(choices or [('', 'No eligible choices')], default=current, select_on_focus=True)
        page_status = Label('')
        more = Button('More results', handler=lambda: self.spawn(load_more()))
        page_state = {'offset': 0, 'next_offset': None, 'total': len(original), 'choices': [], 'request': 0, 'loading': False}

        def set_choices(choices):
            radios.values = choices or [('', 'No matching choices')]
            radios._selected_index = 0
            radios.current_value = radios.values[0][0]

        async def load_page(query, offset, append=False):
            if loader is None or page_state['loading']: return
            page_state['loading'] = True
            page_state['request'] += 1
            request = page_state['request']
            page_status.text = 'Loading choices…'
            more.text = 'Loading…'
            self.app.invalidate()
            try:
                page = await loader(query, offset)
                if request != page_state['request'] or query != search.text: return
                items = page.get('items', [])
                page_choices = [(item['id'], clean(item.get('label') or item.get('title') or item['id'])) for item in items]
                combined = page_state['choices'] + page_choices if append else page_choices
                page_state.update(offset=offset, next_offset=page.get('next_offset'), total=page.get('total', len(combined)), choices=combined)
                set_choices(combined)
                showing = len(combined)
                page_status.text = f"{page_state['total']} matches · showing {showing}"
                more.text = 'More results' if page_state['next_offset'] is not None else 'No more results'
            except StoryboardError as exc:
                page_status.text = clean(str(exc))
                more.text = 'Retry results'
            finally:
                if request == page_state['request']:
                    page_state['loading'] = False
                self.app.invalidate()

        async def load_more():
            if page_state['next_offset'] is not None:
                await load_page(search.text, page_state['next_offset'], append=True)

        def filter_(_):
            if loader:
                page_state['request'] += 1
                page_state['loading'] = False
                page_state['next_offset'] = None
                page_state['choices'] = []
                self.spawn(load_page(search.text, 0))
                return
            choices = [(v, clean(label)) for v, label in original if search.text.casefold() in str(label).casefold()]
            set_choices(choices)
        search.buffer.on_text_changed += filter_
        def resolve(value):
            if not future.done(): future.set_result(value)
        if loader:
            body = HSplit([search, page_status, Window(height=1), Box(radios, height=D(min=4, max=18, preferred=14))])
            buttons = [Button('Choose', handler=lambda: resolve(radios.current_value)), more, Button('Cancel', handler=lambda: resolve(None))]
            self.spawn(load_page(search.text, 0))
        else:
            body = HSplit([search, Window(height=1), Box(radios, height=D(min=4, max=18, preferred=14))])
            buttons = [Button('Choose', handler=lambda: resolve(radios.current_value)), Button('Cancel', handler=lambda: resolve(None))]
        dialog = Dialog(title=title, body=body, buttons=buttons, width=D(preferred=92, max=110))
        return await self.show_dialog(dialog, future, radios)

    async def simple_form(self, title, fields, warning=''):
        future = asyncio.get_running_loop().create_future()
        inputs = {key: TextArea(text=str(value or ''), multiline=False, height=1,
                               completer=PathCompleter(expanduser=True) if 'path' in key or key == 'archive' else None) for key,label,value in fields}
        error = Label('')
        body = [Label(warning, style='class:warning')] if warning else []
        for key, label, value in fields: body += [Label(label), inputs[key], Window(height=1)]
        body += [error]
        def submit():
            if any(not v.text.strip() for v in inputs.values()):
                error.text = 'Complete each required field.'
                return
            if not future.done(): future.set_result({key: v.text.strip() for key,v in inputs.items()})
        dialog = Dialog(title=title, body=HSplit(body), buttons=[Button('Continue', handler=submit), Button('Cancel', handler=lambda: future.set_result(None) if not future.done() else None)], width=D(preferred=84, max=100))
        return await self.show_dialog(dialog, future, next(iter(inputs.values())))

    async def command_form(self, name, initial=None):
        if self.busy:
            self.set_message('Wait for the current action to finish before opening another form.')
            return
        command = COMMANDS[name]
        initial = initial or {}
        future = asyncio.get_running_loop().create_future()
        values = {f.name: initial.get(f.name, f.default) for f in command.fields}
        # A shot reference only offers images from its selected library item.
        if initial.get('asset_id'): values['asset_id'] = initial['asset_id']
        widgets, labels, body = {}, {}, []
        status = Label('Your edits are checked against the latest saved version.', style='class:muted')
        body += [status, Window(height=1)]
        if name == 'job.run': body += [Label('Only run tools you trust. They run on this computer with the access allowed to your account.', style='class:warning'), Window(height=1)]
        all_records = [r for rows in self.state.values() if isinstance(rows,list) for r in rows if isinstance(r,dict) and 'id' in r]
        def current_values():
            result = dict(values)
            for field in command.fields:
                w = widgets.get(field.name)
                if isinstance(w, TextArea): result[field.name] = w.text
                if isinstance(w, Checkbox): result[field.name] = w.checked
            return result
        def selected_record(field, value, payload=None):
            if value in (None, ''): return None
            if field.source in PAGED_CHOICES:
                try: return source_record(self.service, field.source, value, payload or current_values())
                except StoryboardError: return None
            return next((r for r in all_records if r.get('id') == value), None)

        if any(field.name == 'revision' for field in command.fields):
            for field in command.fields:
                if field.name not in ('revision', 'target_revision') and field.source:
                    record = selected_record(field, values.get(field.name), values)
                    if record and record.get('revision') is not None:
                        values['revision'] = record['revision']
                        if name == 'annotation.update':
                            values['content'] = record.get('text', '')
                            values['state'] = record.get('state', 'open')
                        break

        def update_widgets(record):
            merged = defaults(record)
            for field in command.fields:
                if field.name in merged: values[field.name] = merged[field.name]
                if field.name in merged and field.name in widgets:
                    if isinstance(widgets[field.name], TextArea):
                        value = merged[field.name]
                        widgets[field.name].text = ', '.join(value) if isinstance(value,list) and field.type == 'tags' else json.dumps(value,ensure_ascii=False,indent=2) if isinstance(value,(dict,list)) else str(value or '')
                    elif isinstance(widgets[field.name], Button):
                        values[field.name] = merged[field.name]
                        choices = options_for(field.source,self.state,current_values(),self.service) if field.source else [(v,human(v)) for v in field.options]
                        label = next((label for v,label in choices if v == merged[field.name]), str(merged[field.name]))
                        widgets[field.name].text = clean(label)[:64]
            if record.get('asset_id'): values['asset_id'] = record['asset_id']
        async def pick(field):
            if field.source in PAGED_CHOICES:
                async def load_choices(query, offset):
                    return await self.run_worker(source_options, self.service, field.source, current_values(), query, 100, offset)
                choices = []
                value = await self.choose(field.label, choices, values.get(field.name), loader=load_choices)
            else:
                choices = options_for(field.source,self.state,current_values(),self.service) if field.source else [(v,human(v)) for v in field.options]
                if not field.required: choices = [('', 'Not set')] + choices
                value = await self.choose(field.label, choices, values.get(field.name))
            if value is None: return
            values[field.name] = value
            record = selected_record(field, value)
            if field.source in PAGED_CHOICES and record:
                label = record.get('label') or record.get('title') or record.get('original_name') or record.get('id')
            else:
                label = next((label for key,label in choices if key == value), value)
            widgets[field.name].text = clean(label)[:64] or 'Not set'
            if record and field.name in ('id','source_id','document_id','node_id','edge_id','annotation_id'):
                if name.endswith('.update') and field.name in ('id','source_id'): update_widgets(record)
                if name == 'annotation.update':
                    values['content'] = record.get('text', '')
                    values['state'] = record.get('state', 'open')
                    if 'content' in widgets: widgets['content'].text = record.get('text', '')
                    if 'state' in widgets:
                        state_field = next(item for item in command.fields if item.name == 'state')
                        state_choices = [(option, human(option)) for option in state_field.options]
                        widgets['state'].text = clean(next((label for option,label in state_choices if option == values['state']), values['state']))[:64]
                if 'revision' in values:
                    revision = record.get('revision', record.get('document_revision'))
                    if revision is not None: values['revision'] = revision
            if record and field.name == 'target_id' and 'target_revision' in values:
                revision = record.get('revision', record.get('document_revision'))
                if revision is not None: values['target_revision'] = revision
            if field.name == 'asset_id' and 'media_id' in widgets:
                values['media_id'] = ''
                widgets['media_id'].text = 'Choose a specific image'
            self.app.invalidate()
        for field in command.fields:
            value = values[field.name]
            if field.name in ('revision','target_revision'): continue
            body.append(Label(field.label+(' *' if field.required else '')))
            if field.source or field.options:
                if field.source in PAGED_CHOICES:
                    record = selected_record(field, value, values)
                    label = (record.get('label') or record.get('title') or record.get('original_name') or record.get('id')) if record else ('Choose…' if field.required else 'Not set')
                else:
                    choices = options_for(field.source,self.state,values,self.service) if field.source else [(v,human(v)) for v in field.options]
                    label = next((label for v,label in choices if v == value), 'Choose…' if field.required else 'Not set')
                widget = Button(clean(label)[:64], handler=lambda f=field: self.spawn(pick(f)), width=68)
            elif field.type == 'boolean': widget = Checkbox('Enabled', checked=bool(value))
            else:
                if field.type == 'tags' and isinstance(value,list): value = ', '.join(value)
                if field.type == 'json' and isinstance(value,(dict,list)): value = json.dumps(value, ensure_ascii=False, indent=2)
                widget = TextArea(text='' if value is None else str(value), multiline=field.type in ('textarea','json'), height=4 if field.type in ('textarea','json') else 1,
                                  scrollbar=field.type in ('textarea','json'), wrap_lines=True, name=field.name,
                                  completer=PathCompleter(expanduser=True) if field.name == 'path' else None)
            widgets[field.name] = widget
            body.append(widget)
            if field.help: body.append(Label(field.help, style='class:muted'))
            body.append(Window(height=1))
        confirmed = Checkbox('I understand this will change the project.', checked=False)
        if command.destructive: body += [Label('Confirm this change to continue.', style='class:warning'), confirmed, Window(height=1)]
        working = [False]
        async def submit():
            if working[0]: return
            if command.destructive and not confirmed.checked:
                status.text = 'Review and confirm this change before continuing.'
                return
            payload = {}
            try:
                raw = current_values()
                for field in command.fields:
                    value = raw.get(field.name)
                    if value in (None,''):
                        if name.endswith('.update') and field.name in ('location_id','duration','media_id'):
                            payload[field.name] = None
                            continue
                        if field.required and field.type != 'tags': raise StoryboardError(field.label+' is required.')
                        if field.type in ('integer','number') or field.source: continue
                        if not name.endswith('.update') and field.name not in ('notes','content') and field.type not in ('boolean','tags'): continue
                    if field.type == 'integer': value = int(value)
                    elif field.type == 'number': value = float(value)
                    elif field.type == 'json': value = json.loads(value or '{}') if isinstance(value,str) else value
                    elif field.type == 'tags': value = [s.strip() for s in (value or '').split(',') if s.strip()] if isinstance(value,str) else value or []
                    elif field.type == 'boolean': value = bool(value)
                    payload[field.name] = value
                working[0] = True
                status.text = 'Saving this change to your project…'
                self.app.invalidate()
                async with self.busy_operation():
                    result = await self.run_worker(execute, self.service, name, payload)
                    self.state = await self.run_worker(self.service.state)
                    if self.workspace: self.projects = await self.run_worker(self.workspace.list)
                    if not future.done(): future.set_result(result)
                    self.set_message('Completed · '+command.label)
            except (StoryboardError, OSError, ValueError, TypeError) as exc:
                status.text = clean(str(exc)) + (' Your edits are still here. Refresh the project, then reapply them.' if isinstance(exc,Conflict) else '')
                status.formatted_text_control.style = 'class:error'
            finally:
                working[0] = False
                self.app.invalidate()
        async def reload_record():
            self.state = await self.run_worker(self.service.state)
            record = next((r for r in self.state['entities'] if r['id'] == current_values().get('id')),None)
            if record:
                choice = await self.choose('Replace your draft with the latest saved details?', [('no','Keep my draft'),('yes','Refresh details and replace my draft')], 'no')
                if choice == 'yes': update_widgets(record);status.text='Project details refreshed.'
        async def cancel_run():
            try:
                job = await self.run_worker(self.service.get, 'jobs', current_values()['id'])
                if job['status'] in ('queued','running'):
                    await self.run_worker(execute, self.service, 'job.cancel', {'id':job['id'],'revision':job['revision']})
                    status.text = 'Stop requested. The tool is shutting down.'
            except StoryboardError as exc:
                status.text = clean(str(exc))
            self.app.invalidate()
        def cancel():
            if not working[0] and not future.done(): future.set_result(None)
        buttons = [Button('Save / view', handler=lambda: self.spawn(submit())), Button('Cancel', handler=cancel)]
        if name == 'job.run': buttons.insert(1, Button('Stop this run', handler=lambda: self.spawn(cancel_run())))
        if name.endswith('.update'): buttons.insert(1, Button('Refresh details', handler=lambda: self.spawn(reload_record())))
        pane = ScrollablePane(HSplit(body), height=D(preferred=26, max=32), show_scrollbar=True)
        dialog = Dialog(title=command.label, body=pane, buttons=buttons, width=D(preferred=100,max=116))
        result = await self.show_dialog(dialog, future, next(iter(widgets.values()), buttons[0]), on_escape=cancel)
        self.rebuild_rows()
        if result is not None and (command.read_only or name.startswith('export.') or name in ('project.backup','job.run','job.approve')):
            if name == 'composition.preview': text = markdown(result)
            elif name == 'context.resolve': text = context_text(result)
            elif name == 'project.doctor':
                issues = result.get('issues', [])
                text = ('Project health: In good shape' if result.get('healthy') else 'Project health: Needs attention')+f"\n\n{result.get('media_checked', 0)} reference images checked"
                if issues: text += '\n\nItems to review\n'+'\n'.join(f"• {human(issue.get('severity', 'info'))}: {issue.get('message', 'Review this project item.')}" for issue in issues)
            elif name == 'project.backup': text = f"Project backup created.\n\nSaved in this project at:\n{result.get('path', 'exports/backups')}\n\nSize: {result.get('size', 0)/1024/1024:.1f} MB"
            elif name == 'job.preview':
                text = f"{result.get('title', 'Tool run')}\n\nStatus: {human(result.get('status', 'unknown'))}\nTool: {result.get('script', 'Image tool')}\nResults: {len(result.get('outputs', []))}"
                outputs = result.get('outputs', [])
                if outputs: text += '\n\nResults\n'+'\n'.join(f"• {output.get('title') or output.get('key', 'Image')} — {output.get('notes', '')}" for output in outputs)
                logs = result.get('logs', {})
                if any(logs.values()): text += '\n\nRun notes\n'+'\n'.join(str(value).strip() for value in logs.values() if value)
            elif name.startswith('export.'):
                text = 'Export saved to your project.'
                if result.get('archive'): text += f"\n\nPackage: {result['archive']}"
                elif result.get('path'): text += f"\n\nFile: {result['path']}"
                if result.get('files'): text += f"\n\nFiles created: {len(result['files'])}"
            elif name == 'job.run': text = f"Image tool finished.\n\nStatus: {human(result.get('status', 'unknown'))}\nReview its images and run notes on the Image tools page."
            elif name == 'job.approve': text = 'Reviewed results added to the project.'
            else: text = 'The project has been updated.'
            await self.message_dialog(command.label, text)

    async def palette(self):
        if not self.service:
            await self.message_dialog('Open a project', 'Use the workspace to create or open a project first.')
            return
        hidden = {'entity.update', 'canvas.save', 'project.sync'}
        name = await self.choose('Search actions', [(name, command.label) for name,command in COMMANDS.items() if not command.read_only and name not in hidden])
        if name: self.launch_action(name)

    async def open_project(self, path):
        try:
            self.service = await self.run_worker(Service, path)
            self.state = await self.run_worker(self.service.state)
            if self.workspace: await self.run_worker(self.workspace.register,path)
            self.go('overview')
            self.set_message('Opened '+self.state['project']['title']+' from '+str(self.service.root))
        except (StoryboardError,OSError) as exc: await self.message_dialog('Could not open this project',str(exc))

    async def open_path(self):
        values = await self.simple_form('Open a project folder', [('path','Project folder path', str(Path.cwd()))])
        if values: await self.open_project(values['path'])

    async def create_project(self):
        fields = [('title','Project title','')]
        if self.workspace: fields += [('slug','Folder name','new-project')]
        else: fields += [('path','New project folder',str(Path.cwd()/'new-project'))]
        values = await self.simple_form('Create a project',fields)
        if not values: return
        try:
            async with self.busy_operation():
                if self.workspace: project = await self.run_worker(self.workspace.create,values['title'],values['slug'])
                else: project = await self.run_worker(Project.create,values['path'],values['title'])
                await self.open_project(project.root)
                if self.workspace: self.projects = await self.run_worker(self.workspace.list)
        except (StoryboardError,OSError) as exc: await self.message_dialog('Could not create this project',str(exc))

    async def restore_backup(self):
        values = await self.simple_form('Restore into a new folder', [('archive','Backup ZIP path',''),('path','New project folder','')], 'The destination must not exist. Current project files are never overwritten.')
        if not values:return
        confirmation = await self.choose('Restore this backup?', [('no','Cancel'),('yes','Validate and restore into the new folder')], 'no')
        if confirmation != 'yes': return
        try:
            async with self.busy_operation():
                result = await self.run_worker(restore,values['archive'],values['path'])
                if self.workspace: await self.run_worker(self.workspace.register,values['path'])
            await self.message_dialog('Project restored',f"A new project copy is ready at:\n{result.get('path', values['path'])}")
            await self.refresh()
        except (StoryboardError,OSError) as exc: await self.message_dialog('Restore did not complete',str(exc))

    async def view_image(self):
        if not self.selected:return
        media_id = self.media_id(self.selected.record)
        if not media_id:
            await self.message_dialog('No selected image','Add an image to the library or storyboard frames first. Choose the specific image you want to view.')
            return
        try:
            record = self.service.get('media',media_id)
            path = safe_path(self.service.root,record['path'],must_exist=True)
            opened = await self.run_worker(webbrowser.open,path.as_uri())
            self.set_message(('Opened image: ' if opened else 'Open this image: ')+str(path))
        except (StoryboardError,OSError) as exc: self.set_message(str(exc))

    async def compare_frame(self):
        if not self.selected or 'version' not in self.selected.record:
            self.set_message('Select a storyboard image to compare.');return
        record = self.selected.record
        if record['id'] in self.compare_ids: self.compare_ids.remove(record['id'])
        else: self.compare_ids.append(record['id'])
        self.compare_ids = self.compare_ids[-4:]
        frames = [f for f in self.state['frames'] if f['id'] in self.compare_ids]
        text = '\n\n'.join(f"Image {f['version']} · {f['state']}\n{f['notes']}" for f in frames)
        if len(frames) < 2:
            self.set_message('Image '+str(record['version'])+' selected for comparison. Choose another image, then select Compare images.');return
        # A derived contact sheet is only a view; originals and state remain canonical.
        sheet = Image.new('RGB',(len(frames)*640,480),(246,245,239))
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(sheet)
        for i,f in enumerate(frames):
            media = self.service.get('media',f['media_id'])
            path = thumbnail(self.service.root,media,960)
            with Image.open(path) as image:
                image = ImageOps.contain(image,(610,380))
                sheet.paste(image,(i*640+(640-image.width)//2,30+(380-image.height)//2))
            draw.text((i*640+20,425),f"Version {f['version']} / {f['state']}",fill=(45,61,40),font=ImageFont.load_default(size=20))
        path = self.service.root/'.storyboarder/cache/frame-comparison.png'
        sheet.save(path)
        await self.run_worker(webbrowser.open,path.as_uri())
        await self.message_dialog('Storyboard image comparison',text+'\n\nA comparison sheet was opened in your image viewer.')

    async def help(self):
        await self.message_dialog('Keyboard and workflow guide',
            'NAVIGATION\nTab / Shift+Tab: move focus\nArrow keys / j,k: choose items\nEnter: open, edit, or follow a connection\nCtrl+P: workspace\nCtrl+L: reference library\nCtrl+O: story outline\nF6: connections\nCtrl+F: search this page\nF5: refresh\n\nEDITING\nCtrl+N: create an item for this page\nCtrl+E: edit the selected item\nCtrl+K: search available actions\nChoice fields open a searchable picker. Multi-line fields use Enter for new lines.\nUse Tab to reach Save / view.\n\nCHANGES\nChanges that remove or archive items ask you to confirm. If a project was changed elsewhere, your draft stays available until you choose to refresh it.\nMoving a card on the canvas changes its arrangement. Use Move / reorder to change story order.\nChoose a specific image for a shot reference when needed.\n\nIMAGES\nImage previews adapt to your terminal. View image opens the selected image. Compare images creates a contact sheet for selected storyboard images.\nSet STORYBOARDER_NO_THUMBNAILS=1 to turn off previews.\n\nEXIT\nCtrl+Q or Ctrl+C quits when no project action is running. During an action, wait for it to finish. Project files stay on this computer.')

    async def quit(self):
        if self.busy:
            self.set_message('Finish or cancel the active form before quitting.');return
        self.app.exit()

    def run(self):
        return self.app.run()


def run_tui(project=None, workspace=None):
    if not project and not workspace:
        found = discover(Path.cwd())
        if found: project = found
        elif (Path.cwd()/'workspace.toml').exists(): workspace = Workspace(Path.cwd())
    return Desk(project, workspace).run()
