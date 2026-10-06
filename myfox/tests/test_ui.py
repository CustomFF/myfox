from __future__ import annotations

import unittest
from unittest import mock

from myfox.ui import _has_tty, get_backend
from myfox.ui.plain_backend import PlainBackend



class HasTtyTests(unittest.TestCase):
    def test_true_only_when_both_stdin_and_stdout_are_a_tty(self):
        with mock.patch("sys.stdin.isatty", return_value=True), \
             mock.patch("sys.stdout.isatty", return_value=True):
            self.assertTrue(_has_tty())
        with mock.patch("sys.stdin.isatty", return_value=True), \
             mock.patch("sys.stdout.isatty", return_value=False):
            self.assertFalse(_has_tty())


class GetBackendTests(unittest.TestCase):
    def test_noninteractive_always_gets_plain(self):
        self.assertIsInstance(get_backend(noninteractive=True), PlainBackend)

    def test_no_tty_falls_back_to_plain(self):
        with mock.patch("myfox.ui._has_tty", return_value=False):
            self.assertIsInstance(get_backend(), PlainBackend)

    def test_interactive_tty_gets_picotui(self):
        with mock.patch("myfox.ui._has_tty", return_value=True):
            from myfox.ui.picotui_backend import PicotuiBackend

            self.assertIsInstance(get_backend(), PicotuiBackend)


if __name__ == "__main__":
    unittest.main()
