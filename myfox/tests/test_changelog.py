from __future__ import annotations

import json
import unittest
from unittest import mock

from myfox import changelog

_ENTRIES = {"versions": [
    {"version": "159.0", "date": "2026-11-01", "changes": ["C"]},
    {"version": "158.1", "date": "2026-10-10", "changes": ["B1", "B2"]},
    {"version": "158.0", "date": "2026-10-06", "changes": ["A"]},
]}


class VersionTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(changelog.parse("core-1.2.3"), (1, 2, 3))
        self.assertEqual(changelog.parse("158.0"), (158, 0))
        self.assertIsNone(changelog.parse("dev"))
        self.assertIsNone(changelog.parse(None))

    def test_display_drops_the_prefix(self):
        self.assertEqual(changelog.display("core-1.0.0"), "1.0.0")
        self.assertEqual(changelog.display("158.0"), "158.0")
        self.assertEqual(changelog.display(None), "—")

    def test_is_newer_compares_numbers(self):
        self.assertTrue(changelog.is_newer("core-1.10.0", "1.9.0"))
        self.assertFalse(changelog.is_newer("core-1.0.0", "1.0.0"))
        self.assertFalse(changelog.is_newer("158.0", "158.1"))
        self.assertTrue(changelog.is_newer("158.0", None))
        self.assertTrue(changelog.is_newer("core-1.0.0", "dev"))
        self.assertFalse(changelog.is_newer(None, "1.0.0"))


class ChangesSinceTests(unittest.TestCase):
    def _since(self, current, body=None):
        cm = mock.MagicMock()
        cm.__enter__.return_value.read.return_value = json.dumps(body or _ENTRIES).encode()
        with mock.patch("urllib.request.urlopen", return_value=cm):
            return changelog.changes_since("https://x/changelog.json", current)

    def test_only_versions_newer_than_installed(self):
        self.assertEqual(self._since("158.0"), ["C", "B1", "B2"])

    def test_versions_compare_as_numbers(self):
        self.assertEqual(self._since("158.10"), ["C"])

    def test_unknown_installed_version_shows_everything(self):
        self.assertEqual(self._since(None), ["C", "B1", "B2", "A"])

    def test_malformed_changelog_is_an_error(self):
        with self.assertRaises(OSError):
            self._since("158.0", body={"nope": []})


if __name__ == "__main__":
    unittest.main()
