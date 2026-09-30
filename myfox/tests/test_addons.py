from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from myfox import addons


class InstallThemesTests(unittest.TestCase):
    def test_copies_both_bundled_xpis_using_the_fixed_ids(self):
        with tempfile.TemporaryDirectory() as d:
            profile_dir = Path(d)
            missing = addons.install_themes(profile_dir)
            self.assertEqual(missing, [])
            ext = profile_dir / "extensions"
            self.assertTrue((ext / f"{addons.MYFOX_THEME_DARK_ID}.xpi").is_file())
            self.assertTrue((ext / f"{addons.MYFOX_THEME_LIGHT_ID}.xpi").is_file())

    def test_reports_missing_bundled_assets_instead_of_raising(self):
        with tempfile.TemporaryDirectory() as d, \
             mock.patch("myfox.paths.themes_dir", return_value=Path(d) / "nowhere"):
            missing = addons.install_themes(Path(d) / "profile")
        self.assertCountEqual(missing, [addons.MYFOX_THEME_DARK_ID, addons.MYFOX_THEME_LIGHT_ID])


class IsPlasmaSessionTests(unittest.TestCase):
    def test_true_for_kde_in_xdg_current_desktop(self):
        with mock.patch.dict("os.environ", {"XDG_CURRENT_DESKTOP": "KDE"}, clear=True):
            self.assertTrue(addons.is_plasma_session())

    def test_true_for_kde_among_several_colon_separated_desktops(self):
        with mock.patch.dict("os.environ", {"XDG_CURRENT_DESKTOP": "ubuntu:GNOME:KDE"}, clear=True):
            self.assertTrue(addons.is_plasma_session())

    def test_true_via_kde_full_session_fallback(self):
        with mock.patch.dict("os.environ", {"KDE_FULL_SESSION": "true"}, clear=True):
            self.assertTrue(addons.is_plasma_session())

    def test_false_for_gnome(self):
        with mock.patch.dict("os.environ", {"XDG_CURRENT_DESKTOP": "GNOME"}, clear=True):
            self.assertFalse(addons.is_plasma_session())


class PkgInstalledTests(unittest.TestCase):
    def test_true_when_the_manifest_exists_in_an_override_dir(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "org.kde.plasma.browser_integration.json").write_text("{}", encoding="utf-8")
            with mock.patch.dict("os.environ", {"MYFOX_NMH_DIRS": d}, clear=True):
                self.assertTrue(addons.pkg_installed())

    def test_false_when_absent_everywhere_searched(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.dict("os.environ", {"MYFOX_NMH_DIRS": d}, clear=True):
                self.assertFalse(addons.pkg_installed())


class PkgInstallHintTests(unittest.TestCase):
    def test_prefers_apt_when_present(self):
        with mock.patch("shutil.which", side_effect=lambda c: "/usr/bin/apt-get" if c == "apt-get" else None):
            self.assertIn("apt", addons.pkg_install_hint())

    def test_none_when_no_known_package_manager_is_present(self):
        with mock.patch("shutil.which", return_value=None):
            self.assertIsNone(addons.pkg_install_hint())


class AmoTests(unittest.TestCase):
    def _fake_response(self, body: bytes):
        cm = mock.MagicMock()
        cm.__enter__.return_value.read.return_value = body
        return cm

    def test_addon_guid_extracts_from_the_api_response(self):
        body = b'{"guid": "extension@example.com", "name": "Whatever"}'
        with mock.patch("urllib.request.urlopen", return_value=self._fake_response(body)):
            self.assertEqual(addons.addon_guid("some-slug"), "extension@example.com")

    def test_addon_guid_returns_none_on_network_failure(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("down")):
            self.assertIsNone(addons.addon_guid("some-slug"))

    def test_addon_fetch_writes_a_valid_looking_xpi(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "addon.xpi"
            with mock.patch("urllib.request.urlopen", return_value=self._fake_response(b"PK\x03\x04rest")):
                self.assertTrue(addons.addon_fetch("some-slug", out))
            self.assertTrue(out.is_file())

    def test_addon_fetch_rejects_a_non_zip_response(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "addon.xpi"
            with mock.patch("urllib.request.urlopen", return_value=self._fake_response(b"<html>not an xpi")):
                self.assertFalse(addons.addon_fetch("some-slug", out))
            self.assertFalse(out.exists())

    def test_apply_amo_addons_reports_a_slug_whose_guid_never_resolved(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch("myfox.addons.addon_guid", return_value=None):
                failed = addons.apply_amo_addons(Path(d), ["missing-slug"])
        self.assertEqual(failed, ["missing-slug"])

    def test_apply_amo_addons_installs_a_resolved_slug(self):
        with tempfile.TemporaryDirectory() as d:
            profile_dir = Path(d)
            with mock.patch("myfox.addons.addon_guid", return_value="addon@example.com"), \
                 mock.patch("myfox.addons.addon_fetch", return_value=True) as fetch:
                failed = addons.apply_amo_addons(profile_dir, ["plasma-integration"])
            self.assertEqual(failed, [])
            fetch.assert_called_once_with("plasma-integration", profile_dir / "extensions" / "addon@example.com.xpi")


if __name__ == "__main__":
    unittest.main()
