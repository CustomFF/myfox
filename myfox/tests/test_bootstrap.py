"""bootstrap.py lives at the repo root (it's fetched on its own), so it's
loaded by path here."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import tarfile
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

_PATH = Path(__file__).resolve().parents[2] / "bootstrap.py"
_spec = importlib.util.spec_from_file_location("myfox_bootstrap", _PATH)
bootstrap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bootstrap)


class _Env(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        patcher = mock.patch.dict("os.environ", {"XDG_STATE_HOME": str(self.root / "state"),
                                                 "XDG_DATA_HOME": str(self.root / "data")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def install(self):
        state = self.root / "state" / "myfox" / "state.json"
        state.parent.mkdir(parents=True)
        state.write_text(json.dumps({"install_dir": "/opt/firefox"}))
        launcher = self.root / "data" / "myfox" / "bin" / "myfox"
        launcher.parent.mkdir(parents=True)
        launcher.write_text("#!/bin/sh\n")
        launcher.chmod(0o755)
        return launcher


class _Exec(Exception):
    """os.execv never returns; the stand-in mustn't either."""


class InstalledTests(_Env):
    def test_arguments_go_to_the_installed_myfox(self):
        launcher = self.install()
        with mock.patch("os.execv", side_effect=_Exec) as execv, self.assertRaises(_Exec):
            bootstrap.main(["uninstall", "-y"])
        execv.assert_called_once_with(str(launcher), [str(launcher), "uninstall", "-y"])

    def test_no_arguments_asks_and_yes_runs_refresh(self):
        launcher = self.install()
        with mock.patch("os.execv", side_effect=_Exec) as execv, mock.patch("builtins.input", return_value=""), \
             redirect_stdout(io.StringIO()), self.assertRaises(_Exec):
            bootstrap.main([])
        execv.assert_called_once_with(str(launcher), [str(launcher), "refresh"])

    def test_no_means_exit(self):
        self.install()
        with mock.patch("os.execv") as execv, mock.patch("builtins.input", return_value="n"), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(bootstrap.main([]), 0)
        execv.assert_not_called()

    def test_state_without_install_dir_is_not_installed(self):
        self.install()
        (self.root / "state" / "myfox" / "state.json").write_text("{}")
        self.assertIsNone(bootstrap.installed_launcher())


class FreshTests(_Env):
    def _archive(self, members):
        path = self.root / "core.tar.gz"
        with tarfile.open(path, "w:gz") as tf:
            for name, data in members.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
        return path

    def test_runs_the_wizard_from_the_unpacked_core(self):
        archive = self._archive({"myfox/__init__.py": b"", "autoconfig/x": b"", "chrome/y": b""})
        seen = {}

        def run(cmd, env=None, **kwargs):
            root = Path(env["PYTHONPATH"].split(os.pathsep)[0])
            seen.update(cmd=cmd[1:], version=env["MYFOX_CORE_VERSION"],
                        unpacked=sorted(p.name for p in root.iterdir()))
            return mock.Mock(returncode=0)

        with mock.patch.dict("os.environ", {"MYFOX_CORE_URL": str(archive)}), \
             mock.patch("subprocess.run", side_effect=run):
            self.assertEqual(bootstrap.main(["-y"]), 0)
        self.assertEqual(seen, {"cmd": ["-m", "myfox.wizard", "-y"], "version": "dev",
                                "unpacked": ["autoconfig", "chrome", "myfox"]})

    def test_unsafe_archive_is_refused(self):
        archive = self._archive({"../evil": b"x"})
        with mock.patch.dict("os.environ", {"MYFOX_CORE_URL": str(archive)}), \
             mock.patch("subprocess.run") as run, mock.patch("sys.stderr", new=io.StringIO()):
            self.assertEqual(bootstrap.main([]), 1)
        run.assert_not_called()

    def test_core_dir_skips_the_download(self):
        with mock.patch.dict("os.environ", {"MYFOX_CORE_DIR": "/work/myfox"}), \
             mock.patch("subprocess.run", return_value=mock.Mock(returncode=0)) as run:
            bootstrap.main([])
        self.assertTrue(run.call_args.kwargs["env"]["PYTHONPATH"].startswith("/work/myfox"))


if __name__ == "__main__":
    unittest.main()
