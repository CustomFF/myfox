from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

import myfox
from myfox import i18n, importer, installer
from myfox.install_form import Answers, Cancelled
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

    def _fake_tarball(self, install_dir, lang, channel, on_download=None, on_extract=None, on_wait=None):
        self.calls.append("tarball")
        install_dir.mkdir(parents=True, exist_ok=True)
        for done in (10, 50, 100):
            on_download(done * 1024 * 1024 // 100, 1024 * 1024)
        on_extract(5, 5)
        return "152.0"

    def _install(self, answers, plasma=False, pkg=True, addon_fails=False, gui_error=None, desktop_error=None,
                 progress=None):
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
             mock.patch("myfox.desktop.write_entry", side_effect=desktop_error or record("desktop")):
            installer.install(answers, progress or (lambda message, fraction: self.reports.append((message, fraction))))

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

    def test_doh_off_is_written_only_when_unticked(self):
        with mock.patch("myfox.apply.apply_doh_off") as off:
            self._install(Answers(install_dir=str(self.install_dir)))
            off.assert_not_called()
            self._install(Answers(install_dir=str(self.install_dir), doh=False))
            off.assert_called_once_with(self.profile_dir)

    def _source(self) -> Path:
        source = self.tmp_path / "other" / "a.default"
        source.mkdir(parents=True)
        (source / "prefs.js").write_text('user_pref("services.sync.username", "me");\n', encoding="utf-8")
        (source / "places.sqlite").write_text("x" * 5000, encoding="utf-8")
        (source / "signedInUser.json").write_text("{}", encoding="utf-8")
        return source

    def test_an_import_copies_into_the_new_profile_before_the_tweaks(self):
        source = self._source()
        seen = []
        with mock.patch("myfox.importer.copy_profile", wraps=importer.copy_profile) as copy:
            self._install(Answers(install_dir=str(self.install_dir), import_from=str(source)),
                          progress=lambda m, f: seen.append(m))
            copy.assert_called_once()
        self.assertTrue((self.profile_dir / "places.sqlite").is_file())
        self.assertFalse((self.profile_dir / "signedInUser.json").exists())  # sync: none
        self.assertTrue((source / "signedInUser.json").is_file())
        self.assertIn(i18n.t("progress_import_start"), seen)
        self.assertEqual(importer.read_origin(self.profile_dir), {"source": str(source), "sync": "none", "moved": False, "backups": []})

    def test_moving_sync_signs_the_source_out_with_a_backup(self):
        source = self._source()
        self._install(Answers(install_dir=str(self.install_dir), import_from=str(source), sync=importer.SYNC_MOVE))
        self.assertTrue((self.profile_dir / "signedInUser.json").is_file())
        self.assertFalse((source / "signedInUser.json").exists())
        self.assertEqual(sorted(Path(p).name for p in importer.read_origin(self.profile_dir)["backups"]),
                         ["prefs.js.myfox-backup", "signedInUser.json.myfox-backup"])

    def test_a_failed_import_install_gives_the_source_its_account_back(self):
        source = self._source()
        with mock.patch("myfox.state.State.save", side_effect=OSError("disk full")), self.assertRaises(OSError):
            self._install(Answers(install_dir=str(self.install_dir), import_from=str(source),
                                  sync=importer.SYNC_MOVE))
        self.assertTrue((source / "signedInUser.json").is_file())
        self.assertIn("services.sync.username", (source / "prefs.js").read_text(encoding="utf-8"))
        self.assertFalse(self.profile_dir.exists())

    def test_a_newer_profile_is_opened_once_with_allow_downgrade(self):
        source = self._source()
        with mock.patch("myfox.importer.accept_downgrade") as accept:
            self._install(Answers(install_dir=str(self.install_dir), import_from=str(source)))
            accept.assert_not_called()
        with mock.patch("myfox.importer.accept_downgrade") as accept:
            self._install(Answers(install_dir=str(self.install_dir), import_from=str(source), allow_downgrade=True))
            accept.assert_called_once_with(self.install_dir, self.profile_dir)

    def test_firefox_command_when_asked(self):
        with mock.patch("myfox.command.enable") as enable, \
             mock.patch("myfox.command.check", return_value=["note"]):
            self._install(Answers(install_dir=str(self.install_dir), firefox_command=True))
            enable.assert_called_once_with(self.install_dir)
        with mock.patch("myfox.command.enable") as enable:
            answers = Answers(install_dir=str(self.install_dir))
            self._install(answers)
            enable.assert_not_called()

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


    def test_stopped_during_the_download_it_takes_everything_back(self):
        def progress(message, fraction):
            if fraction > 0.2:
                raise Cancelled()

        with self.assertRaises(Cancelled):
            self._install(Answers(install_dir=str(self.install_dir / "deep")), progress=progress)
        self.assertEqual(self.calls, ["tarball"])
        self.assertFalse(self.install_dir.exists())  # with the parent made for it
        self.assertIsNone(State().get("install_dir"))

    def test_a_failure_later_takes_back_the_new_profile_and_firefox(self):
        with self.assertRaises(OSError), mock.patch("myfox.profiles.unpin_install") as unpin:
            self._install(Answers(install_dir=str(self.install_dir)), desktop_error=OSError("disk full"))
        self.assertFalse(self.install_dir.exists())
        self.assertFalse(self.profile_dir.exists())
        unpin.assert_called_once_with("HASH")
        self.assertIsNone(State().get("install_dir"))

    def test_a_picked_profile_and_an_existing_folder_stay(self):
        self.install_dir.mkdir()
        with self.assertRaises(OSError):
            self._install(Answers(install_dir=str(self.install_dir), profile_dir=str(self.profile_dir)),
                          desktop_error=OSError("disk full"))
        self.assertTrue(self.profile_dir.is_dir())
        self.assertEqual(list(self.install_dir.iterdir()), [])

    def test_a_stop_at_the_very_end_is_too_late(self):
        def progress(message, fraction):
            if fraction == 1.0:
                raise Cancelled()

        self._install(Answers(install_dir=str(self.install_dir)), progress=progress)
        self.assertEqual(State().get("install_dir"), str(self.install_dir))


if __name__ == "__main__":
    unittest.main()
