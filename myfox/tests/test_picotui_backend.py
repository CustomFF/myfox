"""Drives the real picotui widget tree by stubbing Dialog.get_input() to
feed a scripted key sequence instead of reading a real terminal — real
handle_key()/focus/navigation logic runs, only the "read a key" step at
the bottom is replaced. Screen output itself (init_tty/alt-screen/mouse)
is never exercised here; that side is only verified live (see commit
message / session notes) since it needs a real pty.
"""

from __future__ import annotations

import contextlib
import unittest
from unittest import mock

from myfox.ui.picotui_backend import Dialog, PicotuiBackend, Screen
from picotui.defs import KEY_ENTER, KEY_ESC


@contextlib.contextmanager
def _drive(keys):
    """Stubs Dialog.get_input() to feed a scripted key sequence. Also
    stubs _ensure_screen() (the real one touches termios — needs an
    actual tty, which unittest doesn't have — and registers an atexit
    hook we don't want piling up once per test), Screen.screen_size()
    (sends an ANSI query and reads the terminal's reply — also a real-tty
    thing, not something to fake key-by-key), and Screen.wr() (every
    redraw's raw escape-code writes, irrelevant to the outcomes these
    tests check and just noise in the test output otherwise)."""
    keys = list(keys)

    def get_input(self):
        assert keys, "ran out of scripted keys — a real run would have blocked on input here"
        return keys.pop(0)

    with mock.patch.object(Dialog, "get_input", get_input), \
         mock.patch.object(Screen, "screen_size", return_value=(80, 24)), \
         mock.patch.object(Screen, "wr"), \
         mock.patch("myfox.ui.picotui_backend._ensure_screen"):
        yield


class ConfirmTests(unittest.TestCase):
    def test_enter_on_default_true_picks_yes(self):
        with _drive([KEY_ENTER]):
            self.assertTrue(PicotuiBackend().confirm("Proceed?", default=True))

    def test_enter_on_default_false_picks_no(self):
        with _drive([KEY_ENTER]):
            self.assertFalse(PicotuiBackend().confirm("Proceed?", default=False))

    def test_esc_counts_as_no(self):
        with _drive([KEY_ESC]):
            self.assertFalse(PicotuiBackend().confirm("Proceed?", default=True))

    def test_multiline_prompt_does_not_crash(self):
        with _drive([KEY_ENTER]):
            self.assertTrue(PicotuiBackend().confirm("Line one\nLine two\nLine three", default=True))


class MessageTests(unittest.TestCase):
    def test_enter_dismisses_it(self):
        with _drive([KEY_ENTER]):
            self.assertIsNone(PicotuiBackend().message("done"))

    def test_multiline_message_does_not_crash(self):
        with _drive([KEY_ENTER]):
            PicotuiBackend().message("line one\nline two")


class SpinTests(unittest.TestCase):
    def test_does_not_hang_with_no_focusable_widgets(self):
        # Regression: Dialog.redraw()'s default focus_idx=-1 path calls
        # find_focusable_by_idx(), which spins forever with zero focusable
        # children (confirmed live against real picotui, not just this
        # backend) — spin() must never go through Dialog.redraw()/.loop().
        with _drive([]), PicotuiBackend().spin("Downloading..."):
            pass

    def test_propagates_an_exception_from_the_block(self):
        with _drive([]), self.assertRaises(RuntimeError):
            with PicotuiBackend().spin("Downloading..."):
                raise RuntimeError("boom")


if __name__ == "__main__":
    unittest.main()
