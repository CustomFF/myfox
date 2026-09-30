"""One interface, several backends — replaces lib/tui.sh's dialog/whiptail/
read three-way branching inside every widget function.

Pass 1: only plain_backend exists (input()/print(), no dependency at all).
Later passes add urwid_backend (terminal, vendored) and dearpygui_backend
(GUI, fetched on demand) behind the same Backend interface — callers never
branch on which one is active.
"""

from __future__ import annotations

import os
import sys
from typing import Protocol, Sequence


class Backend(Protocol):
    def confirm(self, prompt: str, default: bool = True) -> bool: ...

    def choose(self, header: str, options: Sequence[tuple[str, str]], default: str | None = None) -> str | None: ...

    def input_dir(self, prompt: str, initial: str) -> str | None: ...

    def message(self, text: str) -> None: ...

    def spin(self, title: str):
        """Context manager: shows `title` as busy for the duration of the block."""
        ...


def _has_tty() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _has_display() -> bool:
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def get_backend(force_gui: bool = False, noninteractive: bool = False) -> Backend:
    """Picks a backend without the caller needing to know why.

    -y (noninteractive) always gets plain: nothing it does asks a real
    question, so there's nothing for a heavier backend to buy here. Real
    urwid/dearpygui selection lands in passes 3-4 — this only fixes the
    decision point so call sites never need to change later.
    """
    from . import plain_backend  # local import: keeps this module dependency-free

    if noninteractive:
        return plain_backend.PlainBackend()
    if force_gui or (not _has_tty() and _has_display()):
        # TODO(pass 4): dearpygui_backend, fetched on demand. Falls back to
        # plain for now rather than pretending a GUI it can't yet show.
        return plain_backend.PlainBackend()
    # TODO(pass 3): urwid_backend when _has_tty().
    return plain_backend.PlainBackend()
