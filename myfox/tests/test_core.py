from __future__ import annotations

import io
import tarfile
from unittest import mock

from myfox import core, paths

from ._helpers import IsolatedStateCase


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
    def test_newest_core_tag_with_the_archive(self):
        releases = [
            {"tag_name": "dearpygui-2.3.1", "assets": [{"name": "x.whl", "browser_download_url": "w"}]},
            {"tag_name": "core-3", "assets": []},
            {"tag_name": "core-2.1.0", "assets": [{"name": "myfox-core.tar.gz", "browser_download_url": "x"}]},
            {"tag_name": "core-2.0.0", "assets": [
                {"name": "myfox-core.tar.gz", "browser_download_url": "https://c/2"},
                {"name": "changelog.json", "browser_download_url": "https://c/2.json"},
            ]},
        ]
        # core-3 has no assets, core-2.1.0 no changelog.
        with mock.patch("myfox.version._fetch_releases", return_value=releases):
            self.assertEqual(core.latest_release(), core.Release("core-2.0.0", "https://c/2", "https://c/2.json"))

    def test_local_archive_instead_of_a_release(self):
        with mock.patch.dict("os.environ", {"MYFOX_CORE_URL": "/tmp/myfox-core.tar.gz"}), \
             mock.patch("myfox.version._fetch_releases", side_effect=AssertionError("network")):
            self.assertEqual(core.latest_release(), core.Release("dev", "file:///tmp/myfox-core.tar.gz"))

    def test_none_without_any(self):
        with mock.patch("myfox.version._fetch_releases", return_value=[]):
            self.assertIsNone(core.latest_release())


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
