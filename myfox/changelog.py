"""Versions and changelogs of the two release tracks (tweaks, core).

Tags carry the version, with a prefix for the core (core-1.2.3) and none
for the tweaks (158.0); versions compare as tuples of numbers. Each
release has a cumulative changelog.json, newest first:

    {"versions": [{"version": "1.1.0", "date": "…", "changes": ["…"]}, …]}
"""

from __future__ import annotations

import json
import re
import urllib.request

from . import net

_VERSION_RE = re.compile(r"(\d+(?:\.\d+)*)$")


def parse(tag: str | None) -> tuple[int, ...] | None:
    """"core-1.2.3" -> (1, 2, 3), "158.0" -> (158, 0), "dev"/None -> None."""
    m = _VERSION_RE.search(tag or "")
    return tuple(int(part) for part in m.group(1).split(".")) if m else None


def display(tag: str | None) -> str:
    """What the user sees: the version without the tag's prefix."""
    m = _VERSION_RE.search(tag or "")
    return m.group(1) if m else (tag or "—")


def is_newer(latest: str | None, current: str | None) -> bool:
    """An unknown current version (not recorded, a dev copy) counts as older."""
    new, old = parse(latest), parse(current)
    return new is not None and (old is None or new > old)


def changes_since(changelog_url: str, current: str | None) -> list[str]:
    """The changelog's lines for every version newer than `current`, newest
    first. Raises OSError if it can't be fetched or read."""
    try:
        with urllib.request.urlopen(net.request(changelog_url), timeout=30) as resp:
            entries = json.loads(resp.read().decode("utf-8"))["versions"]
        since = parse(current)
        changes = []
        for entry in entries:
            version = parse(entry.get("version"))
            if version is None or (since is not None and version <= since):
                continue
            changes += [line for line in entry.get("changes", []) if isinstance(line, str)]
        return changes
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise OSError(f"bad changelog: {exc}") from exc
