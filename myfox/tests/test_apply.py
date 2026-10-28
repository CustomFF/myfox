from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from myfox import apply, paths

from ._helpers import IsolatedStateCase, make_tweaks


class _TweaksCase(IsolatedStateCase):
    """A small tweaks tree in paths.tweaks_dir() (under a throwaway
    XDG_DATA_HOME), which apply.py copies from."""

    def setUp(self):
        super().setUp()
        make_tweaks(paths.tweaks_dir())


class ApplyAutoconfigTests(_TweaksCase):

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

    def test_also_applies_to_a_staged_firefox_update(self):
        with tempfile.TemporaryDirectory() as d:
            install_dir = Path(d)
            staged = install_dir / "updated"
            stale = staged / "myfox" / "00-common.js"
            stale.parent.mkdir(parents=True)
            stale.write_text("old", encoding="utf-8")
            apply.apply_autoconfig(install_dir)
            self.assertNotEqual(stale.read_text(encoding="utf-8"), "old")
            self.assertTrue((staged / "myfox.cfg").is_file())
            self.assertTrue((staged / "defaults" / "pref" / "autoconfig.js").is_file())
            self.assertFalse((staged / "updated").exists())

    def test_leaves_alone_an_install_with_no_staged_update(self):
        with tempfile.TemporaryDirectory() as d:
            install_dir = Path(d)
            apply.apply_autoconfig(install_dir)
            self.assertFalse((install_dir / "updated").exists())


class ApplyChromeTests(_TweaksCase):
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

    def test_copies_any_directory_the_tweaks_ship(self):
        author = paths.chrome_dir() / "author"
        author.mkdir()
        (author / "10-z.css").write_text("/* author */\n", encoding="utf-8")
        with tempfile.TemporaryDirectory() as d:
            profile_dir = Path(d)
            apply.apply_chrome(profile_dir)
            stray = profile_dir / "chrome" / "author" / "99-stray.css"
            stray.write_text("x", encoding="utf-8")
            apply.apply_chrome(profile_dir)
            self.assertTrue((profile_dir / "chrome" / "author" / "10-z.css").is_file())
            self.assertFalse(stray.exists())


class ApplyDohOffTests(unittest.TestCase):
    def test_writes_the_opt_out_next_to_the_theme_and_survives_a_theme_rewrite(self):
        with tempfile.TemporaryDirectory() as d:
            profile_dir = Path(d)
            apply.apply_theme_pref(profile_dir, "dark")
            apply.apply_doh_off(profile_dir)
            apply.apply_theme_pref(profile_dir, "light")
            lines = (profile_dir / "user.js").read_text(encoding="utf-8").splitlines()
        self.assertEqual(sorted(lines), ['user_pref("myfox.doh", false);', 'user_pref("myfox.theme", "light");'])


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


class ProfileThemeTests(IsolatedStateCase):
    def test_tweaking_again_keeps_the_theme_the_profile_was_given(self):
        # An import picks its own theme: a refresh mustn't bring the install's back.
        profile_dir = self.tmp_path / "p"
        profile_dir.mkdir()
        apply.apply_theme_pref(profile_dir, "light")
        state = mock.Mock(get=lambda key, default=None: {"theme": "dark"}.get(key, default))
        with mock.patch("myfox.apply.apply_chrome"), mock.patch("myfox.addons.fetch_themes", return_value=(None, [])):
            apply.tweak_profile(profile_dir, state)
        self.assertEqual(apply.profile_theme(profile_dir), "light")


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

            with mock.patch("myfox.apply.latest_ddblm_release") as latest:
                version = apply.apply_bookmarklets(profile_dir, local_dir=str(ddblm))

            latest.assert_not_called()
            self.assertIsNone(version)  # a checkout has no version to record
            self.assertTrue((profile_dir / "chrome" / "blm_panel.css").is_file())
            self.assertTrue((profile_dir / "chrome" / "panel-icons" / "foo.svg").is_file())

    def test_unreachable_ddblm_keeps_the_recorded_version_without_raising(self):
        with tempfile.TemporaryDirectory() as d:
            profile_dir = Path(d)
            with mock.patch("urllib.request.urlopen", side_effect=OSError("network down")):
                result = apply.apply_bookmarklets(profile_dir, local_dir=None, current="ddblm-1")
            self.assertEqual(result, "ddblm-1")

    def _fetch_all(self, profile_dir, fetched, **kwargs):
        def fake_fetch(rel, out, local_dir, ref):
            fetched.append((rel, ref))
            out.write_text("/* css */" if rel.endswith(".css") else "<svg/>", encoding="utf-8")
            return True

        with mock.patch("myfox.apply._ddblm_fetch", side_effect=fake_fetch):
            return apply.apply_bookmarklets(profile_dir, **kwargs)

    def test_the_latest_version_comes_from_its_commit_and_is_returned(self):
        with tempfile.TemporaryDirectory() as d:
            fetched: list = []
            release = apply.DdblmRelease("ddblm-20261015123456", "abc123")
            with mock.patch("myfox.apply.latest_ddblm_release", return_value=release):
                version = self._fetch_all(Path(d), fetched, current="ddblm-20261001000000")
            self.assertEqual(version, "ddblm-20261015123456")
            self.assertEqual({ref for _rel, ref in fetched}, {"abc123"})

    def test_the_recorded_version_is_not_downloaded_again(self):
        with tempfile.TemporaryDirectory() as d:
            profile_dir = Path(d)
            (profile_dir / "chrome").mkdir()
            (profile_dir / "chrome" / "blm_panel.css").write_text("/* css */", encoding="utf-8")
            fetched: list = []
            release = apply.DdblmRelease("ddblm-1", "abc123")
            version = self._fetch_all(profile_dir, fetched, current="ddblm-1", release=release)
            self.assertEqual(version, "ddblm-1")
            self.assertEqual(fetched, [])

    def test_without_github_it_takes_master_and_records_nothing_new(self):
        with tempfile.TemporaryDirectory() as d:
            fetched: list = []
            with mock.patch("myfox.apply.latest_ddblm_release", side_effect=OSError("rate limited")):
                version = self._fetch_all(Path(d), fetched, current="ddblm-1")
            self.assertEqual(version, "ddblm-1")
            self.assertEqual({ref for _rel, ref in fetched}, {"master"})

    def test_latest_release_is_the_newest_commit_of_the_css_or_the_icons(self):
        answers = {"docs/blm_panel.css": [{"sha": "old", "commit": {"committer": {"date": "2026-10-01T00:00:00Z"}}}],
                   "icons": [{"sha": "new", "commit": {"committer": {"date": "2026-10-15T12:34:56Z"}}}]}

        def fake_urlopen(req, timeout):
            path = req.full_url.split("path=")[1].split("&")[0]
            return mock.MagicMock(**{"__enter__.return_value.read.return_value": json.dumps(answers[path]).encode()})

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            self.assertEqual(apply.latest_ddblm_release(), apply.DdblmRelease("ddblm-20261015123456", "new"))
        self.assertEqual(apply.ddblm_display("ddblm-20261015123456"), "2026-10-15 12:34")

    def test_extracts_icon_names_referenced_in_css_when_no_local_checkout(self):
        with tempfile.TemporaryDirectory() as d:
            profile_dir = Path(d)
            fetched: list[str] = []

            def fake_fetch(rel, out, local_dir, ref):
                fetched.append(rel)
                if rel == "docs/blm_panel.css":
                    out.write_text('background: url("panel-icons/gallery.svg");', encoding="utf-8")
                else:
                    out.write_text("<svg/>", encoding="utf-8")
                return True

            with mock.patch("myfox.apply._ddblm_fetch", side_effect=fake_fetch), \
                 mock.patch("myfox.apply.latest_ddblm_release", return_value=None):
                apply.apply_bookmarklets(profile_dir, local_dir=None)

            self.assertIn("icons/gallery.svg", fetched)
            self.assertIn("icons/import-bookmarklets.svg", fetched)


if __name__ == "__main__":
    unittest.main()
