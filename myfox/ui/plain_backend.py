"""Zero-dependency fallback: plain input()/print(). Used whenever nothing
richer is available (or -y, where nothing here is actually asked)."""

from __future__ import annotations

import contextlib
from typing import Sequence

from .. import i18n
from . import _UNSET


class PlainBackend:
    def confirm(
        self, prompt: str, default: bool = True, yes_label: str = _UNSET, no_label: str | None = _UNSET,
        show_back: bool = False,
    ) -> bool | None:
        if yes_label == _UNSET:
            yes_label = i18n.t("ui_yes")
        if no_label == _UNSET:
            no_label = i18n.t("ui_no")
        back_hint = "/b=back" if show_back else ""
        if no_label is None:
            ans = input(f"{prompt} [{yes_label}{back_hint}/Ctrl+C to cancel] ").strip().lower()
            if show_back and ans in ("b", "back"):
                return None
            return True if not ans else ans in ("y", "yes", "д", "да")
        marker = i18n.t("confirm_yes_no") if default else "[y/N]"
        ans = input(f"{prompt} {marker}{back_hint} ").strip().lower()
        if show_back and ans in ("b", "back"):
            return None
        if not ans:
            return default
        return ans in ("y", "yes", "д", "да")

    def choose(
        self, header: str, options: Sequence[tuple[str, str]], default: str | None = None, next_label: str = _UNSET,
    ) -> str | None:
        print(header)
        for i, (_value, label) in enumerate(options, 1):
            print(f"  {i}) {label}")
        raw = input(i18n.t("prompt_choice")).strip()
        if not raw:
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1][0]
        return None

    def input_dir(self, prompt: str, initial: str, next_label: str = _UNSET) -> str | None:
        ans = input(f"{prompt} [{initial}] ").strip()
        return ans or initial

    def toggle(self, prompt: str, default: bool = True, next_label: str = _UNSET) -> bool | None:
        marker = i18n.t("confirm_yes_no") if default else "[y/N]"
        ans = input(f"{prompt} {marker}/b=back ").strip().lower()
        if ans in ("b", "back"):
            return None
        if not ans:
            return default
        return ans in ("y", "yes", "д", "да")

    def message(self, text: str) -> None:
        print(text)

    @contextlib.contextmanager
    def spin(self, title: str):
        print(title)
        yield
