"""MyFox's own code (the myfox package) from this repo's releases tagged
core-*, each carrying myfox-core.tar.gz with myfox/ at its root (built by
scripts/build-core-dist.sh). install() replaces the package in
paths.share_dir()/myfox; the browser, tweaks and dearpygui next to it are
left alone. The running process keeps its already-imported modules, so the
new code takes effect on the next start.

MYFOX_CORE_URL=<path or URL of an archive> replaces the release (dev use),
as for bootstrap.py.
"""

from __future__ import annotations

import os
import shutil
import tarfile
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import net, paths, version

ARCHIVE = "myfox-core.tar.gz"


@dataclass(frozen=True)
class Release:
    tag: str
    archive_url: str


def latest_release() -> Release | None:
    """The newest core-* release with the archive; None if there is none.
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
        for asset in rel.get("assets", []):
            if asset.get("name") == ARCHIVE and asset.get("browser_download_url"):
                return Release(rel["tag_name"], asset["browser_download_url"])
    return None


def install(release: Release) -> str:
    """Replaces share_dir()/myfox with the release's package; returns its tag.
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
        # Swap only once the new package is complete.
        old = Path(tmp) / "old"
        if dest.exists():
            dest.rename(old)
        (unpacked / "myfox").rename(dest)
        shutil.rmtree(old, ignore_errors=True)
    return release.tag
