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


class FindLatestTagTests(unittest.TestCase):
    def test_network_failure_raises(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("down")), self.assertRaises(OSError):
            version.find_latest_tag(version.CORE_TAG_RE)

    def test_bad_json_raises_oserror(self):
        cm = mock.MagicMock()
        cm.__enter__.return_value.read.return_value = b"not json"
        with mock.patch("urllib.request.urlopen", return_value=cm), self.assertRaises(OSError):
            version.find_latest_tag(version.CORE_TAG_RE)


if __name__ == "__main__":
    unittest.main()
