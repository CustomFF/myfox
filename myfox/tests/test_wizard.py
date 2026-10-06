from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from myfox import wizard
from myfox.install_form import InstallForm, Lang
from myfox.ui import form_plain

# Sorted by English name, as InstallForm.load() returns them.
LANGS = [Lang("be", "Belarusian", "Беларуская"), Lang("en-US", "English (US)", "English (US)"),
         Lang("ru", "Russian", "Русский")]


class PlainFormTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.form = InstallForm(langs=LANGS, profiles=[])
        self.form.answers.install_dir = self._tmp.name
        self.form.answers.lang = "en-US"
        self.installed = []

    def install(self, answers, progress):
        progress("step…", 0.5)
        self.installed.append(answers)

    def _run(self, inputs, **kwargs):
        with mock.patch("builtins.input", side_effect=list(inputs)), redirect_stdout(io.StringIO()), \
             redirect_stderr(io.StringIO()):
            return form_plain.run(self.form, self.install, **kwargs)

    def test_enter_everywhere_keeps_the_defaults(self):
        # dir, channel, tweaks, theme, lang
        answers = self._run(["", "", "", "", ""])
        self.assertEqual(self.installed, [answers])
        self.assertEqual((answers.channel, answers.tweaks, answers.theme, answers.lang), ("stable", True, "dark", "en-US"))

    def test_answers_are_taken(self):
        answers = self._run(["", "2", "y", "2", "ru"])
        self.assertEqual((answers.channel, answers.theme, answers.lang), ("beta", "light", "ru"))

    def test_no_theme_question_without_tweaks(self):
        answers = self._run(["", "", "n", ""])  # dir, channel, tweaks=no, lang
        self.assertFalse(answers.tweaks)

    def test_lang_by_word_with_several_matches_asks_which(self):
        answers = self._run(["", "", "", "", "рус", "2"])  # be, ru -> pick 2
        self.assertEqual(answers.lang, "ru")

    def test_invalid_dir_is_asked_again(self):
        answers = self._run(["relative", "", "", "", "", ""])
        self.assertEqual(answers.install_dir, self._tmp.name)

    def test_noninteractive_asks_nothing(self):
        with mock.patch("builtins.input", side_effect=AssertionError("asked")), redirect_stdout(io.StringIO()):
            self.assertIsNotNone(form_plain.run(self.form, self.install, noninteractive=True))

    def test_mozilla_error_installs_nothing(self):
        form = InstallForm(langs=[], profiles=[], error="no network")
        with redirect_stderr(io.StringIO()):
            self.assertIsNone(form_plain.run(form, self.install, noninteractive=True))
        self.assertEqual(self.installed, [])


class DispatchTests(unittest.TestCase):
    """--gui only changes the look: every path gets the same loaded form."""

    def setUp(self):
        self.form = InstallForm(langs=LANGS, profiles=[])
        patcher = mock.patch("myfox.wizard.InstallForm.load", return_value=self.form)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_gui_flag_uses_the_gui_view(self):
        fake = mock.Mock()
        with mock.patch.dict("sys.modules", {"myfox.ui.form_gui": fake}), \
             mock.patch("myfox.ui.form_gui", fake, create=True):
            wizard.run(gui=True)
        fake.run.assert_called_once()
        self.assertIs(fake.run.call_args[0][0], self.form)

    def test_gui_unavailable_is_reported(self):
        with mock.patch.dict("sys.modules", {"myfox.ui.form_gui": None}), redirect_stderr(io.StringIO()) as err:
            self.assertIsNone(wizard.run(gui=True))
        self.assertTrue(err.getvalue().strip())

    def test_tty_uses_the_tui_view(self):
        with mock.patch("myfox.wizard._has_tty", return_value=True), \
             mock.patch("myfox.ui.form_tui.run") as run:
            wizard.run()
        self.assertIs(run.call_args[0][0], self.form)

    def test_no_tty_uses_plain_questions(self):
        with mock.patch("myfox.wizard._has_tty", return_value=False), \
             mock.patch("myfox.ui.form_plain.run") as run:
            wizard.run()
        self.assertIs(run.call_args[0][0], self.form)

    def test_noninteractive_wins_over_gui(self):
        with mock.patch("myfox.ui.form_plain.run") as run:
            wizard.run(gui=True, noninteractive=True)
        self.assertTrue(run.call_args.kwargs["noninteractive"])


if __name__ == "__main__":
    unittest.main()
