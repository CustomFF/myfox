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

# Sentinel for "caller didn't override this label" — distinct from None,
# which confirm()'s no_label already uses to mean "suppress this button
# entirely". Each backend resolves an unset label through i18n.t() itself
# (ui_yes/ui_no/ui_back/ui_cancel/ui_select/ui_ok) at call time, rather
# than baking a hardcoded English word into the parameter's own default
# value — a live review caught exactly that: wizard.py's tweaks page never
# overrode yes_label/no_label, so its Yes/No buttons stayed in English
# inside an otherwise fully-Russian dialog.
_UNSET: str = "\0unset"


class Backend(Protocol):
    def confirm(
        self, prompt: str, default: bool = True, yes_label: str = _UNSET, no_label: str | None = _UNSET,
        show_back: bool = False,
    ) -> bool | None:
        """no_label=None suppresses the second button entirely (e.g. the
        wizard's first page: just "Continue" plus whatever cancel
        affordance the backend already offers — Escape in picotui, a
        dedicated Cancel button in dearpygui) rather than showing a
        redundant second negative answer alongside it. Leaving yes_label/
        no_label unset (the default) resolves to the current locale's
        "Yes"/"No" — pass an explicit string only to say something more
        specific ("Continue", "Install", ...).

        show_back=True adds a leading "Back" button/affordance, returning
        None — the same "None means back" convention choose()/input_dir()
        already use, so every interactive method agrees on what a None
        return means, and "declining this means go fix something on an
        earlier page" (e.g. the wizard's summary) isn't conflated with
        no_label's "this is a real negative answer" (e.g. the tweaks
        page's actual Yes/No question). Button ORDER is always
        [Back?, yes_label, no_label?, Cancel] — the same position for the
        same role on every dialog this backend draws, confirm() included;
        a live review flagged confirm()'s primary-action-first order and
        choose()/input_dir()'s back-first order as feeling like different
        dialogs built without reference to each other."""
        ...

    def choose(
        self, header: str, options: Sequence[tuple[str, str]], default: str | None = None, next_label: str = _UNSET,
    ) -> str | None: ...

    def input_dir(self, prompt: str, initial: str, next_label: str = _UNSET) -> str | None: ...

    def toggle(self, prompt: str, default: bool = True, next_label: str = _UNSET) -> bool | None:
        """A single on/off setting (e.g. the wizard's "apply tweaks?" page)
        — a real checkbox/toggle control, not a two-item choose() list.
        choose() is for picking one of several named options; shoehorning
        a yes/no switch into it (a live review caught this live) means
        a filterable search box and a scrollable listbox for a single
        boolean, equally bad as going the other way and dressing a binary
        toggle up as a confirm() yes/no question. Same [Back, next_label,
        Cancel] button row as choose()/input_dir(), None for Back."""
        ...

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
