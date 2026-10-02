"""dearpygui-based GUI backend — used when there's no tty but a display is
available (e.g. the .desktop context-menu action), or when --gui is
passed explicitly.

dearpygui itself isn't vendored (it ships a compiled _dearpygui.so per
Python-minor-version x architecture pair, ~9MB each — not portable
source, see docs/python-rewrite-plan.md's rejected-alternatives table).
_vendor_fetch.ensure_available() fetches the right pair from this
project's own GitHub Release (never PyPI) the first time the GUI path is
actually used, and adds it to sys.path.

One viewport for the whole process, not one per dialog — recreating the
OS window for every confirm()/choose() in a wizard would flash it open
and closed repeatedly. Each dialog clears and rebuilds the single window
tag, then pumps the render loop itself until its own callback sets a
result — same "backend owns its own blocking wait" shape as
picotui_backend.py's Dialog.loop().
"""

from __future__ import annotations

import atexit
import contextlib
from pathlib import Path
from typing import Sequence

from . import _vendor_fetch

_vendor_fetch.ensure_available()

import dearpygui.dearpygui as dpg  # noqa: E402 (must follow ensure_available())

_WINDOW_TAG = "myfox_window"
_started = False

# dearpygui's own default font has no Cyrillic glyphs — Russian text
# renders as a row of "?" (confirmed live) without an explicit font that
# carries it. These are common on most Linux desktops; silently keeps
# dearpygui's default (ASCII-only) if none are found — no font is
# bundled with myfox itself yet.
_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
)


def _bind_cyrillic_font() -> None:
    font_path = next((p for p in _FONT_CANDIDATES if Path(p).is_file()), None)
    if font_path is None:
        return
    with dpg.font_registry():
        font = dpg.add_font(font_path, 16)  # character ranges are automatic in this dearpygui version
    dpg.bind_font(font)


def _ensure_viewport() -> None:
    global _started
    if _started:
        return
    _started = True
    dpg.create_context()
    dpg.create_viewport(title="MyFox", width=480, height=260)
    dpg.setup_dearpygui()
    _bind_cyrillic_font()
    dpg.show_viewport()
    atexit.register(_teardown)


def _teardown() -> None:
    dpg.destroy_context()


@contextlib.contextmanager
def _window(width: int, height: int):
    """Deletes and rebuilds the one window tag this backend uses, instead
    of a fresh window per dialog — the viewport itself never closes.
    Resizes the viewport to fit each dialog (found live: one fixed size
    for every dialog either clips the long choose() list or wastes space
    on the short ones)."""
    if dpg.does_item_exist(_WINDOW_TAG):
        dpg.delete_item(_WINDOW_TAG)
    dpg.set_viewport_width(width)
    dpg.set_viewport_height(height)
    with dpg.window(
        tag=_WINDOW_TAG, pos=(0, 0), width=width, height=height, no_title_bar=True, no_resize=True,
        no_move=True, no_collapse=True,
    ) as win:
        yield win


def _pump_until(is_done) -> None:
    while dpg.is_dearpygui_running() and not is_done():
        dpg.render_dearpygui_frame()


class DearpyguiBackend:
    def confirm(self, prompt: str, default: bool = True) -> bool:
        _ensure_viewport()
        result: dict[str, bool | None] = {"value": None}

        def pick(value: bool) -> None:
            result["value"] = value

        with _window(width=460, height=140):
            dpg.add_text(prompt, wrap=440)
            dpg.add_spacer(height=12)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Yes", width=90, callback=lambda: pick(True))
                dpg.add_button(label="No", width=90, callback=lambda: pick(False))

        _pump_until(lambda: result["value"] is not None)
        return result["value"] if result["value"] is not None else default

    def choose(self, header: str, options: Sequence[tuple[str, str]], default: str | None = None) -> str | None:
        _ensure_viewport()
        result: dict[str, str | None] = {"value": "__pending__"}
        labels = [label for _value, label in options]
        by_label = {label: value for value, label in options}

        def pick(label: str | None) -> None:
            result["value"] = by_label.get(label) if label else None

        with _window(width=460, height=420):
            dpg.add_text(header)
            filter_box = dpg.add_input_text(hint="type to filter")
            listbox = dpg.add_listbox(items=labels, num_items=10, width=440)

            def refilter() -> None:
                query = dpg.get_value(filter_box).lower()
                dpg.configure_item(listbox, items=[l for l in labels if query in l.lower()] or labels)

            dpg.set_item_callback(filter_box, lambda: refilter())
            dpg.add_spacer(height=8)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Back", width=90, callback=lambda: pick(None))
                dpg.add_button(label="Select", width=90, callback=lambda: pick(dpg.get_value(listbox)))

        _pump_until(lambda: result["value"] != "__pending__")
        return result["value"]

    def input_dir(self, prompt: str, initial: str) -> str | None:
        _ensure_viewport()
        result: dict[str, str | None] = {"value": "__pending__"}

        with _window(width=460, height=160):
            dpg.add_text(prompt)
            entry = dpg.add_input_text(default_value=initial, width=440)
            dpg.add_spacer(height=12)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Back", width=90, callback=lambda: result.update(value=None))
                dpg.add_button(
                    label="OK", width=90, callback=lambda: result.update(value=dpg.get_value(entry) or initial)
                )

        _pump_until(lambda: result["value"] != "__pending__")
        return result["value"]

    def message(self, text: str) -> None:
        _ensure_viewport()
        result = {"done": False}

        with _window(width=460, height=140):
            dpg.add_text(text, wrap=440)
            dpg.add_spacer(height=12)
            dpg.add_button(label="OK", width=90, callback=lambda: result.update(done=True))

        _pump_until(lambda: result["done"])

    @contextlib.contextmanager
    def spin(self, title: str):
        """No render loop here: the caller's own blocking work runs inside
        the `with` block, so nothing can pump dearpygui's event loop
        concurrently — one static frame, not animated, same depth as the
        other two backends' spin()."""
        _ensure_viewport()
        with _window(width=460, height=100):
            dpg.add_text(title, wrap=440)
        dpg.render_dearpygui_frame()
        yield
