from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from myfox import i18n, wizard
from myfox.install_form import INSTALL_COMMAND, Answers, InstallForm, Lang, summary
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

    def test_without_yes_shows_the_defaults_and_the_command(self):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("builtins.input", side_effect=AssertionError("asked")), redirect_stdout(out), \
             redirect_stderr(err):
            self.assertIsNone(form_plain.run(self.form, self.install))
        self.assertEqual(self.installed, [])
        self.assertIn(self._tmp.name, out.getvalue())
        self.assertIn("English (US) (en-US)", out.getvalue())
        self.assertIn(i18n.t("needs_yes_install", INSTALL_COMMAND), err.getvalue())

    def test_noninteractive_asks_nothing(self):
        with mock.patch("builtins.input", side_effect=AssertionError("asked")), redirect_stdout(io.StringIO()):
            self.assertIsNotNone(form_plain.run(self.form, self.install, noninteractive=True))

    def test_mozilla_error_installs_nothing(self):
        form = InstallForm(langs=[], profiles=[], error="no network")
        with redirect_stderr(io.StringIO()):
            self.assertIsNone(form_plain.run(form, self.install, noninteractive=True))
        self.assertEqual(self.installed, [])


class SummaryTests(unittest.TestCase):
    def test_lists_what_was_installed(self):
        answers = Answers(install_dir="/opt/ff", profile_dir="/p/myfox-1", lang="ru", firefox_version="152.0")
        lines = summary(answers)
        self.assertEqual(lines[0], i18n.t("install_done"))
        self.assertTrue(any("152.0" in line for line in lines))
        self.assertTrue(any("/opt/ff" in line for line in lines))
        self.assertTrue(any("/p/myfox-1" in line for line in lines))
        self.assertTrue(any(i18n.t("wizard_theme_dark") in line for line in lines))
        self.assertEqual(lines[-1], i18n.t("install_done_run"))

    def test_without_tweaks_no_theme(self):
        lines = summary(Answers(install_dir="/opt/ff", tweaks=False))
        self.assertFalse(any(i18n.t("form_theme") in line for line in lines))

    def test_printed_after_a_successful_install(self):
        answers = Answers(install_dir="/opt/ff", notes=["a note"])
        with mock.patch("myfox.wizard.run", return_value=answers), redirect_stdout(io.StringIO()) as out:
            self.assertEqual(wizard.main([]), 0)
        self.assertEqual(out.getvalue().splitlines(), summary(answers) + ["a note"])


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
             mock.patch("myfox.ui.form_gui", fake, create=True), \
             mock.patch("myfox.gui_deps.prepare"):
            wizard.run(gui=True)
        fake.run.assert_called_once()
        self.assertIs(fake.run.call_args[0][0], self.form)

    def test_gui_unavailable_is_reported_and_the_terminal_takes_over(self):
        with mock.patch("myfox.gui_deps.prepare", side_effect=RuntimeError("no window")), \
             mock.patch("myfox.wizard._has_tty", return_value=True), \
             mock.patch("myfox.ui.form_tui.run") as tui, redirect_stderr(io.StringIO()) as err:
            wizard.run(gui=True)
        self.assertIn("no window", err.getvalue())
        self.assertIs(tui.call_args[0][0], self.form)

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
