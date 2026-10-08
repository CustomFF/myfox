from __future__ import annotations

import contextlib
import io
import unittest
from pathlib import Path
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from myfox import core, i18n, refresh, tweaks
from myfox.state import State
from myfox.ui import task_plain, task_tui
from picotui.defs import KEY_ENTER, KEY_ESC

from ._helpers import IsolatedStateCase
from .test_form_tui import _drive


def _latest(tweaks="151.3", core="core-5", changes=("Rounded popup menus",)):
    return {"tweaks": tweaks, "core": core, "changes": list(changes)}


@contextlib.contextmanager
def _releases(latest):
    """Stands in for both release lookups (core tag, tweaks release) and the
    tweaks changelog; an exception makes the lookups fail."""
    if isinstance(latest, Exception):
        with mock.patch("myfox.core.latest_release", side_effect=latest), \
             mock.patch("myfox.tweaks.latest_release", side_effect=latest):
            yield
        return
    release = tweaks.Release(latest["tweaks"], "https://x/a.tar.gz", "https://x/c.json") if latest["tweaks"] else None
    core_release = core.Release(latest["core"], "https://x/core.tar.gz", "https://x/core.json") if latest["core"] else None
    with mock.patch("myfox.core.latest_release", return_value=core_release), \
         mock.patch("myfox.tweaks.latest_release", return_value=release), \
         mock.patch("myfox.changelog.changes_since", return_value=latest["changes"]):
        yield


def _state(tweaks="151.2", core="core-5") -> State:
    state = State()
    state.set("tweaks_version", tweaks)
    state.set("core_version", core)
    return state


class PlanTests(IsolatedStateCase):
    def _check(self, force=False, **latest):
        with _releases(_latest(**latest)):
            return refresh.RefreshPlan.check(_state(), force=force)

    def test_only_tracks_with_a_new_tag_are_todo(self):
        plan = self._check()
        self.assertEqual([t.track.key for t in plan.todo], ["tweaks_version"])
        self.assertEqual(plan.todo[0].describe(), i18n.t("refresh_version_change", "151.2", "151.3"))

    def test_nothing_new_means_not_needed(self):
        self.assertFalse(self._check(tweaks="151.2").needed)

    def test_force_takes_everything(self):
        plan = self._check(force=True, tweaks="151.2")
        self.assertEqual(len(plan.todo), 2)
        self.assertEqual(plan.todo[0].describe(), "151.2")

    def test_an_older_release_is_not_an_update(self):
        self.assertFalse(self._check(tweaks="151.1", core="core-4").needed)

    def test_versions_show_without_the_tag_prefix(self):
        plan = self._check(core="core-6")
        core_track = next(t for t in plan.todo if t.track.key == "core_version")
        self.assertEqual(core_track.describe(), i18n.t("refresh_version_change", "5", "6"))

    def test_force_skips_a_track_with_no_release(self):
        plan = self._check(force=True, tweaks="151.2", core=None)
        self.assertEqual([t.track.key for t in plan.todo], ["tweaks_version"])

    def test_whats_new_comes_from_the_changelog(self):
        self.assertEqual(self._check(changes=["A", "B"]).changes, ["A", "B"])

    def test_long_whats_new_is_cut_with_a_count(self):
        plan = self._check(changes=[str(i) for i in range(12)])
        self.assertEqual(refresh.to_task(plan, self.fail).lines_shown(5), ["0", "1", "2", "3", i18n.t("refresh_more", 8)])

    def test_no_new_tweaks_means_no_whats_new_even_forced(self):
        self.assertEqual(self._check(force=True, tweaks="151.2").changes, [])

    def test_check_failure_is_an_error(self):
        with _releases(OSError("rate limited")):
            plan = refresh.RefreshPlan.check(_state())
        self.assertEqual(plan.error, i18n.t("refresh_check_failed", "rate limited"))


class RunTests(IsolatedStateCase):
    def setUp(self):
        super().setUp()
        self.updated = []

    def update(self, plan, progress):
        progress("step…", 0.5)
        self.updated.append(plan)

    def _run(self, latest, **kwargs):
        out, err = io.StringIO(), io.StringIO()
        with _releases(latest), redirect_stdout(out), redirect_stderr(err):
            rc = refresh.run(_state(), update=self.update, **kwargs)
        return rc, out.getvalue(), err.getvalue()

    def test_no_updates_prints_a_line_and_shows_no_dialog(self):
        with mock.patch("myfox.ui.task_tui.run") as tui:
            rc, out, _err = self._run(_latest(tweaks="151.2"))
        self.assertEqual((rc, out.strip()), (0, i18n.t("refresh_none")))
        tui.assert_not_called()

    def test_no_updates_with_gui_is_a_notification(self):
        with mock.patch("myfox.ui.notify.send", return_value=True) as send:
            rc, out, _err = self._run(_latest(tweaks="151.2"), gui=True)
        send.assert_called_once_with(i18n.t("refresh_title"), i18n.t("refresh_none"))
        self.assertEqual((rc, out), (0, ""))

    def test_check_failure_returns_an_error(self):
        rc, _out, err = self._run(OSError("down"))
        self.assertEqual(rc, 1)
        self.assertIn(i18n.t("refresh_check_failed", "down"), err)

    def test_yes_updates_without_asking(self):
        with mock.patch("builtins.input", side_effect=AssertionError("asked")):
            rc, _out, _err = self._run(_latest(), noninteractive=True)
        self.assertEqual((rc, len(self.updated)), (0, 1))

    def test_force_with_yes_updates_everything_without_a_dialog(self):
        rc, _out, _err = self._run(_latest(tweaks="151.2"), noninteractive=True, force=True)
        self.assertEqual(len(self.updated[0].todo), 2)

    def test_tty_shows_the_tui_dialog(self):
        with mock.patch("myfox.ui._has_tty", return_value=True), \
             mock.patch("myfox.ui.task_tui.run", return_value=True) as tui:
            self.assertEqual(self._run(_latest())[0], 0)
        tui.assert_called_once()


class RestartTests(IsolatedStateCase):
    """New tweaks apply when Firefox starts: a running one is offered a restart."""

    def _offer(self, running=True, since="151.2", current="151.2", **latest):
        state = _state(tweaks=current)
        state.set("install_dir", "/opt/ff")
        with _releases(_latest(**latest)):
            plan = refresh.RefreshPlan.check(state)
        with mock.patch("myfox.firefox.running_pids", return_value=[42] if running else []), \
             mock.patch.object(refresh, "RESTART_SINCE_TWEAKS", since):
            return plan, refresh.restart_offer(plan, state)

    def test_running_firefox_with_restart_capable_tweaks_is_offered_one(self):
        plan, restart = self._offer()
        with mock.patch("myfox.firefox.request_restart") as request:
            restart()
        request.assert_called_once_with(Path("/opt/ff"))
        task = refresh.to_task(plan, lambda plan, progress: None, restart)
        self.assertEqual([(o.label, o.value) for o in task.options], [(i18n.t("refresh_restart_firefox"), True)])

    def test_not_offered_without_a_running_firefox(self):
        self.assertIsNone(self._offer(running=False)[1])

    def test_not_offered_when_running_tweaks_predate_the_handler(self):
        self.assertIsNone(self._offer(since="151.3", current="151.2", tweaks="151.4")[1])

    def test_not_offered_for_a_core_only_update(self):
        self.assertIsNone(self._offer(tweaks="151.2", core="core-6")[1])

    def test_restart_comes_after_the_update_and_only_if_ticked(self):
        plan, _restart = self._offer()
        calls = []
        task = refresh.to_task(plan, lambda plan, progress: calls.append("update"), lambda: calls.append("restart"))
        task.run(lambda message, fraction: None)
        task.options[0].value = False
        task.run(lambda message, fraction: None)
        self.assertEqual(calls, ["update", "restart", "update"])


class TuiDialogTests(IsolatedStateCase):
    def _plan(self):
        with _releases(_latest()):
            return refresh.RefreshPlan.check(_state())

    def test_enter_updates_then_closes(self):
        updated = []
        with _drive([KEY_ENTER, KEY_ENTER]), mock.patch("myfox.ui.task_tui._ensure_screen"):
            self.assertTrue(task_tui.run(refresh.to_task(self._plan(), lambda plan, progress: updated.append(plan))))
        self.assertEqual(len(updated), 1)

    def test_escape_cancels(self):
        with _drive([KEY_ESC]), mock.patch("myfox.ui.task_tui._ensure_screen"):
            self.assertFalse(task_tui.run(refresh.to_task(self._plan(), lambda plan, progress: self.fail("updated"))))


class ApplyUpdatesTests(IsolatedStateCase):
    def test_tweaks_are_installed_applied_and_recorded(self):
        state = _state()
        state.set("install_dir", "/opt/firefox")
        state.set("profile_dir", "/p/myfox-1")
        state.save()
        with _releases(_latest()):
            plan = refresh.RefreshPlan.check(State())
        with mock.patch("myfox.tweaks.install", return_value="151.3") as install, \
             mock.patch("myfox.apply.reapply_tweaks") as reapply:
            refresh.apply_updates(plan, lambda message, fraction: None)
        install.assert_called_once_with(plan.todo[0].release)
        self.assertEqual(reapply.call_args.args[:2], (Path("/opt/firefox"), Path("/p/myfox-1")))
        self.assertEqual(State().get("tweaks_version"), "151.3")

    def test_core_is_replaced_last_and_recorded(self):
        state = _state()
        state.set("install_dir", "/opt/firefox")
        state.save()
        with _releases(_latest(core="core-6")):
            plan = refresh.RefreshPlan.check(State())
        order, messages = [], []
        with mock.patch("myfox.tweaks.install", side_effect=lambda r: order.append("tweaks") or "151.3"), \
             mock.patch("myfox.apply.reapply_tweaks"), \
             mock.patch("myfox.core.install", side_effect=lambda r: order.append("core") or r.tag):
            refresh.apply_updates(plan, lambda message, fraction: messages.append(message))
        self.assertEqual(order, ["tweaks", "core"])
        self.assertIn(i18n.t("progress_refresh_core_download", "6"), messages)  # no "core-" prefix
        self.assertEqual(State().get("core_version"), "core-6")


class PlainDialogTests(IsolatedStateCase):
    def test_without_yes_it_shows_whats_new_and_the_command(self):
        with _releases(_latest()):
            plan = refresh.RefreshPlan.check(_state())
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            t = refresh.to_task(plan, lambda plan, progress: self.fail("updated"))
            self.assertFalse(task_plain.run(t, confirmed=False))
        self.assertIn("Rounded popup menus", out.getvalue())
        self.assertIn(i18n.t("needs_yes_refresh", "myfox refresh -y"), err.getvalue())


if __name__ == "__main__":
    unittest.main()
