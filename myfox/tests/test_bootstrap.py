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

from ._helpers import WINDOWS, only_linux

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
                                                 "XDG_DATA_HOME": str(self.root / "data"),
                                                 "LOCALAPPDATA": str(self.root / "local")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def state_file(self) -> Path:
        if WINDOWS:
            return self.root / "local" / "myfox" / "state" / "state.json"
        return self.root / "state" / "myfox" / "state.json"

    def install(self):
        state = self.state_file()
        state.parent.mkdir(parents=True)
        state.write_text(json.dumps({"install_dir": "/opt/firefox"}))
        launcher = (self.root / "local" / "myfox" / "bin" / "myfox.cmd" if WINDOWS
                    else self.root / "data" / "myfox" / "bin" / "myfox")
        launcher.parent.mkdir(parents=True)
        launcher.write_text("#!/bin/sh\n")
        launcher.chmod(0o755)
        return launcher


class InstalledTests(_Env):
    def test_arguments_go_to_the_installed_myfox(self):
        launcher = self.install()
        with mock.patch.object(bootstrap, "_exec", return_value=3) as run:
            self.assertEqual(bootstrap.main(["uninstall", "-y"]), 3)
        run.assert_called_once_with(launcher, ["uninstall", "-y"])

    def test_no_arguments_asks_and_yes_runs_refresh(self):
        launcher = self.install()
        with mock.patch.object(bootstrap, "_exec", return_value=0) as run, mock.patch("builtins.input", return_value=""), \
             mock.patch.object(bootstrap, "_has_tty", return_value=True), redirect_stdout(io.StringIO()):
            bootstrap.main([])
        run.assert_called_once_with(launcher, ["refresh"])

    def test_no_means_exit(self):
        self.install()
        with mock.patch.object(bootstrap, "_exec") as run, mock.patch("builtins.input", return_value="n"), \
             mock.patch.object(bootstrap, "_has_tty", return_value=True), redirect_stdout(io.StringIO()):
            self.assertEqual(bootstrap.main([]), 0)
        run.assert_not_called()

    def test_install_flags_are_not_passed_to_myfox(self):
        launcher = self.install()
        with mock.patch.object(bootstrap, "_exec", return_value=0) as run, mock.patch("builtins.input", return_value=""), \
             mock.patch.object(bootstrap, "_has_tty", return_value=True), redirect_stdout(io.StringIO()):
            bootstrap.main(["--gui"])
        run.assert_called_once_with(launcher, ["refresh", "--gui"])

    def test_yes_when_installed_asks_nothing(self):
        self.install()
        out = io.StringIO()
        with mock.patch.object(bootstrap, "_exec") as run, mock.patch("builtins.input", side_effect=AssertionError("asked")), \
             mock.patch.object(bootstrap, "_has_tty", return_value=True), redirect_stdout(out):
            self.assertEqual(bootstrap.main(["-y"]), 0)
        run.assert_not_called()
        self.assertIn(bootstrap.t("updates_hint"), out.getvalue())

    def test_without_a_terminal_names_the_command_instead_of_asking(self):
        self.install()
        out = io.StringIO()
        with mock.patch.object(bootstrap, "_exec") as run, mock.patch("builtins.input", side_effect=AssertionError("asked")), \
             mock.patch.object(bootstrap, "_has_tty", return_value=False), redirect_stdout(out):
            self.assertEqual(bootstrap.main([]), 0)
        run.assert_not_called()
        self.assertIn(bootstrap.t("updates_hint"), out.getvalue())

    @only_linux
    def test_the_installed_myfox_takes_this_process_over(self):
        launcher = self.install()
        with mock.patch("os.execv") as execv:
            bootstrap._exec(launcher, ["refresh"])
        execv.assert_called_once_with(str(launcher), [str(launcher), "refresh"])

    def test_state_without_install_dir_is_not_installed(self):
        self.install()
        self.state_file().write_text("{}")
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
            seen.update(cmd=cmd[1:], unpacked=sorted(p.name for p in root.iterdir()), cwd=kwargs.get("cwd") == root)
            return mock.Mock(returncode=0)

        with mock.patch.dict("os.environ", {"MYFOX_CORE_URL": str(archive)}), \
             mock.patch("subprocess.run", side_effect=run):
            self.assertEqual(bootstrap.main(["-y"]), 0)
        # From the core, so a myfox/ in the user's current directory isn't what runs.
        self.assertEqual(seen, {"cmd": ["-m", "myfox.wizard", "-y"], "unpacked": ["autoconfig", "chrome", "myfox"],
                                "cwd": True})

    def test_unsafe_archive_is_refused(self):
        archive = self._archive({"../evil": b"x"})
        with mock.patch.dict("os.environ", {"MYFOX_CORE_URL": str(archive)}), \
             mock.patch("subprocess.run") as run, mock.patch("sys.stderr", new=io.StringIO()):
            self.assertEqual(bootstrap.main([]), 1)
        run.assert_not_called()

    def test_core_dir_skips_the_download(self):
        core_dir = str(Path("/work/myfox").resolve())
        with mock.patch.dict("os.environ", {"MYFOX_CORE_DIR": core_dir}), \
             mock.patch("subprocess.run", return_value=mock.Mock(returncode=0)) as run:
            bootstrap.main([])
        self.assertTrue(run.call_args.kwargs["env"]["PYTHONPATH"].startswith(core_dir))


class CoreUrlTests(unittest.TestCase):
    def test_the_newest_core_tag_whose_release_has_the_archive(self):
        from ._helpers import git_refs
        refs = git_refs("refs/heads/master", "refs/tags/core-1.9.0", "refs/tags/core-1.10.0",
                        "refs/tags/core-1.11.0", "refs/tags/dearpygui-2.3.1")
        base = "https://github.com/CustomFF/myfox/releases/download/"

        def fake_urlopen(req, timeout):
            if req.full_url.endswith("/info/refs?service=git-upload-pack"):
                return mock.MagicMock(**{"__enter__.return_value.read.return_value": refs})
            if "core-1.11.0" in req.full_url:  # tagged, its release not out yet
                raise bootstrap.urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)
            return mock.MagicMock()

        with mock.patch.dict("os.environ", {}, clear=False), mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            os.environ.pop("MYFOX_CORE_URL", None)
            self.assertEqual(bootstrap._core_url(), (base + "core-1.10.0/myfox-core.tar.gz", "core-1.10.0"))


class LanguageTests(unittest.TestCase):
    def test_environment_wins_over_the_c_locale(self):
        env = {"LANGUAGE": "", "LC_ALL": "", "LC_MESSAGES": "", "LANG": "ru_RU.UTF-8"}
        with mock.patch.dict("os.environ", env), mock.patch("locale.getlocale", return_value=("C", "UTF-8")):
            self.assertEqual(bootstrap.t("check_updates"), bootstrap._MESSAGES["ru"]["check_updates"])


if __name__ == "__main__":
    unittest.main()
