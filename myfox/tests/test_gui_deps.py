from __future__ import annotations

import hashlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from myfox import gui_deps


def _wheel_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("dearpygui/__init__.py", "")
        zf.writestr("dearpygui/dearpygui.py", "# stub\n")
        zf.writestr("dearpygui-2.3.1.dist-info/METADATA", "")
    return buf.getvalue()


class WheelNameTests(unittest.TestCase):
    def test_picks_the_wheel_for_python_and_arch(self):
        self.assertEqual(gui_deps.wheel_name((3, 12), "amd64"), "dearpygui-2.3.1-cp312-cp312-manylinux1_x86_64.whl")
        self.assertEqual(gui_deps.wheel_name((3, 8), "arm64"), "dearpygui-2.3.1-cp38-cp38-manylinux2014_aarch64.whl")

    def test_none_when_there_is_no_such_wheel(self):
        self.assertIsNone(gui_deps.wheel_name((3, 7), "amd64"))
        self.assertIsNone(gui_deps.wheel_name((3, 12), "riscv64"))


class InstallIntoTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.wheels = self.root / "wheels"
        self.wheels.mkdir()
        self.name = "dearpygui-2.3.1-cp312-cp312-manylinux1_x86_64.whl"
        (self.wheels / self.name).write_bytes(_wheel_bytes())
        tag = "cp312-cp312-manylinux1_x86_64"
        patches = [
            mock.patch("importlib.util.find_spec", return_value=None),
            mock.patch("myfox.gui_deps.wheel_name", return_value=self.name),
            mock.patch.dict("os.environ", {"MYFOX_DEARPYGUI_DIR": str(self.wheels)}),
            mock.patch.dict(gui_deps._SHA256, {tag: hashlib.sha256(_wheel_bytes()).hexdigest()}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_extracts_only_the_package(self):
        gui_deps.install_into(self.root / "share")
        self.assertTrue((self.root / "share" / "dearpygui" / "dearpygui.py").is_file())
        marker = self.root / "share" / "dearpygui" / gui_deps.MARKER
        self.assertEqual(marker.read_text().strip(), "cp312-cp312-manylinux1_x86_64")
        self.assertFalse(any((self.root / "share").glob("*.dist-info")))

    def test_checksum_mismatch_refuses(self):
        (self.wheels / self.name).write_bytes(b"tampered")
        with self.assertRaises(RuntimeError):
            gui_deps.install_into(self.root / "share")
        self.assertFalse((self.root / "share" / "dearpygui").exists())

    def test_an_importable_copy_is_reused(self):
        source = self.root / "dev" / "dearpygui"
        source.mkdir(parents=True)
        (source / "marker").write_text("dev")
        spec = mock.Mock(submodule_search_locations=[str(source)])
        with mock.patch("importlib.util.find_spec", return_value=spec):
            gui_deps.install_into(self.root / "share")
        self.assertEqual((self.root / "share" / "dearpygui" / "marker").read_text(), "dev")
        self.assertTrue((self.root / "share" / "dearpygui" / gui_deps.MARKER).is_file())

    def test_not_reusing_ignores_an_importable_copy(self):
        spec = mock.Mock(submodule_search_locations=[str(self.root / "nowhere")])
        with mock.patch("importlib.util.find_spec", return_value=spec):
            gui_deps.install_into(self.root / "share", reuse_importable=False)
        self.assertTrue((self.root / "share" / "dearpygui" / "dearpygui.py").is_file())


class CurrentTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.share = Path(self._tmp.name)
        (self.share / "dearpygui").mkdir()
        patcher = mock.patch("myfox.gui_deps._current_tag", return_value="cp313-cp313-manylinux1_x86_64")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _marker(self, tag):
        (self.share / "dearpygui" / gui_deps.MARKER).write_text(tag + "\n")

    def test_matching_marker_fetches_nothing(self):
        self._marker("cp313-cp313-manylinux1_x86_64")
        with mock.patch("myfox.gui_deps.install_into") as install:
            gui_deps.ensure_current(self.share)
        install.assert_not_called()

    def test_python_upgrade_fetches_the_new_wheel_not_the_old_copy(self):
        self._marker("cp312-cp312-manylinux1_x86_64")
        with mock.patch("myfox.gui_deps.install_into") as install:
            gui_deps.ensure_current(self.share)
        install.assert_called_once_with(self.share, reuse_importable=False)

    def test_missing_marker_fetches(self):
        with mock.patch("myfox.gui_deps.install_into") as install:
            gui_deps.ensure_current(self.share)
        install.assert_called_once()

    def test_working_copy_is_not_touched(self):
        with mock.patch("myfox.gui_deps.ensure_current") as ensure, \
             mock.patch("myfox.launcher.share_dir", return_value=self.share):
            gui_deps.prepare()
        ensure.assert_not_called()

    def test_installed_copy_is_checked(self):
        with mock.patch("myfox.gui_deps.ensure_current") as ensure, \
             mock.patch("myfox.launcher.share_dir", return_value=self.share), \
             mock.patch("myfox.paths.myfox_root", return_value=self.share):
            gui_deps.prepare()
        ensure.assert_called_once_with(self.share)


if __name__ == "__main__":
    unittest.main()
