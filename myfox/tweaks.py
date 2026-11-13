"""The tweaks (autoconfig/ + chrome/) from CustomFF/myfox-tweaks' releases, tagged
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

from . import archive as archive_mod, changelog, i18n, net, paths, version
from .addons import TWEAKS_REPO

ARCHIVE = "myfox-tweaks.tar.gz"
CHANGELOG = "changelog.json"
LOCAL_TAG = "dev"


@dataclass(frozen=True)
class Release:
    tag: str
    archive_url: str
    changelog_url: str


# The oldest release `myfox tweaks use` offers.
OLDEST = (159, 0)
# The state key of the version `myfox tweaks use` pinned; refresh leaves the tweaks alone then.
PIN = "tweaks_pin"


def release(tag: str) -> Release:
    return Release(tag, version.asset_url(TWEAKS_REPO, tag, ARCHIVE), version.asset_url(TWEAKS_REPO, tag, CHANGELOG))


def latest_release() -> Release | None:
    """The newest tweaks release with its archive; None if there is none.
    Raises OSError when GitHub can't be asked."""
    tag = version.find_latest_tag(version.TWEAKS_TAG_RE, TWEAKS_REPO, asset=ARCHIVE)
    return release(tag) if tag is not None else None


def tags() -> list[str]:
    """Every release from OLDEST on, newest first. Unchecked for the archive:
    only the newest may still lack it (see version.py). Raises OSError
    when GitHub can't be asked."""
    found = [r[len("refs/tags/"):] for r in version.refs(TWEAKS_REPO) if r.startswith("refs/tags/")]
    found = [t for t in found if version.TWEAKS_TAG_RE.match(t) and changelog.parse(t) >= OLDEST]
    return sorted(found, key=changelog.parse, reverse=True)


def major(tag: str | None) -> int | None:
    """The Firefox major a tag (158.4) or a Firefox version (160.0.2, 161.0b3) is for."""
    parsed = changelog.parse((tag or "").split("b")[0].split("a")[0])
    return parsed[0] if parsed else None


def resolve(wanted: str, found: list[str]) -> Release | None:
    """What `myfox tweaks use <wanted>` installs: "latest", a Firefox major
    (its newest release) or an exact version, one with its archive; None
    if there is none such. Raises OSError when GitHub can't be asked."""
    if wanted == "latest":
        picks = found
    elif "." in wanted:
        picks = [t for t in found if changelog.parse(t) == changelog.parse(wanted)]
    else:
        picks = [t for t in found if wanted.isdigit() and major(t) == int(wanted)]
    for tag in picks:
        if version._has_asset(TWEAKS_REPO, tag, ARCHIVE):
            return release(tag)
    return None


def pinned(state) -> str | None:
    return state.get(PIN) or None


def pin_note(state) -> str | None:
    """What refresh says while the tweaks are pinned."""
    pin = pinned(state)
    return i18n.t("tweaks_pinned_note", changelog.display(pin), "myfox tweaks use latest") if pin else None


def _download(url: str) -> bytes:
    with urllib.request.urlopen(net.request(url), timeout=net.TIMEOUT) as resp:
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
                archive_mod.extract_all(tf, new)
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
