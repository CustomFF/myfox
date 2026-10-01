from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from myfox import addons


class FetchThemesTests(unittest.TestCase):
    def _fake_response(self, body: bytes):
        cm = mock.MagicMock()
        cm.__enter__.return_value.read.return_value = body
        return cm

    def test_local_dir_copies_both_signed_xpis(self):
        with tempfile.TemporaryDirectory() as d:
            local = Path(d) / "tweaks-checkout" / "build" / "signed"
            local.mkdir(parents=True)
            (local / "myfox-dark.xpi").write_bytes(b"dark")
            (local / "myfox-light.xpi").write_bytes(b"light")

            profile_dir = Path(d) / "profile"
            missing = addons.fetch_themes(profile_dir, local_dir=str(Path(d) / "tweaks-checkout"))

            self.assertEqual(missing, [])
            ext = profile_dir / "extensions"
            self.assertEqual((ext / f"{addons.MYFOX_THEME_DARK_ID}.xpi").read_bytes(), b"dark")
            self.assertEqual((ext / f"{addons.MYFOX_THEME_LIGHT_ID}.xpi").read_bytes(), b"light")

    def test_local_dir_reports_missing_files_instead_of_raising(self):
        with tempfile.TemporaryDirectory() as d:
            missing = addons.fetch_themes(Path(d) / "profile", local_dir=str(Path(d) / "nowhere"))
        self.assertCountEqual(missing, [addons.MYFOX_THEME_DARK_ID, addons.MYFOX_THEME_LIGHT_ID])

    def test_fetches_both_xpis_from_the_latest_themes_release(self):
        release_json = {
            "assets": [
                {"name": "myfox-dark.xpi", "browser_download_url": "https://example/dark"},
                {"name": "myfox-light.xpi", "browser_download_url": "https://example/light"},
            ]
        }
        responses = {
            "https://api.github.com/repos/CustomFF/tweaks/releases/tags/themes-20261001": self._fake_response(
                json.dumps(release_json).encode("utf-8")
            ),
            "https://example/dark": self._fake_response(b"dark"),
            "https://example/light": self._fake_response(b"light"),
        }

        def fake_urlopen(req, timeout=None):
            return responses[req.full_url]

        with mock.patch("myfox.version.latest_tag", return_value="themes-20261001"), \
             mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with tempfile.TemporaryDirectory() as d:
                profile_dir = Path(d)
                missing = addons.fetch_themes(profile_dir)

                self.assertEqual(missing, [])
                ext = profile_dir / "extensions"
                self.assertEqual((ext / f"{addons.MYFOX_THEME_DARK_ID}.xpi").read_bytes(), b"dark")
                self.assertEqual((ext / f"{addons.MYFOX_THEME_LIGHT_ID}.xpi").read_bytes(), b"light")

    def test_no_themes_release_found_reports_both_missing(self):
        with mock.patch("myfox.version.latest_tag", return_value=None):
            with tempfile.TemporaryDirectory() as d:
                missing = addons.fetch_themes(Path(d))
        self.assertCountEqual(missing, [addons.MYFOX_THEME_DARK_ID, addons.MYFOX_THEME_LIGHT_ID])

    def test_release_missing_one_asset_reports_only_that_one(self):
        release_json = {"assets": [{"name": "myfox-dark.xpi", "browser_download_url": "https://example/dark"}]}
        responses = {
            "https://api.github.com/repos/CustomFF/tweaks/releases/tags/themes-20261001": self._fake_response(
                json.dumps(release_json).encode("utf-8")
            ),
            "https://example/dark": self._fake_response(b"dark"),
        }

        def fake_urlopen(req, timeout=None):
            return responses[req.full_url]

        with mock.patch("myfox.version.latest_tag", return_value="themes-20261001"), \
             mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with tempfile.TemporaryDirectory() as d:
                missing = addons.fetch_themes(Path(d))

        self.assertEqual(missing, [addons.MYFOX_THEME_LIGHT_ID])

    def test_release_lookup_network_failure_reports_both_missing(self):
        with mock.patch("myfox.version.latest_tag", return_value="themes-20261001"), \
             mock.patch("urllib.request.urlopen", side_effect=OSError("down")):
            with tempfile.TemporaryDirectory() as d:
                missing = addons.fetch_themes(Path(d))
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
