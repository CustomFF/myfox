from __future__ import annotations

import contextlib
import io
import json
import re
import sqlite3
import os
from pathlib import Path
from unittest import mock

from myfox import __main__ as cli
from myfox import i18n, importer, paths, profile_commands, profiles
from myfox.state import State

from ._helpers import IsolatedStateCase


class ProfileListTests(IsolatedStateCase):
    def setUp(self):
        super().setUp()
        self.store = Path.home() / ".mozilla" / "firefox"
        self.install = self.tmp_path / "firefox"
        self.install.mkdir()
        entries = []
        for folder, name, last in (("myfox-1", "myfox", self.install), ("myfox-2", "work copy", self.install),
                                   ("aaaa.dev", "dev", self.install), ("bbbb.new", "new", None),
                                   ("cccc.default-release", "default-release", Path("/usr/lib/firefox"))):
            path = self.store / folder
            path.mkdir(parents=True)
            (path / "prefs.js").touch()
            if last is not None:
                (path / "compatibility.ini").write_text(
                    f"[Compatibility]\nLastVersion=158.0_1/1\nLastPlatformDir={last}\n", encoding="utf-8")
            entries.append(f"[Profile{len(entries)}]\nName={name}\nIsRelative=1\nPath={folder}\n")
        (self.store / "profiles.ini").write_text("\n".join(entries), encoding="utf-8")
        for folder in ("myfox-1", "myfox-2"):
            (self.store / folder / ".myfox").touch()
        importer.write_origin(self.store / "myfox-2", self.store / "cccc.default-release", importer.SYNC_NONE, [])
        state = State()
        state.set("install_dir", str(self.install))
        state.set("profile_dir", str(self.store / "myfox-1"))
        state.save()
        in_use = mock.patch("myfox.sources.in_use", side_effect=lambda p: p.id == "aaaa.dev")
        in_use.start()
        self.addCleanup(in_use.stop)

    def _run(self, *argv: str) -> str:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cli.main(["profile", "list", *argv]), 0)
        return out.getvalue()

    def test_the_related_ones_with_their_state(self):
        lines = self._run().splitlines()
        self.assertEqual(lines[0].split(), [i18n.t("profile_col_id"), i18n.t("profile_col_name"),
                                            i18n.t("profile_col_tweaks"), i18n.t("profile_col_status")])
        rows = {line.split()[0]: line for line in lines[1:4]}
        self.assertEqual(list(rows), ["myfox-1", "myfox-2", "aaaa.dev"])
        self.assertTrue(rows["myfox-1"].endswith(i18n.t("profile_status_used")))
        self.assertIn("work copy", rows["myfox-2"])
        self.assertTrue(rows["myfox-2"].endswith(i18n.t("profile_status_imported", "cccc.default-release")))
        self.assertTrue(rows["aaaa.dev"].endswith(", ".join([i18n.t("profile_status_ours"),
                                                             i18n.t("profile_status_open")])))
        self.assertEqual(lines[5:], ["", i18n.t("profile_list_hidden", 1, "myfox profile list --all")])
        # Columns line up.
        self.assertEqual(len({line.index(i18n.t("summary_yes")) for line in lines[1:3]}), 1)

    def test_one_outside_profiles_ini_is_listed_by_its_own_name(self):
        outside = self.store / "myfox-3"
        outside.mkdir()
        for f in ("prefs.js", ".myfox", ".myfox-created"):
            (outside / f).touch()
        (outside / ".myfox-name").write_text("Work\n", encoding="utf-8")
        row = next(line for line in self._run().splitlines() if line.startswith("myfox-3"))
        self.assertIn("Work", row)
        self.assertTrue(row.endswith(i18n.t("profile_status_myfox")))

    def test_never_run_is_related_too(self):
        self.assertIn(i18n.t("profile_status_unused"), self._run())

    def test_all_adds_the_foreign_ones(self):
        out = self._run("--all")
        self.assertIn(i18n.t("profile_status_foreign"), out)
        self.assertNotIn(i18n.t("profile_list_hidden", 1, "myfox profile list --all"), out)

    def test_json(self):
        out = self._run("--all", "--json")
        self.assertEqual(out.count("\n"), 1)  # one line
        records = {r["id"]: r for r in json.loads(out)}
        self.assertEqual(len(records), 5)
        self.assertEqual({k: records["myfox-1"][k] for k in ("tweaks", "used", "owner", "store", "last_version")},
                         {"tweaks": True, "used": True, "owner": "myfox", "store": "myfox", "last_version": "158.0"})
        self.assertEqual(records["myfox-2"]["imported_from"], str(self.store / "cccc.default-release"))
        self.assertTrue(records["aaaa.dev"]["open"])
        self.assertEqual(records["cccc.default-release"]["owner"], "foreign")
        self.assertEqual([records[i]["created"] for i in ("myfox-1", "aaaa.dev")], [False, False])
        self.assertIsNone(records["myfox-1"]["last_used"])
        self.assertEqual([records["myfox-2"][k] for k in ("moved", "account")], [False, False])

    def test_firefoxs_placeholder_only_with_all_and_marked(self):
        stub = self.store / "dddd.default"
        stub.mkdir()
        (stub / "times.json").write_text("{}", encoding="utf-8")
        ini = self.store / "profiles.ini"
        ini.write_text(ini.read_text(encoding="utf-8") + "\n[Profile9]\nName=default\nIsRelative=1\nPath=dddd.default\n",
                       encoding="utf-8")
        self.assertNotIn("dddd.default", self._run())
        self.assertNotIn("dddd.default", self._run("--json"))
        self.assertIn(i18n.t("profile_status_placeholder"), self._run("--all"))
        records = {r["id"]: r for r in json.loads(self._run("--all", "--json"))}
        self.assertTrue(records["dddd.default"]["placeholder"])
        self.assertFalse(records["aaaa.dev"]["placeholder"])

    def test_json_says_which_are_signed_in(self):
        (self.store / "cccc.default-release" / "signedInUser.json").write_text("{}", encoding="utf-8")
        records = {r["id"]: r for r in json.loads(self._run("--all", "--json"))}
        self.assertTrue(records["cccc.default-release"]["account"])

    def test_json_created_and_last_used(self):
        (self.store / "myfox-2" / ".myfox-created").touch()
        lock = self.store / "myfox-1" / ".parentlock"
        lock.touch()
        os.utime(lock, (1767225600, 1767225600))
        records = {r["id"]: r for r in json.loads(self._run("--json"))}
        self.assertTrue(records["myfox-2"]["created"])
        self.assertEqual(records["myfox-1"]["last_used"], "2026-01-01T00:00:00Z")

    def test_json_error(self):
        with mock.patch("myfox.sources.listing", side_effect=OSError("denied")), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cli.main(["profile", "list", "--json"]), 1)
        self.assertEqual(json.loads(out.getvalue()), {"error": "denied"})

    def test_none_related(self):
        state = State()
        state.clear()
        state.save()
        for folder in ("myfox-1", "myfox-2"):
            (self.store / folder / ".myfox").unlink()
        with mock.patch("myfox.sources.listing", return_value=[]):
            self.assertEqual(self._run(), i18n.t("profile_list_none") + "\n")

    def test_quoted_ids(self):
        self.assertEqual(profile_commands.quoted("my profile"), "'my profile'")
        self.assertEqual(profile_commands.quoted("myfox-1"), "myfox-1")


class _ProfileCase(IsolatedStateCase):
    """A store with our profile, a related one and another Firefox's."""

    def setUp(self):
        super().setUp()
        self.store = Path.home() / ".mozilla" / "firefox"
        self.install = self.tmp_path / "firefox"
        self.install.mkdir()
        self.used = self._profile("myfox-1", "myfox", created=True, tweaked=True, last=self.install)
        self.dev = self._profile("aaaa.dev", "dev", last=self.install)
        self.other = self._profile("cccc.default-release", "default-release", last=Path("/usr/lib/firefox"))
        state = State()
        for key, value in (("install_dir", str(self.install)), ("profile_dir", str(self.used)),
                           ("install_hash", "HASH"), ("firefox_version", "158.0"), ("theme", "dark")):
            state.set(key, value)
        state.save()
        self.running = []
        self.open = set()
        for target, kwargs in (("myfox.firefox.running_pids", {"side_effect": lambda d: self.running}),
                               ("myfox.sources.in_use", {"side_effect": lambda p: p.path in self.open}),
                               ("myfox.apply.tweak_profile", {"side_effect": self._tweak}),
                               ("myfox.profiles.pin_install", {"return_value": "HASH"}),
                               ("myfox.importer.system_theme", {"return_value": None}),
                               ("myfox.firefox.start", {}),
                               ("myfox.firefox.quit_and_wait", {"return_value": True})):
            patcher = mock.patch(target, **kwargs)
            setattr(self, target.rsplit(".", 1)[1], patcher.start())
            self.addCleanup(patcher.stop)

    @staticmethod
    def _tweak(profile_dir, state):
        (profile_dir / ".myfox").touch()

    def _profile(self, folder, name, created=False, tweaked=False, last=None) -> Path:
        path = self.store / folder
        path.mkdir(parents=True)
        (path / "prefs.js").write_text('user_pref("browser.x", 1);\n', encoding="utf-8")
        if created:
            (path / ".myfox-created").touch()
        if tweaked:
            (path / ".myfox").touch()
        if last is not None:
            (path / "compatibility.ini").write_text(
                f"[Compatibility]\nLastVersion=157.0_1/1\nLastPlatformDir={last}\n", encoding="utf-8")
        ini = self.store / "profiles.ini"
        text = ini.read_text(encoding="utf-8") if ini.is_file() else ""
        n = text.count("[Profile")
        ini.write_text(text + f"[Profile{n}]\nName={name}\nIsRelative=1\nPath={folder}\n\n", encoding="utf-8")
        return path

    def _run(self, *argv: str) -> int:
        with contextlib.redirect_stdout(io.StringIO()) as self.out, \
             contextlib.redirect_stderr(io.StringIO()) as self.err:
            return cli.main(["profile", *argv])

    def _ini(self) -> str:
        return (self.store / "profiles.ini").read_text(encoding="utf-8")

class ProfileChangeTests(_ProfileCase):
    """new, apply, use, remove, import, rename — confirmed with -y."""

    def test_new_makes_a_tweaked_profile_outside_profiles_ini_with_firefox_open(self):
        self.running = [42]
        self.assertEqual(self._run("new", "-y"), 0)
        made = self.store / "myfox-2"
        self.assertTrue((made / ".myfox-created").is_file() and (made / ".myfox").is_file())
        self.assertEqual(State().get("profile_dir"), str(self.used))
        self.assertNotIn("myfox-2", self._ini())
        self.assertEqual(profiles.read_name(made), "myfox-2")
        self.assertIn("myfox-2", self._run_list())

    def _run_list(self) -> str:
        self._run("list")
        return self.out.getvalue()

    def test_new_with_a_name_opened_beside(self):
        self.running = [42]
        self.assertEqual(self._run("new", "--name", " Work ", "--open", "-y"), 0)
        made = self.store / "myfox-2"
        self.assertEqual(profiles.read_name(made), "Work")
        self.start.assert_called_once_with(self.install, made)

    def test_new_with_use_switches_to_it(self):
        self.assertEqual(self._run("new", "--use", "-y"), 0)
        self.assertEqual(State().get("profile_dir"), str(self.store / "myfox-2"))
        self.assertEqual(self.pin_install.call_args.args[1], self.store / "myfox-2")

    def test_new_to_use_waits_for_our_firefox(self):
        self.running = [42]
        self.assertEqual(self._run("new", "--use", "-y"), 1)
        self.assertIn(i18n.t("err_firefox_running"), self.err.getvalue())
        self.assertFalse((self.store / "myfox-2").exists())

    def test_a_failed_new_takes_itself_back(self):
        self.tweak_profile.side_effect = OSError("no network")
        self.assertEqual(self._run("new", "-y"), 1)
        self.assertFalse((self.store / "myfox-2").exists())
        self.assertNotIn("myfox-2", (self.store / "profiles.ini").read_text(encoding="utf-8"))

    def test_without_yes_the_command_is_named(self):
        with mock.patch("myfox.ui._has_tty", return_value=False):
            self.assertEqual(self._run("apply", "dev"), 1)
        self.assertIn(i18n.t("needs_yes_profile", "myfox profile apply aaaa.dev -y"), self.err.getvalue())
        self.tweak_profile.assert_not_called()

    def test_apply_a_related_one(self):
        self.assertEqual(self._run("apply", "dev", "-y"), 0)
        self.assertTrue((self.dev / ".myfox").is_file())

    def test_apply_waits_for_it_to_close(self):
        self.open = {self.dev}
        self.assertEqual(self._run("apply", "aaaa.dev", "-y"), 1)
        self.assertIn(i18n.t("err_profile_open", "aaaa.dev"), self.err.getvalue())

    def test_a_foreign_one_is_only_imported(self):
        for command in ("apply", "use"):
            self.assertEqual(self._run(command, "default-release", "-y"), 1)
            self.assertIn(i18n.t("err_profile_foreign", "cccc.default-release",
                                 "myfox profile import cccc.default-release"), self.err.getvalue())

    def test_apply_needs_the_tweaks_installed(self):
        state = State()
        state.set("tweaks", False)
        state.save()
        self.assertEqual(self._run("apply", "dev", "-y"), 1)
        self.assertIn(i18n.t("err_profile_no_tweaks"), self.err.getvalue())

    def test_use_switches(self):
        self.assertEqual(self._run("use", "dev", "-y"), 0)
        self.assertEqual(State().get("profile_dir"), str(self.dev))
        self.assertIn("myfox profile apply aaaa.dev", self.out.getvalue())  # no tweaks yet

    def test_use_the_one_already_used(self):
        self.assertEqual(self._run("use", "myfox-1", "-y"), 1)
        self.assertIn(i18n.t("profile_use_already", "myfox-1"), self.err.getvalue())

    def test_remove_only_ours_and_not_the_used_one(self):
        self.assertEqual(self._run("remove", "dev", "-y"), 1)
        self.assertIn(i18n.t("err_profile_not_created", "aaaa.dev"), self.err.getvalue())
        self.assertEqual(self._run("remove", "myfox-1", "-y"), 1)
        self.assertIn(i18n.t("err_profile_used", "myfox-1", "myfox profile use"), self.err.getvalue())
        self.assertTrue(self.used.is_dir() and self.dev.is_dir())

    def test_remove(self):
        made = self._profile("myfox-2", "myfox", created=True, tweaked=True)
        self.assertEqual(self._run("remove", "myfox-2", "-y"), 0)
        self.assertFalse(made.exists())
        self.assertNotIn("myfox-2", (self.store / "profiles.ini").read_text(encoding="utf-8"))

    def test_remove_with_our_firefox_open_on_another_profile(self):
        self.running = [42]
        self.assertEqual(self._run("new", "-y"), 0)
        self.assertEqual(self._run("remove", "myfox-2", "-y"), 0)
        self.assertFalse((self.store / "myfox-2").exists())

    def test_remove_of_one_profiles_ini_lists_waits_for_our_firefox(self):
        # An older MyFox listed them all; a running Firefox would put it back.
        made = self._profile("myfox-2", "myfox", created=True, tweaked=True)
        self.running = [42]
        self.assertEqual(self._run("remove", "myfox-2", "-y"), 1)
        self.assertIn(i18n.t("err_firefox_running"), self.err.getvalue())
        self.assertTrue(made.exists())

    def test_remove_takes_it_out_of_its_profile_group(self):
        made = self._profile("myfox-2", "myfox", created=True, tweaked=True)
        with mock.patch("myfox.sources.forget_in_groups") as forget:
            self.assertEqual(self._run("remove", "myfox-2", "-y"), 0)
        forget.assert_called_once_with(self.store, made)

    def test_json_says_where_a_moved_account_goes_back(self):
        moved = self._profile("myfox-2", "myfox", created=True, tweaked=True)
        copied = self._profile("myfox-3", "myfox", created=True, tweaked=True)
        (self.other / "signedInUser.json").write_text("{}", encoding="utf-8")
        importer.write_origin(copied, self.other, importer.SYNC_COPY, [])
        importer.write_origin(moved, self.other, importer.SYNC_MOVE, importer.move_sync_out(self.other))
        self._run("list", "--json")
        records = {r["id"]: r for r in json.loads(self.out.getvalue())}
        self.assertEqual(records["myfox-2"]["restore_sync"], str(self.other))
        self.assertIsNone(records["myfox-3"]["restore_sync"])
        self.assertIsNone(records["myfox-1"]["restore_sync"])

    def test_remove_gives_a_moved_account_back(self):
        made = self._profile("myfox-2", "myfox", created=True, tweaked=True)
        (self.other / "signedInUser.json").write_text("{}", encoding="utf-8")
        importer.write_origin(made, self.other, importer.SYNC_MOVE, importer.move_sync_out(self.other))
        self.open = {self.other}
        self.assertEqual(self._run("remove", "myfox-2", "-y"), 1)
        self.assertIn(i18n.t("err_restore_sync_in_use", str(self.other).replace(str(Path.home()), "~")),
                      self.err.getvalue())
        self.open = set()
        self.assertEqual(self._run("remove", "myfox-2", "-y"), 0)
        self.assertTrue((self.other / "signedInUser.json").is_file())

    def test_import(self):
        (self.other / "places.sqlite").write_text("x", encoding="utf-8")
        (self.other / "signedInUser.json").write_text("{}", encoding="utf-8")
        self.assertEqual(self._run("import", "default-release", "--sync", "move", "--use", "-y"), 0)
        copy = self.store / "myfox-2"
        self.assertTrue((copy / "places.sqlite").is_file() and (copy / "signedInUser.json").is_file())
        self.assertTrue((copy / ".myfox").is_file())
        self.assertFalse((self.other / "signedInUser.json").exists())
        self.assertEqual(importer.read_origin(copy)["source"], str(self.other))
        self.assertEqual(State().get("profile_dir"), str(copy))
        self.assertEqual(profiles.read_name(copy), "default-release (MyFox)")
        # The one opened before leaves profiles.ini, its name kept.
        self.assertNotIn("Path=myfox-1\n", self._ini())
        self.assertEqual(profiles.read_name(self.used), "myfox")

    def test_import_with_firefox_open_and_out_of_the_originals_group(self):
        (self.other / "prefs.js").write_text('user_pref("toolkit.profiles.storeID", "15475d1e");\n'
                                             'user_pref("browser.x", 1);\n', encoding="utf-8")
        self.running = [42]
        self.assertEqual(self._run("import", "cccc.default-release", "-y"), 0)
        copy = self.store / "myfox-2"
        self.assertNotIn("storeID", (copy / "prefs.js").read_text(encoding="utf-8"))
        self.assertIn("storeID", (self.other / "prefs.js").read_text(encoding="utf-8"))
        self.assertNotIn("myfox-2", self._ini())

    def test_import_of_a_newer_profile_needs_the_flag(self):
        (self.other / "compatibility.ini").write_text("[Compatibility]\nLastVersion=160.0_1/1\n", encoding="utf-8")
        self.assertEqual(self._run("import", "cccc.default-release", "-y"), 1)
        self.assertIn(i18n.t("err_profile_downgrade", "160.0", "158.0"), self.err.getvalue())
        with mock.patch("myfox.importer.accept_downgrade") as accept:
            self.assertEqual(self._run("import", "cccc.default-release", "--allow-downgrade", "-y"), 0)
        accept.assert_called_once()

    def test_import_of_an_open_one_waits(self):
        self.open = {self.other}
        self.assertEqual(self._run("import", "cccc.default-release", "-y"), 1)
        self.assertIn(i18n.t("err_import_in_use", "cccc.default-release"), self.err.getvalue())

    def test_a_failed_import_takes_itself_back(self):
        (self.other / "signedInUser.json").write_text("{}", encoding="utf-8")
        with mock.patch("myfox.importer.write_origin", side_effect=OSError("disk full")):
            self.assertEqual(self._run("import", "cccc.default-release", "--sync", "move", "-y"), 1)
        self.assertFalse((self.store / "myfox-2").exists())
        self.assertTrue((self.other / "signedInUser.json").is_file())

    def test_import_names_the_copy(self):
        self.assertEqual(self._run("import", "cccc.default-release", "--name", "  Work  stuff ", "-y"), 0)
        self.assertEqual(profiles.read_name(self.store / "myfox-2"), "Work stuff")

    def test_rename_with_firefox_open(self):
        self.running = [42]
        self.assertEqual(self._run("new", "-y"), 0)
        self.assertEqual(self._run("rename", "myfox-2", " Work  stuff "), 0)
        self.assertEqual(profiles.read_name(self.store / "myfox-2"), "Work stuff")
        self._run("list", "--json")
        names = {r["id"]: r["name"] for r in json.loads(self.out.getvalue())}
        self.assertEqual(names["myfox-2"], "Work stuff")

    def test_rename_of_the_one_profiles_ini_lists_follows_there_once_firefox_is_closed(self):
        self.running = [42]
        self.assertEqual(self._run("rename", "myfox-1", "Main"), 0)
        self.assertIn("Name=myfox\nIsRelative=1\nPath=myfox-1", self._ini())
        self.running = []
        self.assertEqual(self._run("rename", "myfox-1", "Main"), 0)
        self.assertIn("Name=Main\nIsRelative=1\nPath=myfox-1", self._ini())

    def test_rename_only_myfoxs_own_and_not_to_nothing(self):
        self.assertEqual(self._run("rename", "aaaa.dev", "x", "--json"), 1)
        self.assertEqual(json.loads(self.out.getvalue()),
                         {"error": i18n.t("err_profile_rename_not_created", "aaaa.dev")})
        self.assertEqual(self._run("rename", "myfox-1", "  "), 1)
        self.assertIn(i18n.t("err_profile_rename_empty"), self.err.getvalue())
        self.assertEqual(self._run("rename", "myfox-1", "Main", "--json"), 0)
        self.assertEqual(json.loads(self.out.getvalue()), {"ok": True, "id": "myfox-1", "name": "Main"})

    def test_import_switches_the_copy_to_the_myfox_theme_like_its_own(self):
        with (self.other / "prefs.js").open("a", encoding="utf-8") as f:
            f.write('user_pref("browser.theme.toolbar-theme", 1);\n')
        self.assertEqual(self._run("import", "cccc.default-release", "-y"), 0)
        copy = self.store / "myfox-2"
        self.assertTrue((copy / importer.THEME_MARKER).is_file())
        self.assertIn('user_pref("myfox.theme", "light");', (copy / "user.js").read_text(encoding="utf-8"))

    def test_import_move_takes_the_source_out_of_its_firefox(self):
        (self.other / "signedInUser.json").write_text("{}", encoding="utf-8")
        ini = self.store / "profiles.ini"
        ini.write_text(ini.read_text(encoding="utf-8") + "[InstallABC]\nDefault=cccc.default-release\nLocked=1\n\n",
                       encoding="utf-8")
        self.assertEqual(self._run("import", "cccc.default-release", "--move", "-y"), 0)
        copy = self.store / "myfox-2"
        self.assertTrue((copy / "signedInUser.json").is_file())  # the account goes along
        self.assertFalse(self.other.exists())
        self.assertEqual(list(self.store.glob(".*myfox-moving")), [])
        text = ini.read_text(encoding="utf-8")
        self.assertNotIn("cccc.default-release", text)
        self.assertNotIn("[Profile3]", text)  # no gap left behind
        self.assertTrue(importer.read_origin(copy)["moved"])

    def test_a_failed_move_leaves_the_source_as_it_was(self):
        ini = self.store / "profiles.ini"
        before = ini.read_text(encoding="utf-8")
        with mock.patch("myfox.profile_commands._use", side_effect=OSError("pin failed")):
            self.assertEqual(self._run("import", "cccc.default-release", "--move", "--use", "-y"), 1)
        self.assertTrue((self.other / "prefs.js").is_file())
        self.assertFalse((self.store / "myfox-2").exists())
        self.assertEqual(ini.read_text(encoding="utf-8").rstrip(), before.rstrip())

    def test_import_open_starts_the_copy_beside_our_firefox(self):
        self.assertEqual(self._run("import", "cccc.default-release", "--open", "-y"), 0)
        self.start.assert_called_once_with(self.install, self.store / "myfox-2")

    def test_import_open_with_use_starts_our_firefox_in_it(self):
        self.assertEqual(self._run("import", "cccc.default-release", "--open", "--use", "-y"), 0)
        self.start.assert_called_once_with(self.install, None)

    def test_relaunch_closes_our_firefox_imports_and_starts_it_again(self):
        self.running = [42]  # closed by the run, not a reason to refuse
        self.assertEqual(self._run("import", "cccc.default-release", "--open", "--relaunch"), 0)
        self.quit_and_wait.assert_called_once()
        self.assertEqual([c.args for c in self.start.call_args_list],
                         [(self.install,), (self.install, self.store / "myfox-2")])

    def test_relaunch_closes_and_reopens_every_open_myfox_profile(self):
        self.running = [42]
        self.open = {self.used, self.dev}
        self.assertEqual(self._run("use", "dev", "--relaunch"), 0)
        self.assertEqual(self.quit_and_wait.call_args.args[1], [self.used, self.dev])
        # dev is the default now: it opens in the usual way; myfox-1 isn't reopened beside it.
        self.assertEqual([c.args for c in self.start.call_args_list], [(self.install,)])

    def test_relaunch_reopens_a_second_profile_beside_the_default(self):
        self.running = [42]
        self.open = {self.used, self.dev}
        self.assertEqual(self._run("import", "cccc.default-release", "--relaunch"), 0)
        self.assertEqual([c.args for c in self.start.call_args_list], [(self.install,), (self.install, self.dev)])

    def test_relaunch_starts_firefox_again_after_a_failure(self):
        self.running = [42]
        with mock.patch("myfox.importer.write_origin", side_effect=OSError("disk full")):
            self.assertEqual(self._run("import", "cccc.default-release", "--open", "--relaunch"), 1)
        self.assertEqual([c.args for c in self.start.call_args_list], [(self.install,)])
        self.assertFalse((self.store / "myfox-2").exists())

    def test_relaunch_that_cannot_close_firefox_changes_nothing(self):
        self.quit_and_wait.side_effect = OSError(i18n.t("err_firefox_did_not_quit"))
        self.assertEqual(self._run("use", "dev", "--relaunch"), 1)
        self.assertEqual(State().get("profile_dir"), str(self.used))
        self.start.assert_not_called()

    def test_use_relaunch_switches_and_starts_firefox_again(self):
        self.running = [42]
        self.assertEqual(self._run("use", "dev", "--relaunch"), 0)
        self.assertEqual(State().get("profile_dir"), str(self.dev))
        self.start.assert_called_once_with(self.install)

    def test_without_an_id_the_choice_is_listed(self):
        self.assertEqual(self._run("use"), 1)
        self.assertIn("aaaa.dev", self.out.getvalue())
        self.assertIn(i18n.t("err_profile_missing", "myfox profile use <ID>"), self.err.getvalue())

    def test_without_an_id_in_a_terminal_it_asks_which(self):
        shown = []

        def show(t, gui=False, noninteractive=False):
            shown.append(t)
            if t.choices:
                t.choice = t.choices[0][0]
            return True

        with mock.patch("myfox.ui._has_tty", return_value=True), mock.patch("myfox.task.show", side_effect=show):
            self.assertEqual(self._run("use"), 0)
        picker, confirm = shown
        # Not the one already used; related only.
        self.assertEqual(picker.choices, [("aaaa.dev", "dev (aaaa.dev)")])
        self.assertEqual(confirm.rows[0][1], f"aaaa.dev ({paths.shown(self.dev)})")

    def test_a_cancelled_pick_does_nothing(self):
        with mock.patch("myfox.ui._has_tty", return_value=True), mock.patch("myfox.task.show", return_value=False):
            self.assertEqual(self._run("apply"), 1)
        self.tweak_profile.assert_not_called()

    def test_what_each_command_can_pick(self):
        made = self._profile("myfox-2", "spare", created=True, tweaked=True)
        ids = {c: [p.id for p in profile_commands.candidates(State(), c)] for c in ("apply", "use", "remove", "import")}
        self.assertEqual(ids, {"apply": ["myfox-1", "aaaa.dev", "myfox-2"], "use": ["aaaa.dev", "myfox-2"],
                               "remove": [made.name], "import": ["aaaa.dev", "cccc.default-release"]})

    def test_apply_json(self):
        self.assertEqual(self._run("apply", "dev", "--json"), 0)
        self.assertEqual(json.loads(self.out.getvalue()), {"ok": True, "id": "aaaa.dev"})
        self.assertTrue((self.dev / ".myfox").is_file())

    def test_apply_json_errors(self):
        self.open = {self.dev}
        self.assertEqual(self._run("apply", "dev", "--json"), 1)
        self.assertEqual(json.loads(self.out.getvalue()), {"error": i18n.t("err_profile_open", "aaaa.dev")})
        self.assertEqual(self._run("apply", "default-release", "--json"), 1)
        self.assertIn("error", json.loads(self.out.getvalue()))
        self.tweak_profile.side_effect = OSError("no network")
        self.open = set()
        self.assertEqual(self._run("apply", "dev", "--json"), 1)
        self.assertEqual(json.loads(self.out.getvalue()), {"error": "no network"})

    def test_not_installed(self):
        State().delete_file()
        self.assertEqual(self._run("new", "-y"), 1)
        self.assertIn(i18n.t("err_not_installed"), self.err.getvalue())



class TidyTests(_ProfileCase):
    """What an older MyFox and Firefox's profile groups left in profiles.ini."""

    def setUp(self):
        super().setUp()
        self.made = self._profile("myfox-2", "Work", created=True, tweaked=True)
        ini = self.store / "profiles.ini"
        ini.write_text(ini.read_text(encoding="utf-8")
                       + "[Profile4]\nName=myfox\nIsRelative=1\nPath=myfox-1\nStoreID=abc\n\n"
                       + "[Profile5]\nName=myfox\nIsRelative=1\nPath=myfox-7\n\n"
                       + "[Profile6]\nName=gone\nIsRelative=1\nPath=zzzz.gone\n\n", encoding="utf-8")
        (self.made / "prefs.js").write_text('user_pref("toolkit.profiles.storeID", "abc");\n', encoding="utf-8")
        groups = self.store / "Profile Groups"
        groups.mkdir()
        con = sqlite3.connect(str(groups / "abc.sqlite"))
        with con:
            con.execute("CREATE TABLE Profiles (id INTEGER PRIMARY KEY, path TEXT, name TEXT)")
            con.executemany("INSERT INTO Profiles (path, name) VALUES (?, ?)",
                            [("cccc.default-release", "Base"), ("myfox-2", "Work")])
        con.close()

    def _group(self) -> list[str]:
        con = sqlite3.connect(str(self.store / "Profile Groups" / "abc.sqlite"))
        try:
            return [path for path, in con.execute("SELECT path FROM Profiles")]
        finally:
            con.close()

    def test_tidies_with_our_firefox_closed(self):
        profile_commands.tidy(State())
        ini = self._ini()
        # MyFox's other profile leaves profiles.ini, its name kept.
        self.assertNotIn("Path=myfox-2\n", ini)
        self.assertEqual(profiles.read_name(self.made), "Work")
        # The one it opens is listed once.
        self.assertEqual(ini.count("Path=myfox-1\n"), 1)
        # A myfox-N folder gone goes, another Firefox's entry stays.
        self.assertNotIn("myfox-7", ini)
        self.assertIn("Path=zzzz.gone\n", ini)
        self.assertEqual(sorted(re.findall(r"\[Profile(\d+)\]", ini)), ["0", "1", "2", "3"])
        # The copy leaves the original's group.
        self.assertEqual(self._group(), ["cccc.default-release"])
        self.assertNotIn("storeID", (self.made / "prefs.js").read_text(encoding="utf-8"))

    def test_nothing_while_our_firefox_runs(self):
        before = self._ini()
        self.running = [42]
        profile_commands.tidy(State())
        self.assertEqual(self._ini(), before)
        self.assertEqual(self._group(), ["cccc.default-release", "myfox-2"])

    def test_the_one_opened_takes_its_name_there(self):
        profiles.write_name(self.used, "Main")
        profile_commands.tidy(State())
        self.assertIn("Name=Main\nIsRelative=1\nPath=myfox-1\n", self._ini())
