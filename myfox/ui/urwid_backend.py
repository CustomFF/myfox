"""urwid-based terminal backend — real dialogs instead of plain
input()/print(), used whenever stdin+stdout are both a tty (see
ui/__init__.py's get_backend()).

Each Backend method runs its own short-lived urwid MainLoop for just that
one dialog — the same call shape as the old per-widget dialog/whiptail
wrappers in lib/tui.sh, not one long-lived screen spanning the whole
wizard (wizard.py calls these one at a time; see its own TODO for the
page-stack design that will eventually sit on top of this).
"""

from __future__ import annotations

import contextlib
from typing import Sequence

from .. import _vendor

_vendor.ensure_on_path()

import urwid  # noqa: E402 (must follow ensure_on_path())

_PALETTE = [("selected", "standout", "")]


class UrwidBackend:
    def confirm(self, prompt: str, default: bool = True) -> bool:
        answer = {"value": default}

        def pick(value: bool) -> None:
            answer["value"] = value
            raise urwid.ExitMainLoop()

        yes = urwid.Button("Yes")
        no = urwid.Button("No")
        urwid.connect_signal(yes, "click", lambda _b: pick(True))
        urwid.connect_signal(no, "click", lambda _b: pick(False))
        buttons = urwid.Columns(
            [("pack", urwid.AttrMap(yes, None, "selected")), ("pack", urwid.AttrMap(no, None, "selected"))],
            dividechars=2,
        )
        pile = urwid.Pile([urwid.Text(prompt), urwid.Divider(), buttons])
        pile.focus_position = 2
        urwid.MainLoop(urwid.Filler(pile), palette=_PALETTE).run()
        return answer["value"]

    def choose(self, header: str, options: Sequence[tuple[str, str]], default: str | None = None) -> str | None:
        """ListBox, not Pile+Filler: options can run into the hundreds
        (the Firefox language picker is ~170) and a Pile doesn't scroll —
        it would just overflow the screen past terminal height."""
        answer: dict[str, str | None] = {"value": default}

        def pick(value: str) -> None:
            answer["value"] = value
            raise urwid.ExitMainLoop()

        buttons = []
        for value, label in options:
            button = urwid.Button(label)
            urwid.connect_signal(button, "click", lambda _b, v=value: pick(v))
            buttons.append(urwid.AttrMap(button, None, "selected"))
        listbox = urwid.ListBox(urwid.SimpleFocusListWalker(buttons))
        frame = urwid.Frame(listbox, header=urwid.Pile([urwid.Text(header), urwid.Divider()]))

        def unhandled(key: str) -> None:
            if key == "esc":
                raise urwid.ExitMainLoop()

        urwid.MainLoop(frame, palette=_PALETTE, unhandled_input=unhandled).run()
        return answer["value"]

    def input_dir(self, prompt: str, initial: str) -> str | None:
        answer: dict[str, str | None] = {"value": None}
        edit = urwid.Edit(f"{prompt}\n", initial)

        def unhandled(key: str) -> None:
            if key == "enter":
                answer["value"] = edit.edit_text or initial
                raise urwid.ExitMainLoop()
            if key == "esc":
                raise urwid.ExitMainLoop()

        urwid.MainLoop(urwid.Filler(edit), palette=_PALETTE, unhandled_input=unhandled).run()
        return answer["value"]

    def message(self, text: str) -> None:
        def unhandled(key: str) -> None:
            raise urwid.ExitMainLoop()

        pile = urwid.Pile([urwid.Text(text), urwid.Divider(), urwid.Text("(press any key)")])
        urwid.MainLoop(urwid.Filler(pile), palette=_PALETTE, unhandled_input=unhandled).run()

    @contextlib.contextmanager
    def spin(self, title: str):
        """No MainLoop here: the caller's own blocking work runs inside the
        `with` block, so nothing can pump urwid's event loop concurrently.
        One static frame drawn directly via the Screen, not animated —
        matches PlainBackend's own plain "print the title" depth for now."""
        from urwid import raw_display

        screen = raw_display.Screen()
        screen.start()
        try:
            widget = urwid.Filler(urwid.Text(title, align="center"))
            size = screen.get_cols_rows()
            screen.draw_screen(size, widget.render(size))
            yield
        finally:
            screen.stop()
