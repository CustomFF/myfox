"""The task dialog (task.Task) as one picotui box: rows, an optional list,
the action and Cancel, progress in place of the status line, then Close."""

from __future__ import annotations

import textwrap

from .. import i18n
from ..task import Task
from .form_tui import _bar, _Checkbox, _FormDialog, _Label
from .picotui_base import ThemedButton, _button_row, _centered, _clear, _ensure_screen, _set_focus

from picotui.defs import C_RED  # noqa: E402 (picotui_base put it on sys.path)
from picotui.widgets import ACTION_CANCEL, ACTION_OK  # noqa: E402

_MAX_W = 72


def _button(label: str, action) -> ThemedButton:
    button = ThemedButton(max(12, len(label) + 4), label)
    button.finish_dialog = action
    return button


def _show_error(status: _Label, bar: _Label, text: str, width: int) -> None:
    lines = textwrap.wrap(text, width, max_lines=2, placeholder="…") or [""]
    status.t, bar.t = lines[0], lines[1] if len(lines) > 1 else ""
    status.fg = bar.fg = C_RED


def run(task: Task) -> bool:
    """True once the action ran through; False if cancelled, blocked or failed."""
    from picotui.screen import Screen

    _ensure_screen()
    cols, rows = Screen.screen_size()
    w = min(_MAX_W, cols - 2)
    label_w = max(len(label) for label, _value in task.rows) + 2
    row_lines = [textwrap.wrap(value, w - 4 - label_w, break_on_hyphens=False) or [""] for _label, value in task.rows]
    rows_h = sum(len(lines) + 1 for lines in row_lines)
    listed = []
    for line in task.lines_shown(max(1, rows - rows_h - len(task.options) - 9)):
        listed += textwrap.wrap(line, w - 8, initial_indent="- ", subsequent_indent="  ", break_on_hyphens=False) or ["-"]
    list_h = len(listed) + (1 if task.heading else 0) + 1 if listed else 0
    options_h = len(task.options) + 1 if task.options else 0
    h = min(rows - 1, rows_h + list_h + options_h + 4)
    x, y = _centered(w, h)
    _clear()
    d = _FormDialog(x, y, w, h, title=task.title)

    top = 1
    for (label, _value), lines in zip(task.rows, row_lines):
        d.add(2, top, _Label(label, label_w))
        for i, line in enumerate(lines):
            d.add(2 + label_w, top + i, _Label(line, w - 4 - label_w))
        top += len(lines) + 1
    if listed:
        if task.heading:
            d.add(2, top, _Label(task.heading, w - 4))
            top += 1
        for line in listed[:max(0, h - top - 4 - options_h)]:
            d.add(4, top, _Label(line, w - 6))
            top += 1
        top += 1
    checks = []
    for option in task.options:
        check = _Checkbox(option.label[:w - 8], choice=option.value)
        d.add(2, top, check)
        checks.append((check, option))
        top += 1

    status, bar = _Label("", w - 4), _Label("", w - 4)
    d.add(2, h - 4, status)
    d.add(2, h - 3, bar)
    action_btn = _button(task.action, ACTION_OK)
    cancel_btn = _button(i18n.t("ui_cancel"), ACTION_CANCEL)
    _button_row(d, w, h - 2, [action_btn, cancel_btn])
    if task.blocked:
        _show_error(status, bar, task.blocked, w - 4)
        action_btn.disabled = True
    _set_focus(d, cancel_btn if task.destructive or task.blocked else action_btn)

    if d.loop() != ACTION_OK or task.blocked:
        return False
    for check, option in checks:
        option.value = check.choice
        # Settled once the action runs: shown, no longer focusable.
        d.childs[d.childs.index(check)] = label = _Label(("[x] " if check.choice else "[ ] ") + check.t, check.w)
        label.set_xy(check.x, check.y)
        label.owner = d

    def progress(message: str, fraction: float) -> None:
        status.t, bar.t = message, _bar(fraction, w - 4)
        status.redraw()
        bar.redraw()

    action_btn.disabled = True
    action_btn.redraw()
    ok = True
    try:
        task.run(progress)
    except Exception as exc:  # shown in the dialog
        _show_error(status, bar, str(exc) or type(exc).__name__, w - 4)
        status.redraw()
        bar.redraw()
        ok = False

    d.childs.remove(action_btn)
    d.childs.remove(cancel_btn)
    close_btn = _button(i18n.t("form_close"), ACTION_OK)
    _button_row(d, w, h - 2, [close_btn])
    d.focus_idx, d.focus_w = d.childs.index(close_btn), close_btn
    close_btn.focus = True
    d.loop()
    return ok
