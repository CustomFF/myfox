from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

import myfox
from myfox import i18n, installer
from myfox.install_form import Answers
from myfox.state import State

from ._helpers import IsolatedStateCase


class InstallTests(IsolatedStateCase):
    def setUp(self):
        super().setUp()
        self.install_dir = self.tmp_path / "firefox"
        self.profile_dir = self.tmp_path / "profile"
        self.profile_dir.mkdir()
        self.reports = []
        self.calls = []

    def _fake_tarball(self, install_dir, lang, channel, on_download=None, on_extract=None):
        self.calls.append("tarball")
        install_dir.mkdir(parents=True, exist_ok=True)
        for done in (10, 50, 100):
            on_download(done * 1024 * 1024 // 100, 1024 * 1024)
        on_extract(5, 5)
        return "152.0"

    def _install(self, answers, plasma=False, pkg=True, addon_fails=False, gui_error=None):
        record = lambda name: (lambda *a, **k: self.calls.append(name))  # noqa: E731
        amo = lambda *a, **k: self.calls.append("plasma") or (["plasma-integration"] if addon_fails else [])  # noqa: E731
        with mock.patch("myfox.addons.is_plasma_session", return_value=plasma), \
             mock.patch("myfox.addons.apply_amo_addons", side_effect=amo), \
             mock.patch("myfox.addons.pkg_installed", return_value=pkg), \
             mock.patch("myfox.addons.pkg_install_hint", return_value="sudo apt install plasma-browser-integration"), \
             mock.patch("myfox.firefox.install_tarball", side_effect=self._fake_tarball), \
             mock.patch("myfox.tweaks.install", side_effect=lambda: self.calls.append("tweaks") or "158.0"), \
             mock.patch("myfox.profiles.create_new", return_value=self.profile_dir), \
             mock.patch("myfox.profiles.pin_install", side_effect=lambda *a, **k: self.calls.append("pin") or "HASH"), \
             mock.patch("myfox.apply.apply_autoconfig", side_effect=record("autoconfig")), \
             mock.patch("myfox.apply.apply_chrome", side_effect=record("chrome")), \
             mock.patch("myfox.apply.apply_theme_pref", side_effect=record("theme")), \
             mock.patch("myfox.addons.fetch_themes", side_effect=lambda *a, **k: self.calls.append("themes") or ("themes-1", [])), \
             mock.patch("myfox.apply.apply_bookmarklets", side_effect=record("bookmarklets")), \
             mock.patch("myfox.launcher.install_self", return_value=Path("/x/bin/myfox")), \
             mock.patch("myfox.gui_deps.install_into", side_effect=gui_error or record("gui")), \
             mock.patch("myfox.desktop.write_entry", side_effect=record("desktop")):
            installer.install(answers, lambda message, fraction: self.reports.append((message, fraction)))

    def test_full_install_runs_every_step_and_saves_state(self):
        answers = Answers(install_dir=str(self.install_dir), lang="ru", theme="light")
        self._install(answers)
        self.assertEqual(self.calls, ["tarball", "tweaks", "pin", "autoconfig", "chrome", "theme", "themes",
                                      "bookmarklets", "gui", "desktop"])
        self.assertTrue((self.install_dir / ".myfox-installed").is_file())
        state = State()
        self.assertEqual((state.get("install_dir"), state.get("profile_dir"), state.get("install_hash")),
                         (str(self.install_dir), str(self.profile_dir), "HASH"))
        self.assertEqual((state.get("firefox_version"), state.get("lang"), state.get("theme")), ("152.0", "ru", "light"))
        self.assertEqual(state.get("tweaks_version"), "158.0")
        self.assertEqual(state.get("themes_version"), "themes-1")
        self.assertEqual(state.get("core_version"), myfox.__version__)
        # What the summary shows.
        self.assertEqual((answers.profile_dir, answers.firefox_version), (str(self.profile_dir), "152.0"))

    def test_progress_only_goes_up_and_ends_done(self):
        self._install(Answers(install_dir=str(self.install_dir)))
        fractions = [f for _m, f in self.reports]
        self.assertEqual(fractions, sorted(fractions))
        self.assertEqual(self.reports[-1], (i18n.t("progress_done"), 1.0))
        self.assertIn(i18n.t("progress_firefox_download"), [m for m, _f in self.reports])

    def test_without_tweaks_the_profile_is_left_alone(self):
        self._install(Answers(install_dir=str(self.install_dir), tweaks=False))
        self.assertEqual(self.calls, ["tarball", "gui", "desktop"])

    def test_plasma_session_gets_the_addon_and_no_note_with_the_package(self):
        answers = Answers(install_dir=str(self.install_dir))
        self._install(answers, plasma=True)
        self.assertEqual(self.calls[-3:], ["plasma", "gui", "desktop"])
        self.assertEqual(answers.notes, [])
        self.assertTrue(State().get("opt_plasma"))

    def test_missing_plasma_package_leaves_a_note_with_the_command(self):
        answers = Answers(install_dir=str(self.install_dir))
        self._install(answers, plasma=True, pkg=False)
        self.assertEqual(answers.notes, [i18n.t("note_plasma_pkg_missing", "sudo apt install plasma-browser-integration")])

    def test_failed_plasma_addon_leaves_a_note(self):
        answers = Answers(install_dir=str(self.install_dir))
        self._install(answers, plasma=True, addon_fails=True)
        self.assertIn(i18n.t("note_plasma_addon_failed"), answers.notes)

    def test_no_plasma_without_tweaks(self):
        self._install(Answers(install_dir=str(self.install_dir), tweaks=False), plasma=True)
        self.assertNotIn("plasma", self.calls)

    def test_gui_failure_is_a_note_not_a_failed_install(self):
        answers = Answers(install_dir=str(self.install_dir))
        self._install(answers, gui_error=OSError("no release"))
        self.assertEqual(answers.notes, [i18n.t("note_gui_failed", "no release")])
        self.assertIn("desktop", self.calls)

    def test_an_install_of_ours_is_reused(self):
        self.install_dir.mkdir()
        (self.install_dir / "application.ini").write_text("[App]\nVersion=151.0\n", encoding="utf-8")
        (self.install_dir / ".myfox-installed").touch()
        self._install(Answers(install_dir=str(self.install_dir)))
        self.assertNotIn("tarball", self.calls)
        self.assertEqual(State().get("firefox_version"), "151.0")


if __name__ == "__main__":
    unittest.main()
