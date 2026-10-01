"""Drives the real urwid widget tree via widget.keypress() sequences —
same dispatch MainLoop itself would do (consumed keys stop there, anything
returned unconsumed goes to unhandled_input) — instead of faking urwid's
whole screen/event-loop contract just to test our own callback wiring.
"""

from __future__ import annotations

import unittest
from unittest import mock

from myfox import _vendor
from myfox.ui.urwid_backend import UrwidBackend, urwid

_SIZE = (40, 10)


class _KeyDriver:
    """Stand-in for urwid.MainLoop: .run() feeds `keys` to the widget tree
    one at a time and forwards anything left unconsumed to
    unhandled_input, then suppresses ExitMainLoop the same way the real
    MainLoop.run() does."""

    def __init__(self, widget, palette=None, unhandled_input=None, keys=()):
        self.widget = widget
        self.unhandled_input = unhandled_input
        self.keys = keys

    def run(self) -> None:
        try:
            for key in self.keys:
                rest = self.widget.keypress(_SIZE, key)
                if rest is not None and self.unhandled_input is not None:
                    self.unhandled_input(rest)
        except urwid.ExitMainLoop:
            pass


def _drive(keys):
    return mock.patch(
        "myfox.ui.urwid_backend.urwid.MainLoop",
        lambda widget, **kw: _KeyDriver(widget, keys=keys, **kw),
    )


class VendoringTests(unittest.TestCase):
    def test_ensure_on_path_is_idempotent(self):
        import sys

        _vendor.ensure_on_path()
        _vendor.ensure_on_path()
        self.assertEqual(sys.path.count(_vendor._DIR), 1)

    def test_backend_instantiates(self):
        UrwidBackend()


class ConfirmTests(unittest.TestCase):
    def test_enter_on_default_focus_picks_yes(self):
        with _drive(["enter"]):
            self.assertTrue(UrwidBackend().confirm("Proceed?", default=False))

    def test_moving_right_then_enter_picks_no(self):
        with _drive(["right", "enter"]):
            self.assertFalse(UrwidBackend().confirm("Proceed?", default=True))


class ChooseTests(unittest.TestCase):
    OPTIONS = [("a", "Option A"), ("b", "Option B")]

    def test_enter_on_first_option(self):
        with _drive(["enter"]):
            self.assertEqual(UrwidBackend().choose("Pick one", self.OPTIONS), "a")

    def test_moving_down_then_enter_picks_second_option(self):
        with _drive(["down", "enter"]):
            self.assertEqual(UrwidBackend().choose("Pick one", self.OPTIONS), "b")

    def test_esc_returns_the_default(self):
        with _drive(["esc"]):
            self.assertEqual(UrwidBackend().choose("Pick one", self.OPTIONS, default="a"), "a")

    def test_a_list_longer_than_the_screen_scrolls_instead_of_overflowing(self):
        # Regression: the first cut used Filler(Pile(...)), which has no
        # concept of scrolling — a 170-option list (the real Firefox
        # language picker) would just run off the bottom of the terminal.
        options = [(str(i), f"Option {i}") for i in range(200)]
        with _drive(["down"] * 150 + ["enter"]):
            self.assertEqual(UrwidBackend().choose("Pick one", options), "150")


class InputDirTests(unittest.TestCase):
    def test_typing_appends_at_the_cursor_after_the_prefilled_value(self):
        # Edit() places the cursor at the end of its initial text, same as
        # every plain terminal line editor — there's no "select all" to
        # type over it, so typed keys land after "/opt/firefox".
        with _drive(["/", "t", "m", "p", "enter"]):
            self.assertEqual(UrwidBackend().input_dir("Install where?", "/opt/firefox"), "/opt/firefox/tmp")

    def test_enter_with_no_edits_returns_the_initial_value(self):
        with _drive(["enter"]):
            self.assertEqual(UrwidBackend().input_dir("Install where?", "/opt/firefox"), "/opt/firefox")

    def test_esc_returns_none(self):
        with _drive(["esc"]):
            self.assertIsNone(UrwidBackend().input_dir("Install where?", "/opt/firefox"))


class MessageTests(unittest.TestCase):
    def test_any_key_dismisses_it(self):
        with _drive(["x"]):
            UrwidBackend().message("done")  # must not raise or hang


class SpinTests(unittest.TestCase):
    """Patches urwid.display.raw.Screen, not the urwid.raw_display name
    spin() imports it through — that's a compat alias registered in
    sys.modules under a distinct proxy object (confirmed live), so
    patching it wouldn't touch what `from urwid import raw_display`
    actually returns at call time."""

    def test_starts_and_stops_the_screen_around_the_block(self):
        screen = mock.Mock()
        screen.get_cols_rows.return_value = (40, 10)
        with mock.patch("urwid.display.raw.Screen", return_value=screen):
            with UrwidBackend().spin("Downloading..."):
                pass
        screen.start.assert_called_once()
        screen.draw_screen.assert_called_once()
        screen.stop.assert_called_once()

    def test_stops_the_screen_even_if_the_block_raises(self):
        screen = mock.Mock()
        screen.get_cols_rows.return_value = (40, 10)
        with mock.patch("urwid.display.raw.Screen", return_value=screen):
            with self.assertRaises(RuntimeError):
                with UrwidBackend().spin("Downloading..."):
                    raise RuntimeError("boom")
        screen.stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
