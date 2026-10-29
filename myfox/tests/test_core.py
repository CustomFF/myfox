from __future__ import annotations

import io
import tarfile
from unittest import mock

from myfox import core, paths

from ._helpers import IsolatedStateCase, git_refs


def _archive(files) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _response(data: bytes):
    cm = mock.MagicMock()
    cm.__enter__.return_value.read.return_value = data
    return cm


class LatestReleaseTests(IsolatedStateCase):
    def _latest(self, *tags, missing=()):
        with mock.patch("myfox.version._fetch_refs", return_value=git_refs(*tags)), \
             mock.patch("myfox.version._has_asset", side_effect=lambda repo, tag, name: tag not in missing):
            return core.latest_release()

    def test_newest_core_tag_with_the_archive(self):
        # core-3's release has no archive yet; dearpygui-* isn't core.
        release = self._latest("refs/tags/dearpygui-2.3.1", "refs/tags/core-3", "refs/tags/core-2.10.0",
                               "refs/tags/core-2.9.0", missing={"core-3"})
        url = "https://github.com/CustomFF/myfox/releases/download/core-2.10.0/"
        self.assertEqual(release, core.Release("core-2.10.0", url + "myfox-core.tar.gz", url + "changelog.json"))

    def test_local_archive_instead_of_a_release(self):
        with mock.patch.dict("os.environ", {"MYFOX_CORE_URL": "/tmp/myfox-core.tar.gz"}), \
             mock.patch("myfox.version._fetch_refs", side_effect=AssertionError("network")):
            self.assertEqual(core.latest_release(), core.Release("dev", "file:///tmp/myfox-core.tar.gz"))

    def test_none_without_any(self):
        self.assertIsNone(self._latest("refs/heads/master", "refs/tags/dearpygui-2.3.1"))


class InstallTests(IsolatedStateCase):
    def setUp(self):
        super().setUp()
        self.share = paths.share_dir()
        for part in ("myfox/__main__.py", "myfox/old_module.py", "firefox/firefox", "tweaks/chrome/x.css",
                     "dearpygui/__init__.py"):
            (self.share / part).parent.mkdir(parents=True, exist_ok=True)
            (self.share / part).write_text("old")
        self.release = core.Release("core-7", "https://c/7")

    def _install(self, files):
        with mock.patch("urllib.request.urlopen", return_value=_response(_archive(files))):
            return core.install(self.release)

    def test_replaces_only_the_package(self):
        self.assertEqual(self._install({"myfox/__main__.py": b"new", "myfox/new_module.py": b"new"}), "core-7")
        self.assertEqual((self.share / "myfox" / "__main__.py").read_text(), "new")
        self.assertFalse((self.share / "myfox" / "old_module.py").exists())
        for part in ("firefox/firefox", "tweaks/chrome/x.css", "dearpygui/__init__.py"):
            self.assertEqual((self.share / part).read_text(), "old", part)

    def test_returns_the_new_package_s_own_version(self):
        version = self._install({"myfox/__main__.py": b"new", "myfox/__init__.py": b'__version__ = "1.2.3"\n'})
        self.assertEqual(version, "1.2.3")

    def test_unsafe_archive_keeps_the_current_package(self):
        with self.assertRaises(OSError):
            self._install({"myfox/__main__.py": b"new", "../evil": b"x"})
        self.assertEqual((self.share / "myfox" / "__main__.py").read_text(), "old")

    def test_archive_without_the_package_is_refused(self):
        with self.assertRaises(OSError):
            self._install({"README": b"x"})
        self.assertTrue((self.share / "myfox" / "old_module.py").is_file())
