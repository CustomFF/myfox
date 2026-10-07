"""The task dialog (task.Task) as a dearpygui window, in the install form's
look: rows, an optional list, the action and Cancel, progress in the footer,
then Close. Left/Right/Tab move between the buttons, Enter presses the
focused one, Escape closes."""

from __future__ import annotations

import math
import threading

import dearpygui.dearpygui as dpg

from .. import i18n
from ..task import Task
from .form_gui import (
    ACCENT, ASSETS, BTN_GAP, BTN_H, BTN_W, ERROR, FOOTER_H, HEADER_H, LABEL_W, LINE, MUTED, PAD, WIN_W,
    _button_theme, _color_theme, _global_theme, _load_fonts, px, symbol_font,
)

ROW_H = 32
LINE_H = 22
LINES_LIMIT = 10
_CHAR_W = 7.5  # rough logical px per character, only to size wrapped values


def _value_lines(text: str, indent: int) -> int:
    return max(1, math.ceil(len(text) * _CHAR_W / (WIN_W - PAD * 2 - indent)))


class _Window:
    def __init__(self, task: Task, bold_font: int | None) -> None:
        self.task = task
        self._progress: tuple[str, float] | None = None
        self._failure: str | None = None
        self._worker: threading.Thread | None = None
        self._done = False
        self._measured = False
        self.ok = False
        self.lines = task.lines_shown(LINES_LIMIT)
        # Body blocks top to bottom: (items sharing a line, gap before). Only
        # an estimate sizes the first frame; relayout() measures the real one.
        self._blocks: list[tuple[list[int], int]] = []
        est = [ROW_H + LINE_H * (_value_lines(value, LABEL_W) - 1) for _label, value in task.rows]
        if self.lines:
            est.append(PAD // 2 + LINE_H * (1 if task.heading else 0))
            est += [LINE_H * _value_lines(line, 12) for line in self.lines]
        est += [ROW_H] * len(task.options)
        self.height = px(HEADER_H) + 1 + px(PAD * 2 + sum(est)) + 1 + px(FOOTER_H)
        self._build(bold_font)

    def _build(self, bold_font: int | None) -> None:
        w, h = px(WIN_W), self.height
        header_h, footer_h = px(HEADER_H), px(FOOTER_H)
        footer_y = h - footer_h
        with dpg.window(tag="root", no_scrollbar=True):
            dpg.draw_line((0, header_h), (w, header_h), color=LINE)
            self.footer_line = dpg.draw_line((0, footer_y - 1), (w, footer_y - 1), color=LINE)

            with dpg.child_window(pos=(0, 0), width=w, height=header_h, border=False, no_scrollbar=True) as header:
                title = dpg.add_text(self.task.title, pos=(px(PAD), px(12)))
                dpg.add_text(self.task.subtitle, pos=(px(PAD + 12), px(36)), color=MUTED)
            dpg.bind_item_theme(header, _color_theme(ChildBg=(255, 255, 255)))
            if bold_font is not None:
                dpg.bind_item_font(title, bold_font)

            with dpg.child_window(pos=(0, header_h + 1), width=w, height=footer_y - header_h - 2, border=False,
                                  no_scrollbar=True) as self.body:
                arrow_font = symbol_font("→")
                y = px(PAD)
                for label, value in self.task.rows:
                    items = [dpg.add_text(label, pos=(px(PAD), y))]
                    old, arrow, new = value.partition(" → ")
                    if not arrow:
                        items.append(dpg.add_text(value, pos=(px(PAD + LABEL_W), y),
                                                  wrap=px(WIN_W - PAD * 2 - LABEL_W)))
                    else:
                        # The system sans may lack "→": the arrow gets a font
                        # that has it, or falls back to "->".
                        with dpg.group(horizontal=True, horizontal_spacing=px(4), pos=(px(PAD + LABEL_W), y)) as group:
                            dpg.add_text(old)
                            arrow_item = dpg.add_text("→" if arrow_font else "->")
                            dpg.add_text(new)
                        if arrow_font:
                            dpg.bind_item_font(arrow_item, arrow_font)
                        items.append(group)
                    self._blocks.append((items, px(ROW_H - LINE_H) if self._blocks else 0))
                    y += px(ROW_H)
                if self.lines:
                    gap = px(PAD // 2 + ROW_H - LINE_H) if self._blocks else 0
                    if self.task.heading:
                        self._blocks.append(([dpg.add_text(self.task.heading, pos=(px(PAD), y))], gap))
                        gap = 0
                    for line in self.lines:
                        item = dpg.add_text(f"•  {line}", pos=(px(PAD + 12), y), wrap=px(WIN_W - PAD * 2 - 12))
                        self._blocks.append(([item], gap))
                        gap = 0
                self.checks = []
                for option in self.task.options:
                    item = dpg.add_checkbox(
                        label=option.label, default_value=option.value, pos=(px(PAD), y),
                        callback=lambda sender, value, option=option: setattr(option, "value", value),
                    )
                    self._blocks.append(([item], px(PAD) if self._blocks else 0))
                    self.checks.append((item, option))

            with dpg.child_window(pos=(0, footer_y), width=w, height=footer_h, border=False,
                                  no_scrollbar=True) as self.footer:
                y = (footer_h - px(BTN_H)) // 2
                x_cancel = px(WIN_W - PAD - BTN_W)
                x_action = x_cancel - px(BTN_GAP) - px(BTN_W)
                status_w = x_action - px(PAD) * 2
                self.status = dpg.add_text("", pos=(px(PAD), px(8)), wrap=status_w)
                self.bar = dpg.add_progress_bar(pos=(px(PAD), px(32)), width=status_w, height=px(8), show=False)
                self.action = dpg.add_button(
                    label=self.task.action, width=px(BTN_W), height=px(BTN_H), pos=(x_action, y),
                    callback=self._on_action,
                )
                self.cancel = dpg.add_button(
                    label=i18n.t("ui_cancel"), width=px(BTN_W), height=px(BTN_H), pos=(x_cancel, y),
                    callback=lambda: dpg.stop_dearpygui(),
                )

        if self.task.blocked:
            dpg.set_value(self.status, self.task.blocked)
            dpg.bind_item_theme(self.status, _color_theme(Text=ERROR))
            dpg.configure_item(self.action, enabled=False)
        self._themes = {
            self.action: (_button_theme(True, False), _button_theme(True, True)),
            self.cancel: (_button_theme(False, False), _button_theme(False, True)),
        }
        check_themes = (_color_theme(), _color_theme(Border=ACCENT))
        for item, _option in self.checks:
            self._themes[item] = check_themes
        self._focus(self.cancel if self.task.destructive or self.task.blocked else self.action)
        with dpg.handler_registry():
            for key in (dpg.mvKey_Return, dpg.mvKey_NumPadEnter, dpg.mvKey_Left, dpg.mvKey_Right, dpg.mvKey_Tab,
                        dpg.mvKey_Escape, dpg.mvKey_Spacebar):
                dpg.add_key_press_handler(key, callback=lambda sender, key: self._on_key(key))
        dpg.set_primary_window("root", True)

    def relayout(self) -> None:
        """Once a frame is drawn: stacks the body by the measured heights of
        its (wrapped) texts and fits the window to it."""
        self._measured = True
        y = px(PAD)
        for items, gap in self._blocks:
            y += gap
            for item in items:
                dpg.configure_item(item, pos=(dpg.get_item_pos(item)[0], y))
            y += max(dpg.get_item_rect_size(item)[1] for item in items)
        header_h, footer_h, w = px(HEADER_H), px(FOOTER_H), px(WIN_W)
        body_h = y + px(PAD)
        h = header_h + 1 + body_h + 1 + footer_h
        if h == self.height:
            return
        self.height = h
        dpg.configure_item(self.body, height=body_h)
        dpg.configure_item(self.footer, pos=(0, h - footer_h))
        dpg.configure_item(self.footer_line, p1=(0, h - footer_h - 1), p2=(w, h - footer_h - 1))
        dpg.set_viewport_max_height(max(h, dpg.get_viewport_height()))
        dpg.set_viewport_min_height(h)
        dpg.set_viewport_max_height(h)
        dpg.set_viewport_height(h)

    def on_close(self) -> None:
        """The window's own close button: ignored while the action runs."""
        if self._worker is None:
            dpg.stop_dearpygui()

    def _focus(self, button: int) -> None:
        self._focused = button
        for item, (idle, focused) in self._themes.items():
            dpg.bind_item_theme(item, focused if item == button else idle)

    def _buttons(self) -> list[int]:
        return [b for b in (self.action, self.cancel)
                if dpg.get_item_configuration(b)["show"] and dpg.get_item_configuration(b)["enabled"]]

    def _on_key(self, key: int) -> None:
        if self._worker is not None:
            return
        checks = dict(self.checks) if not self._done else {}
        if key == dpg.mvKey_Escape:
            dpg.stop_dearpygui()
        elif self._focused in checks and key in (dpg.mvKey_Spacebar, dpg.mvKey_Return, dpg.mvKey_NumPadEnter):
            option = checks[self._focused]
            option.value = not option.value
            dpg.set_value(self._focused, option.value)
        elif key in (dpg.mvKey_Return, dpg.mvKey_NumPadEnter):
            (self._on_action if self._focused == self.action else dpg.stop_dearpygui)()
        elif key in (dpg.mvKey_Left, dpg.mvKey_Right, dpg.mvKey_Tab):
            # Tab goes through the checkboxes too, Left/Right only the buttons.
            order = list(checks) + self._buttons() if key == dpg.mvKey_Tab else self._buttons()
            if self._focused in order and len(order) > 1:
                step = -1 if key == dpg.mvKey_Left else 1
                self._focus(order[(order.index(self._focused) + step) % len(order)])
            elif order:
                self._focus(order[0])

    def _on_action(self) -> None:
        if self._worker is not None or self._done or self.task.blocked:
            return
        # Closing mid-run would kill the worker halfway through.
        dpg.configure_item(self.action, enabled=False)
        dpg.configure_item(self.cancel, enabled=False)
        for item, _option in self.checks:
            dpg.configure_item(item, enabled=False)
        dpg.configure_item(self.bar, show=True)
        self._progress = ("", 0.0)

        def run() -> None:
            try:
                self.task.run(lambda message, fraction: setattr(self, "_progress", (message, fraction)))
            except Exception as exc:  # shown in the window
                self._failure = str(exc) or type(exc).__name__

        self._worker = threading.Thread(target=run, daemon=True)
        self._worker.start()

    def tick(self) -> None:
        if self._worker is None:
            return
        if self._progress is not None:
            message, fraction = self._progress
            dpg.set_value(self.status, message)
            dpg.set_value(self.bar, fraction)
        if not self._worker.is_alive():
            self._worker, self._done = None, True
            if self._failure:
                dpg.set_value(self.status, self._failure)
                dpg.bind_item_theme(self.status, _color_theme(Text=ERROR))
            else:
                self.ok = True
            dpg.configure_item(self.action, show=False)
            dpg.configure_item(self.cancel, label=i18n.t("form_close"), enabled=True)
            self._focus(self.cancel)


def run(task: Task) -> bool:
    """True once the action ran through; False if cancelled, blocked or failed."""
    dpg.create_context()
    regular, bold = _load_fonts()
    if regular is not None:
        dpg.bind_font(regular)
    dpg.bind_theme(_global_theme())
    window = _Window(task, bold)

    w, h = px(WIN_W), window.height
    dpg.create_viewport(
        title="MyFox", width=w, height=h, min_width=w, max_width=w, min_height=h, max_height=h, resizable=False,
        small_icon=str(ASSETS / "icon-48.png"), large_icon=str(ASSETS / "icon-256.png"), disable_close=True,
    )
    dpg.set_exit_callback(window.on_close)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    try:
        while dpg.is_dearpygui_running():
            window.tick()
            dpg.render_dearpygui_frame()
            if not window._measured:
                window.relayout()
    finally:
        dpg.destroy_context()
    return window.ok
