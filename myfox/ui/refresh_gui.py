"""The refresh dialog as a dearpygui window, in the install form's look:
what will be updated, Update/Cancel, progress in the footer. The logic
lives in refresh.RefreshPlan; this only draws it."""

from __future__ import annotations

import threading

import dearpygui.dearpygui as dpg

from .. import i18n
from ..refresh import RefreshPlan, Updater
from .form_gui import (
    ASSETS, BTN_GAP, BTN_H, BTN_W, ERROR, FOOTER_H, HEADER_H, LABEL_W, LINE, MUTED, PAD, WIN_W,
    _button_theme, _color_theme, _global_theme, _load_fonts, px,
)

ROW_H = 32


class _Window:
    def __init__(self, plan: RefreshPlan, update: Updater, bold_font: int | None) -> None:
        self.plan, self._update = plan, update
        self._progress: tuple[str, float] | None = None
        self._failure: str | None = None
        self._worker: threading.Thread | None = None
        self.ok = False
        self.height = px(HEADER_H) + 1 + px(PAD * 2 + ROW_H * len(plan.todo)) + 1 + px(FOOTER_H)
        self._build(bold_font)

    def _build(self, bold_font: int | None) -> None:
        w, h = px(WIN_W), self.height
        header_h, footer_h = px(HEADER_H), px(FOOTER_H)
        footer_y = h - footer_h
        with dpg.window(tag="root", no_scrollbar=True):
            dpg.draw_line((0, header_h), (w, header_h), color=LINE)
            dpg.draw_line((0, footer_y - 1), (w, footer_y - 1), color=LINE)

            with dpg.child_window(pos=(0, 0), width=w, height=header_h, border=False, no_scrollbar=True) as header:
                title = dpg.add_text(i18n.t("refresh_title"), pos=(px(PAD), px(12)))
                subtitle = "refresh_subtitle_force" if self.plan.force else "refresh_subtitle"
                dpg.add_text(i18n.t(subtitle), pos=(px(PAD + 12), px(36)), color=MUTED)
            dpg.bind_item_theme(header, _color_theme(ChildBg=(255, 255, 255)))
            if bold_font is not None:
                dpg.bind_item_font(title, bold_font)

            with dpg.child_window(pos=(0, header_h + 1), width=w, height=footer_y - header_h - 2, border=False,
                                  no_scrollbar=True):
                for i, t in enumerate(self.plan.todo):
                    y = px(PAD + ROW_H * i)
                    dpg.add_text(t.label, pos=(px(PAD), y))
                    dpg.add_text(t.describe(), pos=(px(PAD) + px(LABEL_W), y))

            with dpg.child_window(pos=(0, footer_y), width=w, height=footer_h, border=False, no_scrollbar=True):
                y = (footer_h - px(BTN_H)) // 2
                x_cancel = px(WIN_W - PAD - BTN_W)
                x_update = x_cancel - px(BTN_GAP) - px(BTN_W)
                status_w = x_update - px(PAD) * 2
                self.status = dpg.add_text("", pos=(px(PAD), px(8)), wrap=status_w)
                self.bar = dpg.add_progress_bar(pos=(px(PAD), px(32)), width=status_w, height=px(8), show=False)
                self.update_btn = dpg.add_button(
                    label=i18n.t("refresh_update"), width=px(BTN_W), height=px(BTN_H), pos=(x_update, y),
                    callback=self._on_update,
                )
                dpg.bind_item_theme(self.update_btn, _button_theme(True, True))
                self.cancel = dpg.add_button(
                    label=i18n.t("ui_cancel"), width=px(BTN_W), height=px(BTN_H), pos=(x_cancel, y),
                    callback=lambda: dpg.stop_dearpygui(),
                )
                dpg.bind_item_theme(self.cancel, _button_theme(False, False))

        with dpg.handler_registry():
            for key in (dpg.mvKey_Return, dpg.mvKey_NumPadEnter):
                dpg.add_key_press_handler(key, callback=lambda: self._on_enter())
            dpg.add_key_press_handler(dpg.mvKey_Escape, callback=lambda: dpg.stop_dearpygui())
        dpg.set_primary_window("root", True)

    def _on_enter(self) -> None:
        if self._worker is None and dpg.get_item_configuration(self.update_btn)["show"]:
            self._on_update()
        elif self._worker is None:
            dpg.stop_dearpygui()  # Enter on the finished dialog closes it

    def _on_update(self) -> None:
        if self._worker is not None:
            return
        dpg.configure_item(self.update_btn, enabled=False)
        dpg.configure_item(self.bar, show=True)
        self._progress = ("", 0.0)

        def run() -> None:
            try:
                self._update(self.plan, lambda message, fraction: setattr(self, "_progress", (message, fraction)))
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
            self._worker = None
            if self._failure:
                dpg.set_value(self.status, self._failure)
                dpg.bind_item_theme(self.status, _color_theme(Text=ERROR))
            else:
                self.ok = True
            dpg.configure_item(self.update_btn, show=False)
            dpg.configure_item(self.cancel, label=i18n.t("form_close"))
            dpg.bind_item_theme(self.cancel, _button_theme(False, True))


def run(plan: RefreshPlan, update: Updater) -> bool:
    """True if the update went through; False if cancelled or failed."""
    dpg.create_context()
    regular, bold = _load_fonts()
    if regular is not None:
        dpg.bind_font(regular)
    dpg.bind_theme(_global_theme())
    window = _Window(plan, update, bold)

    w, h = px(WIN_W), window.height
    dpg.create_viewport(
        title="MyFox", width=w, height=h, min_width=w, max_width=w, min_height=h, max_height=h, resizable=False,
        small_icon=str(ASSETS / "icon-48.png"), large_icon=str(ASSETS / "icon-256.png"),
    )
    dpg.setup_dearpygui()
    dpg.show_viewport()
    try:
        while dpg.is_dearpygui_running():
            window.tick()
            dpg.render_dearpygui_frame()
    finally:
        dpg.destroy_context()
    return window.ok
