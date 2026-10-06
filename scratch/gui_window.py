"""Test window for the future dearpygui wizard: the whole wizard as one
fixed-size form, Install/Cancel at the bottom. The install itself is
simulated. Not wired into myfox.ui yet.

    PYTHONPATH=<dir with an unpacked dearpygui wheel> python3 scratch/gui_window.py
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

import dearpygui.dearpygui as dpg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from myfox import firefox, i18n  # noqa: E402
from myfox.ui import portal  # noqa: E402

ASSETS = ROOT / "myfox" / "ui" / "assets"

# Logical (96 dpi) pixels; everything is multiplied by SCALE.
WIN_W, WIN_H = 600, 480
HEADER_H = 64
FOOTER_H = 52
PAD = 16
BTN_W, BTN_H = 96, 28
LABEL_W = 110
BTN_GAP = 8
FONT_PT = 10

ACCENT = (61, 174, 233)
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


def load_fonts() -> tuple[int | None, int | None]:
    regular, bold = _font_file("sans-serif"), _font_file("sans-serif:bold")
    size = round(FONT_PT * DPI / 72)
    fonts = []
    with dpg.font_registry():
        for path, extra in ((regular, 0), (bold, 2)):
            if path is None:
                fonts.append(None)
                continue
            # Glyph ranges (Cyrillic included) are picked automatically.
            fonts.append(dpg.add_font(path, size + extra))
    return fonts[0], fonts[1]


def global_theme() -> int:
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvAll):
            for col, rgb in (
                (dpg.mvThemeCol_WindowBg, (239, 240, 241)),
                (dpg.mvThemeCol_ChildBg, (239, 240, 241)),
                (dpg.mvThemeCol_PopupBg, (255, 255, 255)),
                (dpg.mvThemeCol_Text, (35, 38, 41)),
                (dpg.mvThemeCol_TextDisabled, (112, 125, 138)),
                (dpg.mvThemeCol_Border, FRAME_BORDER),
                (dpg.mvThemeCol_BorderShadow, (0, 0, 0, 0)),
                (dpg.mvThemeCol_Separator, (205, 207, 208)),
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


def header_theme() -> int:
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (255, 255, 255))
    return theme


def padded_theme() -> int:
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, px(PAD), px(PAD))
    return theme


def list_theme() -> int:
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (255, 255, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg, (255, 255, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Border, FRAME_BORDER)
            dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 1)
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, px(4), px(4))
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 0, 0)
    return theme


def primary_button_theme() -> int:
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button, ACCENT)
            dpg.add_theme_color(dpg.mvThemeCol_Border, ACCENT)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (89, 188, 239))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (41, 150, 207))
            dpg.add_theme_color(dpg.mvThemeCol_Text, (255, 255, 255))
    return theme


def input_themes() -> tuple[int, int]:
    """(idle, focused): the usual faint outline, the accent one while typing."""
    themes = []
    for border, color in ((1, FRAME_BORDER), (1, ACCENT)):
        with dpg.theme() as theme:
            with dpg.theme_component(dpg.mvInputText):
                dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, border)
                dpg.add_theme_color(dpg.mvThemeCol_Border, color)
        themes.append(theme)
    return themes[0], themes[1]


def _renderable(text: str) -> bool:
    """Latin, Greek and Cyrillic only — what the system sans font carries.
    dpg loads one font file with no fallback chain, so other scripts would
    render as replacement boxes."""
    return all(ord(ch) < 0x0530 or 0x1E00 <= ord(ch) <= 0x206F for ch in text)


def lang_options() -> tuple[list[tuple[str, str, str]], str]:
    """[(code, label, search haystack)], default code. Raises OSError when
    Mozilla is unreachable — then Firefox can't be downloaded either."""
    names = firefox.fetch_lang_names()
    options = []
    for code, (english, native) in sorted(names.items(), key=lambda item: item[1][0]):
        shown = native != english and _renderable(native)
        label = f"{native} — {english} ({code})" if shown else f"{english} ({code})"
        options.append((code, label, f"{english} {native} {code}".lower()))
    return options, firefox.pick_lang({code: english for code, (english, _native) in names.items()})


class SelectList:
    """Single-choice list on selectables — dpg's listbox can't scroll to
    its selected row, and a default buried in 172 languages must be visible."""

    def __init__(self, options: list[tuple[str, str, str]], default: str | None, height: int) -> None:
        self.value = default
        self._rows: dict[str, int] = {}
        self._haystacks = {value: haystack for value, _label, haystack in options}
        with dpg.child_window(height=height, border=True, always_use_window_padding=True) as self.box:
            for value, label, _haystack in options:
                self._rows[value] = dpg.add_selectable(
                    label=label, default_value=value == default, user_data=value, callback=self._pick,
                )
        dpg.bind_item_theme(self.box, list_theme())

    def _pick(self, sender, app_data, value) -> None:
        for v, item in self._rows.items():
            dpg.set_value(item, v == value)
        self.value = value

    def set_enabled(self, enabled: bool) -> None:
        for item in self._rows.values():
            dpg.configure_item(item, enabled=enabled)

    def filter(self, query: str) -> None:
        query = query.strip().lower()
        for value, item in self._rows.items():
            dpg.configure_item(item, show=query in self._haystacks[value])
        if query:
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


class FakeInstall:
    """Stands in for the real install: (status, fraction) over time."""

    FIREFOX_MB = 82.0
    STAGES = (
        ("progress_firefox_download", 4.0),
        ("progress_firefox_install", 2.0),
        ("progress_tweaks_styles_download", 1.0),
        ("progress_tweaks_styles_unpack", 0.6),
        ("progress_tweaks_themes_download", 1.0),
        ("progress_tweaks_addons", 1.0),
    )

    def __init__(self) -> None:
        self._start = time.monotonic()
        self._total = sum(seconds for _label, seconds in self.STAGES)

    def poll(self) -> tuple[str, float, bool]:
        elapsed = time.monotonic() - self._start
        if elapsed >= self._total:
            return i18n.t("progress_done"), 1.0, True
        offset = 0.0
        for key, seconds in self.STAGES:
            if elapsed < offset + seconds:
                if key == "progress_firefox_download":
                    mb = self.FIREFOX_MB * (elapsed - offset) / seconds
                    label = i18n.t(key, f"{mb:.1f}", f"{self.FIREFOX_MB:.0f}")
                else:
                    label = i18n.t(key)
                return label, elapsed / self._total, False
            offset += seconds
        return "", 1.0, True


class App:
    def __init__(self, bold_font: int | None) -> None:
        self._idle_input, self._focused_input = input_themes()
        self._focused: set[int] = set()
        self._picked: str | None = None
        self._picking = False
        self._install: FakeInstall | None = None
        # Combos show translated labels; the answers are the wizard's codes.
        self._channels = {i18n.t("wizard_channel_stable"): "stable", i18n.t("wizard_channel_beta"): "beta"}
        self._themes = {i18n.t("wizard_theme_dark"): "dark", i18n.t("wizard_theme_light"): "light"}
        self._build(bold_font)

    def _build(self, bold_font: int | None) -> None:
        try:
            langs, default_lang = lang_options()
            fetch_error = None
        except OSError as exc:
            langs, default_lang, fetch_error = [], None, exc

        # The window size is fixed, so blocks are placed at absolute positions:
        # stacked layout adds ImGui's own item spacing between them and
        # inflates a 1px child window to 4px, overflowing the window.
        w, h = px(WIN_W), px(WIN_H)
        header_h, footer_h = px(HEADER_H), px(FOOTER_H)
        content_y = header_h + 1
        footer_y = h - footer_h

        with dpg.window(tag="root", no_scrollbar=True):
            dpg.draw_line((0, header_h), (w, header_h), color=(205, 207, 208))
            dpg.draw_line((0, footer_y - 1), (w, footer_y - 1), color=(205, 207, 208))

            with dpg.child_window(pos=(0, 0), width=w, height=header_h, border=False, no_scrollbar=True) as header:
                title = dpg.add_text(i18n.t("gui_title"), pos=(px(PAD), px(12)))
                dpg.add_text(i18n.t("gui_subtitle"), pos=(px(PAD + 12), px(36)), color=(112, 125, 138))
            dpg.bind_item_theme(header, header_theme())
            if bold_font is not None:
                dpg.bind_item_font(title, bold_font)

            with dpg.child_window(
                pos=(0, content_y), width=w, height=footer_y - 1 - content_y, border=False, no_scrollbar=True,
                always_use_window_padding=True,
            ) as content:
                with dpg.group(horizontal=True, xoffset=px(LABEL_W)):
                    dpg.add_text(i18n.t("gui_dir"))
                    with dpg.group(horizontal=True):
                        self.dir_input = dpg.add_input_text(
                            default_value=str(Path.home() / ".local" / "share" / "firefox"), width=-px(BTN_W + 8),
                        )
                        self.browse = dpg.add_button(label=i18n.t("gui_browse"), width=-1, callback=self._on_browse)
                with dpg.group(horizontal=True, xoffset=px(LABEL_W)):
                    dpg.add_text(i18n.t("gui_channel"))
                    self.channel = dpg.add_combo(
                        list(self._channels), default_value=i18n.t("wizard_channel_stable"), width=px(220),
                    )
                with dpg.group(horizontal=True, xoffset=px(LABEL_W)):
                    dpg.add_spacer()
                    self.tweaks = dpg.add_checkbox(
                        label=i18n.t("gui_tweaks"), default_value=True,
                        callback=lambda s, checked: dpg.configure_item(self.theme, enabled=checked),
                    )
                with dpg.group(horizontal=True, xoffset=px(LABEL_W)):
                    dpg.add_text(i18n.t("gui_theme"))
                    self.theme = dpg.add_combo(
                        list(self._themes), default_value=i18n.t("wizard_theme_dark"), width=px(220),
                    )
                dpg.add_spacer(height=px(4))
                self.search = dpg.add_input_text(
                    hint=i18n.t("gui_lang_search"), width=-1,
                    callback=lambda s, query: self.langs.filter(query),
                )
                self.langs = SelectList(langs, default_lang, height=-1)
            dpg.bind_item_theme(content, padded_theme())

            with dpg.child_window(pos=(0, footer_y), width=w, height=footer_h, border=False, no_scrollbar=True):
                y = (footer_h - px(BTN_H)) // 2
                x_cancel = px(WIN_W - PAD - BTN_W)
                x_install = x_cancel - px(BTN_GAP) - px(BTN_W)
                status_w = x_install - px(PAD) * 2
                self.status = dpg.add_text("", pos=(px(PAD), px(8)), show=False)
                self.progress = dpg.add_progress_bar(
                    pos=(px(PAD), px(32)), width=status_w, height=px(8), show=False,
                )
                self.install = dpg.add_button(
                    label=i18n.t("wizard_install"), width=px(BTN_W), height=px(BTN_H), pos=(x_install, y),
                    callback=self._on_install,
                )
                dpg.bind_item_theme(self.install, primary_button_theme())
                self.cancel = dpg.add_button(
                    label=i18n.t("ui_cancel"), width=px(BTN_W), height=px(BTN_H), pos=(x_cancel, y),
                    callback=lambda: dpg.stop_dearpygui(),
                )

        for item in (self.dir_input, self.search):
            dpg.bind_item_theme(item, self._idle_input)
        if fetch_error is not None:
            dpg.set_value(self.status, i18n.t("err_mozilla_unreachable", getattr(fetch_error, "reason", fetch_error)))
            dpg.configure_item(self.status, show=True, color=(218, 68, 83), wrap=status_w)
            dpg.configure_item(self.install, enabled=False)
        dpg.set_primary_window("root", True)

    def _on_browse(self) -> None:
        if self._picking:
            return
        self._picking = True
        initial = dpg.get_value(self.dir_input)

        def run() -> None:
            self._picked = portal.pick_directory(i18n.t("gui_browse_title"), initial)
            self._picking = False

        threading.Thread(target=run, daemon=True).start()

    def _on_install(self) -> None:
        for item in (self.dir_input, self.browse, self.channel, self.tweaks, self.theme, self.search, self.install):
            dpg.configure_item(item, enabled=False)
        self.langs.set_enabled(False)
        dpg.configure_item(self.status, show=True)
        dpg.configure_item(self.progress, show=True)
        self._install = FakeInstall()
        print("install:", dpg.get_value(self.dir_input), self._channels[dpg.get_value(self.channel)],
              self.langs.value, dpg.get_value(self.tweaks), self._themes[dpg.get_value(self.theme)], flush=True)

    def tick(self) -> None:
        """Per-frame work dpg has no event for; runs on the UI thread."""
        for item in (self.dir_input, self.search):
            active = dpg.is_item_active(item)
            if active != (item in self._focused):
                dpg.bind_item_theme(item, self._focused_input if active else self._idle_input)
                (self._focused.add if active else self._focused.discard)(item)

        if self._picked is not None:
            dpg.set_value(self.dir_input, self._picked)
            self._picked = None
        dpg.configure_item(self.browse, enabled=not self._picking and self._install is None)

        if self._install is not None:
            label, fraction, done = self._install.poll()
            dpg.set_value(self.status, label)
            dpg.set_value(self.progress, fraction)
            if done:
                self._install = None
                dpg.configure_item(self.install, show=False)
                dpg.configure_item(self.cancel, label=i18n.t("gui_close"))


def main() -> None:
    dpg.create_context()
    regular, bold = load_fonts()
    if regular is not None:
        dpg.bind_font(regular)
    dpg.bind_theme(global_theme())
    app = App(bold)

    w, h = px(WIN_W), px(WIN_H)
    dpg.create_viewport(
        title="MyFox", width=w, height=h, min_width=w, max_width=w, min_height=h, max_height=h, resizable=False,
        small_icon=str(ASSETS / "icon-48.png"), large_icon=str(ASSETS / "icon-256.png"),
    )
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.render_dearpygui_frame()
    app.langs.scroll_to_value()
    print(f"dpi={DPI} scale={SCALE:.2f}", flush=True)
    while dpg.is_dearpygui_running():
        app.tick()
        dpg.render_dearpygui_frame()
    print("lang:", app.langs.value)
    dpg.destroy_context()


if __name__ == "__main__":
    main()
