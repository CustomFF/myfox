"""dearpygui itself isn't vendored (see _vendor_fetch.py) and opening a
real viewport isn't something a unit test should do (needs a display,
flashes a window, and the render loop genuinely blocks on user input) —
so these tests swap `dearpygui_backend.dpg` for a small FakeDpg that
tracks widgets in a plain dict and replays scripted "frame_actions" (one
callable per render_dearpygui_frame() call) to simulate clicks/typing.
The backend's own callback-wiring logic (pick(), refilter(), the
`get_value(...) or initial` fallback) all runs for real against the fake
widgets — only drawing and the actual GUI event loop are faked, mirroring
how test_picotui_backend.py stubs Dialog.get_input() instead of the
terminal but drives real widget logic.

The module-level `import dearpygui.dearpygui as dpg` in dearpygui_backend
needs *something* importable at import time, before any test gets to
monkeypatch per-test state — a dummy parent+submodule pair is installed
into sys.modules once, here at collection time, so collecting this file
never triggers _vendor_fetch's real network fetch path.
"""

from __future__ import annotations

import contextlib
import sys
import types
import unittest
from collections import deque
from unittest import mock

# Must be installed before the `from myfox.ui import dearpygui_backend`
# import below runs (it needs *something* importable at that moment), so
# this can't wait for setUpModule — but it's undone in tearDownModule so
# other test modules (e.g. test_ui.py's get_backend() fallback test) still
# see a clean sys.modules rather than a permanent process-wide stub.
_PREEXISTING = {name: sys.modules.get(name) for name in ("dearpygui", "dearpygui.dearpygui")}
_stub_pkg = types.ModuleType("dearpygui")
_stub_submodule = types.ModuleType("dearpygui.dearpygui")
_stub_pkg.dearpygui = _stub_submodule
sys.modules["dearpygui"] = _stub_pkg
sys.modules["dearpygui.dearpygui"] = _stub_submodule


def tearDownModule():
    for name, original in _PREEXISTING.items():
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original


from myfox.ui import dearpygui_backend  # noqa: E402 (needs the stub installed first)
from myfox.ui.dearpygui_backend import DearpyguiBackend  # noqa: E402


class FakeDpg:
    """Enough of dearpygui's imperative-mode API for dearpygui_backend.py
    to build its widget trees against, plus `frame_actions`/`find`/`click`
    test helpers that have no real-dpg counterpart."""

    def __init__(self):
        self.items: dict[str, dict] = {}
        self._next_id = 0
        self.frame_actions: deque = deque()
        self.destroyed = False
        self.viewport_width = None
        self.viewport_height = None
        # Safety net: a test that forgets to script a click would otherwise
        # hang _pump_until()'s `while is_dearpygui_running(): ...` forever.
        self._frames_budget = 10_000

    def _new_id(self) -> str:
        self._next_id += 1
        return f"item{self._next_id}"

    def _add(self, type_: str, **fields) -> str:
        tag = self._new_id()
        self.items[tag] = {"type": type_, **fields}
        return tag

    def create_context(self): pass

    def create_viewport(self, **kw): pass

    def setup_dearpygui(self): pass

    def show_viewport(self): pass

    def destroy_context(self): self.destroyed = True

    def does_item_exist(self, tag): return tag in self.items

    def delete_item(self, tag): self.items.pop(tag, None)

    def set_viewport_width(self, width): self.viewport_width = width

    def set_viewport_height(self, height): self.viewport_height = height

    @contextlib.contextmanager
    def window(self, tag=None, **kw):
        wid = tag or self._new_id()
        self.items[wid] = {"type": "window", **kw}
        yield wid

    @contextlib.contextmanager
    def group(self, horizontal=False):
        gid = self._new_id()
        self.items[gid] = {"type": "group", "horizontal": horizontal}
        yield gid

    def add_text(self, text, wrap=None): return self._add("text", text=text, wrap=wrap)

    def add_spacer(self, height=None): return self._add("spacer", height=height)

    def add_button(self, label=None, width=None, callback=None):
        return self._add("button", label=label, width=width, callback=callback)

    def add_input_text(self, default_value="", hint=None, width=None):
        return self._add("input_text", value=default_value, hint=hint, width=width)

    def add_listbox(self, items=None, num_items=None, width=None):
        return self._add("listbox", items=list(items or []), value="", num_items=num_items, width=width)

    def set_item_callback(self, tag, callback): self.items[tag]["callback"] = callback

    def configure_item(self, tag, **kw): self.items[tag].update(kw)

    def get_value(self, tag): return self.items[tag].get("value")

    def set_value(self, tag, value): self.items[tag]["value"] = value

    @contextlib.contextmanager
    def font_registry(self): yield

    def add_font(self, path, size): return self._add("font", path=path, size=size)

    def bind_font(self, font): self.bound_font = font

    def is_dearpygui_running(self):
        if self._frames_budget <= 0:
            return False
        self._frames_budget -= 1
        return True

    def render_dearpygui_frame(self):
        if self.frame_actions:
            self.frame_actions.popleft()()

    def find(self, type_: str, label: str | None = None) -> str:
        for tag, data in self.items.items():
            if data["type"] == type_ and (label is None or data.get("label") == label):
                return tag
        raise AssertionError(f"no {type_!r} item found" + (f" with label {label!r}" if label else ""))

    def click(self, label: str) -> None:
        tag = self.find("button", label=label)
        self.items[tag]["callback"]()


@contextlib.contextmanager
def _fake_backend():
    fake = FakeDpg()
    with mock.patch.object(dearpygui_backend, "dpg", fake), \
         mock.patch.object(dearpygui_backend, "_started", False), \
         mock.patch.object(dearpygui_backend.atexit, "register"):
        yield fake


class ConfirmTests(unittest.TestCase):
    def test_yes_click_returns_true(self):
        with _fake_backend() as fake:
            fake.frame_actions.append(lambda: fake.click("Yes"))
            self.assertTrue(DearpyguiBackend().confirm("Proceed?", default=False))

    def test_no_click_returns_false(self):
        with _fake_backend() as fake:
            fake.frame_actions.append(lambda: fake.click("No"))
            self.assertFalse(DearpyguiBackend().confirm("Proceed?", default=True))

    def test_multiline_prompt_does_not_crash(self):
        with _fake_backend() as fake:
            fake.frame_actions.append(lambda: fake.click("Yes"))
            self.assertTrue(DearpyguiBackend().confirm("Line one\nLine two", default=True))


class ChooseTests(unittest.TestCase):
    OPTIONS = [("id1", "Alpha"), ("id2", "Beta"), ("id3", "Gamma")]

    def test_select_returns_the_value_mapped_to_the_chosen_label(self):
        with _fake_backend() as fake:
            def pick_and_select():
                fake.set_value(fake.find("listbox"), "Beta")
                fake.click("Select")

            fake.frame_actions.append(pick_and_select)
            result = DearpyguiBackend().choose("Pick one", self.OPTIONS)
        self.assertEqual(result, "id2")

    def test_back_returns_none(self):
        with _fake_backend() as fake:
            fake.frame_actions.append(lambda: fake.click("Back"))
            self.assertIsNone(DearpyguiBackend().choose("Pick one", self.OPTIONS))

    def test_typing_narrows_the_listbox_before_selecting(self):
        with _fake_backend() as fake:
            def type_filter():
                filter_box = fake.find("input_text")
                fake.set_value(filter_box, "be")
                fake.items[filter_box]["callback"]()

            def select_filtered():
                listbox = fake.find("listbox")
                self.assertEqual(fake.items[listbox]["items"], ["Beta"])
                fake.set_value(listbox, "Beta")
                fake.click("Select")

            fake.frame_actions.extend([type_filter, select_filtered])
            result = DearpyguiBackend().choose("Pick one", self.OPTIONS)
        self.assertEqual(result, "id2")

    def test_filter_with_no_matches_falls_back_to_the_full_list(self):
        with _fake_backend() as fake:
            def type_unmatched_then_select():
                filter_box = fake.find("input_text")
                fake.set_value(filter_box, "zzz-no-match")
                fake.items[filter_box]["callback"]()
                listbox = fake.find("listbox")
                self.assertEqual(fake.items[listbox]["items"], ["Alpha", "Beta", "Gamma"])
                fake.set_value(listbox, "Alpha")
                fake.click("Select")

            fake.frame_actions.append(type_unmatched_then_select)
            result = DearpyguiBackend().choose("Pick one", self.OPTIONS)
        self.assertEqual(result, "id1")


class InputDirTests(unittest.TestCase):
    def test_ok_returns_the_entered_value(self):
        with _fake_backend() as fake:
            def enter_and_ok():
                fake.set_value(fake.find("input_text"), "/custom/path")
                fake.click("OK")

            fake.frame_actions.append(enter_and_ok)
            result = DearpyguiBackend().input_dir("Where?", "/default")
        self.assertEqual(result, "/custom/path")

    def test_back_returns_none(self):
        with _fake_backend() as fake:
            fake.frame_actions.append(lambda: fake.click("Back"))
            self.assertIsNone(DearpyguiBackend().input_dir("Where?", "/default"))

    def test_blank_value_falls_back_to_initial(self):
        with _fake_backend() as fake:
            def clear_and_ok():
                fake.set_value(fake.find("input_text"), "")
                fake.click("OK")

            fake.frame_actions.append(clear_and_ok)
            result = DearpyguiBackend().input_dir("Where?", "/default")
        self.assertEqual(result, "/default")


class MessageTests(unittest.TestCase):
    def test_ok_closes_the_dialog_without_hanging(self):
        with _fake_backend() as fake:
            fake.frame_actions.append(lambda: fake.click("OK"))
            self.assertIsNone(DearpyguiBackend().message("All done."))


class SpinTests(unittest.TestCase):
    def test_spin_renders_once_and_never_pumps(self):
        with _fake_backend() as fake:
            with DearpyguiBackend().spin("Working..."):
                pass
        self.assertEqual(len(fake.frame_actions), 0)


class CyrillicFontTests(unittest.TestCase):
    def test_binds_the_first_candidate_font_that_exists(self):
        with _fake_backend() as fake, \
             mock.patch.object(dearpygui_backend, "_FONT_CANDIDATES", ("/nope", "/also-nope", "/yes")), \
             mock.patch("pathlib.Path.is_file", lambda self: str(self) == "/yes"):
            dearpygui_backend._bind_cyrillic_font()
        font_tag = fake.find("font")
        self.assertEqual(fake.items[font_tag]["path"], "/yes")
        self.assertEqual(fake.bound_font, font_tag)

    def test_no_candidate_found_leaves_the_default_font_unbound(self):
        with _fake_backend() as fake, \
             mock.patch.object(dearpygui_backend, "_FONT_CANDIDATES", ("/nope",)), \
             mock.patch("pathlib.Path.is_file", return_value=False):
            dearpygui_backend._bind_cyrillic_font()
        self.assertFalse(hasattr(fake, "bound_font"))
        self.assertEqual([i for i in fake.items.values() if i["type"] == "font"], [])


if __name__ == "__main__":
    unittest.main()
