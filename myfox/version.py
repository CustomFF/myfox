"""Finds the newest release of a track (core, tweaks, themes) without
GitHub's API, whose 60 requests an hour per address a few checks use up.

The tags come from the repo's git refs (what `git ls-remote` reads, one
small request); a release's files from their plain download URLs, whose
names are fixed. A tag is pushed a minute before its release has the
files, so a tag counts once its archive is there.

Comparing versions is changelog.is_newer()'s job; this only finds tags.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request

from . import net

GITHUB_REPO = "CustomFF/myfox"

CORE_TAG_RE = re.compile(r"^core-")
TWEAKS_TAG_RE = re.compile(r"^\d+\.\d+$")


def _fetch_refs(repo: str) -> bytes:
    url = f"https://github.com/{repo}.git/info/refs?service=git-upload-pack"
    with urllib.request.urlopen(net.request(url), timeout=net.TIMEOUT) as resp:
        return resp.read()


def refs(repo: str = GITHUB_REPO) -> dict[str, str]:
    """Ref name ("refs/tags/core-1.3.2", "refs/heads/master") -> commit.
    Raises OSError when GitHub can't be asked or answers something else."""
    data, found, i = _fetch_refs(repo), {}, 0
    # pkt-lines: 4 hex digits of length (counting themselves), "0000" a flush.
    while i + 4 <= len(data):
        try:
            size = int(data[i:i + 4], 16)
        except ValueError:
            raise OSError("bad response from GitHub: not git refs") from None
        if size < 4:
            i += 4
            continue
        line = data[i + 4:i + size].split(b"\0")[0].decode("utf-8", "replace").strip()
        i += size
        m = re.fullmatch(r"([0-9a-f]{40}) (refs/\S+)", line)
        if m and not m[2].endswith("^{}"):
            found[m[2]] = m[1]
    if not found:
        raise OSError("bad response from GitHub: no refs")
    return found


def _order(tag: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", tag))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def asset_url(repo: str, tag: str, name: str) -> str:
    return f"https://github.com/{repo}/releases/download/{tag}/{name}"


def _has_asset(repo: str, tag: str, name: str) -> bool:
    # The download answers with a redirect to the file; following it would fetch it.
    req = net.request(asset_url(repo, tag, name), method="HEAD")
    try:
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=net.TIMEOUT):
            return True
    except urllib.error.HTTPError as exc:
        if 300 <= exc.code < 400:
            return True
        if exc.code == 404:
            return False
        raise


def find_latest_tag(pattern: re.Pattern, repo: str = GITHUB_REPO, asset: str | None = None) -> str | None:
    """The newest tag matching `pattern` (by its numbers), with `asset` in
    its release if one is named; None if there is none. Raises OSError
    when GitHub can't be asked."""
    tags = [r[len("refs/tags/"):] for r in refs(repo) if r.startswith("refs/tags/")]
    for tag in sorted((t for t in tags if pattern.match(t)), key=_order, reverse=True):
        if asset is None or _has_asset(repo, tag, asset):
            return tag
    return None


def latest_tag(pattern: re.Pattern, repo: str = GITHUB_REPO, asset: str | None = None) -> str | None:
    """find_latest_tag() with any failure folded into None."""
    try:
        return find_latest_tag(pattern, repo, asset)
    except OSError:
        return None
