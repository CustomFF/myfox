from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from myfox import importer
from myfox.install_form import Cancelled

PREFS = (
    '// Mozilla User Preferences\n'
    'user_pref("browser.startup.page", 3);\n'
    'user_pref("services.sync.client.GUID", "abc");\n'
    'user_pref("services.sync.username", "me@example.org");\n'
    'user_pref("services.sync.engine.passwords", false);\n'
    'user_pref("services.sync.declinedEngines", "passwords");\n'
)


class ImporterTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.src, self.dest = root / "src", root / "dest"
        files = {
            "prefs.js": PREFS, "places.sqlite": "x" * 3000, "signedInUser.json": "{}",
            "weave/toFetch/bookmarks.json": "[]", "chrome/userChrome.css": "/* mine */",
            "startupCache/startupCache.8.little": "c", "user.js": 'user_pref("a", 1);\n',
            "storage/default/site/ls/data.sqlite": "s",
        }
        for rel, text in files.items():
            (self.src / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.src / rel).write_text(text, encoding="utf-8")
        os.symlink("127.0.1.1:+1", self.src / "lock")
        (self.src / ".parentlock").touch()
        self.dest.mkdir()
        (self.dest / ".myfox-created").touch()

    def _names(self, root: Path) -> set[str]:
        return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() or p.is_symlink()}

    def test_without_sync_the_account_and_its_identity_stay_behind(self):
        importer.copy_profile(self.src, self.dest, importer.SYNC_NONE)
        self.assertEqual(self._names(self.dest), {
            ".myfox-created", "prefs.js", "places.sqlite", "user.js", "storage/default/site/ls/data.sqlite"})
        prefs = (self.dest / "prefs.js").read_text(encoding="utf-8")
        self.assertNotIn("services.sync.client.GUID", prefs)
        self.assertNotIn("services.sync.username", prefs)
        self.assertIn('"services.sync.engine.passwords", false', prefs)
        self.assertIn("browser.startup.page", prefs)
        self.assertEqual((self.src / "prefs.js").read_text(encoding="utf-8"), PREFS)  # the source is only read

    def test_copy_and_move_take_the_account_along(self):
        importer.copy_profile(self.src, self.dest, importer.SYNC_COPY)
        self.assertTrue({"signedInUser.json", "weave/toFetch/bookmarks.json"} <= self._names(self.dest))
        self.assertEqual((self.dest / "prefs.js").read_text(encoding="utf-8"), PREFS)
        self.assertNotIn("chrome/userChrome.css", self._names(self.dest))

    def test_progress_counts_up_to_the_total_and_can_stop_it(self):
        seen = []
        importer.copy_profile(self.src, self.dest, importer.SYNC_NONE, on_copy=lambda d, t: seen.append((d, t)))
        self.assertEqual(seen[-1][0], seen[-1][1])
        self.assertEqual([d for d, _t in seen], sorted(d for d, _t in seen))

        def stop(done, total):
            raise Cancelled()

        other = self.dest.parent / "other"
        other.mkdir()
        with self.assertRaises(Cancelled):
            importer.copy_profile(self.src, other, importer.SYNC_NONE, on_copy=stop)

    def test_not_enough_space(self):
        with mock.patch("shutil.disk_usage", return_value=mock.Mock(free=10)):
            with self.assertRaises(OSError):
                importer.copy_profile(self.src, self.dest)
        self.assertEqual(self._names(self.dest), {".myfox-created"})

    def test_a_fifo_is_skipped(self):
        os.mkfifo(self.src / "storage" / "pipe")
        importer.copy_profile(self.src, self.dest)
        self.assertFalse((self.dest / "storage" / "pipe").exists())

    def test_move_signs_the_source_out_and_restore_puts_it_back(self):
        backups = importer.move_sync_out(self.src)
        self.assertEqual(sorted(p.name for p in backups), ["prefs.js.myfox-backup", "signedInUser.json.myfox-backup"])
        self.assertFalse(importer.has_account(self.src))
        self.assertNotIn("services.sync.client.GUID", (self.src / "prefs.js").read_text(encoding="utf-8"))
        self.assertTrue(importer.can_restore_sync(self.src))

        # The source Firefox ran meanwhile and changed a pref.
        with (self.src / "prefs.js").open("a", encoding="utf-8") as f:
            f.write('user_pref("browser.later", true);\n')
        importer.restore_sync(self.src)
        prefs = (self.src / "prefs.js").read_text(encoding="utf-8")
        self.assertIn('"services.sync.client.GUID", "abc"', prefs)
        self.assertIn("browser.later", prefs)
        self.assertEqual(prefs.count("services.sync.engine.passwords"), 1)
        self.assertTrue(importer.has_account(self.src))
        self.assertFalse(any(p.name.endswith(".myfox-backup") for p in self.src.iterdir()))

    def test_nothing_to_move_without_an_account(self):
        (self.src / "signedInUser.json").unlink()
        self.assertEqual(importer.move_sync_out(self.src), [])
        self.assertEqual((self.src / "prefs.js").read_text(encoding="utf-8"), PREFS)

    def test_no_restore_over_an_account_signed_in_since(self):
        importer.move_sync_out(self.src)
        (self.src / "signedInUser.json").write_text('{"new": 1}', encoding="utf-8")
        self.assertFalse(importer.can_restore_sync(self.src))


if __name__ == "__main__":
    unittest.main()
