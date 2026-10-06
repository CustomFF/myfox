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
from picotui.defs import KEY_BACKSPACE, KEY_DOWN, KEY_ENTER, KEY_ESC, KEY_TAB


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
        # wizard.py's summary page confirms a multi-line block of text.
        with _drive([KEY_ENTER]):
            self.assertTrue(PicotuiBackend().confirm("Line one\nLine two\nLine three", default=True))

    def test_custom_yes_label_still_resolves_to_true_on_enter(self):
        with _drive([KEY_ENTER]):
            self.assertTrue(PicotuiBackend().confirm("Proceed?", default=True, yes_label="Continue"))

    def test_show_back_does_not_disturb_the_default_enter_path(self):
        # The Back button's own tab-reachability isn't exercised here (it
        # needs a real terminal's focus-cycling, not something to assume
        # the exact order of without live-testing it) — this only pins
        # down that adding it doesn't regress the existing Enter/Esc paths.
        with _drive([KEY_ENTER]):
            self.assertTrue(PicotuiBackend().confirm("Proceed?", default=True, show_back=True))
        with _drive([KEY_ESC]):
            self.assertFalse(PicotuiBackend().confirm("Proceed?", default=True, show_back=True))

    def test_no_label_none_still_cancels_via_escape(self):
        # wizard.py's welcome page: no visible second button, but Escape —
        # picotui's own built-in ACTION_CANCEL binding — must still work.
        with _drive([KEY_ESC]):
            self.assertFalse(PicotuiBackend().confirm("Proceed?", default=True, yes_label="Continue", no_label=None))

    def test_no_label_none_still_confirms_via_enter(self):
        with _drive([KEY_ENTER]):
            self.assertTrue(PicotuiBackend().confirm("Proceed?", default=True, yes_label="Continue", no_label=None))


class ChooseTests(unittest.TestCase):
    OPTIONS = [("a", "Option A"), ("b", "Option B")]

    def test_enter_on_default_focus_picks_the_first_option(self):
        with _drive([KEY_ENTER]):
            self.assertEqual(PicotuiBackend().choose("Pick one", self.OPTIONS), "a")

    def test_down_then_enter_picks_the_second_option(self):
        with _drive([KEY_DOWN, KEY_ENTER]):
            self.assertEqual(PicotuiBackend().choose("Pick one", self.OPTIONS), "b")

    def test_esc_returns_none(self):
        with _drive([KEY_ESC]):
            self.assertIsNone(PicotuiBackend().choose("Pick one", self.OPTIONS, default="a"))

    def test_custom_next_label_still_confirms_the_highlighted_option(self):
        with _drive([KEY_ENTER]):
            self.assertEqual(PicotuiBackend().choose("Pick one", self.OPTIONS, next_label="Next"), "a")

    def test_back_button_returns_none(self):
        # Tab from the (default-focused) list reaches the Back button next.
        with _drive([KEY_TAB, KEY_ENTER]):
            self.assertIsNone(PicotuiBackend().choose("Pick one", self.OPTIONS))

    def test_typing_filters_then_enter_picks_the_match(self):
        with _drive([b"B", KEY_ENTER]):
            self.assertEqual(PicotuiBackend().choose("Pick one", self.OPTIONS), "b")

    def test_backspace_widens_the_filter_back_out(self):
        options = [("a", "Apple"), ("b", "Banana")]
        # "Ba" narrows to Banana, backspace widens back to both -> first
        # (Apple) is what Enter then picks, proving the filter actually
        # reset rather than staying narrowed.
        with _drive([b"B", b"a", KEY_BACKSPACE, KEY_BACKSPACE, KEY_ENTER]):
            self.assertEqual(PicotuiBackend().choose("Pick one", options), "a")

    def test_a_list_longer_than_the_screen_does_not_crash(self):
        # Regression motivation: Filler(Pile(...)) in the old urwid backend
        # didn't scroll at all for a list this size (the real Firefox
        # language picker is ~170 entries).
        options = [(str(i), f"Option {i}") for i in range(200)]
        with _drive([KEY_DOWN] * 150 + [KEY_ENTER]):
            self.assertEqual(PicotuiBackend().choose("Pick one", options), "150")


class InputDirTests(unittest.TestCase):
    def test_enter_with_no_edits_returns_the_initial_value(self):
        with _drive([KEY_ENTER]):
            self.assertEqual(PicotuiBackend().input_dir("Install where?", "/opt/firefox"), "/opt/firefox")

    def test_esc_returns_none(self):
        with _drive([KEY_ESC]):
            self.assertIsNone(PicotuiBackend().input_dir("Install where?", "/opt/firefox"))

    def test_custom_next_label_still_confirms(self):
        with _drive([KEY_ENTER]):
            result = PicotuiBackend().input_dir("Install where?", "/opt/firefox", next_label="Next")
        self.assertEqual(result, "/opt/firefox")


class ToggleTests(unittest.TestCase):
    # Add order is label, checkbox, back, ok — same _button_row helper as
    # choose(), whose own test_back_button_returns_none above already pins
    # down that one Tab from the default-focused widget reaches Back next;
    # toggle()'s default focus is the checkbox itself, so the same single
    # Tab reaches Back, and a second reaches the OK/next_label button.
    def test_tab_tab_enter_confirms_the_default_value_unchanged(self):
        with _drive([KEY_TAB, KEY_TAB, KEY_ENTER]):
            self.assertTrue(PicotuiBackend().toggle("Apply tweaks?", default=True))

    def test_space_flips_the_checkbox_before_confirming(self):
        with _drive([b" ", KEY_TAB, KEY_TAB, KEY_ENTER]):
            self.assertFalse(PicotuiBackend().toggle("Apply tweaks?", default=True))

    def test_tab_enter_reaches_back_and_returns_none(self):
        with _drive([KEY_TAB, KEY_ENTER]):
            self.assertIsNone(PicotuiBackend().toggle("Apply tweaks?", default=True))

    def test_esc_returns_none(self):
        # toggle() has no separate "No" button to fall back to, unlike
        # confirm() — Escape must mean Back here, same as choose()/
        # input_dir(), not "return the checkbox's unchanged default".
        with _drive([KEY_ESC]):
            self.assertIsNone(PicotuiBackend().toggle("Apply tweaks?", default=True))

    def test_custom_next_label_still_confirms(self):
        with _drive([KEY_TAB, KEY_TAB, KEY_ENTER]):
            self.assertTrue(PicotuiBackend().toggle("Apply tweaks?", default=True, next_label="Next"))


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
