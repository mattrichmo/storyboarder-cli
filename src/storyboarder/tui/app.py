"""Full-screen authoring desk. All mutations call application.commands.execute."""
from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
import json
import os
import webbrowser
from pathlib import Path
from typing import Any
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
from storyboarder.application.commands import COMMANDS, execute, options_for, source_options, source_record
from storyboarder.application.recovery import restore
from storyboarder.domain.errors import StoryboardError, Conflict
from storyboarder.media.files import safe_path, thumbnail
from storyboarder.rendering.composer import markdown
from .pages import PAGES, PAGE_MAP, defaults, rows_for, describe, context_text, human, display_title
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
            VSplit([Box(nav, padding=1, width=29, style='class:nav'), Window(width=1, char='│', style='class:frame.border'), DynamicContainer(lambda: self.page_body)]),
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

    def build_page(self):
        page = PAGE_MAP[self.page]
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

    def rebuild_rows(self):
        previous = self.selected.id if self.selected else None
        self.records.rows = rows_for(self.page, self.state, self.projects, self.search.text, self.anchor, self.neighbors)
        self.records.index = next((i for i, r in enumerate(self.records.rows) if r.id == previous), 0)
        self.select(self.records.selected)
        if hasattr(self, 'app'): self.app.invalidate()

    def select(self, row):
        self.selected = row
        self.thumbnail_fragments = []
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
