"""Drives the real picotui form with a scripted key sequence (see
test_picotui_backend.py for the approach); only key reading and terminal
output are stubbed."""

from __future__ import annotations

import contextlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from myfox.install_form import InstallForm, Lang
from myfox.ui import form_tui
from myfox.ui.picotui_backend import Dialog, Screen
from picotui.defs import KEY_BACKSPACE, KEY_DOWN, KEY_ENTER, KEY_ESC, KEY_SHIFT_TAB, KEY_TAB

LANGS = [Lang("en-US", "English (US)", "English (US)"), Lang("ru", "Russian", "Русский")]
TO_INSTALL = [KEY_SHIFT_TAB, KEY_SHIFT_TAB]  # from the first field, backwards past Cancel
TO_INSTALL_FROM_BROWSE = [KEY_SHIFT_TAB] * 3  # Browse -> dir -> Cancel -> Install


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
        # dir -> browse -> channel -> tweaks -> theme -> search, type, -> list -> Install
        keys = [KEY_TAB] * 5 + [b"r", b"u", b"s", b"s"] + [KEY_TAB, KEY_TAB, KEY_ENTER, KEY_ENTER]
        with _drive(keys):
            answers = form_tui.run(self.form, self.install)
        self.assertEqual(answers.lang, "ru")

    def test_enter_walks_search_list_install(self):
        # Enter in search -> list; Down moves English -> Russian; Enter -> Install; Enter presses it.
        keys = [KEY_TAB] * 5 + [KEY_ENTER, KEY_DOWN, KEY_ENTER, KEY_ENTER, KEY_ENTER]
        with _drive(keys):
            answers = form_tui.run(self.form, self.install)
        self.assertEqual(answers.lang, "ru")
        self.assertEqual(len(self.installed), 1)

    def test_unticking_tweaks_hides_and_skips_the_theme(self):
        # dir -> browse -> channel -> tweaks, Space; then Tab must jump past theme to search.
        keys = [KEY_TAB] * 3 + [b" ", KEY_TAB, KEY_TAB, KEY_TAB, KEY_ENTER, KEY_ENTER]
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


class PickDirTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        for name in ("beta", "alpha", ".hidden"):
            os.mkdir(os.path.join(self.root, name))
        open(os.path.join(self.root, "file.txt"), "w").close()

    def _pick(self, keys, start=None):
        with _drive(keys):
            return form_tui.pick_dir(start or self.root, "Pick")

    def test_lists_dirs_plain_then_hidden_files_excluded(self):
        self.assertEqual(form_tui._subdirs(Path(self.root)), ["..", "alpha", "beta", ".hidden"])

    def test_select_returns_the_current_directory(self):
        self.assertEqual(self._pick([KEY_TAB, KEY_ENTER]), self.root)  # list -> Select

    def test_enter_opens_a_directory(self):
        self.assertEqual(self._pick([KEY_DOWN, KEY_ENTER, KEY_TAB, KEY_ENTER]), os.path.join(self.root, "alpha"))

    def test_typing_jumps_and_backspace_goes_back_up(self):
        keys = [b"b", KEY_ENTER, KEY_BACKSPACE, KEY_TAB, KEY_ENTER]  # into beta, back up, Select
        self.assertEqual(self._pick(keys), self.root)

    def test_starts_from_the_nearest_existing_directory(self):
        start = os.path.join(self.root, "alpha", "not", "yet")
        self.assertEqual(self._pick([KEY_TAB, KEY_ENTER], start=start), os.path.join(self.root, "alpha"))

    def test_escape_cancels(self):
        self.assertIsNone(self._pick([KEY_ESC]))

    def test_browse_button_fills_the_form(self):
        form = InstallForm(langs=LANGS, profiles=[])
        form.answers.install_dir = os.path.join(self.root, "alpha")
        installed = []
        # Tab to Browse, Enter opens it, Tab+Enter selects the current dir; then Install, Close.
        keys = [KEY_TAB, KEY_ENTER, KEY_TAB, KEY_ENTER] + TO_INSTALL_FROM_BROWSE + [KEY_ENTER, KEY_ENTER]
        with _drive(keys):
            answers = form_tui.run(form, lambda a, progress: installed.append(a))
        self.assertEqual(answers.install_dir, os.path.join(self.root, "alpha"))


if __name__ == "__main__":
    unittest.main()
