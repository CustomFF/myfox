from __future__ import annotations

import sys
import types
import unittest
from unittest import mock

from myfox.ui import _has_display, _has_tty, get_backend
from myfox.ui.plain_backend import PlainBackend


def _dearpygui_backend_module():
    """`from . import dearpygui_backend` inside get_backend() resolves
    through the parent package's own attribute (falling back to
    sys.modules only if that attribute is unset) — so patching
    sys.modules["myfox.ui.dearpygui_backend"] alone is silently ignored
    once some other test has already triggered a real import (which sets
    that attribute). Returning the one real module object — stubbing
    dearpygui itself first if it isn't already imported, so this never
    makes a real network call — and patching *its* DearpyguiBackend
    attribute works correctly either way."""
    if "myfox.ui.dearpygui_backend" not in sys.modules:
        stub_pkg = types.ModuleType("dearpygui")
        stub_submodule = types.ModuleType("dearpygui.dearpygui")
        stub_pkg.dearpygui = stub_submodule
        with mock.patch.dict(sys.modules, {"dearpygui": stub_pkg, "dearpygui.dearpygui": stub_submodule}):
            from myfox.ui import dearpygui_backend
    else:
        from myfox.ui import dearpygui_backend
    return dearpygui_backend


class HasTtyTests(unittest.TestCase):
    def test_true_only_when_both_stdin_and_stdout_are_a_tty(self):
        with mock.patch("sys.stdin.isatty", return_value=True), \
             mock.patch("sys.stdout.isatty", return_value=True):
            self.assertTrue(_has_tty())
        with mock.patch("sys.stdin.isatty", return_value=True), \
             mock.patch("sys.stdout.isatty", return_value=False):
            self.assertFalse(_has_tty())


class HasDisplayTests(unittest.TestCase):
    def test_true_with_x11_display(self):
        with mock.patch.dict("os.environ", {"DISPLAY": ":0"}, clear=True):
            self.assertTrue(_has_display())

    def test_true_with_wayland_display(self):
        with mock.patch.dict("os.environ", {"WAYLAND_DISPLAY": "wayland-0"}, clear=True):
            self.assertTrue(_has_display())

    def test_false_with_neither(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertFalse(_has_display())


class GetBackendTests(unittest.TestCase):
    def test_noninteractive_always_gets_plain(self):
        self.assertIsInstance(get_backend(noninteractive=True), PlainBackend)

    def test_force_gui_returns_dearpygui_backend_when_available(self):
        dearpygui_backend = _dearpygui_backend_module()
        with mock.patch.object(dearpygui_backend, "DearpyguiBackend") as backend_cls:
            self.assertIs(get_backend(force_gui=True), backend_cls.return_value)

    def test_force_gui_falls_back_to_plain_when_dearpygui_unavailable(self):
        # Mirrors ensure_available() raising (no prebuilt release reachable)
        # surfacing as the backend failing to construct — get_backend must
        # swallow that and hand back a working backend, never crash.
        dearpygui_backend = _dearpygui_backend_module()
        with mock.patch.object(dearpygui_backend, "DearpyguiBackend", side_effect=RuntimeError("no release yet")):
            self.assertIsInstance(get_backend(force_gui=True), PlainBackend)

    def test_no_tty_no_display_falls_back_to_plain(self):
        with mock.patch("myfox.ui._has_tty", return_value=False), \
             mock.patch("myfox.ui._has_display", return_value=False):
            self.assertIsInstance(get_backend(), PlainBackend)

    def test_interactive_tty_gets_picotui(self):
        with mock.patch("myfox.ui._has_tty", return_value=True):
            from myfox.ui.picotui_backend import PicotuiBackend

            self.assertIsInstance(get_backend(), PicotuiBackend)


if __name__ == "__main__":
    unittest.main()
