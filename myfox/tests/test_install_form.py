from __future__ import annotations

import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from myfox import i18n
from myfox.install_form import Answers, InstallForm, Lang, simulate_install

NAMES = {"en-US": ("English (US)", "English (US)"), "ru": ("Russian", "Русский"), "be": ("Belarusian", "Беларуская")}


def _load(names=NAMES, profiles=(), env_lang="ru_RU.UTF-8") -> InstallForm:
    with mock.patch("myfox.firefox.fetch_lang_names", return_value=names), \
         mock.patch("myfox.profiles.list_myfox", return_value=list(profiles)), \
         mock.patch.dict("os.environ", {"LANG": env_lang}):
        return InstallForm.load()


class LangTests(unittest.TestCase):
    def test_label_shows_native_then_english_and_code(self):
        self.assertEqual(Lang("ru", "Russian", "Русский").label(), "Русский — Russian (ru)")

    def test_label_skips_native_when_identical_or_unwanted(self):
        self.assertEqual(Lang("en-US", "English (US)", "English (US)").label(), "English (US) (en-US)")
        self.assertEqual(Lang("ru", "Russian", "Русский").label(show_native=False), "Russian (ru)")

    def test_matches_english_native_and_code_case_insensitively(self):
        lang = Lang("ru", "Russian", "Русский")
        for query in ("russ", "РУС", "ru", "", "  "):
            self.assertTrue(lang.matches(query), query)
        self.assertFalse(lang.matches("deutsch"))


class LoadTests(unittest.TestCase):
    def test_default_lang_follows_the_system_locale(self):
        self.assertEqual(_load().answers.lang, "ru")

    def test_langs_sorted_by_english_name(self):
        self.assertEqual([lang.code for lang in _load().langs], ["be", "en-US", "ru"])

    def test_no_profile_question_without_existing_myfox_profiles(self):
        self.assertEqual(_load().profiles, [])

    def test_existing_profiles_come_after_a_create_new_choice(self):
        form = _load(profiles=[(Path("/p/abc.myfox"), "myfox")])
        self.assertEqual([c.value for c in form.profiles], ["", "/p/abc.myfox"])
        self.assertEqual(form.profiles[0].label, i18n.t("wizard_profile_new"))

    def test_unreachable_mozilla_is_an_error_not_a_fallback_list(self):
        with mock.patch("myfox.firefox.fetch_lang_names", side_effect=urllib.error.URLError("no dns")), \
             mock.patch("myfox.profiles.list_myfox", return_value=[]):
            form = InstallForm.load()
        self.assertEqual(form.langs, [])
        self.assertEqual(form.error, i18n.t("err_mozilla_unreachable", "no dns"))
        self.assertEqual(form.validate(), form.error)


class FormTests(unittest.TestCase):
    def test_filter_langs(self):
        self.assertEqual([lang.code for lang in _load().filter_langs("рус")], ["be", "ru"])

    def test_theme_applies_only_with_tweaks(self):
        form = _load()
        self.assertTrue(form.theme_applies)
        form.answers.tweaks = False
        self.assertFalse(form.theme_applies)

    def test_validate_normalizes_a_good_dir(self):
        form = _load()
        with tempfile.TemporaryDirectory() as tmp:
            form.answers.install_dir = f"  {tmp}/firefox/ "
            self.assertIsNone(form.validate())
            self.assertEqual(form.answers.install_dir, f"{tmp}/firefox")

    def test_validate_returns_the_localized_error(self):
        form = _load()
        form.answers.install_dir = "relative/path"
        self.assertEqual(form.validate(), i18n.t("err_installdir_relative", "relative/path"))


class SimulateInstallTests(unittest.TestCase):
    def test_reports_increasing_progress_and_ends_done(self):
        reports = []
        with mock.patch("myfox.install_form.time.sleep"):
            simulate_install(Answers(), lambda message, fraction: reports.append((message, fraction)))
        fractions = [fraction for _message, fraction in reports]
        self.assertEqual(fractions, sorted(fractions))
        self.assertEqual(reports[-1], (i18n.t("progress_done"), 1.0))

    def test_no_tweak_stages_without_tweaks(self):
        messages = []
        with mock.patch("myfox.install_form.time.sleep"):
            simulate_install(Answers(tweaks=False), lambda message, fraction: messages.append(message))
        self.assertNotIn(i18n.t("progress_tweaks_addons"), messages)


if __name__ == "__main__":
    unittest.main()
