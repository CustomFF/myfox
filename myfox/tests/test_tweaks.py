from __future__ import annotations

import io
import tarfile
from pathlib import Path
from unittest import mock

from myfox import paths, tweaks

from ._helpers import IsolatedStateCase, git_refs, make_tweaks

_TAGS = ("refs/tags/themes-20261001", "refs/tags/158.1", "refs/tags/158.0", "refs/heads/master")


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
    def _latest(self, tags, missing=()):
        with mock.patch("myfox.version._fetch_refs", return_value=git_refs(*tags)), \
             mock.patch("myfox.version._has_asset", side_effect=lambda repo, tag, name: tag not in missing):
            return tweaks.latest_release()

    def test_newest_tweaks_tag_with_the_archive(self):
        # 158.1's release has no archive yet, themes-* doesn't match the tag pattern.
        url = "https://github.com/CustomFF/myfox-tweaks/releases/download/158.0/"
        self.assertEqual(self._latest(_TAGS, missing={"158.1"}),
                         tweaks.Release("158.0", url + "myfox-tweaks.tar.gz", url + "changelog.json"))

    def test_none_without_any(self):
        self.assertIsNone(self._latest(_TAGS[:1]))


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
