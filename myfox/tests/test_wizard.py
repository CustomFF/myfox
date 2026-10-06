from __future__ import annotations

import contextlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from myfox import i18n, wizard


class _ScriptedUI:
    """Feeds pre-recorded answers to each call, by call order — the wizard's
    page-stack logic is what's under test here, not any real backend. Runs
    out of scripted answers -> AssertionError, not a silent default: a page
    calling this more times than the test expected is exactly the kind of
    bug this should catch (an earlier, looser version of this double masked
    exactly that and hung in an infinite welcome<->dir loop instead)."""

    def __init__(self, confirms=(), chooses=(), input_dirs=(), toggles=()):
        self._confirms = list(confirms)
        self._chooses = list(chooses)
        self._input_dirs = list(input_dirs)
        self._toggles = list(toggles)
        self.messages: list[str] = []

    def confirm(self, prompt, default=True, yes_label="Yes", no_label="No", show_back=False):
        assert self._confirms, f"unscripted confirm() call: {prompt!r}"
        return self._confirms.pop(0)

    def choose(self, header, options, default=None, next_label="Select"):
        assert self._chooses, f"unscripted choose() call: {header!r}"
        return self._chooses.pop(0)

    def input_dir(self, prompt, initial, next_label="OK"):
        assert self._input_dirs, f"unscripted input_dir() call: {prompt!r}"
        return self._input_dirs.pop(0)

    def toggle(self, prompt, default=True, next_label="OK"):
        assert self._toggles, f"unscripted toggle() call: {prompt!r}"
        return self._toggles.pop(0)

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
            confirms=[True, True],  # welcome, summary
            chooses=["beta", "ru", "dark"],  # channel, lang, theme
            toggles=[True],  # tweaks
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
            confirms=[True, True],  # welcome, summary
            chooses=["stable", "en-US"],  # channel, lang (no theme choice consumed)
            toggles=[False],  # tweaks
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
            confirms=[True, True],
            chooses=["stable", "en-US", "dark"],
            toggles=[True],
            input_dirs=[install_dir],
        )
        with mock.patch("myfox.profiles.list_myfox", return_value=[]), \
             mock.patch("myfox.firefox.fetch_lang_catalog", return_value={"en-US": "English (US)"}):
            wizard.run(ui)
        # the 3 chooses above are channel/lang/theme — if profile had asked
        # a 4th choose, one of those would have silently consumed the wrong
        # scripted answer instead.

    def test_offers_an_existing_profile_when_one_exists(self):
        install_dir = _valid_dir()
        existing_profile = Path(_valid_dir())
        ui = _ScriptedUI(
            confirms=[True, True],
            chooses=["stable", "en-US", str(existing_profile), "dark"],
            toggles=[True],
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
            confirms=[True, True],
            # First dir attempt, then channel returns None (Back), then
            # dir is asked again, then channel/lang/theme for real.
            chooses=[None, "stable", "en-US", "dark"],
            toggles=[True],
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
            confirms=[True, False, True],  # welcome, summary=no, summary (retry)
            chooses=["stable", "en-US", "dark", "light"],  # channel, lang, theme, theme (retry)
            toggles=[True],  # tweaks
            input_dirs=[install_dir],
        )
        with mock.patch("myfox.profiles.list_myfox", return_value=[]), \
             mock.patch("myfox.firefox.fetch_lang_catalog", return_value={"en-US": "English (US)"}):
            answers = wizard.run(ui)

        self.assertIsNotNone(answers)
        self.assertTrue(answers.tweaks)  # never re-asked
        self.assertEqual(answers.theme, "light")  # re-asked and changed


class ButtonLabelTests(unittest.TestCase):
    """Welcome and summary aren't generic yes/no questions — the user-visible
    difference (and why this exists) is a GUI session reporting these two
    pages still showing bare "Yes"/"No" alongside a separate always-on
    Cancel, which read as a Back/Next/Cancel wizard pretending to be a
    plain confirmation dialog."""

    def test_welcome_asks_to_continue_with_no_redundant_second_button(self):
        ui = mock.MagicMock()
        ui.confirm.return_value = True
        self.assertEqual(wizard._page_welcome(wizard.Answers(), ui, wizard.NEXT), wizard.NEXT)
        _, kwargs = ui.confirm.call_args
        self.assertEqual(kwargs["yes_label"], i18n.t("wizard_continue"))
        self.assertIsNone(kwargs["no_label"])

    def test_summary_offers_install_with_a_real_back_not_a_redundant_no(self):
        # show_back, not a second labeled-"Back" button sitting in the
        # no_label slot — that put it in a different position than every
        # other page's actual Back button (found live).
        ui = mock.MagicMock()
        ui.confirm.return_value = True
        self.assertEqual(wizard._page_summary(wizard.Answers(), ui, wizard.NEXT), wizard.NEXT)
        _, kwargs = ui.confirm.call_args
        self.assertEqual(kwargs["yes_label"], i18n.t("wizard_install"))
        self.assertIsNone(kwargs["no_label"])
        self.assertTrue(kwargs["show_back"])

    def test_summary_back_click_returns_to_the_previous_page(self):
        ui = mock.MagicMock()
        ui.confirm.return_value = None  # Back
        self.assertEqual(wizard._page_summary(wizard.Answers(), ui, wizard.NEXT), wizard.BACK)

    def test_tweaks_page_is_a_toggle_not_confirm_or_a_choose_list(self):
        # A single on/off setting is a checkbox (toggle()) — not a
        # confirm() yes/no question (a live review: "где тут хоть в одном
        # месте Да или Нет"), and not a two-item choose() list either (an
        # earlier attempt at this fix tried that — a filterable search box
        # and scrollable listbox is nonsense for one boolean).
        ui = mock.MagicMock()
        ui.toggle.return_value = True
        self.assertEqual(wizard._page_tweaks(wizard.Answers(), ui, wizard.NEXT), wizard.NEXT)
        ui.confirm.assert_not_called()
        ui.choose.assert_not_called()
        _, kwargs = ui.toggle.call_args
        self.assertEqual(kwargs["next_label"], i18n.t("wizard_next"))

    def test_tweaks_back_click_returns_to_the_previous_page_without_changing_the_answer(self):
        ui = mock.MagicMock()
        ui.toggle.return_value = None  # Back
        answers = wizard.Answers(tweaks=True)
        self.assertEqual(wizard._page_tweaks(answers, ui, wizard.NEXT), wizard.BACK)
        self.assertTrue(answers.tweaks)  # untouched — Back didn't answer the question

    def test_dir_page_uses_the_shared_next_label(self):
        ui = mock.MagicMock()
        ui.input_dir.return_value = _valid_dir()
        self.assertEqual(wizard._page_dir(wizard.Answers(), ui, wizard.NEXT), wizard.NEXT)
        _, kwargs = ui.input_dir.call_args
        self.assertEqual(kwargs["next_label"], i18n.t("wizard_next"))

    def test_channel_page_uses_the_shared_next_label(self):
        ui = mock.MagicMock()
        ui.choose.return_value = "stable"
        self.assertEqual(wizard._page_channel(wizard.Answers(), ui, wizard.NEXT), wizard.NEXT)
        _, kwargs = ui.choose.call_args
        self.assertEqual(kwargs["next_label"], i18n.t("wizard_next"))

    def test_lang_page_uses_the_shared_next_label(self):
        ui = mock.MagicMock()
        ui.choose.return_value = "en-US"
        with mock.patch("myfox.firefox.fetch_lang_catalog", return_value={"en-US": "English (US)"}):
            self.assertEqual(wizard._page_lang(wizard.Answers(), ui, wizard.NEXT), wizard.NEXT)
        _, kwargs = ui.choose.call_args
        self.assertEqual(kwargs["next_label"], i18n.t("wizard_next"))

    def test_profile_page_uses_the_shared_next_label(self):
        ui = mock.MagicMock()
        ui.choose.return_value = ""
        with mock.patch("myfox.profiles.list_myfox", return_value=[(Path(_valid_dir()), "existing")]):
            self.assertEqual(wizard._page_profile(wizard.Answers(), ui, wizard.NEXT), wizard.NEXT)
        _, kwargs = ui.choose.call_args
        self.assertEqual(kwargs["next_label"], i18n.t("wizard_next"))

    def test_theme_page_uses_the_shared_next_label(self):
        ui = mock.MagicMock()
        ui.choose.return_value = "dark"
        answers = wizard.Answers(tweaks=True)
        self.assertEqual(wizard._page_theme(answers, ui, wizard.NEXT), wizard.NEXT)
        _, kwargs = ui.choose.call_args
        self.assertEqual(kwargs["next_label"], i18n.t("wizard_next"))


class DirValidationTests(unittest.TestCase):
    def test_rejects_an_invalid_path_then_accepts_a_valid_one(self):
        install_dir = _valid_dir()
        ui = _ScriptedUI(
            confirms=[True, True],  # welcome, summary
            chooses=["stable", "en-US", "dark"],  # channel, lang, theme
            toggles=[True],  # tweaks
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
            confirms=[True, True],  # welcome, summary
            chooses=["stable", "dark"],  # channel, theme (no lang choice consumed)
            toggles=[True],  # tweaks
            input_dirs=[install_dir],
        )
        with mock.patch("myfox.profiles.list_myfox", return_value=[]), \
             mock.patch("myfox.firefox.fetch_lang_catalog", side_effect=OSError("network down")):
            answers = wizard.run(ui)

        self.assertIsNotNone(answers)
        self.assertEqual(answers.lang, "en-US")


if __name__ == "__main__":
    unittest.main()
