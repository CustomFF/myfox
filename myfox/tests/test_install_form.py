from __future__ import annotations

import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from myfox import i18n, importer, sources
from myfox.install_form import IMPORT, OTHER, Answers, InstallForm, Lang, simulate_install

from ._helpers import IsolatedStateCase

NAMES = {"en-US": ("English (US)", "English (US)"), "ru": ("Russian", "Русский"), "be": ("Belarusian", "Беларуская")}


VERSIONS = {"stable": "158.0.1", "beta": "159.0b5"}


def _load(names=NAMES, profiles=(), env_lang="ru_RU.UTF-8", found=()) -> InstallForm:
    with mock.patch("myfox.firefox.fetch_lang_names", return_value=names), \
         mock.patch("myfox.firefox.latest_versions", return_value=VERSIONS), \
         mock.patch("myfox.profiles.list_myfox", return_value=list(profiles)), \
         mock.patch("myfox.sources.listing", return_value=list(found)), \
         mock.patch.dict("os.environ", {"LANG": env_lang}):
        return InstallForm.load()


def _found(path, name, store="", owner=sources.FOREIGN, version="157.0"):
    folder = Path(path).name
    return sources.Profile(id=f"{store}:{folder}" if store else folder, name=name, path=Path(path), store=store,
                           owner=owner, last_version=version)


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

    def test_with_nothing_found_only_new_and_a_folder_to_import(self):
        self.assertEqual([c.value for c in _load().profiles], ["", OTHER])

    def test_existing_profiles_come_after_a_create_new_choice(self):
        form = _load(profiles=[(Path("/p/abc.myfox"), "myfox")])
        self.assertEqual([c.value for c in form.profiles], ["", "/p/abc.myfox", OTHER])
        self.assertEqual(form.profiles[0].label, i18n.t("wizard_profile_new"))

    def test_other_firefoxes_profiles_to_import(self):
        found = [_found("/s/a.default", "default"), _found("/s/b.default", "default"),
                 _found("/snap/c.work", "work", store="snap"), _found("/s/myfox-1", "myfox", owner=sources.MYFOX)]
        form = _load(found=found)
        self.assertEqual([c.value for c in form.profiles], [
            "", IMPORT + "/s/a.default", IMPORT + "/s/b.default", IMPORT + "/snap/c.work", OTHER])
        self.assertEqual([c.label for c in form.profiles[1:4]], [
            i18n.t("form_profile_import", "default (a.default)"), i18n.t("form_profile_import", "default (b.default)"),
            i18n.t("form_profile_import", "work (snap:c.work)")])

    def test_unreachable_mozilla_is_an_error_not_a_fallback_list(self):
        with mock.patch("myfox.firefox.fetch_lang_names", side_effect=urllib.error.URLError("no dns")), \
             mock.patch("myfox.profiles.list_myfox", return_value=[]), \
             mock.patch("myfox.sources.listing", return_value=[]):
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
        with mock.patch("myfox.install_form.time.sleep"), mock.patch("myfox.addons.is_plasma_session", return_value=True):
            simulate_install(Answers(), lambda message, fraction: reports.append((message, fraction)))
        self.assertIn(i18n.t("progress_tweaks_plasma"), [m for m, _f in reports])
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


class ImportFormTests(IsolatedStateCase):
    def setUp(self):
        super().setUp()
        store = Path.home() / ".mozilla" / "firefox"
        self.source = store / "a.default"
        self.source.mkdir(parents=True)
        (self.source / "prefs.js").touch()
        (self.source / "compatibility.ini").write_text(
            "[Compatibility]\nLastVersion=157.0_1/1\nLastPlatformDir=/usr/lib/firefox\n", encoding="utf-8")
        (store / "profiles.ini").write_text("[Profile0]\nName=default\nIsRelative=1\nPath=a.default\n",
                                            encoding="utf-8")
        with mock.patch("myfox.firefox.fetch_lang_names", return_value=NAMES), \
             mock.patch("myfox.firefox.latest_versions", return_value=VERSIONS):
            self.form = InstallForm.load()
        self.form.answers.install_dir = str(self.tmp_path / "firefox")
        self.value = IMPORT + str(self.source)

    def test_picking_an_import_and_back(self):
        a = self.form.answers
        self.assertIn(self.value, [c.value for c in self.form.profiles])
        self.form.pick_profile(self.value)
        self.assertEqual((a.import_from, a.profile_dir, self.form.profile_value), (str(self.source), None, self.value))
        self.form.pick_profile("")
        self.assertEqual((a.import_from, a.profile_dir, self.form.profile_value), (None, None, ""))

    def test_sync_is_asked_only_for_a_signed_in_profile(self):
        self.form.pick_profile(self.value)
        self.assertFalse(self.form.sync_applies)
        (self.source / "signedInUser.json").write_text("{}", encoding="utf-8")
        self.assertTrue(self.form.sync_applies)

    def test_a_folder_becomes_a_choice_once(self):
        loose = self.tmp_path / "loose"
        loose.mkdir()
        (loose / "times.json").touch()
        value = self.form.add_import(str(loose))
        self.assertEqual(self.form.add_import(str(loose)), value)
        values = [c.value for c in self.form.profiles]
        self.assertEqual((values.count(value), values[-1]), (1, OTHER))
        empty = self.tmp_path / "empty"
        empty.mkdir()
        with self.assertRaises(sources.ProfileLookupError):
            self.form.add_import(str(empty))

    def test_an_open_profile_is_refused(self):
        self.form.pick_profile(self.value)
        with mock.patch("myfox.sources.in_use", return_value=True):
            self.assertEqual(self.form.validate(), i18n.t("err_import_in_use", "default"))

    def test_a_newer_profile_asks_once_then_goes_on(self):
        (self.source / "compatibility.ini").write_text("[Compatibility]\nLastVersion=160.0_1/1\n", encoding="utf-8")
        self.form.pick_profile(self.value)
        self.assertEqual(self.form.validate(), i18n.t("warn_import_downgrade", "160.0", "158.0.1"))
        self.assertIsNone(self.form.validate())
        self.assertTrue(self.form.answers.allow_downgrade)

    def test_switching_the_channel_asks_again(self):
        (self.source / "compatibility.ini").write_text("[Compatibility]\nLastVersion=160.0_1/1\n", encoding="utf-8")
        self.form.pick_profile(self.value)
        self.assertIsNotNone(self.form.validate())
        self.form.answers.channel = "beta"
        self.assertEqual(self.form.validate(), i18n.t("warn_import_downgrade", "160.0", "159.0b5"))

    def test_sync_falls_back_to_none_without_an_account(self):
        self.form.pick_profile(self.value)
        self.form.answers.sync = importer.SYNC_MOVE
        self.assertIsNone(self.form.validate())
        self.assertEqual(self.form.answers.sync, importer.SYNC_NONE)
