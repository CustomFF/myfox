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
    """Pass 1: every branch resolves to PlainBackend (urwid/dearpygui are
    pass 3/4). These lock in the call contract now so that wiring in a real
    backend later is a deliberate, visible change to these assertions, not
    a silent one."""

    def test_noninteractive_always_gets_plain(self):
        self.assertIsInstance(get_backend(noninteractive=True), PlainBackend)

    def test_force_gui_currently_falls_back_to_plain(self):
        self.assertIsInstance(get_backend(force_gui=True), PlainBackend)

    def test_default_currently_falls_back_to_plain(self):
        self.assertIsInstance(get_backend(), PlainBackend)


if __name__ == "__main__":
    unittest.main()
