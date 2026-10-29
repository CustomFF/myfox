from __future__ import annotations

import unittest
import urllib.error
from unittest import mock

from myfox import version

from ._helpers import git_refs


def _fake_response(body: bytes):
    cm = mock.MagicMock()
    cm.__enter__.return_value.read.return_value = body
    return cm


TAGS = ("refs/heads/master", "refs/tags/core-1.9.0", "refs/tags/158.4", "refs/tags/core-1.10.0",
        "refs/tags/158.10", "refs/tags/dearpygui-2.3.1", "refs/tags/core-1.2.0")


class RefsTests(unittest.TestCase):
    def test_reads_the_refs_without_the_peeled_tags(self):
        with mock.patch("urllib.request.urlopen", return_value=_fake_response(git_refs(*TAGS))) as urlopen:
            found = version.refs("CustomFF/myfox")
        self.assertEqual(urlopen.call_args.args[0].full_url,
                         "https://github.com/CustomFF/myfox.git/info/refs?service=git-upload-pack")
        self.assertEqual(sorted(found), sorted(TAGS))
        self.assertEqual(found["refs/heads/master"], f"{1:040x}")

    def test_something_else_raises_oserror(self):
        for body in (b"<html>rate limited</html>", b"0000"):
            with mock.patch("urllib.request.urlopen", return_value=_fake_response(body)), \
                 self.assertRaises(OSError):
                version.refs()


class LatestTagTests(unittest.TestCase):
    def _latest(self, pattern, missing=(), **kwargs):
        with mock.patch("myfox.version._fetch_refs", return_value=git_refs(*TAGS)), \
             mock.patch("myfox.version._has_asset", side_effect=lambda repo, tag, name: tag not in missing):
            return version.find_latest_tag(pattern, **kwargs)

    def test_the_newest_by_its_numbers_each_track(self):
        self.assertEqual(self._latest(version.CORE_TAG_RE), "core-1.10.0")
        self.assertEqual(self._latest(version.TWEAKS_TAG_RE), "158.10")

    def test_a_tag_whose_release_has_no_archive_yet_is_skipped(self):
        self.assertEqual(self._latest(version.CORE_TAG_RE, missing={"core-1.10.0"}, asset="a.tgz"), "core-1.9.0")

    def test_no_matching_tag_returns_none(self):
        self.assertIsNone(self._latest(version.TWEAKS_TAG_RE, missing={"158.4", "158.10"}, asset="a.tgz"))

    def test_network_failure_returns_none_not_raise(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("down")):
            self.assertIsNone(version.latest_tag(version.CORE_TAG_RE))
            with self.assertRaises(OSError):
                version.find_latest_tag(version.CORE_TAG_RE)

    def test_tweaks_pattern_does_not_match_a_core_tag(self):
        self.assertIsNone(version.TWEAKS_TAG_RE.match("core-3"))
        self.assertIsNone(version.CORE_TAG_RE.match("158.4"))


class HasAssetTests(unittest.TestCase):
    def _has(self, outcome):
        opener = mock.MagicMock()
        if isinstance(outcome, int):
            opener.open.side_effect = urllib.error.HTTPError("u", outcome, "x", {}, None)
        with mock.patch("urllib.request.build_opener", return_value=opener):
            result = version._has_asset("CustomFF/myfox", "core-1.3.2", "myfox-core.tar.gz")
        return result, opener

    def test_the_redirect_to_the_file_means_it_is_there_and_is_not_followed(self):
        result, opener = self._has(302)
        self.assertTrue(result)
        req = opener.open.call_args.args[0]
        self.assertEqual((req.get_method(), req.full_url),
                         ("HEAD", "https://github.com/CustomFF/myfox/releases/download/core-1.3.2/myfox-core.tar.gz"))

    def test_not_found_means_not_yet(self):
        self.assertFalse(self._has(404)[0])

    def test_other_errors_raise(self):
        with self.assertRaises(OSError):
            self._has(503)


if __name__ == "__main__":
    unittest.main()
