from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import myfox
from myfox import desktop, launcher


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        patcher = mock.patch.dict("os.environ", {"XDG_DATA_HOME": str(self.root / "data")})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.install_dir = self.root / "firefox"
        self.install_dir.mkdir()

    def test_entry_runs_the_wrapper_and_offers_a_refresh_action(self):
        with mock.patch("myfox.desktop._refresh_menu_cache"):
            path = desktop.write_entry(self.install_dir, Path("/x/bin/myfox"))
        text = path.read_text(encoding="utf-8")
        wrapper = self.install_dir / "firefox-myfox"
        self.assertIn(f"Exec={wrapper} %u", text)
        self.assertIn("[Desktop Action myfox-refresh]\nExec=/x/bin/myfox refresh --gui", text)
        self.assertIn("myfox-refresh;", text.splitlines()[1])
        self.assertIn(f"[Desktop Action restart]\nExec={wrapper} --myfox-restart", text)
        self.assertIn("restart;", text.splitlines()[1])
        self.assertTrue(os.access(wrapper, os.X_OK))
        self.assertIn(f'exec "{self.install_dir / "firefox"}" "$@"', wrapper.read_text(encoding="utf-8"))

    def test_wrapper_started_from_a_deleted_directory_runs_firefox_from_home(self):
        with mock.patch("myfox.desktop._refresh_menu_cache"):
            desktop.write_entry(self.install_dir, Path("/x/bin/myfox"))
        firefox = self.install_dir / "firefox"
        out = self.root / "cwd"
        firefox.write_text(f'#!/bin/sh\n/bin/pwd > "{out}"\n', encoding="utf-8")
        firefox.chmod(0o755)
        gone = self.root / "gone"
        gone.mkdir()
        home = self.root / "home"
        home.mkdir()
        script = f'cd "{gone}" && rmdir "{gone}" && exec "{self.install_dir / "firefox-myfox"}"'
        subprocess.run(["sh", "-c", script], env={**os.environ, "HOME": str(home)},
                       stderr=subprocess.DEVNULL, check=True)
        self.assertEqual(out.read_text(encoding="utf-8").strip(), str(home.resolve()))

    def test_manifest_tells_the_browser_where_myfox_is_and_what_it_can_do(self):
        with mock.patch("myfox.desktop._refresh_menu_cache"):
            desktop.write_entry(self.install_dir, Path('/x/my "fox"/bin/myfox'))
        manifest = self.install_dir / "myfox.json"
        self.assertEqual(json.loads(manifest.read_text(encoding="utf-8")),
                         {"launcher": '/x/my "fox"/bin/myfox', "version": myfox.__version__, "features": ["command", "command-backup", "profiles", "update"]})
        self.assertEqual(stat.S_IMODE(manifest.stat().st_mode), 0o644)

    def test_manifest_has_the_installed_packages_version(self):
        package = self.root / "data" / "myfox" / "myfox"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text('__version__ = "9.9.9"\n', encoding="utf-8")
        desktop.write_manifest(self.install_dir, Path("/x/bin/myfox"))
        self.assertEqual(json.loads((self.install_dir / "myfox.json").read_text(encoding="utf-8"))["version"], "9.9.9")

    def test_menu_cache_refresh_tells_both_caches(self):
        present = {"update-desktop-database", "kbuildsycoca6", "kbuildsycoca5"}
        with mock.patch("shutil.which", side_effect=lambda name: name if name in present else None), \
             mock.patch("subprocess.run") as run:
            desktop._refresh_menu_cache()
        ran = [call.args[0][0] for call in run.call_args_list]
        self.assertEqual(ran, ["update-desktop-database", "kbuildsycoca6"])

    def test_templates_of_the_installed_myfox_win(self):
        # A core update lays down new templates before the old code writes.
        installed = self.root / "data" / "myfox" / "myfox" / "templates"
        installed.mkdir(parents=True)
        (installed / desktop.DESKTOP_NAME).write_text("[Desktop Entry]\nExec=@WRAPPER@ --new\n", encoding="utf-8")
        (installed / desktop.WRAPPER_NAME).write_text("#!/bin/sh\nexec \"@FIREFOX@\" \"$@\"\n", encoding="utf-8")
        with mock.patch("myfox.desktop._refresh_menu_cache"):
            path = desktop.write_entry(self.install_dir, Path("/x/bin/myfox"))
        self.assertEqual(path.read_text(encoding="utf-8"),
                         f"[Desktop Entry]\nExec={self.install_dir / 'firefox-myfox'} --new\n")
        self.assertIn(f'exec "{self.install_dir / "firefox"}" "$@"',
                      (self.install_dir / "firefox-myfox").read_text(encoding="utf-8"))

    def test_entry_texts_come_from_every_locale_catalog(self):
        # A translation is only a catalog: de.json here, with no template change.
        installed = self.root / "data" / "myfox" / "myfox"
        (installed / "templates").mkdir(parents=True)
        (installed / "templates" / desktop.DESKTOP_NAME).write_text(
            "[Desktop Entry]\nComment=@T:desktop_comment@\nName=@T:desktop_action_restart@\n", encoding="utf-8")
        (installed / "templates" / desktop.WRAPPER_NAME).write_text("#!/bin/sh\n", encoding="utf-8")
        (installed / "locales").mkdir()
        for lang, comment, restart in (("en", "Fast", "Restart"), ("de", "Schnell", "Restart"), ("ru", "Быстрый", "")):
            (installed / "locales" / f"{lang}.json").write_text(
                json.dumps({"desktop_comment": comment, "desktop_action_restart": restart}), encoding="utf-8")
        with mock.patch("myfox.desktop._refresh_menu_cache"):
            text = desktop.write_entry(self.install_dir, Path("/x/bin/myfox")).read_text(encoding="utf-8")
        # Untranslated (empty or the same as en) messages get no localized line.
        self.assertEqual(text, "[Desktop Entry]\nComment=Fast\nComment[de]=Schnell\nComment[ru]=Быстрый\n"
                               "Name=Restart\n")

    def test_shipped_entry_has_the_russian_texts(self):
        with mock.patch("myfox.desktop._refresh_menu_cache"):
            text = desktop.write_entry(self.install_dir, Path("/x/bin/myfox")).read_text(encoding="utf-8")
        self.assertIn("\nGenericName=Web Browser\nGenericName[ru]=Веб-браузер\n", text)
        self.assertIn("\nName=Restart\nName[ru]=Перезапустить\n", text)
        self.assertNotIn("@T:", text)

    def test_an_unchanged_entry_is_not_rewritten(self):
        with mock.patch("myfox.desktop._refresh_menu_cache") as refresh_cache:
            path = desktop.write_entry(self.install_dir, Path("/x/bin/myfox"))
            mtime = path.stat().st_mtime_ns
            desktop.write_entry(self.install_dir, Path("/x/bin/myfox"))
        self.assertEqual(refresh_cache.call_count, 1)
        self.assertEqual(path.stat().st_mtime_ns, mtime)

    def test_entry_is_named_after_the_installs_channel(self):
        for channel, name in (("release", "Firefox"), ("beta", "Firefox Beta")):
            prefs = self.install_dir / "defaults/pref/channel-prefs.js"
            prefs.parent.mkdir(parents=True, exist_ok=True)
            prefs.write_text(f'pref("app.update.channel", "{channel}");\n', encoding="utf-8")
            with mock.patch("myfox.desktop._refresh_menu_cache"):
                text = desktop.write_entry(self.install_dir, Path("/x/bin/myfox")).read_text(encoding="utf-8")
            self.assertIn(f"\nName={name}\n", text)
            self.assertIn(f"\nX-GNOME-FullName={name}\n", text)
        self.assertIn("\nComment[ru]=Быстрый и приватный браузер\n", text)
        self.assertNotIn("@", text.replace("%u", ""))

    def test_remove_entry(self):
        with mock.patch("myfox.desktop._refresh_menu_cache"):
            desktop.write_entry(self.install_dir, Path("/x/bin/myfox"))
            desktop.remove_entry()
        self.assertFalse(desktop.desktop_file().exists())


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        patcher = mock.patch.dict("os.environ", {"XDG_DATA_HOME": str(self.root / "data"),
                                                 "MYFOX_BIN_DIR": str(self.root / "bin")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_copies_itself_and_links_the_command(self):
        path = launcher.install_self()
        share = launcher.share_dir()
        self.assertTrue((share / "myfox" / "launcher.py").is_file())
        self.assertFalse((share / "myfox" / "tests").exists())
        self.assertEqual(Path(os.readlink(launcher.link_path())), path)
        self.assertIn(f'PYTHONPATH="{share}', path.read_text(encoding="utf-8"))

    def test_reinstalling_itself_leaves_the_browser_alone(self):
        browser = launcher.share_dir() / "firefox" / "firefox"
        browser.parent.mkdir(parents=True)
        browser.write_text("binary")
        launcher.install_self()
        self.assertTrue(browser.is_file())

    def test_remove_keeps_a_foreign_myfox_command(self):
        launcher.install_self()
        launcher.link_path().unlink()
        launcher.link_path().symlink_to("/usr/bin/true")
        launcher.remove_self()
        self.assertTrue(launcher.link_path().is_symlink())
        self.assertFalse(launcher.share_dir().exists())


if __name__ == "__main__":
    unittest.main()
