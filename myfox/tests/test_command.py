from __future__ import annotations

import io
import os
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from myfox import command, i18n
from myfox.state import State

from ._helpers import IsolatedStateCase


class CommandTests(IsolatedStateCase):
    def setUp(self):
        super().setUp()
        self.bin = self.tmp_path / "home" / ".local" / "bin"
        self.install_dir = self.tmp_path / "ff"
        self.install_dir.mkdir()
        (self.install_dir / "firefox-myfox").write_text("#!/bin/sh\n", encoding="utf-8")
        self.link = self.bin / "firefox"
        self._path(str(self.bin))

    def _path(self, *dirs):
        patch = mock.patch.dict("os.environ", {"PATH": os.pathsep.join(dirs)})
        patch.start()
        self.addCleanup(patch.stop)

    def _system_firefox(self, name="usr") -> Path:
        directory = self.tmp_path / name
        directory.mkdir()
        exe = directory / "firefox"
        exe.write_text("#!/bin/sh\n", encoding="utf-8")
        exe.chmod(0o755)
        return exe

    def test_on_links_firefox_to_the_wrapper_and_off_removes_it(self):
        command.enable(self.install_dir)
        self.assertEqual(os.readlink(self.link), str(self.install_dir / "firefox-myfox"))
        self.assertTrue(command.is_on(self.install_dir))
        self.assertTrue(command.disable(self.install_dir))
        self.assertFalse(self.link.is_symlink() or self.link.exists())

    def test_a_foreign_firefox_is_kept_and_put_back(self):
        self.bin.mkdir(parents=True)
        self.link.symlink_to("/usr/lib/firefox/firefox")
        notes = command.check(self.install_dir)
        self.assertEqual(notes, [i18n.t("command_replaces", "~/.local/bin/firefox", "/usr/lib/firefox/firefox",
                                        "~/.local/bin/firefox.myfox-backup")])
        command.enable(self.install_dir)
        self.assertEqual(os.readlink(self.bin / "firefox.myfox-backup"), "/usr/lib/firefox/firefox")
        command.disable(self.install_dir)
        self.assertEqual(os.readlink(self.link), "/usr/lib/firefox/firefox")
        self.assertFalse((self.bin / "firefox.myfox-backup").is_symlink())

    def test_a_link_left_by_another_myfox_install_is_not_kept(self):
        self.bin.mkdir(parents=True)
        self.link.symlink_to("/gone/firefox-myfox")
        self.assertEqual(command.check(self.install_dir), [])
        command.enable(self.install_dir)
        self.assertFalse((self.bin / "firefox.myfox-backup").is_symlink())

    def test_off_leaves_a_firefox_that_isnt_ours(self):
        self.bin.mkdir(parents=True)
        self.link.write_text("#!/bin/sh\n", encoding="utf-8")
        self.assertFalse(command.disable(self.install_dir))
        self.assertTrue(self.link.is_file())

    def test_bin_dir_missing_from_path(self):
        self._path(str(self._system_firefox().parent.parent / "nowhere"))
        self.assertEqual(command.shadow(), ("not_in_path", None))
        self.assertEqual(command.check(self.install_dir), [i18n.t("command_not_in_path", "~/.local/bin")])

    def test_another_firefox_earlier_in_path_wins(self):
        exe = self._system_firefox()
        self._path(str(exe.parent), str(self.bin))
        self.assertEqual(command.shadow(), ("shadowed", str(exe)))

    def test_ours_earlier_in_path_wins(self):
        exe = self._system_firefox()
        self._path(str(self.bin), str(exe.parent))
        self.assertEqual(command.shadow(), ("ok", None))

    def test_status_and_on_with_yes(self):
        state = State()
        state.set("install_dir", str(self.install_dir))
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(command.run(state, None), 0)
            self.assertEqual(command.run(state, "on", noninteractive=True), 0)
            self.assertEqual(command.run(state, None), 0)
        self.assertTrue(command.is_on(self.install_dir))
        lines = out.getvalue().splitlines()
        self.assertEqual(lines[0], i18n.t("command_is_off"))
        self.assertEqual(lines[-1], i18n.t("command_is_on", "~/.local/bin/firefox"))

    def test_replacing_a_foreign_firefox_starts_on_cancel(self):
        self.bin.mkdir(parents=True)
        self.link.symlink_to("/usr/bin/firefox")
        state = State()
        state.set("install_dir", str(self.install_dir))
        self.assertTrue(command.build(state, on=True).destructive)
