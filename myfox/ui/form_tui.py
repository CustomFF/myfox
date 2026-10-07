"""The install form as one picotui dialog on a tty: the same fields as the
GUI, Tab between them, Install/Cancel at the bottom, progress in place of
the status line while installing. All decisions live in
install_form.InstallForm; this only draws it.
"""

from __future__ import annotations

import os
import textwrap
import time
import unicodedata
from pathlib import Path

from .. import i18n
from ..install_form import Answers, Choice, InstallForm, Installer, Lang
from .picotui_backend import BOX_BG, SGR_GRAY_ON_CYAN, SGR_WHITE_ON_GRAY, BoxDialog, ThemedButton, _button_row, _centered, _clear, _ensure_screen, _set_focus

from picotui.defs import (  # noqa: E402 (picotui_backend put it on sys.path)
    KEYMAP, KEY_BACKSPACE, KEY_DOWN, KEY_ENTER, KEY_F5, KEY_F6, KEY_F7, KEY_F8, KEY_F9, KEY_F10, KEY_SHIFT_TAB,
    C_B_BLUE, C_BLACK, C_RED, C_WHITE,
)
from picotui.widgets import (  # noqa: E402
    ACTION_CANCEL, ACTION_NEXT, ACTION_OK, WCheckbox, WDropDown, WFrame, WLabel, WListBox, WTextEntry,
)

_MAX_W, _MAX_H = 78, 24
_COMBO_W = 24


def _single_width(text: str) -> bool:
    """picotui sizes text by len(); wide (CJK) and combining characters
    take a different number of cells and would break the box edge."""
    return all(unicodedata.east_asian_width(ch) not in ("W", "F") and not unicodedata.combining(ch)
               and unicodedata.category(ch) != "Mc" for ch in text)


class _Label(WLabel):
    """Always paints its own colors: after a widget that resets attributes,
    a plain WLabel would be drawn in the terminal's default colors."""

    def __init__(self, text: str, w: int, fg: int = C_BLACK):
        super().__init__(text, w)
        self.fg = fg
        self.hidden = False

    def redraw(self):
        self.goto(self.x, self.y)
        self.attr_color(self.fg, C_WHITE)
        self.wr_fixedw("" if self.hidden else self.t, self.w)
        self.attr_reset()


class _Checkbox(WCheckbox):
    """WCheckbox draws with whatever attributes were left active (and only
    a foreground when focused); this always paints on the box background."""

    def redraw(self):
        self.goto(self.x, self.y)
        self.attr_color(C_B_BLUE if self.focus else C_BLACK, C_WHITE)
        self.wr(("[x] " if self.choice else "[ ] ") + self.t)
        self.attr_reset()


class _Frame(WFrame):
    """A plain box in the dialog's colors (WFrame draws with whatever
    attributes were left active)."""

    def redraw(self):
        self.attr_color(*BOX_BG)
        self.draw_box(self.x, self.y, self.w, self.h)
        self.attr_reset()


class _Entry(WTextEntry):
    """Emits "changed" on edits and shows a hint while empty and unfocused.
    With moves_on, Enter or Down moves on to the next widget."""

    def __init__(self, w: int, text: str, hint: str = "", moves_on: bool = False):
        super().__init__(w, text)
        self.hint = hint
        self.moves_on = moves_on

    def handle_key(self, key):
        if self.moves_on and key in (KEY_ENTER, KEY_DOWN):
            return ACTION_NEXT
        return super().handle_key(key)

    def handle_edit_key(self, key):
        before = self.get()
        res = super().handle_edit_key(key)
        if self.get() != before:
            self.signal("changed")
        return res

    def redraw(self):
        if self.hint and not self.focus and not self.get():
            self.goto(self.x, self.y)
            # Same cyan field as a filled entry, so it reads as an input.
            self.wr(SGR_GRAY_ON_CYAN)
            self.wr_fixedw(self.hint, self.w)
            self.attr_reset()
            return
        super().redraw()


class _Dropdown(WDropDown):
    def __init__(self, choices: list[Choice], value: str):
        super().__init__(_COMBO_W, [choice.label for choice in choices], dropdown_h=len(choices) + 2)
        self.choices = choices
        self.choice = next(i for i, choice in enumerate(choices) if choice.value == value)
        self.disabled = False
        self.hidden = False

    @property
    def value(self) -> str:
        return self.choices[self.choice].value

    def redraw(self):
        if not (self.disabled or self.hidden):
            super().redraw()
            return
        self.goto(self.x, self.y)
        if self.hidden:
            self.attr_color(*BOX_BG)
        else:
            self.wr(SGR_WHITE_ON_GRAY)
        self.wr_fixedw("" if self.hidden else self.items[self.choice], self.w)
        self.attr_reset()

    def handle_mouse(self, x, y):
        if not (self.disabled or self.hidden):
            super().handle_mouse(x, y)

    def handle_key(self, key):
        if not (self.disabled or self.hidden):
            super().handle_key(key)


class _LangList(WListBox):
    def __init__(self, w: int, h: int, langs: list[Lang], default: str):
        self.visible = langs
        super().__init__(w, h, self._labels(langs))
        self._select(default)

    @staticmethod
    def _labels(langs: list[Lang]) -> list[str]:
        return [lang.label(show_native=_single_width(lang.native)) for lang in langs]

    def _select(self, code: str | None) -> None:
        index = next((i for i, lang in enumerate(self.visible) if lang.code == code), 0)
        self.cur_line = self.choice = index
        self.top_line = max(0, index - self.height // 2)
        self.row = self.cur_line - self.top_line

    @property
    def value(self) -> str | None:
        return self.visible[self.cur_line].code if self.visible else None

    def show(self, langs: list[Lang]) -> None:
        current = self.value
        self.visible = langs
        self.set_items(self._labels(langs))
        self._select(current)
        self.redraw()

    def handle_key(self, key):
        # Enter takes the highlighted language and moves on to Install.
        if key == KEY_ENTER:
            return ACTION_NEXT
        return super().handle_key(key)

    def show_line(self, l, i):
        if self.cur_line != i:
            self.attr_color(*BOX_BG)
        super().show_line(l, i)
        self.attr_reset()


# Escape sequences picotui knows: mapped ones plus those it passes on raw.
_SEQUENCES = {
    **{k: v for k, v in KEYMAP.items() if isinstance(k, bytes) and k.startswith(b"\x1b")},
    **{k: k for k in (KEY_SHIFT_TAB, KEY_F5, KEY_F6, KEY_F7, KEY_F8, KEY_F9, KEY_F10)},
}


class _FormDialog(BoxDialog):
    def get_input(self):
        # picotui hands out the first character of a read whole but then
        # takes its leftover buffer one byte at a time, splitting multibyte
        # (e.g. Cyrillic) characters typed or pasted together. And a read
        # starting with ESC is looked up as one key, so two arrows read
        # together (a held key, fast typing) match nothing and are lost.
        if not self.kbuf:
            key = super().get_input()
            if not (isinstance(key, bytes) and key.startswith(b"\x1b") and len(key) > 1 and key not in _SEQUENCES):
                return key
            self.kbuf = key
        buf = self.kbuf
        if buf.startswith(b"\x1b"):
            for n in range(min(len(buf), 8), 1, -1):
                if buf[:n] in _SEQUENCES:
                    self.kbuf = buf[n:]
                    return _SEQUENCES[buf[:n]]
            # Unknown sequence (ctrl+arrow, …): skipped up to the next one.
            end = buf.find(b"\x1b", 1)
            self.kbuf = buf[end:] if end > 0 else b""
            return None if len(buf) > 1 else KEYMAP[b"\x1b"]
        end = buf.find(b"\x1b")
        text, self.kbuf = (buf, b"") if end < 0 else (buf[:end], buf[end:])
        text = text.decode(errors="replace")
        key = text[0].encode()
        self.kbuf = text[1:].encode() + self.kbuf
        return KEYMAP.get(key, key)

    def find_focusable_by_idx(self, from_idx, direction):
        # Tab skips disabled and hidden widgets (the theme without tweaks).
        sz = len(self.childs)
        for _ in range(sz):
            idx, widget = super().find_focusable_by_idx(from_idx, direction)
            if widget is None or not (getattr(widget, "disabled", False) or getattr(widget, "hidden", False)):
                return idx, widget
            from_idx = (idx + direction) % sz
        return None, None


ACTION_OPEN, ACTION_UP = 1100, 1101  # outside picotui's reserved 1000-1003


class _DirList(WListBox):
    """Subdirectories of one directory: Enter opens one, Backspace goes up,
    typing jumps to the first name starting with what was typed."""

    def __init__(self, w: int, h: int, names: list[str]):
        self.names = names
        super().__init__(w, h, [name if name == ".." else name + "/" for name in names])
        self._typed, self._typed_at = "", 0.0

    @property
    def value(self) -> str | None:
        return self.names[self.cur_line] if self.names else None

    def select(self, index: int) -> None:
        self.cur_line = self.choice = index
        self.top_line = max(0, index - self.height // 2)
        self.row = self.cur_line - self.top_line

    def handle_key(self, key):
        if key == KEY_ENTER:
            return ACTION_OPEN if self.names else None
        if key == KEY_BACKSPACE:
            return ACTION_UP
        if isinstance(key, bytes):
            try:
                ch = key.decode()
            except UnicodeDecodeError:
                ch = ""
            if ch.isprintable():
                now = time.monotonic()
                self._typed = (self._typed if now - self._typed_at < 1 else "") + ch.lower()
                self._typed_at = now
                match = next((i for i, name in enumerate(self.names)
                              if name != ".." and name.lower().startswith(self._typed)), None)
                if match is not None:
                    self.select(match)
                    self.redraw()
                return None
        return super().handle_key(key)

    def show_line(self, l, i):
        if self.cur_line != i:
            self.attr_color(*BOX_BG)
        super().show_line(l, i)
        self.attr_reset()


def _subdirs(path: Path) -> list[str]:
    """".." (unless at /), then subdirectories: plain ones, then hidden."""
    try:
        names = sorted(entry.name for entry in os.scandir(path) if entry.is_dir())
    except OSError:
        names = []
    up = [".."] if path.parent != path else []
    return up + [n for n in names if not n.startswith(".")] + [n for n in names if n.startswith(".")]


def _nearest_dir(raw: str) -> Path:
    path = Path(os.path.expanduser(raw.strip() or "~"))
    if not path.is_absolute():
        path = Path.home()
    while not path.is_dir():
        path = path.parent
    return path


def pick_dir(start: str, title: str) -> str | None:
    """A directory chooser dialog, starting from the nearest existing
    directory of `start`. Returns the chosen path, None on cancel."""
    from picotui.screen import Screen

    cur, came_from = _nearest_dir(start), None
    cols, rows = Screen.screen_size()
    w, h = min(_MAX_W - 8, cols - 4), min(_MAX_H - 4, rows - 2)
    while True:
        x, y = _centered(w, h)
        d = _FormDialog(x, y, w, h, title=title)
        shown = str(cur) if len(str(cur)) <= w - 4 else "…" + str(cur)[-(w - 5):]
        d.add(2, 1, _Label(shown, w - 4))
        names = _subdirs(cur)
        dirs = _DirList(w - 4, h - 5, names)
        d.add(2, 2, dirs)
        if came_from in names:
            dirs.select(names.index(came_from))
        select_btn = ThemedButton(max(12, len(i18n.t("form_select")) + 4), i18n.t("form_select"))
        select_btn.finish_dialog = ACTION_OK
        cancel_btn = ThemedButton(max(12, len(i18n.t("ui_cancel")) + 4), i18n.t("ui_cancel"))
        cancel_btn.finish_dialog = ACTION_CANCEL
        _button_row(d, w, h - 2, [select_btn, cancel_btn])
        _set_focus(d, dirs)

        res = d.loop()
        if res == ACTION_OK:
            return str(cur)
        if res == ACTION_OPEN and dirs.value != "..":
            cur, came_from = cur / dirs.value, None
        elif res in (ACTION_OPEN, ACTION_UP) and cur.parent != cur:
            cur, came_from = cur.parent, cur.name
        elif res not in (ACTION_OPEN, ACTION_UP):
            return None


def _bar(fraction: float, width: int) -> str:
    filled = round(fraction * (width - 7))
    return f"[{'#' * filled}{'-' * (width - 7 - filled)}] {round(fraction * 100):3d}%"


def run(form: InstallForm, install: Installer) -> Answers | None:
    """Shows the form until the user leaves it; the answers if the install
    went through, None if cancelled or failed."""
    from picotui.screen import Screen

    _ensure_screen()
    a = form.answers
    cols, rows = Screen.screen_size()
    w, h = min(_MAX_W, cols - 2), min(_MAX_H, rows - 1)
    x, y = _centered(w, h)
    _clear()
    d = _FormDialog(x, y, w, h, title=i18n.t("form_title"))

    labels = [i18n.t(k) for k in ("form_dir", "form_channel", "form_profile", "form_tweaks", "form_theme")]
    ctrl_x = 2 + max(len(label) for label in labels) + 2
    ctrl_w = w - ctrl_x - 2
    row = 1

    def add_row(label_key: str, widget, gap: int = 0) -> _Label:
        nonlocal row
        label = _Label(i18n.t(label_key), ctrl_x - 2)
        d.add(2, row, label)
        d.add(ctrl_x, row, widget)
        row += 1 + gap
        return label

    browse_label = i18n.t("form_browse")
    browse_btn = ThemedButton(len(browse_label) + 4, browse_label)
    dir_entry = _Entry(ctrl_w - browse_btn.w - 1, a.install_dir)
    dir_row = row
    add_row("form_dir", dir_entry, gap=1)
    d.add(ctrl_x + ctrl_w - browse_btn.w, dir_row, browse_btn)
    channel = _Dropdown(form.channels, a.channel)
    add_row("form_channel", channel, gap=1)
    profile = None
    if form.profiles:
        profile = _Dropdown(form.profiles, a.profile_dir or "")
        add_row("form_profile", profile, gap=1)
    tweaks = _Checkbox("", choice=a.tweaks)
    add_row("form_tweaks", tweaks)
    theme = _Dropdown(form.themes, a.theme)
    theme_label = add_row("form_theme", theme)
    theme.hidden = theme_label.hidden = not form.theme_applies
    row += 1

    search = _Entry(w - 4, "", hint=i18n.t("form_lang_search"), moves_on=True)
    d.add(2, row, search)
    row += 1
    frame_h = max(5, h - row - 5)
    d.add(2, row, _Frame(w - 4, frame_h))
    langs = _LangList(w - 6, frame_h - 2, form.langs, a.lang)
    d.add(3, row + 1, langs)

    status = _Label("", w - 4)
    bar = _Label("", w - 4)
    d.add(2, h - 4, status)
    d.add(2, h - 3, bar)

    def set_error(text: str) -> None:
        # Two lines: the bar's row is free until the install starts.
        lines = textwrap.wrap(text, w - 4, max_lines=2, placeholder="…") or [""]
        status.t, bar.t = lines[0], lines[1] if len(lines) > 1 else ""
        status.fg = bar.fg = C_RED

    def show_error(text: str) -> None:
        set_error(text)
        status.redraw()
        bar.redraw()

    if form.error:
        set_error(form.error)
    install_btn = ThemedButton(max(12, len(i18n.t("wizard_install")) + 4), i18n.t("wizard_install"))
    install_btn.finish_dialog = ACTION_OK
    cancel_btn = ThemedButton(max(12, len(i18n.t("ui_cancel")) + 4), i18n.t("ui_cancel"))
    cancel_btn.finish_dialog = ACTION_CANCEL
    install_btn.disabled = bool(form.error)
    _button_row(d, w, h - 2, [install_btn, cancel_btn])

    def on_tweaks(widget) -> None:
        a.tweaks = widget.choice
        theme.hidden = theme_label.hidden = not form.theme_applies
        theme.redraw()
        theme_label.redraw()

    def on_browse(widget) -> None:
        picked = pick_dir(dir_entry.get(), i18n.t("form_browse_title"))
        if picked:
            dir_entry.set(picked)
            dir_entry.col = len(picked)
            dir_entry.adjust_cursor_eol()
        _clear()
        d.redraw()

    tweaks.on("changed", on_tweaks)
    browse_btn.on("click", on_browse)
    search.on("changed", lambda widget: langs.show(form.filter_langs(widget.get())))

    while True:
        if d.loop() != ACTION_OK:
            return None
        if form.error:
            continue
        a.install_dir = dir_entry.get()
        a.channel = channel.value
        a.profile_dir = (profile.value or None) if profile else None
        a.theme = theme.value
        a.lang = langs.value or a.lang
        error = form.validate()
        if error is None:
            break
        show_error(error)

    dir_entry.set(a.install_dir)
    status.fg = bar.fg = C_BLACK

    def progress(message: str, fraction: float) -> None:
        status.t, bar.t = message, _bar(fraction, w - 4)
        status.redraw()
        bar.redraw()

    install_btn.disabled = True
    install_btn.redraw()
    result: Answers | None = a
    try:
        install(a, progress)
    except Exception as exc:  # shown in the form; the user decides what next
        show_error(str(exc) or type(exc).__name__)
        result = None

    # One button left: Close.
    d.childs.remove(install_btn)
    d.childs.remove(cancel_btn)
    close_btn = ThemedButton(max(12, len(i18n.t("form_close")) + 4), i18n.t("form_close"))
    close_btn.finish_dialog = ACTION_OK
    _button_row(d, w, h - 2, [close_btn])
    d.focus_idx, d.focus_w = d.childs.index(close_btn), close_btn
    for widget in d.childs:
        widget.focus = widget is close_btn
        if widget is not close_btn:
            widget.disabled = True  # nothing left to edit; Tab stays on Close
    d.loop()
    return result
