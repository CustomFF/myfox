"""The refresh dialog as one picotui box: what will be updated, then
Update/Cancel, progress in place of the status line. The logic lives in
refresh.RefreshPlan; this only draws it."""

from __future__ import annotations

import textwrap

from .. import i18n
from ..refresh import RefreshPlan, Updater
from .form_tui import _bar, _FormDialog, _Label
from .picotui_backend import ThemedButton, _button_row, _centered, _clear, _ensure_screen, _set_focus

from picotui.defs import C_RED  # noqa: E402 (picotui_backend put it on sys.path)
from picotui.widgets import ACTION_CANCEL, ACTION_OK  # noqa: E402

_MAX_W = 64


def _button(label: str, action) -> ThemedButton:
    button = ThemedButton(max(12, len(label) + 4), label)
    button.finish_dialog = action
    return button


def run(plan: RefreshPlan, update: Updater) -> bool:
    """True if the update went through; False if cancelled or failed."""
    from picotui.screen import Screen

    _ensure_screen()
    cols, _rows = Screen.screen_size()
    todo = plan.todo
    w = min(_MAX_W, cols - 2)
    h = 2 * len(todo) + 5
    x, y = _centered(w, h)
    _clear()
    d = _FormDialog(x, y, w, h, title=i18n.t("refresh_title"))

    label_w = max(len(t.label) for t in todo) + 2
    for i, t in enumerate(todo):
        d.add(2, 1 + 2 * i, _Label(t.label, label_w))
        d.add(2 + label_w, 1 + 2 * i, _Label(t.describe(), w - 4 - label_w))

    status, bar = _Label("", w - 4), _Label("", w - 4)
    d.add(2, h - 4, status)
    d.add(2, h - 3, bar)
    update_btn = _button(i18n.t("refresh_update"), ACTION_OK)
    cancel_btn = _button(i18n.t("ui_cancel"), ACTION_CANCEL)
    _button_row(d, w, h - 2, [update_btn, cancel_btn])
    _set_focus(d, update_btn)

    if d.loop() != ACTION_OK:
        return False

    def progress(message: str, fraction: float) -> None:
        status.t, bar.t = message, _bar(fraction, w - 4)
        status.redraw()
        bar.redraw()

    update_btn.disabled = True
    update_btn.redraw()
    ok = True
    try:
        update(plan, progress)
    except Exception as exc:  # shown in the dialog
        lines = textwrap.wrap(str(exc) or type(exc).__name__, w - 4, max_lines=2, placeholder="…") or [""]
        status.t, bar.t = lines[0], lines[1] if len(lines) > 1 else ""
        status.fg = bar.fg = C_RED
        status.redraw()
        bar.redraw()
        ok = False

    d.childs.remove(update_btn)
    d.childs.remove(cancel_btn)
    close_btn = _button(i18n.t("form_close"), ACTION_OK)
    _button_row(d, w, h - 2, [close_btn])
    d.focus_idx, d.focus_w = d.childs.index(close_btn), close_btn
    close_btn.focus = True
    d.loop()
    return ok
