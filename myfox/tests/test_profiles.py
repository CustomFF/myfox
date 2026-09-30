from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from myfox import profiles


class IsolatedHomeCase(unittest.TestCase):
    """Every profiles.py entry point walks from $HOME/$XDG_CONFIG_HOME —
    point both at a throwaway directory so nothing here can ever touch a
    real ~/.mozilla or ~/.config/mozilla."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        env = {"HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home / ".config")}
        patcher = mock.patch.dict("os.environ", env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)


class NativeDirTests(IsolatedHomeCase):
    def test_prefers_legacy_path_when_it_exists(self):
        (self.home / ".mozilla" / "firefox").mkdir(parents=True)
        self.assertEqual(profiles.native_dir(), self.home / ".mozilla" / "firefox")

    def test_falls_back_to_xdg_path_otherwise(self):
        self.assertEqual(profiles.native_dir(), self.home / ".config" / "mozilla" / "firefox")


class ParseAndResolveTests(IsolatedHomeCase):
    INI_TEXT = (
        "[Profile0]\nName=default\nIsRelative=1\nPath=abc.default\nDefault=1\n\n"
        "[Profile1]\nName=myfox\nIsRelative=1\nPath=myfox-1\n\n"
        "[Profile2]\nName=absolute\nIsRelative=0\nPath=/somewhere/else\n"
    )

    def _write_ini(self) -> Path:
        store = self.home / ".mozilla" / "firefox"
        store.mkdir(parents=True)
        ini = store / "profiles.ini"
        ini.write_text(self.INI_TEXT, encoding="utf-8")
        return ini

    def test_parses_all_profile_sections(self):
        ini = self._write_ini()
        entries = profiles.parse_profiles(ini)
        self.assertEqual([e.section for e in entries], ["Profile0", "Profile1", "Profile2"])
        self.assertTrue(entries[0].is_default)
        self.assertFalse(entries[1].is_default)

    def test_resolve_dir_relative_and_absolute(self):
        ini = self._write_ini()
        entries = profiles.parse_profiles(ini)
        ini_dir = ini.parent
        self.assertEqual(profiles.resolve_dir(ini_dir, entries[1]), ini_dir / "myfox-1")
        self.assertEqual(profiles.resolve_dir(ini_dir, entries[2]), Path("/somewhere/else"))

    def test_find_ini_locates_it(self):
        ini = self._write_ini()
        self.assertEqual(profiles.find_ini(), ini)

    def test_find_ini_returns_none_when_absent(self):
        self.assertIsNone(profiles.find_ini())


class ListMyfoxTests(IsolatedHomeCase):
    def test_lists_entries_from_ini_plus_orphaned_created_dirs(self):
        store = self.home / ".mozilla" / "firefox"
        store.mkdir(parents=True)
        (store / "profiles.ini").write_text(
            "[Profile0]\nName=myfox\nIsRelative=1\nPath=myfox-1\n", encoding="utf-8"
        )
        (store / "myfox-1").mkdir()
        # orphan: has the marker but no profiles.ini entry (left by uninstall)
        (store / "myfox-2").mkdir()
        (store / "myfox-2" / ".myfox-created").write_text("", encoding="utf-8")
        # decoy: myfox-* dir with neither an ini entry nor the marker
        (store / "myfox-3").mkdir()

        result = profiles.list_myfox()
        paths = {p.name for p, _name in result}
        self.assertEqual(paths, {"myfox-1", "myfox-2"})

    def test_empty_store_gives_empty_list(self):
        self.assertEqual(profiles.list_myfox(), [])


class CreateNewTests(IsolatedHomeCase):
    def test_creates_profiles_ini_when_none_exists(self):
        profile_dir = profiles.create_new()
        self.assertTrue(profile_dir.is_dir())
        self.assertTrue((profile_dir / ".myfox-created").is_file())
        ini = profiles.find_ini()
        self.assertIsNotNone(ini)
        entries = profiles.parse_profiles(ini)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].path, "myfox-1")

    def test_numbering_skips_existing_myfox_dirs(self):
        store = self.home / ".mozilla" / "firefox"
        store.mkdir(parents=True)
        (store / "myfox-1").mkdir()
        profile_dir = profiles.create_new()
        self.assertEqual(profile_dir.name, "myfox-2")

    def test_second_call_reuses_the_next_free_section_number(self):
        first = profiles.create_new()
        second = profiles.create_new()
        self.assertNotEqual(first, second)
        ini = profiles.find_ini()
        entries = profiles.parse_profiles(ini)
        self.assertEqual([e.section for e in entries], ["Profile0", "Profile1"])


class SectionRoundTripTests(IsolatedHomeCase):
    def test_write_then_read_then_remove(self):
        ini = self.home / "test.ini"
        profiles.write_install_section(ini, "InstallABCD1234", "myfox-1")
        text = ini.read_text(encoding="utf-8")
        self.assertIn("[InstallABCD1234]", text)
        self.assertIn("Default=myfox-1", text)
        self.assertIn("Locked=1", text)

        profiles.remove_ini_section(ini, "InstallABCD1234")
        self.assertNotIn("[InstallABCD1234]", ini.read_text(encoding="utf-8"))

    def test_write_replaces_an_existing_section_of_the_same_name(self):
        ini = self.home / "test.ini"
        profiles.write_install_section(ini, "InstallX", "old-path")
        profiles.write_install_section(ini, "InstallX", "new-path")
        text = ini.read_text(encoding="utf-8")
        self.assertEqual(text.count("[InstallX]"), 1)
        self.assertIn("Default=new-path", text)
        self.assertNotIn("old-path", text)

    def test_remove_leaves_unrelated_sections_untouched(self):
        ini = self.home / "test.ini"
        ini.write_text("[Keep]\nA=1\n\n[Drop]\nB=2\n\n[AlsoKeep]\nC=3\n", encoding="utf-8")
        profiles.remove_ini_section(ini, "Drop")
        text = ini.read_text(encoding="utf-8")
        self.assertIn("[Keep]", text)
        self.assertIn("[AlsoKeep]", text)
        self.assertNotIn("[Drop]", text)


class RegisterEntryTests(IsolatedHomeCase):
    def test_registers_a_new_relative_entry(self):
        store = self.home / ".mozilla" / "firefox"
        store.mkdir(parents=True)
        ini = store / "profiles.ini"
        ini.write_text("", encoding="utf-8")
        profile_dir = store / "myfox-1"
        profile_dir.mkdir()

        path_value = profiles.register_entry(ini, profile_dir)
        self.assertEqual(path_value, "myfox-1")
        entries = profiles.parse_profiles(ini)
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0].is_relative)

    def test_is_idempotent_for_the_same_directory(self):
        store = self.home / ".mozilla" / "firefox"
        store.mkdir(parents=True)
        ini = store / "profiles.ini"
        ini.write_text("", encoding="utf-8")
        profile_dir = store / "myfox-1"
        profile_dir.mkdir()

        first = profiles.register_entry(ini, profile_dir)
        second = profiles.register_entry(ini, profile_dir)
        self.assertEqual(first, second)
        self.assertEqual(len(profiles.parse_profiles(ini)), 1)


class RemoveMyfoxSectionTests(IsolatedHomeCase):
    def test_removes_only_the_matching_directorys_section(self):
        store = self.home / ".mozilla" / "firefox"
        store.mkdir(parents=True)
        ini = store / "profiles.ini"
        ini.write_text(
            "[Profile0]\nName=myfox\nIsRelative=1\nPath=myfox-1\n\n"
            "[Profile1]\nName=other-myfox-install\nIsRelative=1\nPath=myfox-2\n",
            encoding="utf-8",
        )
        (store / "myfox-1").mkdir()
        (store / "myfox-2").mkdir()

        profiles.remove_myfox_section(store / "myfox-1")
        text = ini.read_text(encoding="utf-8")
        self.assertNotIn("[Profile0]", text)
        self.assertIn("[Profile1]", text)  # the *other* myfox install survives


class PinInstallTests(IsolatedHomeCase):
    """headless_once/install_hash_fresh call a real Firefox binary — mocked
    here via subprocess.run's side effect writing the section Firefox would
    have written, so the diff logic gets exercised for real. The actual
    binary path is verified once, live, in scratch/ (see commit)."""

    def _make_store_with_ini(self) -> Path:
        store = self.home / ".mozilla" / "firefox"
        store.mkdir(parents=True)
        (store / "profiles.ini").write_text("", encoding="utf-8")
        return store

    def test_headless_once_detects_a_freshly_written_install_section(self):
        store = self._make_store_with_ini()
        install_dir = self.home / "install"
        install_dir.mkdir()
        binary = install_dir / "firefox"
        binary.write_text("#!/bin/sh\n", encoding="utf-8")
        binary.chmod(0o755)
        our_profile = store / "myfox-1"
        our_profile.mkdir()

        def fake_run(*args, **kwargs):
            ini = store / "profiles.ini"
            ini.write_text(ini.read_text(encoding="utf-8") + "[InstallDEADBEEF]\nDefault=myfox-1\n", encoding="utf-8")
            return mock.Mock(returncode=0)

        with mock.patch("subprocess.run", side_effect=fake_run):
            result = profiles.headless_once(install_dir, our_profile)
        self.assertEqual(result, "DEADBEEF")

    def test_headless_once_purges_a_stray_profile_it_did_not_ask_for(self):
        store = self._make_store_with_ini()
        install_dir = self.home / "install"
        install_dir.mkdir()
        binary = install_dir / "firefox"
        binary.write_text("#!/bin/sh\n", encoding="utf-8")
        binary.chmod(0o755)
        our_profile = store / "myfox-1"
        our_profile.mkdir()

        def fake_run(*args, **kwargs):
            # Simulates Firefox creating its own throwaway first-run profile
            # during the headless pass, with no [Install<HASH>] at all.
            stray = store / "abcd1234.default-release"
            stray.mkdir()
            (stray / "prefs.js").write_text("", encoding="utf-8")
            return mock.Mock(returncode=0)

        with mock.patch("subprocess.run", side_effect=fake_run):
            result = profiles.headless_once(install_dir, our_profile)

        self.assertIsNone(result)  # no hash was ever written, by design of this fake
        self.assertFalse((store / "abcd1234.default-release").exists())

    def test_headless_once_returns_none_without_an_executable_binary(self):
        store = self._make_store_with_ini()
        install_dir = self.home / "install"
        install_dir.mkdir()  # no firefox binary at all
        self.assertIsNone(profiles.headless_once(install_dir, store / "myfox-1"))

    def test_pin_install_writes_both_ini_files(self):
        store = self._make_store_with_ini()
        install_dir = self.home / "install"
        install_dir.mkdir()
        binary = install_dir / "firefox"
        binary.write_text("#!/bin/sh\n", encoding="utf-8")
        binary.chmod(0o755)
        our_profile = store / "myfox-1"
        our_profile.mkdir()

        def fake_run(*args, **kwargs):
            ini = store / "profiles.ini"
            ini.write_text(ini.read_text(encoding="utf-8") + "[InstallCAFE]\nDefault=x\n", encoding="utf-8")
            return mock.Mock(returncode=0)

        with mock.patch("subprocess.run", side_effect=fake_run):
            result_hash = profiles.pin_install(install_dir, our_profile, saved_hash=None)

        self.assertEqual(result_hash, "CAFE")
        ini_text = (store / "profiles.ini").read_text(encoding="utf-8")
        self.assertIn("[InstallCAFE]", ini_text)
        self.assertIn("Default=myfox-1", ini_text)
        installs_text = (store / "installs.ini").read_text(encoding="utf-8")
        self.assertIn("[CAFE]", installs_text)
        self.assertIn("Default=myfox-1", installs_text)

    def test_pin_install_reuses_a_saved_hash_already_present(self):
        store = self._make_store_with_ini()
        # Real Firefox hashes are hex only ([0-9A-F]) — the section-matching
        # regex depends on that, so the fixture has to look like a real one.
        (store / "profiles.ini").write_text("[InstallCAFEBABE]\nDefault=old\n", encoding="utf-8")
        install_dir = self.home / "install"
        install_dir.mkdir()
        our_profile = store / "myfox-1"
        our_profile.mkdir()

        with mock.patch("subprocess.run") as run:
            result_hash = profiles.pin_install(install_dir, our_profile, saved_hash="CAFEBABE")

        run.assert_not_called()
        self.assertEqual(result_hash, "CAFEBABE")

    def test_unpin_removes_from_both_files(self):
        store = self._make_store_with_ini()
        (store / "profiles.ini").write_text("[InstallCAFE]\nDefault=x\n", encoding="utf-8")
        (store / "installs.ini").write_text("[CAFE]\nDefault=x\n", encoding="utf-8")

        profiles.unpin_install("CAFE")

        self.assertNotIn("[InstallCAFE]", (store / "profiles.ini").read_text(encoding="utf-8"))
        self.assertNotIn("[CAFE]", (store / "installs.ini").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
