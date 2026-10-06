"""One interface, several backends — replaces lib/tui.sh's dialog/whiptail/
read three-way branching inside every widget function.

plain_backend (input()/print()) needs nothing; picotui_backend (pass 3,
vendored) renders real dialogs on a tty — both behind the same Backend
interface, so callers never branch on which one is active.
"""

from __future__ import annotations

import sys
from typing import Protocol


class Backend(Protocol):
    """What the commands (uninstall, reinstall, refresh) need; the install
    form has its own views (form_plain/form_tui/form_gui)."""

    def confirm(self, prompt: str, default: bool = True) -> bool: ...

    def message(self, text: str) -> None: ...

    def spin(self, title: str):
        """Context manager: shows `title` as busy for the duration of the block."""
        ...


def _has_tty() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def get_backend(noninteractive: bool = False) -> Backend:
    """Picks a backend without the caller needing to know why.

    -y (noninteractive) always gets plain: nothing it does asks a real
    question, so there's nothing for a heavier backend to buy here.
    An interactive tty gets picotui; anything else (piped, no tty — e.g.
    a cron job) falls back to plain.
    """
    from . import plain_backend  # local import: keeps this module dependency-free

    if noninteractive:
        return plain_backend.PlainBackend()
    if _has_tty():
        from . import picotui_backend

        return picotui_backend.PicotuiBackend()
    return plain_backend.PlainBackend()
