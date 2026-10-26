"""The task dialog (task.Task) as one picotui box: rows, an optional list,
the action and Cancel, progress in place of the status line, then Close."""

from __future__ import annotations

import textwrap

from .. import i18n
from ..install_form import Cancelled
from ..task import Task
from .form_tui import _Checkbox, _FormDialog, _Label, _list_line, run_live
from .picotui_base import ThemedButton, _button_row, _centered, _clear, _ensure_screen, _set_focus

from picotui.defs import C_BLACK, C_RED, KEY_ENTER  # noqa: E402 (picotui_base put it on sys.path)
from picotui.widgets import ACTION_CANCEL, ACTION_OK, WListBox  # noqa: E402

_MAX_W = 72


def _button(label: str, action) -> ThemedButton:
    button = ThemedButton(max(12, len(label) + 4), label)
    button.finish_dialog = action
    return button


def _show_error(status: _Label, bar: _Label, text: str, width: int) -> None:
    lines = textwrap.wrap(text, width, max_lines=2, placeholder="…") or [""]
    status.t, bar.t = lines[0], lines[1] if len(lines) > 1 else ""
    status.fg = bar.fg = C_RED


class _ChoiceList(WListBox):
    """Enter takes the highlighted one."""

    def handle_key(self, key):
        if key == KEY_ENTER:
            return ACTION_OK
        return super().handle_key(key)

    def show_line(self, l, i):
        _list_line(self, l, i)


def _pick(task: Task) -> bool:
    from picotui.screen import Screen

    _ensure_screen()
    cols, rows = Screen.screen_size()
    labels = [label for _value, label in task.choices]
    w = min(max(_MAX_W, max(map(len, labels)) + 6), cols - 2)
    list_h = max(1, min(len(labels), rows - 8))
    h = list_h + 6
    x, y = _centered(w, h)
    _clear()
    d = _FormDialog(x, y, w, h, title=task.title)
    d.add(2, 1, _Label(task.subtitle, w - 4))
    choices = _ChoiceList(w - 4, list_h, labels)
    d.add(2, 3, choices)
    _button_row(d, w, h - 2, [_button(task.action, ACTION_OK), _button(i18n.t("ui_cancel"), ACTION_CANCEL)])
    _set_focus(d, choices)
    if d.loop() != ACTION_OK:
        return False
    task.choice = task.choices[choices.cur_line][0]
    return True


def run(task: Task) -> bool:
    """True once the action ran through; False if cancelled, blocked or failed."""
    from picotui.screen import Screen

    if task.choices:
        return _pick(task)
    _ensure_screen()
    cols, rows = Screen.screen_size()
    w = min(_MAX_W, cols - 2)
    label_w = max((len(label) for label, _value in task.rows), default=0) + 2
    row_lines = [textwrap.wrap(value, w - 4 - label_w, break_on_hyphens=False) or [""] for _label, value in task.rows]
    rows_h = sum(len(lines) + 1 for lines in row_lines)
    limit = max(1, rows - rows_h - len(task.options) - 9)
    shown = task.lines_shown(limit)
    # "...and N more" is a button that shows them all.
    more = shown.pop() if task.more and task.cut(limit) else None
    listed = []
    for line in shown:
        listed += textwrap.wrap(line, w - 8, initial_indent="- ", subsequent_indent="  ", break_on_hyphens=False) or ["-"]
    list_h = len(listed) + (1 if more else 0) + (1 if task.heading else 0) + 1 if listed or more else 0
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
    if listed or more:
        if task.heading:
            d.add(2, top, _Label(task.heading, w - 4))
            top += 1
        for line in listed[:max(0, h - top - 4 - options_h - (1 if more else 0))]:
            d.add(4, top, _Label(line, w - 6))
            top += 1
        if more:
            more_btn = ThemedButton(min(len(more) + 2, w - 6), more[:w - 8])
            more_btn.on("click", lambda _button: task.more())
            d.add(4, top, more_btn)
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

    def show_block() -> None:
        # Focus stays put when the action frees up: an Enter meant for
        # Cancel mustn't start it.
        if task.blocked:
            _show_error(status, bar, task.blocked, w - 4)
            if d.focus_w is action_btn:
                d.change_focus(cancel_btn)
        else:
            status.t = bar.t = ""
            status.fg = bar.fg = C_BLACK
        action_btn.disabled = bool(task.blocked)
        for widget in (status, bar, action_btn, cancel_btn):
            widget.redraw()

    def take_options() -> None:
        # A recheck may depend on them (e.g. an option that needs another
        # Firefox closed).
        for check, option in checks:
            option.value = check.choice

    def idle() -> None:
        take_options()
        if task.rechecked():
            show_block()

    if task.recheck is not None:
        d.on_idle = idle
    while True:
        if d.loop() != ACTION_OK:
            return False
        # The last look before running: Firefox may have started since.
        take_options()
        if not task.rechecked() and not task.blocked:
            break
        show_block()
    d.on_idle = None
    for check, _option in checks:
        # Settled once the action runs: shown, no longer focusable.
        d.childs[d.childs.index(check)] = label = _Label(("[x] " if check.choice else "[ ] ") + check.t, check.w)
        label.set_xy(check.x, check.y)
        label.owner = d

    action_btn.disabled = True
    action_btn.redraw()
    failure = run_live(d, status, bar, cancel_btn, task.run, cancellable=task.cancellable)
    if isinstance(failure, Cancelled):
        status.t, bar.t = i18n.t("task_cancelled"), ""
        status.redraw()
        bar.redraw()
    elif isinstance(failure, Exception):  # shown in the dialog
        _show_error(status, bar, str(failure) or type(failure).__name__, w - 4)
        status.redraw()
        bar.redraw()
    elif failure is not None:
        raise failure
    ok = failure is None

    d.childs.remove(action_btn)
    d.childs.remove(cancel_btn)
    close_btn = _button(i18n.t("form_close"), ACTION_OK)
    _button_row(d, w, h - 2, [close_btn])
    d.focus_idx, d.focus_w = d.childs.index(close_btn), close_btn
    close_btn.focus = True
    d.loop()
    return ok
