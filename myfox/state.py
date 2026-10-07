"""Flat JSON state file: one file (~/.local/state/myfox/state.json), read on load(), written back
whole on save(). Values are plain JSON scalars (paths, booleans, version
strings) written only by this tool, so there's nothing to escape.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "myfox"


def state_file() -> Path:
    return state_dir() / "state.json"


class State:
    """Loaded once per process; call save() after any set() you want kept."""

    def __init__(self) -> None:
        self._path = state_file()
        self._data: dict[str, Any] = {}
        if self._path.is_file():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                # A corrupt or unreadable state file is treated as "nothing
                # installed yet", not a crash — the installer itself is the
                # only writer, so this only happens from manual tampering.
                self._data = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def clear(self) -> None:
        self._data = {}

    def is_installed(self) -> bool:
        return bool(self.get("install_dir"))

    def save(self) -> None:
        state_dir().mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(self._path)

    def delete_file(self) -> None:
        try:
            self._path.unlink()
        except FileNotFoundError:
            pass
