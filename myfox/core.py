"""MyFox's own code (the myfox package) from this repo's releases tagged
core-<semver>, each carrying myfox-core.tar.gz with myfox/ at its root and
a cumulative changelog.json (built by scripts/build-core-dist.sh). install() replaces the package in
paths.share_dir()/myfox; the browser, tweaks and dearpygui next to it are
left alone. The running process keeps its already-imported modules, so the
new code takes effect on the next start.

MYFOX_CORE_URL=<path or URL of an archive> replaces the release (dev use),
as for bootstrap.py.
"""

from __future__ import annotations

import os
import re
import shutil
import tarfile
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import net, paths, version

ARCHIVE = "myfox-core.tar.gz"


CHANGELOG = "changelog.json"


@dataclass(frozen=True)
class Release:
    tag: str
    archive_url: str
    changelog_url: str | None = None


def latest_release() -> Release | None:
    """The newest core-* release with the archive and the changelog; None if
    there is none.
    Raises OSError when GitHub can't be asked."""
    override = os.environ.get("MYFOX_CORE_URL")
    if override:
        url = override if "://" in override else Path(override).resolve().as_uri()
        return Release("dev", url)
    try:
        releases = version._fetch_releases(version.GITHUB_REPO)
    except ValueError as exc:
        raise OSError(f"bad response from GitHub: {exc}") from exc
    for rel in releases:
        if not version.CORE_TAG_RE.match(rel.get("tag_name", "")):
            continue
        assets = {a.get("name"): a.get("browser_download_url") for a in rel.get("assets", [])}
        if assets.get(ARCHIVE) and assets.get(CHANGELOG):
            return Release(rel["tag_name"], assets[ARCHIVE], assets[CHANGELOG])
    return None


def package_version(package_dir: Path) -> str | None:
    """__version__ of a myfox package on disk, without importing it."""
    try:
        text = (package_dir / "__init__.py").read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.M)
    return m.group(1) if m else None


def install(release: Release) -> str:
    """Replaces share_dir()/myfox with the release's package; returns its
    version (the package's own __version__).
    Raises OSError on failure, leaving the current package in place."""
    dest = paths.share_dir() / "myfox"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(net.request(release.archive_url), timeout=60) as resp:
        data = resp.read()
    with tempfile.TemporaryDirectory(dir=dest.parent, prefix=".core-") as tmp:
        archive = Path(tmp) / ARCHIVE
        archive.write_bytes(data)
        unpacked = Path(tmp) / "unpacked"
        with tarfile.open(archive) as tf:
            for member in tf.getmembers():
                name = member.name
                if name.startswith("/") or ".." in Path(name).parts or not (member.isfile() or member.isdir()):
                    raise OSError(f"unexpected entry in the core archive: {name}")
            tf.extractall(unpacked)
        if not (unpacked / "myfox" / "__main__.py").is_file():
            raise OSError("myfox/ missing from the core archive")
        installed = package_version(unpacked / "myfox")
        # Swap only once the new package is complete.
        old = Path(tmp) / "old"
        if dest.exists():
            dest.rename(old)
        (unpacked / "myfox").rename(dest)
        shutil.rmtree(old, ignore_errors=True)
    return installed or release.tag
