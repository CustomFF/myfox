"""The tweaks (autoconfig/ + chrome/) from CustomFF/tweaks' releases, tagged
<Firefox beta major>.<patch> (e.g. 158.0). Each release carries
myfox-tweaks.tar.gz (autoconfig/ and chrome/ at its root) and a cumulative
changelog.json:

    {"versions": [{"version": "158.1", "date": "…", "changes": ["…"]}, …]}

newest first. install() puts them into paths.tweaks_dir(); apply.py copies
them on from there. MYFOX_TWEAKS_LOCAL=<tweaks checkout> takes them from a
checkout instead (dev use), as addons.fetch_themes() does for the themes.
"""

from __future__ import annotations

import os
import shutil
import tarfile
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import changelog, net, paths, version
from .addons import TWEAKS_REPO

ARCHIVE = "myfox-tweaks.tar.gz"
CHANGELOG = "changelog.json"
LOCAL_TAG = "dev"


@dataclass(frozen=True)
class Release:
    tag: str
    archive_url: str
    changelog_url: str


def latest_release() -> Release | None:
    """The newest tweaks release with both assets; None if there is none.
    Raises OSError when GitHub can't be asked."""
    try:
        releases = version._fetch_releases(TWEAKS_REPO)
    except ValueError as exc:
        raise OSError(f"bad response from GitHub: {exc}") from exc
    for rel in releases:
        if not version.TWEAKS_TAG_RE.match(rel.get("tag_name", "")):
            continue
        assets = {a.get("name"): a.get("browser_download_url") for a in rel.get("assets", [])}
        if assets.get(ARCHIVE) and assets.get(CHANGELOG):
            return Release(rel["tag_name"], assets[ARCHIVE], assets[CHANGELOG])
    return None


def _download(url: str) -> bytes:
    with urllib.request.urlopen(net.request(url), timeout=60) as resp:
        return resp.read()


def install(release: Release | None = None) -> str:
    """Replaces paths.tweaks_dir() with the given (else the latest) release,
    or with the MYFOX_TWEAKS_LOCAL checkout. Returns the installed tag.
    Raises OSError on failure; the previous tweaks stay in place then."""
    dest = paths.tweaks_dir()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest.parent, prefix=".tweaks-") as tmp:
        new = Path(tmp) / "tweaks"
        local = os.environ.get("MYFOX_TWEAKS_LOCAL")
        if local:
            tag = LOCAL_TAG
            for name in ("autoconfig", "chrome"):
                shutil.copytree(Path(local) / name, new / name)
        else:
            release = release or latest_release()
            if release is None:
                raise OSError("no tweaks release found")
            tag = release.tag
            archive = Path(tmp) / ARCHIVE
            archive.write_bytes(_download(release.archive_url))
            with tarfile.open(archive) as tf:
                for member in tf.getmembers():
                    name = member.name
                    if name.startswith("/") or ".." in Path(name).parts or not (member.isfile() or member.isdir()):
                        raise OSError(f"unexpected entry in the tweaks archive: {name}")
                tf.extractall(new)
        for name in ("autoconfig", "chrome"):
            if not (new / name).is_dir():
                raise OSError(f"{name}/ missing from the tweaks")
        # Swap only once the new copy is complete.
        old = Path(tmp) / "old"
        if dest.exists():
            dest.rename(old)
        new.rename(dest)
    return tag


def changes_since(current: str | None, release: Release) -> list[str]:
    """What's new from `current` up to `release`, newest first."""
    return changelog.changes_since(release.changelog_url, current)
