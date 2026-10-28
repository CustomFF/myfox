from __future__ import annotations

import os
import sqlite3
import unittest
from pathlib import Path
from unittest import mock

from myfox import i18n, sources

from ._helpers import IsolatedStateCase


class SourcesTests(IsolatedStateCase):
    def setUp(self):
        super().setUp()
        self.home = Path.home()
        self.store = self.home / ".mozilla" / "firefox"
        self.install = self.tmp_path / "firefox"
        self.install.mkdir()

    def _profile(self, root: Path, folder: str, last_dir: Path | None = None, version: str = "157.0") -> Path:
        path = root / folder
        path.mkdir(parents=True)
        (path / "prefs.js").write_text("", encoding="utf-8")
        if last_dir is not None:
            (path / "compatibility.ini").write_text(
                f"[Compatibility]\nLastVersion={version}_20260914090352/20260914090352\n"
                f"LastPlatformDir={last_dir}\nLastAppDir={last_dir}/browser\n", encoding="utf-8")
        return path

    def _ini(self, root: Path, *entries: tuple[str, str], extra: str = "") -> None:
        text = "[General]\nVersion=2\n"
        for i, (name, path) in enumerate(entries):
            text += f"\n[Profile{i}]\nName={name}\nIsRelative=1\nPath={path}\n"
        root.mkdir(parents=True, exist_ok=True)
        (root / "profiles.ini").write_text(text + extra, encoding="utf-8")

    def _ids(self, found):
        return {p.id: (p.name, p.owner) for p in found}

    def test_owners_in_our_store(self):
        tweaked = self._profile(self.store, "myfox-1", self.install)
        (tweaked / ".myfox").touch()
        self._profile(self.store, "aaaa.work", self.install)
        self._profile(self.store, "bbbb.fresh")
        self._profile(self.store, "cccc.default-release", Path("/usr/lib/firefox"))
        self._ini(self.store, ("myfox", "myfox-1"), ("work", "aaaa.work"), ("fresh", "bbbb.fresh"),
                  ("default-release", "cccc.default-release"))
        found = sources.listing(self.install)
        self.assertEqual(self._ids(found), {
            "myfox-1": ("myfox", sources.MYFOX),
            "aaaa.work": ("work", sources.OURS),
            "bbbb.fresh": ("fresh", sources.UNUSED),
            "cccc.default-release": ("default-release", sources.FOREIGN),
        })
        self.assertEqual([p.related for p in found], [True, True, True, False])
        self.assertEqual(found[0].last_version, "157.0")

    def test_without_our_install_a_used_profile_is_foreign(self):
        self._profile(self.store, "aaaa.work", self.install)
        self._ini(self.store, ("work", "aaaa.work"))
        self.assertEqual(sources.listing(None)[0].owner, sources.FOREIGN)

    def test_snap_and_flatpak_get_a_prefix_and_are_foreign(self):
        self._ini(self.store)
        snap = self.home / "snap" / "firefox" / "common" / ".mozilla" / "firefox"
        flatpak = self.home / ".var" / "app" / "org.mozilla.firefox" / ".mozilla" / "firefox"
        for root in (snap, flatpak):
            self._profile(root, "dddd.default-release", Path("/snap/firefox/current/usr/lib/firefox"))
            self._ini(root, ("default-release", "dddd.default-release"))
        found = sources.listing(self.install)
        self.assertEqual(self._ids(found), {
            "snap:dddd.default-release": ("default-release", sources.FOREIGN),
            "flatpak:dddd.default-release": ("default-release", sources.FOREIGN),
        })

    def test_the_flatpak_store_on_the_xdg_path(self):
        app = self.home / ".var" / "app" / "org.mozilla.firefox"
        self._profile(app / "config" / "mozilla" / "firefox", "eeee.default")
        self._ini(app / "config" / "mozilla" / "firefox", ("default", "eeee.default"))
        self.assertEqual([p.id for p in sources.listing()], ["flatpak:eeee.default"])

    def test_profile_groups_add_their_profiles_and_names(self):
        self._profile(self.store, "aaaa.default-release")
        self._profile(self.store, "ffff.second")
        self._ini(self.store, ("default-release", "aaaa.default-release"),
                  extra="StoreID=15475d1e\nShowSelector=0\n")
        groups = self.store / "Profile Groups"
        groups.mkdir()
        con = sqlite3.connect(groups / "15475d1e.sqlite")
        con.execute("CREATE TABLE Profiles (id INTEGER PRIMARY KEY, path TEXT, name TEXT)")
        con.executemany("INSERT INTO Profiles (path, name) VALUES (?, ?)",
                        [("aaaa.default-release", "Base"), ("ffff.second", "Second")])
        con.commit()
        con.close()
        self.assertEqual({p.id: p.name for p in sources.listing()},
                         {"aaaa.default-release": "Base", "ffff.second": "Second"})

    def test_a_profile_leaves_its_groups(self):
        groups = self.store / "Profile Groups"
        groups.mkdir(parents=True)
        con = sqlite3.connect(groups / "15475d1e.sqlite")
        con.execute("CREATE TABLE Profiles (id INTEGER PRIMARY KEY, path TEXT, name TEXT)")
        con.executemany("INSERT INTO Profiles (path, name) VALUES (?, ?)",
                        [("aaaa.default-release", "Base"), ("ffff.second", "Second")])
        con.commit()
        con.close()
        sources.forget_in_groups(self.store, self.store / "ffff.second")
        con = sqlite3.connect(groups / "15475d1e.sqlite")
        self.assertEqual(con.execute("SELECT path FROM Profiles").fetchall(), [("aaaa.default-release",)])
        con.close()

    def test_a_folder_listed_twice_and_a_missing_one(self):
        self._profile(self.store, "myfox-1")
        self._ini(self.store, ("myfox", "myfox-1"), ("myfox", "myfox-1"), ("gone", "zzzz.gone"))
        self.assertEqual([p.id for p in sources.listing()], ["myfox-1"])

    def test_our_unregistered_profile_is_still_found(self):
        orphan = self._profile(self.store, "myfox-2")
        (orphan / ".myfox-created").touch()
        self._ini(self.store)
        self.assertEqual([p.id for p in sources.listing()], ["myfox-2"])

    def test_a_folder_outside_its_store_has_its_path_as_id(self):
        outside = self._profile(self.tmp_path / "elsewhere", "work")
        self.store.mkdir(parents=True)
        (self.store / "profiles.ini").write_text(f"[Profile0]\nName=work\nIsRelative=0\nPath={outside}\n",
                                                 encoding="utf-8")
        self.assertEqual([p.id for p in sources.listing()], [str(outside)])

    def test_myfox_dirs_the_used_one_first_then_the_marked_ones(self):
        from myfox.state import State
        for folder in ("myfox-1", "myfox-2", "aaaa.work"):
            self._profile(self.store, folder)
        (self.store / "myfox-1" / ".myfox").touch()
        (self.store / "myfox-2" / ".myfox").touch()
        snap = self.home / "snap" / "firefox" / "common" / ".mozilla" / "firefox"
        (self._profile(snap, "bbbb.x") / ".myfox").touch()
        self._ini(snap, ("x", "bbbb.x"))
        self._ini(self.store, ("myfox", "myfox-1"), ("myfox", "myfox-2"), ("work", "aaaa.work"))
        state = State()
        state.set("profile_dir", str(self.store / "myfox-2"))
        self.assertEqual(sources.myfox_dirs(state), [self.store / "myfox-2", self.store / "myfox-1"])
        state.set("tweaks", False)
        self.assertEqual(sources.myfox_dirs(state), [])

    def test_resolve_by_id_name_and_path(self):
        self._profile(self.store, "aaaa.default-beta")
        self._profile(self.store, "bbbb.default-beta")
        self._profile(self.store, "cccc.work")
        self._ini(self.store, ("default-beta", "aaaa.default-beta"), ("default-beta", "bbbb.default-beta"),
                  ("work", "cccc.work"))
        found = sources.listing()
        self.assertEqual(sources.resolve("bbbb.default-beta", found).name, "default-beta")
        self.assertEqual(sources.resolve("work", found).id, "cccc.work")
        self.assertEqual(sources.resolve(str(self.store / "cccc.work"), found).id, "cccc.work")
        with self.assertRaises(sources.ProfileLookupError) as cm:
            sources.resolve("default-beta", found)
        self.assertEqual(str(cm.exception), i18n.t("err_profile_ambiguous", "default-beta",
                                                   "aaaa.default-beta, bbbb.default-beta"))
        with self.assertRaises(sources.ProfileLookupError) as cm:
            sources.resolve("nope", found)
        self.assertEqual(cm.exception.key, "err_profile_not_found")

    def test_resolve_an_unlisted_path(self):
        loose = self._profile(self.tmp_path / "loose", "p", Path("/opt/firefox"), "160.0a1")
        p = sources.resolve(str(loose), [])
        self.assertEqual((p.id, p.store, p.owner, p.last_version), (str(loose), "", sources.FOREIGN, "160.0a1"))
        (self.tmp_path / "empty").mkdir()
        with self.assertRaises(sources.ProfileLookupError) as cm:
            sources.resolve(str(self.tmp_path / "empty"), [])
        self.assertEqual(cm.exception.key, "err_not_a_profile")


class InUseTests(IsolatedStateCase):
    def _profile(self, store: str = "") -> sources.Profile:
        path = self.tmp_path / "p"
        path.mkdir(exist_ok=True)
        return sources.Profile(id="p", name="p", path=path, store=store, owner=sources.FOREIGN, last_version=None)

    def test_no_lock_is_free(self):
        self.assertFalse(sources.in_use(self._profile()))

    def test_a_lock_of_a_live_firefox(self):
        p = self._profile()
        os.symlink(f"127.0.1.1:+{os.getpid()}", p.path / "lock")
        with mock.patch("os.readlink", side_effect=lambda link: "127.0.1.1:+42" if str(link).endswith("lock")
                        else "/usr/lib/firefox/firefox"):
            self.assertTrue(sources.in_use(p))

    def test_a_stale_lock_whose_pid_is_now_something_else(self):
        p = self._profile()
        os.symlink(f"127.0.1.1:+{os.getpid()}", p.path / "lock")  # this python, not a firefox
        self.assertFalse(sources.in_use(p))

    def test_flatpak_goes_by_the_running_processes(self):
        p = self._profile(sources.FLATPAK)
        os.symlink("127.0.1.1:+2", p.path / "lock")
        with mock.patch("myfox.sources._flatpak_running", return_value=True):
            self.assertTrue(sources.in_use(p))
        with mock.patch("myfox.sources._flatpak_running", return_value=False):
            self.assertFalse(sources.in_use(p))


class DowngradeTests(unittest.TestCase):
    def test_versions(self):
        self.assertTrue(sources.is_downgrade("159.0", "158.0.1"))
        self.assertTrue(sources.is_downgrade("159.0", "159.0b5"))
        self.assertTrue(sources.is_downgrade("161.0a1", "159.0b5"))
        self.assertTrue(sources.is_downgrade("159.0b5", "159.0a1"))
        self.assertFalse(sources.is_downgrade("158.0", "158.0.1"))
        self.assertFalse(sources.is_downgrade("158.0.1", "158.0.1"))
        self.assertFalse(sources.is_downgrade("153.5.1esr", "158.0"))
        self.assertFalse(sources.is_downgrade(None, "158.0"))
        self.assertFalse(sources.is_downgrade("159.0", None))


if __name__ == "__main__":
    unittest.main()
