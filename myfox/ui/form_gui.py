"""The install form as a dearpygui window (--gui): one fixed-size page,
Install/Cancel at the bottom, progress in the footer while installing.
All decisions live in install_form.InstallForm; this only draws it.
"""

from __future__ import annotations

import contextlib
import subprocess
import threading
from pathlib import Path

import dearpygui.dearpygui as dpg

from .. import i18n
from ..install_form import Answers, Choice, InstallForm, Installer, Lang
from . import portal

ASSETS = Path(__file__).resolve().parent / "assets"

# Logical (96 dpi) pixels; everything is multiplied by SCALE.
WIN_W, WIN_H = 600, 480
HEADER_H = 64
FOOTER_H = 52
PAD = 16
BTN_W, BTN_H = 96, 28
LABEL_W = 110
COMBO_W = 220
BTN_GAP = 8
FONT_PT = 10

ACCENT = (61, 174, 233)
ERROR = (218, 68, 83)
MUTED = (112, 125, 138)
LINE = (205, 207, 208)
# Just a shade darker than the window background: edges stay readable
# without the outline drawing attention to itself.
FRAME_BORDER = (214, 216, 218)


def _xft_dpi() -> float:
    # X11 apps on a scaled KDE/GNOME session get the scale only via Xft.dpi.
    try:
        out = subprocess.run(["xrdb", "-query"], capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return 96.0
    for line in out.splitlines():
        if line.startswith("Xft.dpi:"):
            return float(line.split()[1])
    return 96.0


def _font_file(pattern: str) -> str | None:
    try:
        path = subprocess.run(
            ["fc-match", "-f", "%{file}", pattern], capture_output=True, text=True, timeout=2,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return path or None


DPI = _xft_dpi()
SCALE = DPI / 96


def px(v: float) -> int:
    return round(v * SCALE)


def _renderable(text: str) -> bool:
    """Latin, Greek and Cyrillic only — what the system sans font carries.
    dpg loads one font file with no fallback chain, so other scripts would
    render as replacement boxes."""
    return all(ord(ch) < 0x0530 or 0x1E00 <= ord(ch) <= 0x206F for ch in text)


def symbol_font(char: str) -> int | None:
    """A font that has `char` (via fontconfig), for a single item to use
    when the system sans lacks it — dpg has no fallback chain."""
    path = _font_file(f"sans-serif:charset={ord(char):x}")
    if not path:
        return None
    with dpg.font_registry():
        return dpg.add_font(path, round(FONT_PT * DPI / 72))


def _load_fonts() -> tuple[int | None, int | None]:
    regular, bold = _font_file("sans-serif"), _font_file("sans-serif:bold")
    size = round(FONT_PT * DPI / 72)
    fonts = []
    with dpg.font_registry():
        for path, extra in ((regular, 0), (bold, 2)):
            # Glyph ranges (Cyrillic included) are picked automatically.
            fonts.append(dpg.add_font(path, size + extra) if path else None)
    return fonts[0], fonts[1]


def _global_theme() -> int:
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvAll):
            for col, rgb in (
                (dpg.mvThemeCol_WindowBg, (239, 240, 241)),
                (dpg.mvThemeCol_ChildBg, (239, 240, 241)),
                (dpg.mvThemeCol_PopupBg, (255, 255, 255)),
                (dpg.mvThemeCol_Text, (35, 38, 41)),
                (dpg.mvThemeCol_TextDisabled, MUTED),
                (dpg.mvThemeCol_Border, FRAME_BORDER),
                # dpg's default draws an opaque 1px shadow under every
                # frame border, which made any outline look dark and doubled.
                (dpg.mvThemeCol_BorderShadow, (0, 0, 0, 0)),
                (dpg.mvThemeCol_FrameBg, (255, 255, 255)),
                (dpg.mvThemeCol_FrameBgHovered, (255, 255, 255)),
                (dpg.mvThemeCol_FrameBgActive, (255, 255, 255)),
                (dpg.mvThemeCol_Button, (252, 252, 252)),
                (dpg.mvThemeCol_ButtonHovered, (226, 242, 251)),
                (dpg.mvThemeCol_ButtonActive, (196, 229, 246)),
                (dpg.mvThemeCol_Header, (196, 229, 246)),
                (dpg.mvThemeCol_HeaderHovered, (226, 242, 251)),
                (dpg.mvThemeCol_HeaderActive, (196, 229, 246)),
                (dpg.mvThemeCol_CheckMark, ACCENT),
                (dpg.mvThemeCol_PlotHistogram, ACCENT),
                (dpg.mvThemeCol_ScrollbarBg, (239, 240, 241)),
                (dpg.mvThemeCol_ScrollbarGrab, (188, 190, 191)),
                (dpg.mvThemeCol_ScrollbarGrabHovered, (160, 162, 163)),
                (dpg.mvThemeCol_ScrollbarGrabActive, (130, 132, 133)),
                (dpg.mvThemeCol_NavHighlight, ACCENT),
            ):
                dpg.add_theme_color(col, rgb)
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 0)
            dpg.add_theme_style(dpg.mvStyleVar_WindowBorderSize, 0)
            dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 0)
            dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 1)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, px(3))
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, px(6), px(4))
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, px(8), px(6))
        for kind in (dpg.mvCombo, dpg.mvInputText, dpg.mvButton, dpg.mvCheckbox, dpg.mvSelectable):
            with dpg.theme_component(kind, enabled_state=False):
                dpg.add_theme_color(dpg.mvThemeCol_Text, (160, 164, 168))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (246, 246, 247))
                dpg.add_theme_color(dpg.mvThemeCol_Button, (246, 246, 247))
    return theme


def _color_theme(**colors) -> int:
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvAll):
            for name, rgb in colors.items():
                dpg.add_theme_color(getattr(dpg, f"mvThemeCol_{name}"), rgb)
    return theme


def _padded_theme() -> int:
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, px(PAD), px(PAD))
    return theme


def _list_theme(border=FRAME_BORDER) -> int:
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (255, 255, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg, (255, 255, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Border, border)
            dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 1)
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, px(4), px(4))
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 0, 0)
    return theme


def _button_theme(primary: bool, focused: bool) -> int:
    """Install is the accent button; a keyboard-focused button gets a 2px
    ring (darker accent on Install, accent on the others)."""
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvButton):
            if primary:
                dpg.add_theme_color(dpg.mvThemeCol_Button, ACCENT)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (89, 188, 239))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (41, 150, 207))
                dpg.add_theme_color(dpg.mvThemeCol_Text, (255, 255, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Border, (29, 99, 140) if focused else ACCENT)
            elif focused:
                dpg.add_theme_color(dpg.mvThemeCol_Border, ACCENT)
            if focused:
                dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 2)
    return theme


def _input_themes() -> tuple[int, int]:
    """(idle, focused): the usual faint outline, the accent one while typing."""
    themes = []
    for color in (FRAME_BORDER, ACCENT):
        with dpg.theme() as theme:
            with dpg.theme_component(dpg.mvInputText):
                dpg.add_theme_color(dpg.mvThemeCol_Border, color)
        themes.append(theme)
    return themes[0], themes[1]


class _LangList:
    """Single-choice list on selectables — dpg's listbox can't scroll to
    its selected row, and the default in 172 languages must be visible."""

    def __init__(self, langs: list[Lang], default: str) -> None:
        self.value = default
        self._rows: dict[str, int] = {}
        self._shown = [lang.code for lang in langs]
        with dpg.child_window(height=-1, border=True, always_use_window_padding=True) as self.box:
            for lang in langs:
                self._rows[lang.code] = dpg.add_selectable(
                    label=lang.label(show_native=_renderable(lang.native)), default_value=lang.code == default,
                    user_data=lang.code, callback=lambda sender, app_data, code: self.pick(code),
                )
        self._themes = (_list_theme(), _list_theme(ACCENT))
        self.set_focused(False)

    def pick(self, code: str) -> None:
        for other, item in self._rows.items():
            dpg.set_value(item, other == code)
        self.value = code

    def set_focused(self, focused: bool) -> None:
        """Accent border while the keyboard is in the list."""
        dpg.bind_item_theme(self.box, self._themes[focused])
        if focused and self.value not in self._shown and self._shown:
            self.pick(self._shown[0])

    def move(self, delta: int) -> None:
        if not self._shown:
            return
        index = self._shown.index(self.value) if self.value in self._shown else -delta
        self.pick(self._shown[max(0, min(len(self._shown) - 1, index + delta))])
        self._scroll_into_view()

    def _scroll_into_view(self) -> None:
        item = self._rows[self.value]
        y, row_h = dpg.get_item_pos(item)[1], dpg.get_item_rect_size(item)[1]
        top, visible = dpg.get_y_scroll(self.box), dpg.get_item_rect_size(self.box)[1]
        pad = px(4)
        if y - pad < top:
            dpg.set_y_scroll(self.box, max(0, y - pad))
        elif y + row_h + pad > top + visible:
            dpg.set_y_scroll(self.box, y + row_h + pad - visible)

    def set_enabled(self, enabled: bool) -> None:
        for item in self._rows.values():
            dpg.configure_item(item, enabled=enabled)

    def show_only(self, visible: list[Lang], query: str) -> None:
        codes = {lang.code for lang in visible}
        self._shown = [lang.code for lang in visible]
        for code, item in self._rows.items():
            dpg.configure_item(item, show=code in codes)
        if query.strip():
            dpg.set_y_scroll(self.box, 0)
        else:
            # Positions are stale until the unhidden rows render once.
            dpg.split_frame()
            self.scroll_to_value()

    def scroll_to_value(self) -> None:
        # Needs one rendered frame first: item positions are unknown before it.
        item = self._rows.get(self.value)
        if item is None:
            return
        y = dpg.get_item_pos(item)[1]
        visible = dpg.get_item_rect_size(self.box)[1]
        dpg.set_y_scroll(self.box, max(0, y - visible // 2))


def _combo(choices: list[Choice], value: str, callback) -> int:
    by_label = {choice.label: choice.value for choice in choices}
    current = next(choice.label for choice in choices if choice.value == value)
    return dpg.add_combo(
        list(by_label), default_value=current, width=px(COMBO_W),
        callback=lambda sender, label: callback(by_label[label]),
    )


class _Window:
    def __init__(self, form: InstallForm, install: Installer, bold_font: int | None) -> None:
        self.form = form
        self.answers = form.answers
        self._install = install
        self._idle_input, self._focused_input = _input_themes()
        self._error_theme = _color_theme(Text=ERROR)
        self._normal_theme = _color_theme(Text=(35, 38, 41))
        self._focused: set[int] = set()
        self._picked: str | None = None
        self._picking = False
        self._progress: tuple[str, float] | None = None
        self._failure: str | None = None
        self._worker: threading.Thread | None = None
        self._search_was_active = False
        self._was_typing = False
        # Where the keyboard is beyond ImGui's own text fields: None (the
        # form), "list", or a button item. dpg's ImGui keyboard navigation
        # proved unreliable here (focus_item landing on the next row), so
        # this is done by hand.
        self._keyboard: str | int | None = None
        self.result: Answers | None = None
        self._build(bold_font)

    @contextlib.contextmanager
    def _row(self, label: str):
        # xoffset puts the control at LABEL_W, aligning every row's control.
        with dpg.group(horizontal=True, xoffset=px(LABEL_W)) as group:
            dpg.add_text(label)
            yield group

    def _build(self, bold_font: int | None) -> None:
        a = self.answers
        # The window size is fixed, so blocks are placed at absolute positions:
        # stacked layout adds ImGui's own item spacing between them and
        # inflates a 1px child window to 4px, overflowing the window.
        w, h = px(WIN_W), px(WIN_H)
        header_h, footer_h = px(HEADER_H), px(FOOTER_H)
        content_y = header_h + 1
        footer_y = h - footer_h

        with dpg.window(tag="root", no_scrollbar=True):
            dpg.draw_line((0, header_h), (w, header_h), color=LINE)
            dpg.draw_line((0, footer_y - 1), (w, footer_y - 1), color=LINE)

            with dpg.child_window(pos=(0, 0), width=w, height=header_h, border=False, no_scrollbar=True) as header:
                title = dpg.add_text(i18n.t("form_title"), pos=(px(PAD), px(12)))
                dpg.add_text(i18n.t("form_subtitle"), pos=(px(PAD + 12), px(36)), color=MUTED)
            dpg.bind_item_theme(header, _color_theme(ChildBg=(255, 255, 255)))
            if bold_font is not None:
                dpg.bind_item_font(title, bold_font)

            with dpg.child_window(
                pos=(0, content_y), width=w, height=footer_y - 1 - content_y, border=False, no_scrollbar=True,
                always_use_window_padding=True,
            ) as content:
                with self._row(i18n.t("form_dir")):
                    with dpg.group(horizontal=True):
                        self.dir_input = dpg.add_input_text(
                            default_value=a.install_dir, width=-px(BTN_W + 8),
                            callback=lambda s, value: setattr(a, "install_dir", value),
                        )
                        self.browse = dpg.add_button(label=i18n.t("form_browse"), width=-1, callback=self._on_browse)
                with self._row(i18n.t("form_channel")):
                    self.channel = _combo(self.form.channels, a.channel, lambda v: setattr(a, "channel", v))
                self.profile = None
                if self.form.profiles:
                    with self._row(i18n.t("form_profile")):
                        self.profile = _combo(
                            self.form.profiles, a.profile_dir or "",
                            lambda v: setattr(a, "profile_dir", v or None),
                        )
                with self._row(i18n.t("form_tweaks")):
                    self.tweaks = dpg.add_checkbox(default_value=a.tweaks, callback=self._on_tweaks)
                with self._row(i18n.t("form_theme")) as self.theme_row:
                    self.theme = _combo(self.form.themes, a.theme, lambda v: setattr(a, "theme", v))
                dpg.add_spacer(height=px(4))
                self.search = dpg.add_input_text(
                    hint=i18n.t("form_lang_search"), width=-1,
                    callback=lambda s, query: self.langs.show_only(self.form.filter_langs(query), query),
                )
                self.langs = _LangList(self.form.langs, a.lang)
            dpg.bind_item_theme(content, _padded_theme())

            with dpg.child_window(pos=(0, footer_y), width=w, height=footer_h, border=False, no_scrollbar=True):
                y = (footer_h - px(BTN_H)) // 2
                x_cancel = px(WIN_W - PAD - BTN_W)
                x_install = x_cancel - px(BTN_GAP) - px(BTN_W)
                status_w = x_install - px(PAD) * 2
                self.status = dpg.add_text("", pos=(px(PAD), px(8)), wrap=status_w)
                self.progress = dpg.add_progress_bar(pos=(px(PAD), px(32)), width=status_w, height=px(8), show=False)
                self.install = dpg.add_button(
                    label=i18n.t("wizard_install"), width=px(BTN_W), height=px(BTN_H), pos=(x_install, y),
                    callback=self._on_install,
                )
                self.cancel = dpg.add_button(
                    label=i18n.t("ui_cancel"), width=px(BTN_W), height=px(BTN_H), pos=(x_cancel, y),
                    callback=lambda: dpg.stop_dearpygui(),
                )

        for item in (self.dir_input, self.search):
            dpg.bind_item_theme(item, self._idle_input)
        dpg.configure_item(self.theme_row, show=self.form.theme_applies)
        if self.form.error:
            self._show_error(self.form.error)
            dpg.configure_item(self.install, enabled=False)
        self._button_themes = {
            self.install: (_button_theme(True, False), _button_theme(True, True)),
            self.cancel: (_button_theme(False, False), _button_theme(False, True)),
        }
        self._set_keyboard(None)
        with dpg.handler_registry():
            for key in (dpg.mvKey_Return, dpg.mvKey_NumPadEnter, dpg.mvKey_Up, dpg.mvKey_Down,
                        dpg.mvKey_Left, dpg.mvKey_Right, dpg.mvKey_Tab):
                dpg.add_key_press_handler(key, callback=lambda sender, key: self._on_key(key))
            dpg.add_mouse_click_handler(callback=lambda: self._set_keyboard(None))
        dpg.set_primary_window("root", True)

    def _form_items(self) -> list[int]:
        items = [self.dir_input, self.browse, self.channel, self.tweaks, self.theme, self.search, self.install]
        return items + ([self.profile] if self.profile else [])

    def _show_error(self, text: str) -> None:
        dpg.set_value(self.status, text)
        dpg.bind_item_theme(self.status, self._error_theme)

    def _on_tweaks(self, sender, checked: bool) -> None:
        self.answers.tweaks = checked
        dpg.configure_item(self.theme_row, show=self.form.theme_applies)

    def _on_browse(self) -> None:
        if self._picking:
            return
        self._picking = True
        initial = dpg.get_value(self.dir_input)

        def run() -> None:
            self._picked = portal.pick_directory(i18n.t("form_browse_title"), initial)
            self._picking = False

        threading.Thread(target=run, daemon=True).start()

    def _on_install(self) -> None:
        self.answers.lang = self.langs.value
        error = self.form.validate()
        if error:
            self._show_error(error)
            return
        dpg.set_value(self.dir_input, self.answers.install_dir)
        for item in self._form_items():
            dpg.configure_item(item, enabled=False)
        self.langs.set_enabled(False)
        dpg.bind_item_theme(self.status, self._normal_theme)
        dpg.configure_item(self.progress, show=True)
        self._progress = ("", 0.0)

        def run() -> None:
            try:
                self._install(self.answers, lambda message, fraction: setattr(self, "_progress", (message, fraction)))
            except Exception as exc:  # shown in the window; the user decides what next
                self._failure = str(exc) or type(exc).__name__

        self._worker = threading.Thread(target=run, daemon=True)
        self._worker.start()

    def _buttons(self) -> list[int]:
        return [b for b in (self.install, self.cancel)
                if dpg.get_item_configuration(b)["show"] and dpg.get_item_configuration(b)["enabled"]]

    def _set_keyboard(self, where: str | int | None) -> None:
        self._keyboard = where
        self.langs.set_focused(where == "list")
        for button, (idle, focused) in self._button_themes.items():
            dpg.bind_item_theme(button, focused if where == button else idle)

    def _on_key(self, key: int) -> None:
        enter = key in (dpg.mvKey_Return, dpg.mvKey_NumPadEnter)
        where = self._keyboard
        if (enter or key == dpg.mvKey_Down) and self._search_was_active:
            # Checked against the previous frame: Enter itself ends the edit.
            # Down doesn't, so the field is defocused here.
            self._set_keyboard("list")
            dpg.focus_item(self.langs.box)
        elif where == "list":
            if key in (dpg.mvKey_Up, dpg.mvKey_Down):
                self.langs.move(-1 if key == dpg.mvKey_Up else 1)
            elif enter or key == dpg.mvKey_Tab:
                buttons = self._buttons()
                self._set_keyboard(buttons[0] if buttons else None)
        elif where in self._button_themes:
            buttons = self._buttons()
            if enter:
                (self._on_install if where == self.install else dpg.stop_dearpygui)()
            elif key in (dpg.mvKey_Left, dpg.mvKey_Right, dpg.mvKey_Tab) and where in buttons:
                step = -1 if key == dpg.mvKey_Left else 1
                self._set_keyboard(buttons[(buttons.index(where) + step) % len(buttons)])
            elif key == dpg.mvKey_Up and self._worker is None and self.result is None:
                self._set_keyboard("list")

    def tick(self) -> None:
        """Per-frame work dpg has no event for; runs on the UI thread."""
        # Starting to edit a text field takes the keyboard back to the form.
        typing = dpg.is_item_active(self.search) or dpg.is_item_active(self.dir_input)
        if typing and not self._was_typing and self._keyboard is not None:
            self._set_keyboard(None)
        self._was_typing = typing
        self._search_was_active = dpg.is_item_active(self.search)
        for item in (self.dir_input, self.search):
            active = dpg.is_item_active(item)
            if active != (item in self._focused):
                dpg.bind_item_theme(item, self._focused_input if active else self._idle_input)
                (self._focused.add if active else self._focused.discard)(item)

        if self._picked is not None:
            dpg.set_value(self.dir_input, self._picked)
            self.answers.install_dir = self._picked
            self._picked = None
        if self._worker is None and not self.form.error:
            dpg.configure_item(self.browse, enabled=not self._picking)

        if self._worker is not None:
            if self._progress is not None:
                message, fraction = self._progress
                dpg.set_value(self.status, message)
                dpg.set_value(self.progress, fraction)
            if not self._worker.is_alive():
                self._worker = None
                if not self._failure:
                    self.result = self.answers
                    dpg.stop_dearpygui()  # done: the summary goes to the terminal
                    return
                self._show_error(self._failure)
                dpg.configure_item(self.install, show=False)
                dpg.configure_item(self.cancel, label=i18n.t("form_close"))
                if self._keyboard is not None:
                    self._set_keyboard(self.cancel)


def run(form: InstallForm, install: Installer) -> Answers | None:
    """Shows the form until the user closes it or the install is done; the
    answers if the install went through, None if cancelled or failed."""
    dpg.create_context()
    regular, bold = _load_fonts()
    if regular is not None:
        dpg.bind_font(regular)
    dpg.bind_theme(_global_theme())
    window = _Window(form, install, bold)

    w, h = px(WIN_W), px(WIN_H)
    dpg.create_viewport(
        title="MyFox", width=w, height=h, min_width=w, max_width=w, min_height=h, max_height=h, resizable=False,
        small_icon=str(ASSETS / "icon-48.png"), large_icon=str(ASSETS / "icon-256.png"),
    )
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.render_dearpygui_frame()
    window.langs.scroll_to_value()
    try:
        while dpg.is_dearpygui_running():
            window.tick()
            dpg.render_dearpygui_frame()
    finally:
        dpg.destroy_context()
    return window.result
