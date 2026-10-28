from __future__ import annotations

import io
import os
import select
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from myfox import firefox, i18n, paths, task
from myfox.ui import task_plain, task_tui
from picotui.defs import KEY_DOWN, KEY_ENTER, KEY_LEFT, KEY_RIGHT

from ._helpers import IsolatedStateCase
from .test_form_tui import _drive


def _task(ran: list, **kwargs) -> task.Task:
    return task.Task(
        title="T", subtitle="S", rows=[("Row:", "value")], action="Go", unconfirmed=["Run: go -y"],
        run=lambda progress: ran.append(True), **kwargs,
    )


class LinesShownTests(unittest.TestCase):
    def test_short_list_as_is(self):
        self.assertEqual(_task([], lines=["a", "b"]).lines_shown(5), ["a", "b"])

    def test_long_list_ends_with_a_count(self):
        lines = [str(i) for i in range(12)]
        self.assertEqual(_task([], lines=lines).lines_shown(5), ["0", "1", "2", "3", i18n.t("refresh_more", 8)])

    def test_fit_counts_wrapped_lines_not_entries(self):
        # Entries of 3 screen lines each: 3 of them and "...and N more" in 10.
        t = _task([], lines=["x" * 3] * 8)
        limit = t.fit(10, len)
        self.assertEqual(t.lines_shown(limit), ["xxx"] * 3 + [i18n.t("refresh_more", 5)])

    def test_fit_keeps_a_list_that_fits(self):
        t = _task([], lines=["xx"] * 5)
        self.assertEqual(t.lines_shown(t.fit(10, len)), ["xx"] * 5)

    def test_fit_shows_one_entry_even_if_it_is_taller(self):
        t = _task([], lines=["x" * 20, "y", "z"])
        self.assertEqual(t.lines_shown(t.fit(10, len)), ["x" * 20, i18n.t("refresh_more", 2)])

    def test_fit_shows_a_last_entry_rather_than_one_more(self):
        t = _task([], lines=["x" * 20, "y"])
        self.assertEqual(t.lines_shown(t.fit(10, len)), ["x" * 20, "y"])


class ShowTests(IsolatedStateCase):
    def test_yes_runs_without_asking(self):
        ran = []
        with mock.patch("builtins.input", side_effect=AssertionError("asked")), redirect_stdout(io.StringIO()):
            self.assertTrue(task.show(_task(ran), noninteractive=True))
        self.assertEqual(ran, [True])

    def test_yes_still_refuses_a_blocked_task(self):
        ran, err = [], io.StringIO()
        with redirect_stderr(err):
            self.assertFalse(task.show(_task(ran, blocked="busy"), noninteractive=True))
        self.assertEqual((ran, err.getvalue().strip()), ([], "busy"))


class PlainTests(IsolatedStateCase):
    def test_without_yes_it_names_the_command_and_runs_nothing(self):
        ran, err = [], io.StringIO()
        with mock.patch("builtins.input", side_effect=AssertionError("asked")), \
             redirect_stdout(io.StringIO()), redirect_stderr(err):
            self.assertFalse(task_plain.run(_task(ran), confirmed=False))
        self.assertEqual((ran, err.getvalue().strip()), ([], "Run: go -y"))

    def test_no_tty_without_yes_goes_the_same_way(self):
        ran = []
        with mock.patch("myfox.ui._has_tty", return_value=False), \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertFalse(task.show(_task(ran)))
        self.assertEqual(ran, [])

    def test_options_are_shown_with_their_state(self):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            task_plain.run(_task([], options=[task.Option("Also the profile", True)]), confirmed=False)
        self.assertIn("[x] Also the profile", out.getvalue())

    def test_a_failure_is_reported_not_raised(self):
        def fail(progress):
            raise OSError("disk full")

        t = task.Task(title="T", subtitle="S", rows=[], action="Go", unconfirmed=[], run=fail)
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            self.assertFalse(task_plain.run(t, confirmed=True))
        self.assertIn("disk full", err.getvalue())


class AutorunTests(IsolatedStateCase):
    def test_runs_without_asking_even_in_a_terminal(self):
        ran = []
        t = _task(ran, autorun=True)
        with mock.patch("myfox.ui._has_tty", return_value=True), \
             mock.patch("myfox.ui.task_tui.run", side_effect=AssertionError("asked")), \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertTrue(task.show(t))
        self.assertEqual(ran, [True])


class TuiTests(IsolatedStateCase):
    def _run(self, t: task.Task, keys) -> bool:
        with _drive(keys), mock.patch("myfox.ui.task_tui._ensure_screen"):
            return task_tui.run(t)

    def test_enter_runs_then_closes(self):
        ran = []
        self.assertTrue(self._run(_task(ran), [KEY_ENTER, KEY_ENTER]))
        self.assertEqual(ran, [True])

    def test_destructive_starts_on_cancel(self):
        ran = []
        self.assertFalse(self._run(_task(ran, destructive=True), [KEY_ENTER]))
        self.assertEqual(ran, [])

    def test_destructive_runs_once_the_action_is_chosen(self):
        ran = []
        self.assertTrue(self._run(_task(ran, destructive=True), [KEY_LEFT, KEY_ENTER, KEY_ENTER]))
        self.assertEqual(ran, [True])

    def test_space_ticks_an_option_before_the_run(self):
        seen = []
        option = task.Option("Also the profile")
        t = task.Task(title="T", subtitle="S", rows=[("Row:", "v")], action="Go", unconfirmed=["Run: go -y"],
                      run=lambda progress: seen.append(option.value), options=[option], destructive=True)
        # Focus starts on Cancel: Left to the action, Left again to the
        # checkbox, Space ticks it, Down back to the action.
        self.assertTrue(self._run(t, [KEY_LEFT, KEY_LEFT, b" ", KEY_DOWN, KEY_ENTER, KEY_ENTER]))
        self.assertEqual(seen, [True])

    def test_and_n_more_is_a_button_that_shows_them_all(self):
        ran, shown = [], []
        t = _task(ran, lines=[str(i) for i in range(40)], more=lambda: shown.append(True))
        # Focus starts on the action: Left to the button, Enter shows the
        # list without closing, then Right back to the action.
        self.assertTrue(self._run(t, [KEY_LEFT, KEY_ENTER, KEY_RIGHT, KEY_ENTER, KEY_ENTER]))
        self.assertEqual((shown, ran), ([True], [True]))

    def test_a_tall_terminal_still_cuts_the_list(self):
        from picotui.screen import Screen
        ran, shown = [], []
        t = _task(ran, lines=[str(i) for i in range(task.LINES_LIMIT + 6)], more=lambda: shown.append(True))
        with _drive([KEY_LEFT, KEY_ENTER, KEY_RIGHT, KEY_ENTER, KEY_ENTER]), \
             mock.patch.object(Screen, "screen_size", return_value=(100, 200)), \
             mock.patch("myfox.ui.task_tui._ensure_screen"):
            self.assertTrue(task_tui.run(t))
        self.assertEqual((shown, ran), ([True], [True]))

    def test_blocked_never_runs(self):
        ran = []
        self.assertFalse(self._run(_task(ran, blocked="busy"), [KEY_LEFT, KEY_ENTER]))
        self.assertEqual(ran, [])

    def test_closing_firefox_meanwhile_frees_the_action(self):
        ran, blocks = [], iter(["busy", None])
        t = _task(ran, recheck=lambda: next(blocks, None))
        with _drive([KEY_LEFT, KEY_ENTER, KEY_ENTER]), mock.patch("myfox.ui.task_tui._ensure_screen"):
            ready, calls = select.select, []

            def first_idle(rlist, wlist, xlist, timeout):
                calls.append(timeout)
                return ([], [], []) if len(calls) == 1 else ready(rlist, wlist, xlist, timeout)

            with mock.patch("select.select", first_idle):
                # A second without a key: the recheck clears the block, focus
                # stays on Cancel; Left to the action, Enter runs, Enter closes.
                self.assertTrue(task_tui.run(t))
        self.assertEqual((t.blocked, ran), (None, [True]))

    def test_unticking_an_option_the_block_depends_on_frees_the_action(self):
        seen = []
        option = task.Option("Give the account back", True)
        t = task.Task(title="T", subtitle="S", rows=[("Row:", "v")], action="Go", unconfirmed=["Run: go -y"],
                      run=lambda progress: seen.append(option.value), options=[option], destructive=True,
                      recheck=lambda: "close it" if option.value else None)
        with _drive([KEY_LEFT, b" ", KEY_DOWN, KEY_ENTER, KEY_ENTER]), \
             mock.patch("myfox.ui.task_tui._ensure_screen"):
            ready, calls = select.select, []

            def idle_after_space(rlist, wlist, xlist, timeout):
                calls.append(timeout)
                return ([], [], []) if len(calls) == 3 else ready(rlist, wlist, xlist, timeout)

            with mock.patch("select.select", idle_after_space):
                # Cancel first (blocked); Left to the checkbox, Space unticks
                # it, a second passes, Down to the freed action, Enter runs.
                self.assertTrue(task_tui.run(t))
        self.assertEqual((t.blocked, seen), (None, [False]))

    def test_a_picker_takes_the_highlighted_choice(self):
        ran = []
        t = task.Task(title="T", subtitle="Which?", rows=[], action="Next", unconfirmed=[],
                      run=lambda progress: ran.append(True), choices=[("a", "A"), ("b", "B"), ("c", "C")])
        self.assertTrue(self._run(t, [KEY_DOWN, KEY_DOWN, KEY_ENTER]))
        self.assertEqual((t.choice, ran), ("c", []))

    def test_a_cancelled_picker_chooses_nothing(self):
        t = task.Task(title="T", subtitle="Which?", rows=[], action="Next", unconfirmed=[],
                      run=lambda progress: None, choices=[("a", "A")])
        self.assertFalse(self._run(t, [b"\t", b"\t", KEY_ENTER]))  # Tab to Next, to Cancel
        self.assertIsNone(t.choice)

    def test_firefox_started_meanwhile_keeps_it_from_running(self):
        ran, blocks = [], iter([None, "busy"])
        t = _task(ran, recheck=lambda: next(blocks, "busy"))
        # Enter on the action finds it blocked now, focus moves to Cancel.
        self.assertFalse(self._run(t, [KEY_ENTER, KEY_ENTER]))
        self.assertEqual((t.blocked, ran), ("busy", []))


class ShownPathTests(unittest.TestCase):
    def test_home_becomes_a_tilde(self):
        home = Path.home()
        self.assertEqual(paths.shown(home / ".local" / "share"), "~/.local/share")
        self.assertEqual(paths.shown(home), "~")

    def test_a_lookalike_prefix_stays(self):
        self.assertEqual(paths.shown(f"{Path.home()}x/y"), f"{Path.home()}x/y")


class RunningPidsTests(unittest.TestCase):
    def test_finds_a_process_started_from_the_install(self):
        with tempfile.TemporaryDirectory() as d:
            binary = Path(d) / "sleeper"
            shutil.copy(os.path.realpath("/bin/sleep"), binary)
            proc = subprocess.Popen([str(binary), "5"])
            try:
                self.assertIn(proc.pid, firefox.running_pids(Path(d)))
            finally:
                proc.kill()
                proc.wait()

    def test_nothing_in_an_empty_dir(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(firefox.running_pids(Path(d)), [])


if __name__ == "__main__":
    unittest.main()
