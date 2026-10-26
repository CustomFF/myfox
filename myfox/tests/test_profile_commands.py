from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from unittest import mock

from myfox import __main__ as cli
from myfox import i18n, importer, profile_commands
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

    def test_never_run_is_related_too(self):
        self.assertIn(i18n.t("profile_status_unused"), self._run())

    def test_all_adds_the_foreign_ones(self):
        out = self._run("--all")
        self.assertIn(i18n.t("profile_status_foreign"), out)
        self.assertNotIn(i18n.t("profile_list_hidden", 1, "myfox profile list --all"), out)

    def test_json(self):
        records = {r["id"]: r for r in json.loads(self._run("--all", "--json"))}
        self.assertEqual(len(records), 5)
        self.assertEqual({k: records["myfox-1"][k] for k in ("tweaks", "used", "owner", "store", "last_version")},
                         {"tweaks": True, "used": True, "owner": "myfox", "store": "myfox", "last_version": "158.0"})
        self.assertEqual(records["myfox-2"]["imported_from"], str(self.store / "cccc.default-release"))
        self.assertTrue(records["aaaa.dev"]["open"])
        self.assertEqual(records["cccc.default-release"]["owner"], "foreign")

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
