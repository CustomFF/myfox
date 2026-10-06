"""Zero-dependency fallback: plain input()/print(). Used whenever nothing
richer is available (or -y, where nothing here is actually asked)."""

from __future__ import annotations

import contextlib

from .. import i18n


class PlainBackend:
    def confirm(self, prompt: str, default: bool = True) -> bool:
        marker = i18n.t("confirm_yes_no") if default else "[y/N]"
        ans = input(f"{prompt} {marker} ").strip().lower()
        if not ans:
            return default
        return ans in ("y", "yes", "д", "да")

    def message(self, text: str) -> None:
        print(text)

    @contextlib.contextmanager
    def spin(self, title: str):
        print(title)
        yield
