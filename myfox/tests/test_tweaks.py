from __future__ import annotations

import io
import tarfile
from pathlib import Path
from unittest import mock

from myfox import paths, tweaks

from ._helpers import IsolatedStateCase, make_tweaks

_RELEASES = [
    {"tag_name": "themes-20261001", "assets": [{"name": "myfox-dark.xpi", "browser_download_url": "x"}]},
    {"tag_name": "158.1", "assets": [{"name": "myfox-tweaks.tar.gz", "browser_download_url": "https://t/158.1.tgz"}]},
    {"tag_name": "158.0", "assets": [
        {"name": "myfox-tweaks.tar.gz", "browser_download_url": "https://t/158.0.tgz"},
        {"name": "changelog.json", "browser_download_url": "https://t/158.0.json"},
    ]},
]


def _archive(root: Path, extra=None) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        tf.add(root / "autoconfig", arcname="autoconfig")
        tf.add(root / "chrome", arcname="chrome")
        for name, data in (extra or {}).items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class LatestReleaseTests(IsolatedStateCase):
    def test_newest_tweaks_tag_with_both_assets(self):
        with mock.patch("myfox.version._fetch_releases", return_value=_RELEASES):
            release = tweaks.latest_release()
        # 158.1 lacks changelog.json, themes-* doesn't match the tag pattern.
        self.assertEqual(release, tweaks.Release("158.0", "https://t/158.0.tgz", "https://t/158.0.json"))

    def test_none_without_any(self):
        with mock.patch("myfox.version._fetch_releases", return_value=_RELEASES[:1]):
            self.assertIsNone(tweaks.latest_release())


class InstallTests(IsolatedStateCase):
    def setUp(self):
        super().setUp()
        self.src = make_tweaks(self.tmp_path / "src")
        self.release = tweaks.Release("158.0", "https://t/a", "https://t/c")

    def test_unpacks_the_release_into_the_tweaks_dir(self):
        with mock.patch("myfox.tweaks._download", return_value=_archive(self.src)):
            self.assertEqual(tweaks.install(self.release), "158.0")
        self.assertTrue((paths.autoconfig_dir() / "myfox.cfg").is_file())
        self.assertTrue((paths.chrome_dir() / "userChrome.css").is_file())

    def test_unsafe_archive_keeps_the_previous_tweaks(self):
        make_tweaks(paths.tweaks_dir())
        (paths.tweaks_dir() / "chrome" / "old-marker").write_text("old")
        with mock.patch("myfox.tweaks._download", return_value=_archive(self.src, {"../evil": b"x"})), \
             self.assertRaises(OSError):
            tweaks.install(self.release)
        self.assertTrue((paths.tweaks_dir() / "chrome" / "old-marker").is_file())

    def test_replaces_the_previous_tweaks_wholesale(self):
        make_tweaks(paths.tweaks_dir())
        (paths.tweaks_dir() / "chrome" / "dropped.css").write_text("x")
        with mock.patch("myfox.tweaks._download", return_value=_archive(self.src)):
            tweaks.install(self.release)
        self.assertFalse((paths.tweaks_dir() / "chrome" / "dropped.css").exists())

    def test_local_checkout_instead_of_a_release(self):
        with mock.patch.dict("os.environ", {"MYFOX_TWEAKS_LOCAL": str(self.src)}), \
             mock.patch("myfox.tweaks.latest_release", side_effect=AssertionError("network")):
            self.assertEqual(tweaks.install(), tweaks.LOCAL_TAG)
        self.assertTrue((paths.autoconfig_dir() / "autoconfig.js").is_file())

    def test_no_release_is_an_error(self):
        with mock.patch("myfox.tweaks.latest_release", return_value=None), self.assertRaises(OSError):
            tweaks.install()
