from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from myfox import apply


class ApplyAutoconfigTests(unittest.TestCase):
    """Copies from the *real* autoconfig/ in this checkout (paths.py
    resolves relative to myfox/, which lives in this repo) into a throwaway
    destination — exercises the real current tweaks, never touches the
    source, destination is always a tmp dir."""

    def test_copies_autoconfig_js_cfg_and_module_dir(self):
        with tempfile.TemporaryDirectory() as d:
            install_dir = Path(d)
            apply.apply_autoconfig(install_dir)
            self.assertTrue((install_dir / "defaults" / "pref" / "autoconfig.js").is_file())
            self.assertTrue((install_dir / "myfox.cfg").is_file())
            self.assertTrue((install_dir / "myfox" / "00-common.js").is_file())

    def test_removes_a_legacy_firefox_cfg(self):
        with tempfile.TemporaryDirectory() as d:
            install_dir = Path(d)
            install_dir.mkdir(exist_ok=True)
            (install_dir / "firefox.cfg").write_text("stale", encoding="utf-8")
            apply.apply_autoconfig(install_dir)
            self.assertFalse((install_dir / "firefox.cfg").exists())

    def test_replaces_the_myfox_module_dir_wholesale(self):
        with tempfile.TemporaryDirectory() as d:
            install_dir = Path(d)
            apply.apply_autoconfig(install_dir)
            stray = install_dir / "myfox" / "99-not-ours.js"
            stray.write_text("x", encoding="utf-8")
            apply.apply_autoconfig(install_dir)
            self.assertFalse(stray.exists())


class ApplyChromeTests(unittest.TestCase):
    def test_copies_agent_user_and_userchrome_sets_the_marker(self):
        with tempfile.TemporaryDirectory() as d:
            profile_dir = Path(d)
            backed_up = apply.apply_chrome(profile_dir)
            self.assertFalse(backed_up)
            self.assertTrue((profile_dir / "chrome" / "agent").is_dir())
            self.assertTrue((profile_dir / "chrome" / "user").is_dir())
            self.assertTrue((profile_dir / "chrome" / "userChrome.css").is_file())
            self.assertTrue((profile_dir / ".myfox").is_file())

    def test_backs_up_a_preexisting_userchrome_only_once(self):
        with tempfile.TemporaryDirectory() as d:
            profile_dir = Path(d)
            c_dir = profile_dir / "chrome"
            c_dir.mkdir(parents=True)
            (c_dir / "userChrome.css").write_text("/* user's own */", encoding="utf-8")

            first = apply.apply_chrome(profile_dir)
            self.assertTrue(first)
            backup = c_dir / "userChrome.css.myfox-backup"
            self.assertEqual(backup.read_text(encoding="utf-8"), "/* user's own */")

            # A second application (e.g. refresh) must not re-back-up over
            # our own now-installed userChrome.css.
            second = apply.apply_chrome(profile_dir)
            self.assertFalse(second)
            self.assertEqual(backup.read_text(encoding="utf-8"), "/* user's own */")

    def test_no_backup_once_the_myfox_marker_already_exists(self):
        with tempfile.TemporaryDirectory() as d:
            profile_dir = Path(d)
            (profile_dir / ".myfox").write_text("", encoding="utf-8")
            c_dir = profile_dir / "chrome"
            c_dir.mkdir(parents=True)
            (c_dir / "userChrome.css").write_text("/* ours already */", encoding="utf-8")

            backed_up = apply.apply_chrome(profile_dir)
            self.assertFalse(backed_up)
            self.assertFalse((c_dir / "userChrome.css.myfox-backup").exists())

    def test_replaces_agent_and_user_dirs_wholesale(self):
        with tempfile.TemporaryDirectory() as d:
            profile_dir = Path(d)
            apply.apply_chrome(profile_dir)
            stray = profile_dir / "chrome" / "agent" / "99-stray.css"
            stray.write_text("x", encoding="utf-8")
            apply.apply_chrome(profile_dir)
            self.assertFalse(stray.exists())


class ApplyThemePrefTests(unittest.TestCase):
    def test_writes_a_fresh_user_js(self):
        with tempfile.TemporaryDirectory() as d:
            profile_dir = Path(d)
            apply.apply_theme_pref(profile_dir, "dark")
            text = (profile_dir / "user.js").read_text(encoding="utf-8")
            self.assertIn('user_pref("myfox.theme", "dark");', text)

    def test_replaces_an_existing_line_without_duplicating(self):
        with tempfile.TemporaryDirectory() as d:
            profile_dir = Path(d)
            apply.apply_theme_pref(profile_dir, "dark")
            apply.apply_theme_pref(profile_dir, "light")
            text = (profile_dir / "user.js").read_text(encoding="utf-8")
            self.assertEqual(text.count("myfox.theme"), 1)
            self.assertIn('"light"', text)

    def test_preserves_other_existing_prefs(self):
        with tempfile.TemporaryDirectory() as d:
            profile_dir = Path(d)
            (profile_dir / "user.js").write_text('user_pref("some.other.pref", true);\n', encoding="utf-8")
            apply.apply_theme_pref(profile_dir, "dark")
            text = (profile_dir / "user.js").read_text(encoding="utf-8")
            self.assertIn("some.other.pref", text)
            self.assertIn("myfox.theme", text)


class ApplyBookmarkletsTests(unittest.TestCase):
    def test_uses_a_local_checkout_when_given(self):
        with tempfile.TemporaryDirectory() as d:
            profile_dir = Path(d) / "profile"
            profile_dir.mkdir()
            ddblm = Path(d) / "ddblm"
            (ddblm / "docs").mkdir(parents=True)
            (ddblm / "docs" / "blm_panel.css").write_text("/* panel */", encoding="utf-8")
            (ddblm / "icons").mkdir()
            (ddblm / "icons" / "foo.svg").write_text("<svg/>", encoding="utf-8")
            (ddblm / "icons" / "import-bookmarklets.svg").write_text("<svg/>", encoding="utf-8")

            gallery = apply.apply_bookmarklets(profile_dir, local_dir=str(ddblm))

            self.assertEqual(gallery, apply.DDBLM_GALLERY)
            self.assertTrue((profile_dir / "chrome" / "blm_panel.css").is_file())
            self.assertTrue((profile_dir / "chrome" / "panel-icons" / "foo.svg").is_file())

    def test_unreachable_ddblm_returns_none_without_raising(self):
        with tempfile.TemporaryDirectory() as d:
            profile_dir = Path(d)
            with mock.patch("urllib.request.urlopen", side_effect=OSError("network down")):
                result = apply.apply_bookmarklets(profile_dir, local_dir=None)
            self.assertIsNone(result)

    def test_extracts_icon_names_referenced_in_css_when_no_local_checkout(self):
        with tempfile.TemporaryDirectory() as d:
            profile_dir = Path(d)
            fetched: list[str] = []

            def fake_fetch(rel, out, local_dir):
                fetched.append(rel)
                if rel == "docs/blm_panel.css":
                    out.write_text('background: url("panel-icons/gallery.svg");', encoding="utf-8")
                else:
                    out.write_text("<svg/>", encoding="utf-8")
                return True

            with mock.patch("myfox.apply._ddblm_fetch", side_effect=fake_fetch):
                apply.apply_bookmarklets(profile_dir, local_dir=None)

            self.assertIn("icons/gallery.svg", fetched)
            self.assertIn("icons/import-bookmarklets.svg", fetched)


if __name__ == "__main__":
    unittest.main()
