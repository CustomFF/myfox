from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from myfox import i18n, refresh
from myfox.state import State
from myfox.ui import refresh_plain, refresh_tui
from picotui.defs import KEY_ENTER, KEY_ESC

from ._helpers import IsolatedStateCase
from .test_form_tui import _drive


def _latest(tweaks="151.3", core="core-5"):
    """find_latest_tag stand-in answering per repo."""
    def find(pattern, repo):
        return tweaks if repo == refresh.TWEAKS_REPO else core
    return find


def _state(tweaks="151.2", core="core-5") -> State:
    state = State()
    state.set("tweaks_version", tweaks)
    state.set("core_version", core)
    return state


class PlanTests(IsolatedStateCase):
    def _check(self, force=False, **latest):
        with mock.patch("myfox.version.find_latest_tag", side_effect=_latest(**latest)):
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

    def test_check_failure_is_an_error(self):
        with mock.patch("myfox.version.find_latest_tag", side_effect=OSError("rate limited")):
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
        with mock.patch("myfox.version.find_latest_tag", side_effect=latest), redirect_stdout(out), redirect_stderr(err):
            rc = refresh.run(_state(), update=self.update, **kwargs)
        return rc, out.getvalue(), err.getvalue()

    def test_no_updates_prints_a_line_and_shows_no_dialog(self):
        with mock.patch("myfox.ui.refresh_tui.run") as tui:
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
             mock.patch("myfox.ui.refresh_tui.run", return_value=True) as tui:
            self.assertEqual(self._run(_latest())[0], 0)
        tui.assert_called_once()


class TuiDialogTests(IsolatedStateCase):
    def _plan(self):
        with mock.patch("myfox.version.find_latest_tag", side_effect=_latest()):
            return refresh.RefreshPlan.check(_state())

    def test_enter_updates_then_closes(self):
        updated = []
        with _drive([KEY_ENTER, KEY_ENTER]), mock.patch("myfox.ui.refresh_tui._ensure_screen"):
            self.assertTrue(refresh_tui.run(self._plan(), lambda plan, progress: updated.append(plan)))
        self.assertEqual(len(updated), 1)

    def test_escape_cancels(self):
        with _drive([KEY_ESC]), mock.patch("myfox.ui.refresh_tui._ensure_screen"):
            self.assertFalse(refresh_tui.run(self._plan(), lambda plan, progress: self.fail("updated")))


class PlainDialogTests(IsolatedStateCase):
    def test_no_answer_cancels(self):
        with mock.patch("myfox.version.find_latest_tag", side_effect=_latest()):
            plan = refresh.RefreshPlan.check(_state())
        with mock.patch("builtins.input", return_value="n"), redirect_stdout(io.StringIO()):
            self.assertFalse(refresh_plain.run(plan, lambda plan, progress: self.fail("updated")))


if __name__ == "__main__":
    unittest.main()
