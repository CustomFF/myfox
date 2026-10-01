"""Installs the (already-signed) themes built by CustomFF/tweaks and,
optionally, the AMO Plasma integration add-on.

Port of lib/addons.sh. Theme XPIs used to be bundled in this repo and
just copied; autoconfig/chrome/themes have since moved to their own
CustomFF/tweaks repo (see docs/python-rewrite-plan.md), so this fetches
the signed build from its releases instead. Only Plasma integration goes
through AMO directly (urllib + json instead of curl + awk).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import urllib.error
import urllib.request
from pathlib import Path

from . import net, version

MYFOX_THEME_DARK_ID = "myfox-dark-theme@daydve.github.io"
MYFOX_THEME_LIGHT_ID = "myfox-light-theme@daydve.github.io"
MYFOX_ADDON_PLASMA = "plasma-integration"

TWEAKS_REPO = "CustomFF/tweaks"
THEMES_TAG_RE = re.compile(r"^themes-")

_THEME_FILES = {
    MYFOX_THEME_DARK_ID: "myfox-dark.xpi",
    MYFOX_THEME_LIGHT_ID: "myfox-light.xpi",
}


def _release_assets(repo: str, tag: str) -> dict[str, str]:
    """name -> browser_download_url for every asset of a tagged release."""
    url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
    with urllib.request.urlopen(net.request(url), timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return {a["name"]: a["browser_download_url"] for a in data.get("assets", [])}


def fetch_themes(profile_dir: Path, local_dir: str | None = None) -> list[str]:
    """Returns the theme IDs that couldn't be installed (a warning for the
    caller, never a hard failure) — both themes are always installed,
    instant switching later (see resolve_theme in the old bin/myfox-core).

    Fetched from CustomFF/tweaks' latest `themes-*` release, or from a
    local tweaks checkout's `build/signed/` when `local_dir` is given (dev
    use, same shape as apply.py's MYFOX_DDBLM_LOCAL)."""
    ext_dir = profile_dir / "extensions"
    ext_dir.mkdir(parents=True, exist_ok=True)

    assets: dict[str, str] = {}
    if not local_dir:
        tag = version.latest_tag(THEMES_TAG_RE, repo=TWEAKS_REPO)
        if tag:
            try:
                assets = _release_assets(TWEAKS_REPO, tag)
            except (urllib.error.URLError, OSError, json.JSONDecodeError):
                assets = {}

    missing = []
    for addon_id, filename in _THEME_FILES.items():
        dest = ext_dir / f"{addon_id}.xpi"
        if local_dir:
            src = Path(local_dir) / "build" / "signed" / filename
            if not src.is_file():
                missing.append(addon_id)
                continue
            shutil.copy2(src, dest)
            continue
        url = assets.get(filename)
        if not url:
            missing.append(addon_id)
            continue
        try:
            with urllib.request.urlopen(net.request(url), timeout=60) as resp:
                dest.write_bytes(resp.read())
        except (urllib.error.URLError, OSError):
            missing.append(addon_id)
    return missing


# ─── KDE Plasma detection ────────────────────────────────────────────────

def is_plasma_session() -> bool:
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")
    if re.search(r"(^|:)KDE(;|:|$)|(^|:)Plasma(;|:|$)", desktop):
        return True
    return os.environ.get("KDE_FULL_SESSION", "") in ("true", "1")


_NMH_DEFAULT_DIRS = (
    "/usr/lib/mozilla/native-messaging-hosts",
    "/usr/lib64/mozilla/native-messaging-hosts",
    "/usr/local/lib/mozilla/native-messaging-hosts",
)


def pkg_installed() -> bool:
    """Whether the plasma-browser-integration system package (the native-
    messaging host) is present. MYFOX_NMH_DIRS overrides the search dirs —
    dev/test only, to simulate "package missing" without uninstalling it;
    production never sets it."""
    override = os.environ.get("MYFOX_NMH_DIRS")
    candidates = override.split(":") if override else list(_NMH_DEFAULT_DIRS)
    return any((Path(d) / "org.kde.plasma.browser_integration.json").is_file() for d in candidates)


def pkg_install_hint() -> str | None:
    for cmd, suggestion in (
        ("apt-get", "sudo apt install plasma-browser-integration"),
        ("dnf", "sudo dnf install plasma-browser-integration"),
        ("pacman", "sudo pacman -S plasma-browser-integration"),
        ("zypper", "sudo zypper install plasma-browser-integration"),
    ):
        if shutil.which(cmd):
            return suggestion
    return None


# ─── AMO ─────────────────────────────────────────────────────────────────

def addon_guid(slug: str) -> str | None:
    url = f"https://addons.mozilla.org/api/v5/addons/addon/{slug}/"
    try:
        with urllib.request.urlopen(net.request(url), timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None
    return data.get("guid")


def addon_fetch(slug: str, out: Path) -> bool:
    """XPI is a zip — "PK" magic bytes are the only sanity check worth
    doing here, same as the bash version."""
    url = f"https://addons.mozilla.org/firefox/downloads/latest/{slug}/addon-latest.xpi"
    try:
        with urllib.request.urlopen(net.request(url), timeout=60) as resp:
            data = resp.read()
    except (urllib.error.URLError, OSError):
        return False
    if data[:2] != b"PK":
        return False
    out.write_bytes(data)
    return True


def apply_amo_addons(profile_dir: Path, slugs: list[str]) -> list[str]:
    """Returns the slugs that failed (guid unresolved or download/validation
    failed) — a warning per slug for the caller, never a hard failure for
    the whole batch."""
    ext_dir = profile_dir / "extensions"
    ext_dir.mkdir(parents=True, exist_ok=True)
    failed = []
    for slug in slugs:
        guid = addon_guid(slug)
        if not guid or not addon_fetch(slug, ext_dir / f"{guid}.xpi"):
            failed.append(slug)
    return failed
