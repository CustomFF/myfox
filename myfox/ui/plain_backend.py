"""Zero-dependency fallback: plain input()/print(). Used whenever nothing
richer is available (or -y, where nothing here is actually asked)."""

from __future__ import annotations

import contextlib
from typing import Sequence

from .. import i18n


class PlainBackend:
    def confirm(self, prompt: str, default: bool = True) -> bool:
        marker = i18n.t("confirm_yes_no") if default else "[y/N]"
        ans = input(f"{prompt} {marker} ").strip().lower()
        if not ans:
            return default
        return ans in ("y", "yes", "д", "да")

    def choose(self, header: str, options: Sequence[tuple[str, str]], default: str | None = None) -> str | None:
        print(header)
        for i, (_value, label) in enumerate(options, 1):
            print(f"  {i}) {label}")
        raw = input(i18n.t("prompt_choice")).strip()
        if not raw:
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1][0]
        return None

    def input_dir(self, prompt: str, initial: str) -> str | None:
        ans = input(f"{prompt} [{initial}] ").strip()
        return ans or initial

    def message(self, text: str) -> None:
        print(text)

    @contextlib.contextmanager
    def spin(self, title: str):
        print(title)
        yield
