from __future__ import annotations

import json
import unittest
from unittest import mock

from myfox import version


def _fake_response(payload):
    body = json.dumps(payload).encode("utf-8")
    cm = mock.MagicMock()
    cm.__enter__.return_value.read.return_value = body
    return cm


class LatestTagTests(unittest.TestCase):
    RELEASES = [
        {"tag_name": "core-3"},
        {"tag_name": "158.4"},
        {"tag_name": "core-2"},
        {"tag_name": "158.3"},
        {"tag_name": "core-1"},
    ]

    def test_picks_the_first_matching_tag_each_track(self):
        with mock.patch("urllib.request.urlopen", return_value=_fake_response(self.RELEASES)):
            self.assertEqual(version.latest_tag(version.CORE_TAG_RE), "core-3")
            self.assertEqual(version.latest_tag(version.TWEAKS_TAG_RE), "158.4")

    def test_no_matching_releases_returns_none(self):
        with mock.patch("urllib.request.urlopen", return_value=_fake_response([{"tag_name": "core-1"}])):
            self.assertIsNone(version.latest_tag(version.TWEAKS_TAG_RE))

    def test_network_failure_returns_none_not_raise(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("down")):
            self.assertIsNone(version.latest_tag(version.CORE_TAG_RE))

    def test_tweaks_pattern_does_not_match_a_core_tag(self):
        self.assertIsNone(version.TWEAKS_TAG_RE.match("core-3"))
        self.assertIsNone(version.CORE_TAG_RE.match("158.4"))


class UpdateAvailableTests(unittest.TestCase):
    def test_tweaks_update_available_when_tag_differs(self):
        with mock.patch("myfox.version.latest_tag", return_value="158.4"):
            self.assertEqual(version.tweaks_update_available("158.3"), "158.4")

    def test_tweaks_no_update_when_tag_matches_current(self):
        with mock.patch("myfox.version.latest_tag", return_value="158.4"):
            self.assertIsNone(version.tweaks_update_available("158.4"))

    def test_tweaks_no_update_when_nothing_found(self):
        with mock.patch("myfox.version.latest_tag", return_value=None):
            self.assertIsNone(version.tweaks_update_available("158.3"))

    def test_core_update_available_when_tag_differs(self):
        with mock.patch("myfox.version.latest_tag", return_value="core-3"):
            self.assertEqual(version.core_update_available("core-2"), "core-3")

    def test_first_run_with_no_recorded_version_reports_whatever_exists(self):
        with mock.patch("myfox.version.latest_tag", return_value="158.4"):
            self.assertEqual(version.tweaks_update_available(None), "158.4")


if __name__ == "__main__":
    unittest.main()
