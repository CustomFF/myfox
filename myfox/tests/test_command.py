from __future__ import annotations

import io
import json
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

    def test_off_can_leave_the_backup_aside(self):
        self.bin.mkdir(parents=True)
        self.link.symlink_to("/usr/lib/firefox/firefox")
        command.enable(self.install_dir)
        command.disable(self.install_dir, keep_backup=True)
        self.assertFalse(self.link.is_symlink())
        self.assertEqual(os.readlink(command.backup()), "/usr/lib/firefox/firefox")
        # On again: the slot is free, the old backup stays as it is.
        command.enable(self.install_dir)
        self.assertTrue(command.is_on(self.install_dir))
        self.assertEqual(os.readlink(command.backup()), "/usr/lib/firefox/firefox")

    def test_a_second_foreign_firefox_is_never_thrown_away(self):
        self.bin.mkdir(parents=True)
        (self.bin / "firefox.myfox-backup").symlink_to("/old/firefox")
        self.link.symlink_to("/new/firefox")
        with self.assertRaises(command.BackupTaken):
            command.enable(self.install_dir)
        self.assertEqual((os.readlink(self.link), os.readlink(self.bin / "firefox.myfox-backup")),
                         ("/new/firefox", "/old/firefox"))
        state = State()
        state.set("install_dir", str(self.install_dir))
        self.assertEqual(command.build(state, on=True).blocked,
                         i18n.t("command_backup_taken", "~/.local/bin/firefox", "~/.local/bin/firefox.myfox-backup"))

    def test_off_dialog_offers_to_put_the_backup_back(self):
        self.bin.mkdir(parents=True)
        self.link.symlink_to("/usr/bin/firefox")
        command.enable(self.install_dir)
        state = State()
        state.set("install_dir", str(self.install_dir))
        task = command.build(state, on=False)
        self.assertEqual([o.value for o in task.options], [True])
        self.assertEqual([o.value for o in command.build(state, on=False, keep_backup=True).options], [False])
        task.options[0].value = False
        task.run(lambda message, fraction: None)
        self.assertEqual(os.readlink(command.backup()), "/usr/bin/firefox")

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

    def test_json_for_the_browser(self):
        state = State()
        state.set("install_dir", str(self.install_dir))
        self.bin.mkdir(parents=True)
        self.link.symlink_to("/usr/bin/firefox")

        def run(action):
            out = io.StringIO()
            with redirect_stdout(out), mock.patch("myfox.task.show", side_effect=AssertionError("asked")):
                rc = command.run(state, action, as_json=True)
            return rc, json.loads(out.getvalue())

        rc, before = run(None)
        self.assertEqual((rc, before["on"], before["replaces"], before["path"], before["backup"]),
                         (0, False, "/usr/bin/firefox", "ok", None))
        self.assertEqual(before["notes"], command.check(self.install_dir))
        rc, after = run("on")
        self.assertEqual((rc, after["on"], after["replaces"], after["notes"]), (0, True, None, []))
        self.assertEqual(after["backup"], str(self.bin / "firefox.myfox-backup"))
        rc, off = run("off")
        self.assertEqual((rc, off["on"]), (0, False))
        self.assertEqual(os.readlink(self.link), "/usr/bin/firefox")

    def test_json_off_can_keep_the_backup(self):
        state = State()
        state.set("install_dir", str(self.install_dir))
        self.bin.mkdir(parents=True)
        self.link.symlink_to("/usr/bin/firefox")
        command.enable(self.install_dir)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(command.run(state, "off", as_json=True, keep_backup=True), 0)
        result = json.loads(out.getvalue())
        self.assertEqual((result["on"], result["backup"]), (False, str(self.bin / "firefox.myfox-backup")))
        self.assertFalse(self.link.is_symlink())

    def test_json_failure_is_an_error_object(self):
        state = State()
        state.set("install_dir", str(self.install_dir))
        out = io.StringIO()
        with redirect_stdout(out), mock.patch("myfox.command.enable", side_effect=PermissionError("denied")):
            self.assertEqual(command.run(state, "on", as_json=True), 1)
        self.assertEqual(json.loads(out.getvalue()), {"error": "denied"})
