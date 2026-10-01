from __future__ import annotations

import contextlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from myfox import wizard


class _ScriptedUI:
    """Feeds pre-recorded answers to each call, by call order — the wizard's
    page-stack logic is what's under test here, not any real backend. Runs
    out of scripted answers -> AssertionError, not a silent default: a page
    calling this more times than the test expected is exactly the kind of
    bug this should catch (an earlier, looser version of this double masked
    exactly that and hung in an infinite welcome<->dir loop instead)."""

    def __init__(self, confirms=(), chooses=(), input_dirs=()):
        self._confirms = list(confirms)
        self._chooses = list(chooses)
        self._input_dirs = list(input_dirs)
        self.messages: list[str] = []

    def confirm(self, prompt, default=True):
        assert self._confirms, f"unscripted confirm() call: {prompt!r}"
        return self._confirms.pop(0)

    def choose(self, header, options, default=None):
        assert self._chooses, f"unscripted choose() call: {header!r}"
        return self._chooses.pop(0)

    def input_dir(self, prompt, initial):
        assert self._input_dirs, f"unscripted input_dir() call: {prompt!r}"
        return self._input_dirs.pop(0)

    def message(self, text):
        self.messages.append(text)

    @contextlib.contextmanager
    def spin(self, title):
        yield


def _valid_dir():
    d = tempfile.mkdtemp()
    return d


class HappyPathTests(unittest.TestCase):
    def test_runs_start_to_finish_with_no_existing_profiles(self):
        install_dir = _valid_dir()
        ui = _ScriptedUI(
            confirms=[True, True, True],  # welcome, tweaks, summary
            chooses=["beta", "ru", "dark"],  # channel, lang, theme
            input_dirs=[install_dir],
        )
        with mock.patch("myfox.profiles.list_myfox", return_value=[]), \
             mock.patch("myfox.firefox.fetch_lang_catalog", return_value={"ru": "Russian", "en-US": "English (US)"}):
            answers = wizard.run(ui)

        self.assertIsNotNone(answers)
        self.assertEqual(answers.install_dir, install_dir)
        self.assertEqual(answers.channel, "beta")
        self.assertEqual(answers.lang, "ru")
        self.assertIsNone(answers.profile_dir)
        self.assertTrue(answers.tweaks)
        self.assertEqual(answers.theme, "dark")

    def test_declining_welcome_cancels_immediately(self):
        ui = _ScriptedUI(confirms=[False])
        answers = wizard.run(ui)
        self.assertIsNone(answers)

    def test_declining_tweaks_skips_the_theme_page(self):
        install_dir = _valid_dir()
        ui = _ScriptedUI(
            confirms=[True, False, True],  # welcome, tweaks=no, summary
            chooses=["stable", "en-US"],  # channel, lang (no theme choice consumed)
            input_dirs=[install_dir],
        )
        with mock.patch("myfox.profiles.list_myfox", return_value=[]), \
             mock.patch("myfox.firefox.fetch_lang_catalog", return_value={"en-US": "English (US)"}):
            answers = wizard.run(ui)

        self.assertIsNotNone(answers)
        self.assertFalse(answers.tweaks)
        self.assertEqual(answers.theme, "dark")  # untouched default, never asked


class ProfilePageTests(unittest.TestCase):
    def test_skipped_entirely_when_no_myfox_profiles_exist(self):
        install_dir = _valid_dir()
        ui = _ScriptedUI(
            confirms=[True, True, True],
            chooses=["stable", "en-US", "dark"],
            input_dirs=[install_dir],
        )
        with mock.patch("myfox.profiles.list_myfox", return_value=[]), \
             mock.patch("myfox.firefox.fetch_lang_catalog", return_value={"en-US": "English (US)"}):
            wizard.run(ui)
        # the 3 chooses above are channel/lang/theme — if profile had asked
        # a 4th choose, lang or theme would have silently consumed the
        # wrong scripted answer instead.

    def test_offers_an_existing_profile_when_one_exists(self):
        install_dir = _valid_dir()
        existing_profile = Path(_valid_dir())
        ui = _ScriptedUI(
            confirms=[True, True, True],
            chooses=["stable", "en-US", str(existing_profile), "dark"],
            input_dirs=[install_dir],
        )
        with mock.patch("myfox.profiles.list_myfox", return_value=[(existing_profile, "myfox")]), \
             mock.patch("myfox.firefox.fetch_lang_catalog", return_value={"en-US": "English (US)"}):
            answers = wizard.run(ui)

        self.assertEqual(answers.profile_dir, str(existing_profile))


class BackNavigationTests(unittest.TestCase):
    def test_back_from_channel_returns_to_dir_then_forward_again(self):
        install_dir = _valid_dir()
        ui = _ScriptedUI(
            confirms=[True, True, True],
            # First dir attempt, then channel returns None (Back), then
            # dir is asked again, then channel/lang/theme for real.
            chooses=[None, "stable", "en-US", "dark"],
            input_dirs=[install_dir, install_dir],
        )
        with mock.patch("myfox.profiles.list_myfox", return_value=[]), \
             mock.patch("myfox.firefox.fetch_lang_catalog", return_value={"en-US": "English (US)"}):
            answers = wizard.run(ui)

        self.assertIsNotNone(answers)
        self.assertEqual(answers.channel, "stable")

    def test_backing_out_to_welcome_then_declining_cancels(self):
        # _page_welcome itself never returns BACK (no page precedes it) —
        # backing out of _page_dir just re-shows welcome, it doesn't by
        # itself cancel. Only declining welcome (now, on the re-show) does.
        ui = _ScriptedUI(confirms=[True, False], input_dirs=[None])
        with mock.patch("myfox.profiles.list_myfox", return_value=[]):
            answers = wizard.run(ui)
        self.assertIsNone(answers)

    def test_declining_the_summary_goes_back_to_theme_not_tweaks(self):
        install_dir = _valid_dir()
        ui = _ScriptedUI(
            confirms=[True, True, False, True],  # welcome, tweaks, summary=no, summary (retry)
            chooses=["stable", "en-US", "dark", "light"],  # channel, lang, theme, theme (retry)
            input_dirs=[install_dir],
        )
        with mock.patch("myfox.profiles.list_myfox", return_value=[]), \
             mock.patch("myfox.firefox.fetch_lang_catalog", return_value={"en-US": "English (US)"}):
            answers = wizard.run(ui)

        self.assertIsNotNone(answers)
        self.assertTrue(answers.tweaks)  # never re-asked
        self.assertEqual(answers.theme, "light")  # re-asked and changed


class DirValidationTests(unittest.TestCase):
    def test_rejects_an_invalid_path_then_accepts_a_valid_one(self):
        install_dir = _valid_dir()
        ui = _ScriptedUI(
            confirms=[True, True, True],
            chooses=["stable", "en-US", "dark"],
            input_dirs=["relative/path", install_dir],
        )
        with mock.patch("myfox.profiles.list_myfox", return_value=[]), \
             mock.patch("myfox.firefox.fetch_lang_catalog", return_value={"en-US": "English (US)"}):
            answers = wizard.run(ui)

        self.assertIsNotNone(answers)
        self.assertEqual(answers.install_dir, install_dir)


class LangFetchFailureTests(unittest.TestCase):
    def test_network_failure_defaults_to_en_us_without_asking(self):
        install_dir = _valid_dir()
        ui = _ScriptedUI(
            confirms=[True, True, True],
            chooses=["stable", "dark"],  # no lang choice consumed
            input_dirs=[install_dir],
        )
        with mock.patch("myfox.profiles.list_myfox", return_value=[]), \
             mock.patch("myfox.firefox.fetch_lang_catalog", side_effect=OSError("network down")):
            answers = wizard.run(ui)

        self.assertIsNotNone(answers)
        self.assertEqual(answers.lang, "en-US")


if __name__ == "__main__":
    unittest.main()
