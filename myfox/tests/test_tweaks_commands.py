from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from unittest import mock

from myfox import i18n, tweaks, tweaks_commands
from myfox.state import State

from ._helpers import IsolatedStateCase

_TAGS = ["161.1", "161.0", "160.12", "160.11", "159.10"]


class TweaksCommandTests(IsolatedStateCase):
    def setUp(self):
        super().setUp()
        self.install_dir = self.tmp_path / "ff"
        self.install_dir.mkdir()
        self.profile = self.tmp_path / "p"
        self.profile.mkdir()
        (self.profile / ".myfox").touch()
        self._firefox("160.0.2")
        state = State()
        state.set("install_dir", str(self.install_dir))
        state.set("profile_dir", str(self.profile))
        state.set("tweaks_version", "161.1")
        state.save()
        for target, kwargs in (("myfox.tweaks.tags", {"return_value": _TAGS}),
                               ("myfox.version._has_asset", {"return_value": True}),
                               ("myfox.sources.myfox_dirs", {"return_value": [self.profile]}),
                               ("myfox.firefox.running_pids", {"return_value": []})):
            patch = mock.patch(target, **kwargs)
            patch.start()
            self.addCleanup(patch.stop)

    def _firefox(self, version):
        (self.install_dir / "application.ini").write_text(f"[App]\nVersion={version}\n", encoding="utf-8")

    def _use(self, wanted, yes=True):
        out = io.StringIO()
        with mock.patch("myfox.tweaks.install", side_effect=lambda release: release.tag) as install, \
             mock.patch("myfox.apply.reapply_tweaks") as reapply, redirect_stdout(out):
            code = tweaks_commands.use(State(), wanted, noninteractive=yes)
        return code, install, reapply, out.getvalue()

    def test_a_major_installs_its_newest_and_pins_it(self):
        code, install, reapply, _ = self._use("160")
        self.assertEqual(code, 0)
        self.assertEqual(install.call_args.args[0].tag, "160.12")
        reapply.assert_called_once()
        state = State()
        self.assertEqual((state.get("tweaks_version"), state.get(tweaks.PIN)), ("160.12", "160.12"))

    def test_latest_installs_the_newest_and_unpins(self):
        self._use("159.10")
        code, install, _, _ = self._use("latest")
        self.assertEqual(install.call_args.args[0].tag, "161.1")
        self.assertIsNone(State().get(tweaks.PIN))

    def test_pinning_what_is_installed_asks_and_installs_nothing(self):
        code, install, _, out = self._use("161", yes=False)
        self.assertEqual(code, 0)
        install.assert_not_called()
        self.assertEqual(State().get(tweaks.PIN), "161.1")
        self.assertIn(i18n.t("tweaks_now_pinned", "161.1"), out)

    def test_an_unknown_version_changes_nothing(self):
        code, install, _, _ = self._use("158")
        self.assertEqual(code, 1)
        install.assert_not_called()

    def test_a_local_tweaks_copy_has_no_versions(self):
        with mock.patch.dict("os.environ", {"MYFOX_TWEAKS_LOCAL": "/x"}):
            code, install, _, _ = self._use("160")
        self.assertEqual(code, 1)
        install.assert_not_called()

    def test_tweaks_for_a_much_newer_firefox_are_warned_about(self):
        self._firefox("158.0")
        state = State()
        task = tweaks_commands.build(state, tweaks.release("161.1"), None, "latest", _TAGS)
        self.assertEqual(task.lines, [i18n.t("tweaks_warn_too_new", "161.1", 158, 159)])
        self.assertEqual(tweaks_commands.build(state, tweaks.release("159.10"), "159.10", "159", _TAGS).lines, [])

    def test_versions_mark_what_fits_the_firefox(self):
        out = io.StringIO()
        with redirect_stdout(out):
            tweaks_commands.versions(State(), as_json=True)
        records = json.loads(out.getvalue())
        self.assertEqual([r["version"] for r in records if r["fits"]], ["161.1", "161.0"])
        self.assertEqual([r["version"] for r in records if r["installed"]], ["161.1"])
        self._firefox("162.0b1")  # a beta whose tweaks aren't out yet: the newest fit
        self.assertEqual(tweaks_commands.best_major(_TAGS, tweaks_commands.firefox_major(State())), 161)
