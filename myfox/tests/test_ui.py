from __future__ import annotations

import unittest
from unittest import mock

from myfox.ui import _has_tty


class HasTtyTests(unittest.TestCase):
    def test_true_only_when_both_stdin_and_stdout_are_a_tty(self):
        with mock.patch("sys.stdin.isatty", return_value=True), \
             mock.patch("sys.stdout.isatty", return_value=True):
            self.assertTrue(_has_tty())
        with mock.patch("sys.stdin.isatty", return_value=True), \
             mock.patch("sys.stdout.isatty", return_value=False):
            self.assertFalse(_has_tty())
