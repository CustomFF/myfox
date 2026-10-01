"""Copies autoconfig/chrome/bookmarklet tweaks into the install/profile.

Port of lib/apply.sh. Bookmarklets are a separate project (ddblm) — this
only copies its already-built CSS/icons, same as before.
"""

from __future__ import annotations

import re
import shutil
import urllib.error
import urllib.request
from pathlib import Path

from . import net, paths

DDBLM_REPO = "CustomFF/ddblm"
DDBLM_BRANCH = "master"
DDBLM_RAW = f"https://raw.githubusercontent.com/{DDBLM_REPO}/{DDBLM_BRANCH}"
DDBLM_GALLERY = "https://customff.github.io/ddblm/"


def apply_autoconfig(install_dir: Path) -> None:
    src = paths.autoconfig_dir()
    (install_dir / "defaults" / "pref").mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / "autoconfig.js", install_dir / "defaults" / "pref" / "autoconfig.js")
    shutil.copy2(src / "myfox.cfg", install_dir / "myfox.cfg")
    shutil.rmtree(install_dir / "myfox", ignore_errors=True)
    shutil.copytree(src / "myfox", install_dir / "myfox")
    # Older installs had firefox.cfg; autoconfig.js no longer points at it.
    (install_dir / "firefox.cfg").unlink(missing_ok=True)


def apply_chrome(profile_dir: Path) -> bool:
    """Returns True the one time it backs up a pre-existing userChrome.css
    (the caller decides how to tell the user — see warn_backed_up_style in
    the old i18n catalog for the wording this replaces)."""
    src = paths.chrome_dir()
    c_dir = profile_dir / "chrome"
    c_dir.mkdir(parents=True, exist_ok=True)

    marker = profile_dir / ".myfox"
    existing = c_dir / "userChrome.css"
    backup = c_dir / "userChrome.css.myfox-backup"
    backed_up = False
    if not marker.is_file() and existing.is_file() and not backup.is_file():
        shutil.copy2(existing, backup)
        backed_up = True

    # Replaced wholesale, not merged: a file dropped from a newer version
    # (or the single-file agent_overrides.css of very old installs)
    # shouldn't linger and get registered by myfox.cfg.
    shutil.rmtree(c_dir / "agent", ignore_errors=True)
    shutil.rmtree(c_dir / "user", ignore_errors=True)
    (c_dir / "agent_overrides.css").unlink(missing_ok=True)
    shutil.copytree(src / "agent", c_dir / "agent")
    shutil.copytree(src / "user", c_dir / "user")
    shutil.copy2(src / "userChrome.css", c_dir / "userChrome.css")

    # myfox.cfg checks this marker first and refuses to touch any profile
    # without it.
    marker.touch()
    return backed_up


def apply_theme_pref(profile_dir: Path, theme: str) -> None:
    """Pre-seeds myfox.theme into user.js — a fresh profile hasn't run
    Firefox yet to have a prefs.js of its own. Idempotent: replaces any
    existing myfox.theme line instead of piling up duplicates on repeat
    installs against the same profile."""
    f = profile_dir / "user.js"
    lines = []
    if f.is_file():
        lines = [ln for ln in f.read_text(encoding="utf-8").splitlines() if not ln.startswith('user_pref("myfox.theme"')]
    lines.append(f'user_pref("myfox.theme", "{theme}");')
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _ddblm_fetch(rel: str, out: Path, local_dir: str | None) -> bool:
    if local_dir:
        src = Path(local_dir) / rel
        if src.is_file():
            shutil.copy2(src, out)
            return True
    try:
        with urllib.request.urlopen(net.request(f"{DDBLM_RAW}/{rel}"), timeout=30) as resp:
            out.write_bytes(resp.read())
        return True
    except (urllib.error.URLError, OSError):
        return False


_ICON_URL_RE = re.compile(r'url\("panel-icons/([^"]+)\.svg"\)')


def apply_bookmarklets(profile_dir: Path, local_dir: str | None = None) -> str | None:
    """Returns the gallery URL on success, None if ddblm was unreachable —
    a warning for the caller to show, never a hard install failure. Source
    is MYFOX_DDBLM_LOCAL (dev testing against a checkout) or ddblm's raw
    GitHub content otherwise, same as the bash version."""
    c_dir = profile_dir / "chrome"
    c_dir.mkdir(parents=True, exist_ok=True)
    src_dir = Path(local_dir) if local_dir and (Path(local_dir) / "icons").is_dir() else None

    if not _ddblm_fetch("docs/blm_panel.css", c_dir / "blm_panel.css", local_dir):
        return None

    icons_dir = c_dir / "panel-icons"
    icons_dir.mkdir(parents=True, exist_ok=True)
    if src_dir:
        for f in sorted(src_dir.glob("icons/*.svg")):
            shutil.copy2(f, icons_dir / f.name)
    else:
        names: set[str] = set()
        for css_file in (c_dir / "blm_panel.css", c_dir / "userChrome.css"):
            if css_file.is_file():
                names.update(_ICON_URL_RE.findall(css_file.read_text(encoding="utf-8")))
        names.add("import-bookmarklets")
        for name in sorted(names):
            # Best-effort per icon, same as the bash version — a missing
            # icon is a warning the caller can show, not a reason to abort.
            _ddblm_fetch(f"icons/{name}.svg", icons_dir / f"{name}.svg", local_dir)

    return DDBLM_GALLERY
