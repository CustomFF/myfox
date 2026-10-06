"""Drives the real picotui form with a scripted key sequence (see
test_picotui_backend.py for the approach); only key reading and terminal
output are stubbed."""

from __future__ import annotations

import contextlib
import tempfile
import unittest
from unittest import mock

from myfox.install_form import InstallForm, Lang
from myfox.ui import form_tui
from myfox.ui.picotui_backend import Dialog, Screen
from picotui.defs import KEY_DOWN, KEY_ENTER, KEY_ESC, KEY_SHIFT_TAB, KEY_TAB

LANGS = [Lang("en-US", "English (US)", "English (US)"), Lang("ru", "Russian", "Русский")]
TO_INSTALL = [KEY_SHIFT_TAB, KEY_SHIFT_TAB]  # from the first field, backwards past Cancel


@contextlib.contextmanager
def _drive(keys):
    keys = list(keys)

    def get_input(self):
        assert keys, "ran out of scripted keys — a real run would have blocked on input here"
        return keys.pop(0)

    with mock.patch.object(Dialog, "get_input", get_input), \
         mock.patch.object(Screen, "screen_size", return_value=(80, 24)), \
         mock.patch.object(Screen, "wr"), \
         mock.patch("myfox.ui.form_tui._ensure_screen"):
        yield


class FormTuiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.form = InstallForm(langs=LANGS, profiles=[])
        self.form.answers.install_dir = self._tmp.name
        self.form.answers.lang = "en-US"
        self.installed = []

    def install(self, answers, progress):
        progress("working", 0.5)
        self.installed.append(answers)

    def test_install_with_defaults(self):
        with _drive(TO_INSTALL + [KEY_ENTER, KEY_ENTER]):
            answers = form_tui.run(self.form, self.install)
        self.assertEqual(self.installed, [answers])
        self.assertEqual((answers.channel, answers.lang, answers.tweaks, answers.theme), ("stable", "en-US", True, "dark"))

    def test_escape_cancels_without_installing(self):
        with _drive([KEY_ESC]):
            self.assertIsNone(form_tui.run(self.form, self.install))
        self.assertEqual(self.installed, [])

    def test_search_narrows_the_list_and_picks_the_match(self):
        # dir -> channel -> tweaks -> theme -> search, type, -> list -> Install
        keys = [KEY_TAB] * 4 + [b"r", b"u", b"s", b"s"] + [KEY_TAB, KEY_TAB, KEY_ENTER, KEY_ENTER]
        with _drive(keys):
            answers = form_tui.run(self.form, self.install)
        self.assertEqual(answers.lang, "ru")

    def test_enter_walks_search_list_install(self):
        # Enter in search -> list; Down moves English -> Russian; Enter -> Install; Enter presses it.
        keys = [KEY_TAB] * 4 + [KEY_ENTER, KEY_DOWN, KEY_ENTER, KEY_ENTER, KEY_ENTER]
        with _drive(keys):
            answers = form_tui.run(self.form, self.install)
        self.assertEqual(answers.lang, "ru")
        self.assertEqual(len(self.installed), 1)

    def test_unticking_tweaks_disables_and_skips_the_theme(self):
        # dir -> channel -> tweaks, Space; then Tab must jump past theme to search.
        keys = [KEY_TAB, KEY_TAB, b" ", KEY_TAB, KEY_TAB, KEY_TAB, KEY_ENTER, KEY_ENTER]
        with _drive(keys):
            answers = form_tui.run(self.form, self.install)
        self.assertFalse(answers.tweaks)

    def test_invalid_dir_stays_on_the_form(self):
        keys = [b"x"] + TO_INSTALL + [KEY_ENTER, KEY_ESC]  # "x" replaces the path: relative
        with _drive(keys):
            self.assertIsNone(form_tui.run(self.form, self.install))
        self.assertEqual(self.installed, [])

    def test_mozilla_error_refuses_to_install(self):
        form = InstallForm(langs=[], profiles=[], error="no network")
        with _drive(TO_INSTALL + [KEY_ENTER, KEY_ESC]):
            self.assertIsNone(form_tui.run(form, self.install))
        self.assertEqual(self.installed, [])

    def test_typed_together_cyrillic_is_split_into_whole_characters(self):
        dialog = form_tui._FormDialog(0, 0, 10, 5)
        dialog.kbuf = "ус".encode()
        self.assertEqual([dialog.get_input(), dialog.get_input()], ["у".encode(), "с".encode()])
        self.assertEqual(dialog.kbuf, b"")

    def test_failed_install_returns_none(self):
        def failing(answers, progress):
            raise RuntimeError("disk full")

        with _drive(TO_INSTALL + [KEY_ENTER, KEY_ENTER]):
            self.assertIsNone(form_tui.run(self.form, failing))


if __name__ == "__main__":
    unittest.main()
