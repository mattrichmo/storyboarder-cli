"""Small native prompt_toolkit controls, shared by every authoring page."""
from dataclasses import dataclass
from typing import Any, Callable
from prompt_toolkit.application.current import get_app
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.screen import Point
from prompt_toolkit.layout.margins import ScrollbarMargin
from prompt_toolkit.mouse_events import MouseEventType


def clean(value: Any) -> str:
    """Untrusted titles are text, never terminal control sequences or markup."""
    return ''.join(c if c >= ' ' or c in '\n\t' else ' ' for c in str(value))


@dataclass
class Row:
    id: str
    label: str
    detail: str = ''
    record: dict | None = None


class RecordList:
    def __init__(self, rows: list[Row], on_select: Callable, on_enter: Callable, empty='No matching records.', width=None):
        self.rows, self.index = rows, 0
        self.on_select, self.on_enter, self.empty = on_select, on_enter, empty
        keys = KeyBindings()
        for names, step in ((('up', 'k'), -1), (('down', 'j'), 1), (('pageup',), -10), (('pagedown',), 10)):
            for name in names:
                keys.add(name)(lambda event, n=step: self.move(n))
        @keys.add('home')
        def home(event): self.move(-len(self.rows))
        @keys.add('end')
        def end(event): self.move(len(self.rows))
        @keys.add('enter')
        def enter(event):
            if self.selected: self.on_enter(self.selected)
        self.control = FormattedTextControl(self.fragments, focusable=True, key_bindings=keys,
                                            get_cursor_position=lambda: Point(x=0, y=self.index*2))
        self.window = Window(self.control, width=width, right_margins=[ScrollbarMargin(display_arrows=True)],
                             wrap_lines=False, always_hide_cursor=False, style='class:record-list')

    @property
    def selected(self):
        return self.rows[self.index] if self.rows and self.index < len(self.rows) else None

    def move(self, amount):
        if self.rows:
            self.index = max(0, min(len(self.rows)-1, self.index+amount))
            self.on_select(self.selected)
            get_app().invalidate()

    def mouse(self, index):
        def handler(event):
            if event.event_type == MouseEventType.MOUSE_UP:
                self.index = index
                get_app().layout.focus(self.control)
                self.on_select(self.selected)
                get_app().invalidate()
            elif event.event_type == MouseEventType.SCROLL_DOWN:
                self.move(3)
            elif event.event_type == MouseEventType.SCROLL_UP:
                self.move(-3)
        return handler

    def fragments(self):
        if not self.rows:
            return [('class:muted', '  '+self.empty)]
        result = []
        focused = get_app().layout.has_focus(self.control)
        for i, row in enumerate(self.rows):
            style = 'class:list.selected' if i == self.index else 'class:list.row'
            marker = ' > ' if i == self.index else '   '
            result += [(style, marker + clean(row.label).replace('\n', ' ') + '\n', self.mouse(i)),
                       (style+' class:muted' if i != self.index else style,
                        '   '+clean(row.detail).replace('\n', ' ')+'\n', self.mouse(i))]
        return result

    def __pt_container__(self):
        return self.window
