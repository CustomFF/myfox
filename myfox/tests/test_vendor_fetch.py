"""ensure_available()'s "already importable" short-circuit is exercised by
forcing sys.modules["dearpygui.dearpygui"] to a real stand-in object; the
"needs fetching" path is exercised by forcing sys.modules[...] = None,
the standard trick to make `import dearpygui.dearpygui` raise ImportError
regardless of whether the real package happens to be installed in the
dev environment (it was, during live Pass 4 testing — tests must not
depend on that)."""

from __future__ import annotations

import io
import sys
import tempfile
import types
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest import mock

from myfox.ui import _vendor_fetch


def _force_import_error():
    return mock.patch.dict(sys.modules, {"dearpygui": None, "dearpygui.dearpygui": None})


def _fake_zip_bytes(filename="_dearpygui.so", content=b"fake-binary") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(filename, content)
    return buf.getvalue()


def _fake_response(body: bytes):
    cm = mock.MagicMock()
    cm.__enter__.return_value.read.return_value = body
    return cm


class AssetNameTests(unittest.TestCase):
    def test_includes_python_minor_version_and_arch(self):
        with mock.patch.object(sys, "version_info", (3, 11, 0, "final", 0)), \
             mock.patch("myfox.ui._vendor_fetch.firefox.detect_arch", return_value="amd64"):
            self.assertEqual(_vendor_fetch._asset_name(), "dearpygui-cp311-amd64.zip")


class EnsureAvailableTests(unittest.TestCase):
    def test_short_circuits_when_already_importable(self):
        # Needs both the parent package and the submodule stubbed — `import
        # dearpygui.dearpygui` still re-imports the real "dearpygui" (and
        # can raise) if only the submodule entry is faked.
        fake_pkg = types.ModuleType("dearpygui")
        fake_submodule = types.ModuleType("dearpygui.dearpygui")
        fake_pkg.dearpygui = fake_submodule
        with mock.patch.dict(sys.modules, {"dearpygui": fake_pkg, "dearpygui.dearpygui": fake_submodule}), \
             mock.patch.object(_vendor_fetch, "_download_and_extract") as download:
            _vendor_fetch.ensure_available()
        download.assert_not_called()

    def test_download_called_once_then_added_to_syspath(self):
        with _force_import_error(), \
             mock.patch.object(_vendor_fetch, "_asset_name", return_value="dearpygui-cp311-amd64.zip"), \
             mock.patch.object(_vendor_fetch, "_cache_dir", return_value=Path("/tmp/myfox-test-cache")), \
             mock.patch.object(_vendor_fetch, "_download_and_extract") as download, \
             mock.patch("pathlib.Path.is_dir", return_value=False), \
             mock.patch.object(sys, "path", list(sys.path)):
            _vendor_fetch.ensure_available()
            download.assert_called_once_with(
                "dearpygui-cp311-amd64.zip", Path("/tmp/myfox-test-cache/dearpygui-cp311-amd64")
            )
            self.assertEqual(sys.path[0], str(Path("/tmp/myfox-test-cache/dearpygui-cp311-amd64")))

    def test_skips_download_when_already_cached(self):
        with _force_import_error(), \
             mock.patch.object(_vendor_fetch, "_asset_name", return_value="dearpygui-cp311-amd64.zip"), \
             mock.patch.object(_vendor_fetch, "_cache_dir", return_value=Path("/tmp/myfox-test-cache")), \
             mock.patch.object(_vendor_fetch, "_download_and_extract") as download, \
             mock.patch("pathlib.Path.is_dir", return_value=True), \
             mock.patch.object(sys, "path", list(sys.path)):
            _vendor_fetch.ensure_available()
        download.assert_not_called()


class DownloadAndExtractTests(unittest.TestCase):
    def test_no_release_tag_raises_runtime_error(self):
        with mock.patch.object(_vendor_fetch.version, "latest_tag", return_value=None):
            with self.assertRaises(RuntimeError):
                _vendor_fetch._download_and_extract("dearpygui-cp311-amd64.zip", Path("/tmp/wherever"))

    def test_successful_fetch_extracts_into_target_dir(self):
        payload = _fake_zip_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            target_dir = Path(tmp) / "dearpygui-cp311-amd64"
            with mock.patch.object(_vendor_fetch.version, "latest_tag", return_value="dearpygui-v1"), \
                 mock.patch("urllib.request.urlopen", return_value=_fake_response(payload)) as urlopen:
                _vendor_fetch._download_and_extract("dearpygui-cp311-amd64.zip", target_dir)

            self.assertTrue((target_dir / "_dearpygui.so").is_file())
            self.assertEqual((target_dir / "_dearpygui.so").read_bytes(), b"fake-binary")
            requested_url = urlopen.call_args[0][0].full_url
            self.assertEqual(
                requested_url,
                "https://github.com/CustomFF/myfox/releases/download/dearpygui-v1/dearpygui-cp311-amd64.zip",
            )

    def test_network_failure_raises_runtime_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            target_dir = Path(tmp) / "dearpygui-cp311-amd64"
            with mock.patch.object(_vendor_fetch.version, "latest_tag", return_value="dearpygui-v1"), \
                 mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
                with self.assertRaises(RuntimeError):
                    _vendor_fetch._download_and_extract("dearpygui-cp311-amd64.zip", target_dir)

    def test_bad_zip_raises_runtime_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            target_dir = Path(tmp) / "dearpygui-cp311-amd64"
            with mock.patch.object(_vendor_fetch.version, "latest_tag", return_value="dearpygui-v1"), \
                 mock.patch("urllib.request.urlopen", return_value=_fake_response(b"not a zip")):
                with self.assertRaises(RuntimeError):
                    _vendor_fetch._download_and_extract("dearpygui-cp311-amd64.zip", target_dir)


if __name__ == "__main__":
    unittest.main()
