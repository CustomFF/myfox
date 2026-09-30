"""Checks the two independent release tracks (tweaks, core) against GitHub
Releases — never the tarball itself, just enough JSON to compare a tag.

GitHub's own "latest release" endpoint (releases/latest) only ever answers
for the whole repo, not per tag pattern — no use with two independent
tracks sharing one repo. We list releases instead (already sorted newest
first) and take the first tag matching the track's pattern.

Deliberately not semver-aware: the tweaks tag is <firefox-beta-major>.<patch>
(see docs/python-rewrite-plan.md), compared for inequality only, never
ordered — refresh's job is "does this differ from what I have", not
"is this newer".
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from . import net

GITHUB_REPO = "DayDve/myfox"

CORE_TAG_RE = re.compile(r"^core-")
TWEAKS_TAG_RE = re.compile(r"^\d+\.\d+$")


def _fetch_releases(repo: str = GITHUB_REPO) -> list[dict]:
    url = f"https://api.github.com/repos/{repo}/releases?per_page=100"
    req = net.request(url, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def latest_tag(pattern: re.Pattern, repo: str = GITHUB_REPO) -> str | None:
    """None on any failure (network, rate limit, malformed response) — a
    refresh that can't check is "nothing to report", never a crash."""
    try:
        releases = _fetch_releases(repo)
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
        return None
    for rel in releases:
        tag = rel.get("tag_name", "")
        if pattern.match(tag):
            return tag
    return None


def tweaks_update_available(current: str | None) -> str | None:
    """The new tag if it differs from `current`, else None. `current` is
    whatever's recorded in state (see state.py's "tweaks_version" key)."""
    latest = latest_tag(TWEAKS_TAG_RE)
    return latest if latest and latest != current else None


def core_update_available(current: str | None) -> str | None:
    latest = latest_tag(CORE_TAG_RE)
    return latest if latest and latest != current else None
