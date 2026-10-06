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

GITHUB_REPO = "CustomFF/myfox"

CORE_TAG_RE = re.compile(r"^core-")
TWEAKS_TAG_RE = re.compile(r"^\d+\.\d+$")


def _fetch_releases(repo: str = GITHUB_REPO) -> list[dict]:
    url = f"https://api.github.com/repos/{repo}/releases?per_page=100"
    req = net.request(url, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def find_latest_tag(pattern: re.Pattern, repo: str = GITHUB_REPO) -> str | None:
    """The newest tag matching `pattern`, None if there is none. Raises
    OSError when GitHub can't be asked (network, rate limit, bad JSON)."""
    try:
        releases = _fetch_releases(repo)
    except (json.JSONDecodeError, ValueError) as exc:
        raise OSError(f"bad response from GitHub: {exc}") from exc
    for rel in releases:
        tag = rel.get("tag_name", "")
        if pattern.match(tag):
            return tag
    return None


def latest_tag(pattern: re.Pattern, repo: str = GITHUB_REPO) -> str | None:
    """find_latest_tag() with any failure folded into None."""
    try:
        return find_latest_tag(pattern, repo)
    except OSError:
        return None
