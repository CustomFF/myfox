from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
        self.assertTrue(os.access(wrapper, os.X_OK))
        self.assertIn(f'exec "{self.install_dir / "firefox"}" "$@"', wrapper.read_text(encoding="utf-8"))

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
        self.assertTrue((share / "autoconfig").is_dir() and (share / "chrome").is_dir())
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
