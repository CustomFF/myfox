from __future__ import annotations

import unittest
from unittest import mock

from myfox.ui import _has_display, _has_tty, get_backend
from myfox.ui.plain_backend import PlainBackend


class HasTtyTests(unittest.TestCase):
    def test_true_only_when_both_stdin_and_stdout_are_a_tty(self):
        with mock.patch("sys.stdin.isatty", return_value=True), \
             mock.patch("sys.stdout.isatty", return_value=True):
            self.assertTrue(_has_tty())
        with mock.patch("sys.stdin.isatty", return_value=True), \
             mock.patch("sys.stdout.isatty", return_value=False):
            self.assertFalse(_has_tty())


class HasDisplayTests(unittest.TestCase):
    def test_true_with_x11_display(self):
        with mock.patch.dict("os.environ", {"DISPLAY": ":0"}, clear=True):
            self.assertTrue(_has_display())

    def test_true_with_wayland_display(self):
        with mock.patch.dict("os.environ", {"WAYLAND_DISPLAY": "wayland-0"}, clear=True):
            self.assertTrue(_has_display())

    def test_false_with_neither(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertFalse(_has_display())


class GetBackendTests(unittest.TestCase):
    """dearpygui is pass 4 — force_gui and a tty-less run with a display
    still fall back to plain until then; that assertion will need a
    deliberate update once pass 4 lands, not a silent behavior change."""

    def test_noninteractive_always_gets_plain(self):
        self.assertIsInstance(get_backend(noninteractive=True), PlainBackend)

    def test_force_gui_currently_falls_back_to_plain(self):
        self.assertIsInstance(get_backend(force_gui=True), PlainBackend)

    def test_no_tty_no_display_falls_back_to_plain(self):
        with mock.patch("myfox.ui._has_tty", return_value=False), \
             mock.patch("myfox.ui._has_display", return_value=False):
            self.assertIsInstance(get_backend(), PlainBackend)

    def test_interactive_tty_gets_picotui(self):
        with mock.patch("myfox.ui._has_tty", return_value=True):
            from myfox.ui.picotui_backend import PicotuiBackend

            self.assertIsInstance(get_backend(), PicotuiBackend)


if __name__ == "__main__":
    unittest.main()
