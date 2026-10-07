"""Message catalog: locales/en.json is the base, any other locale only
overrides the keys it has. An unknown key prints itself instead of
raising, so a missing translation is visible but never fatal.
"""

from __future__ import annotations

import json
import locale as _locale
import os
from pathlib import Path

_LOCALES_DIR = Path(__file__).parent / "locales"

_messages: dict[str, str] = {}
current_lang = "en"


def _normalize(code: str) -> str:
    return code.split(".")[0].split("_")[0].split("-")[0].lower()


def _env_language() -> str | None:
    """The first of LANGUAGE (its first entry), LC_ALL, LC_MESSAGES, LANG
    that is set — gettext's order. Read directly: locale.getlocale() says
    "C" when the system lacks the generated locale."""
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = (os.environ.get(var) or "").split(":")[0]
        if value:
            return value
    return None


def detect(preferred: str | None = None) -> str:
    """Explicit code, else the environment, else the C library's locale, else
    en — and en if there's no catalog for it."""
    candidate = preferred or _env_language() or _locale.getlocale()[0] or "en"
    code = _normalize(candidate)
    return code if (_LOCALES_DIR / f"{code}.json").is_file() else "en"


def load(preferred: str | None = None) -> None:
    global _messages, current_lang
    base = json.loads((_LOCALES_DIR / "en.json").read_text(encoding="utf-8"))
    current_lang = detect(preferred)
    if current_lang != "en":
        overlay = json.loads((_LOCALES_DIR / f"{current_lang}.json").read_text(encoding="utf-8"))
        base.update(overlay)
    _messages = base


def t(key: str, *args: object) -> str:
    fmt = _messages.get(key, key)
    return fmt.format(*args) if args else fmt


# Loaded with the system default on import so t() works even if a caller
# forgets load() (e.g. early error messages before argv is parsed) —
# main() calls load() again too, redundant in a real one-shot process but
# needed so tests can change $LANG between calls within one test run.
load()
