"""What the picotui views (form_tui, task_tui) share: the terminal session,
the box and button look, and placing buttons.

The terminal session (raw mode, alt screen, mouse reporting) is entered
once, lazily, and torn down at exit: re-entering the alt screen per dialog
would flash the screen, and atexit restores the terminal even after an
uncaught exception.
"""

from __future__ import annotations

import atexit
from typing import Sequence

from .. import _vendor

_vendor.ensure_on_path()

from picotui.screen import Screen  # noqa: E402 (must follow ensure_on_path())
from picotui.widgets import Dialog, WButton  # noqa: E402
from picotui.defs import C_WHITE, C_BLACK, C_RED, C_BLUE  # noqa: E402

BOX_BG = (C_BLACK, C_WHITE)
SHADOW_BG = (C_BLACK, C_BLACK)
BTN_BG = (C_WHITE, C_BLUE)
BTN_FOCUS_BG = (C_WHITE, C_RED)
# picotui's attr_color() can't do gray (C_GRAY == 8 falls through its
# `fg > 8` check and emits a broken ESC[38m), so gray goes out as raw SGR.
SGR_GRAY_ON_CYAN = "\x1b[90;46m"
SGR_WHITE_ON_GRAY = "\x1b[37;100m"


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
    atexit.register(end_screen)


def end_screen() -> None:
    """Leaves the alt screen now (it's otherwise left at exit), so whatever
    is printed next stays visible in the terminal. Safe to call twice."""
    global _started
    if not _started:
        return
    _started = False
    _teardown_screen()


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
        if self.disabled:
            self.wr(SGR_WHITE_ON_GRAY)
        else:
            self.attr_color(*(BTN_FOCUS_BG if self.focus else BTN_BG))
        self.wr(self.t.center(self.w))
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
