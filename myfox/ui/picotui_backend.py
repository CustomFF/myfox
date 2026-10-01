"""picotui-based terminal backend — real dialogs instead of plain
input()/print(), used whenever stdin+stdout are both a tty (see
ui/__init__.py's get_backend()).

The terminal session (raw mode, alt screen, mouse reporting) is entered
once, lazily, on first use and torn down via atexit — not per dialog.
Re-entering the alt screen for every single confirm()/choose() call
across a multi-page wizard would flash the screen between every page;
entering once keeps the whole run on one steady screen and still
guarantees cleanup (atexit fires even on an uncaught exception) so the
real terminal content underneath is never clobbered.
"""

from __future__ import annotations

import atexit
import contextlib
from typing import Sequence

from .. import _vendor

_vendor.ensure_on_path()

from picotui.screen import Screen  # noqa: E402 (must follow ensure_on_path())
from picotui.widgets import Dialog, WButton, WListBox, WLabel, WTextEntry, ACTION_OK, ACTION_CANCEL  # noqa: E402
from picotui.defs import C_WHITE, C_BLACK, C_RED, C_BLUE, KEY_BACKSPACE  # noqa: E402

ACTION_BACK = 1004  # not one of picotui's own reserved 1000-1003 sentinels

BOX_BG = (C_BLACK, C_WHITE)
SHADOW_BG = (C_BLACK, C_BLACK)
BTN_BG = (C_WHITE, C_BLUE)
BTN_FOCUS_BG = (C_WHITE, C_RED)

_MIN_W, _MAX_W = 30, 70

_started = False


def _ensure_screen() -> None:
    global _started
    if _started:
        return
    _started = True
    Screen.init_tty()
    Screen.wr(b"\x1b[?1049h")  # alt screen: real terminal content is untouched underneath
    Screen.enable_mouse()
    Screen.cursor(False)
    atexit.register(_teardown_screen)


def _teardown_screen() -> None:
    Screen.disable_mouse()
    Screen.attr_reset()
    Screen.wr(b"\x1b[?1049l")
    Screen.cursor(True)
    Screen.deinit_tty()


def _clear() -> None:
    # No color fill: the terminal's own background shows around the box
    # instead of a painted field. attr_reset() first, or cls() clears
    # using whatever SGR state a widget last left active.
    Screen.attr_reset()
    Screen.cls()


def _centered(w: int, h: int) -> tuple[int, int]:
    cols, rows = Screen.screen_size()
    return max(0, (cols - w) // 2), max(0, (rows - h) // 2)


def _draw_shadow(x: int, y: int, w: int, h: int, dx: int = 2, dy: int = 1) -> None:
    Screen.attr_color(*SHADOW_BG)
    for row in range(y + dy, y + h + dy):
        Screen.goto(x + w, row)
        Screen.wr(" " * dx)
    Screen.goto(x + dx, y + h)
    Screen.wr(" " * w)
    Screen.attr_reset()


def _box_width(lines: Sequence[str], min_w: int = _MIN_W, max_w: int = _MAX_W) -> int:
    longest = max((len(line) for line in lines), default=0)
    return max(min_w, min(max_w, longest + 6))


class BoxDialog(Dialog):
    """Overrides picotui's own dialog_box(): stock picotui fills the box
    interior with whatever color was last active (so it blends into
    whatever's behind it) and left-aligns the title (dead centering code,
    commented out, in picotui's own source). This makes the box a color
    that actually contrasts with the screen and centers the title."""

    def redraw(self):
        _draw_shadow(self.x, self.y, self.w, self.h)
        super().redraw()

    def dialog_box(self, left, top, width, height, title=""):
        Screen.attr_color(*BOX_BG)
        self.clear_box(left, top, width, height)
        self.draw_box(left, top, width, height)
        if title:
            pos = left + max(1, (width - len(title) - 2) // 2)
            self.goto(pos, top)
            self.wr(f" {title} ")


class ThemedButton(WButton):
    def redraw(self):
        self.goto(self.x, self.y)
        self.attr_color(*(BTN_FOCUS_BG if self.focus else BTN_BG))
        self.wr(f"< {self.t} >".center(self.w))
        self.attr_reset()


def _button_row(d: Dialog, box_w: int, row_y: int, buttons: Sequence[WButton]) -> None:
    gap = 3
    total = sum(b.w for b in buttons) + gap * (len(buttons) - 1)
    x = (box_w - total) // 2
    for b in buttons:
        d.add(x, row_y, b)
        x += b.w + gap


def _set_focus(d: Dialog, widget) -> None:
    d.focus_idx, d.focus_w = d.childs.index(widget), widget
    widget.focus = True


class _FilterableListBox(WListBox):
    """No separate search field: the list has focus by default (arrow
    keys scroll immediately — the obvious first move for anyone used to a
    terminal list), and typing a character starts filtering in place."""

    def __init__(self, w: int, h: int, items: list[str], query_label: WLabel):
        super().__init__(w, h, items)
        self.all_items = items
        self.query = ""
        self.query_label = query_label
        self.finish_dialog = ACTION_OK

    def _refilter(self) -> None:
        q = self.query.lower()
        matches = [item for item in self.all_items if q in item.lower()] or self.all_items
        self.set_items(matches)
        self.top_line = self.cur_line = self.row = 0
        self.query_label.t = f"Filter: {self.query}_" if self.query else "(type to filter)"
        self.owner.redraw()

    def handle_key(self, key):
        if key == KEY_BACKSPACE:
            self.query = self.query[:-1]
            self._refilter()
            return None
        if isinstance(key, bytes):
            try:
                self.query += key.decode("utf-8")
            except UnicodeDecodeError:
                return None
            self._refilter()
            return None
        return super().handle_key(key)


class PicotuiBackend:
    def confirm(self, prompt: str, default: bool = True) -> bool:
        _ensure_screen()
        lines = prompt.split("\n")
        w = _box_width(lines)
        h = len(lines) + 4
        x, y = _centered(w, h)
        _clear()
        d = BoxDialog(x, y, w, h, title="MyFox")
        for i, line in enumerate(lines):
            d.add(2, 1 + i, WLabel(line, w=w - 4))
        yes, no = ThemedButton(10, "Yes"), ThemedButton(10, "No")
        yes.finish_dialog, no.finish_dialog = ACTION_OK, ACTION_CANCEL
        _button_row(d, w, h - 2, [yes, no])
        _set_focus(d, yes if default else no)
        return d.loop() == ACTION_OK

    def choose(self, header: str, options: Sequence[tuple[str, str]], default: str | None = None) -> str | None:
        _ensure_screen()
        labels = [label for _value, label in options]
        w = _box_width(labels + [header])
        h = min(24, len(options) + 8)
        x, y = _centered(w, h)
        _clear()
        d = BoxDialog(x, y, w, h, title=header)

        query_label = WLabel("(type to filter)", w=w - 4)
        lb = _FilterableListBox(w - 4, h - 7, labels, query_label)
        d.add(2, 1, query_label)
        d.add(2, 2, lb)
        back, select = ThemedButton(10, "Back"), ThemedButton(10, "Select")
        back.finish_dialog, select.finish_dialog = ACTION_BACK, ACTION_OK
        _button_row(d, w, h - 2, [back, select])
        _set_focus(d, lb)

        if default is not None:
            default_label = next((label for value, label in options if value == default), None)
            if default_label in lb.items:
                lb.cur_line = lb.items.index(default_label)

        res = d.loop()
        if res != ACTION_OK or not lb.content:
            return None
        chosen_label = lb.content[lb.cur_line]
        return next(value for value, label in options if label == chosen_label)

    def input_dir(self, prompt: str, initial: str) -> str | None:
        _ensure_screen()
        w = _box_width([prompt, initial])
        h = 7
        x, y = _centered(w, h)
        _clear()
        d = BoxDialog(x, y, w, h, title="MyFox")
        d.add(2, 1, WLabel(prompt, w=w - 4))
        entry = WTextEntry(w - 4, initial)
        entry.finish_dialog = ACTION_OK
        d.add(2, 2, entry)
        back = ThemedButton(10, "Back")
        back.finish_dialog = ACTION_BACK
        ok = ThemedButton(10, "OK")
        ok.finish_dialog = ACTION_OK
        _button_row(d, w, h - 2, [back, ok])
        _set_focus(d, entry)

        res = d.loop()
        if res != ACTION_OK:
            return None
        return entry.get() or initial

    def message(self, text: str) -> None:
        _ensure_screen()
        lines = text.split("\n")
        w = _box_width(lines)
        h = len(lines) + 4
        x, y = _centered(w, h)
        _clear()
        d = BoxDialog(x, y, w, h, title="MyFox")
        for i, line in enumerate(lines):
            d.add(2, 1 + i, WLabel(line, w=w - 4))
        ok = ThemedButton(10, "OK")
        ok.finish_dialog = ACTION_OK
        _button_row(d, w, h - 2, [ok])
        _set_focus(d, ok)
        d.loop()

    @contextlib.contextmanager
    def spin(self, title: str):
        """No event loop here: the caller's own blocking work runs inside
        the `with` block, so nothing can process input concurrently — one
        static frame, not animated, same depth as PlainBackend's.

        Draws the frame by calling dialog_box()/WLabel.redraw() directly
        instead of Dialog.redraw()/.loop() — a spinner has no buttons, and
        Dialog.redraw() defaults focus_idx to -1, which makes it call
        find_focusable_by_idx(), which spins forever if there is nothing
        focusable to find (confirmed live: a bare Dialog + WLabel and
        nothing else hangs picotui itself, not just this backend)."""
        _ensure_screen()
        w = _box_width([title])
        h = 5
        x, y = _centered(w, h)
        _clear()
        d = BoxDialog(x, y, w, h, title="MyFox")
        _draw_shadow(x, y, w, h)
        d.dialog_box(x, y, w, h, "MyFox")
        label = WLabel(title, w=w - 4)
        label.set_xy(x + 2, y + 1)
        label.redraw()
        yield
