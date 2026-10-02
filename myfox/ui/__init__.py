"""One interface, several backends — replaces lib/tui.sh's dialog/whiptail/
read three-way branching inside every widget function.

plain_backend (input()/print()) needs nothing; picotui_backend (pass 3,
vendored) renders real dialogs on a tty; dearpygui_backend (pass 4, fetched
on demand) adds a GUI — all behind the same Backend interface, so callers
never branch on which one is active.
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
    question, so there's nothing for a heavier backend to buy here.
    force_gui or a tty-less run with a display goes to dearpygui; an
    interactive tty gets picotui; anything else (piped, no tty, no display
    — e.g. a cron job) falls back to plain. dearpygui itself falls back to
    plain if its compiled pair can't be fetched (no prebuilt release yet,
    or no network) — a GUI it can't actually show is worse than a plain
    prompt, never a crash.
    """
    from . import plain_backend  # local import: keeps this module dependency-free

    if noninteractive:
        return plain_backend.PlainBackend()
    if force_gui or (not _has_tty() and _has_display()):
        try:
            from . import dearpygui_backend

            return dearpygui_backend.DearpyguiBackend()
        except Exception:
            return plain_backend.PlainBackend()
    if _has_tty():
        from . import picotui_backend

        return picotui_backend.PicotuiBackend()
    return plain_backend.PlainBackend()
