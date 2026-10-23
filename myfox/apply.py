"""Copies the tweaks (autoconfig/ into the install, chrome/ into the
profile) and the bookmarklet styling. Bookmarklets are a separate project
(ddblm): this only copies its built CSS and icons.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import net, paths

DDBLM_REPO = "CustomFF/ddblm"
DDBLM_BRANCH = "master"
DDBLM_RAW = f"https://raw.githubusercontent.com/{DDBLM_REPO}"


def apply_autoconfig(install_dir: Path) -> None:
    _copy_autoconfig(install_dir)
    # Firefox stages an update into <install>/updated, a copy of the install
    # as it was then, and on the next start swaps it in for the install:
    # tweaks applied in between would go back to the older ones. They go
    # into the staged copy too.
    staged = install_dir / "updated"
    if staged.is_dir():
        _copy_autoconfig(staged)


def _copy_autoconfig(install_dir: Path) -> None:
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
    (the caller decides how to tell the user)."""
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

    # Every directory the tweaks ship (agent/, user/, author/, ...), so a
    # new one needs no change here. Replaced wholesale, not merged: a file
    # dropped from a newer version (or the single-file agent_overrides.css
    # of very old installs) shouldn't linger and get registered by myfox.cfg.
    (c_dir / "agent_overrides.css").unlink(missing_ok=True)
    for sub in sorted(p for p in src.iterdir() if p.is_dir()):
        shutil.rmtree(c_dir / sub.name, ignore_errors=True)
        shutil.copytree(sub, c_dir / sub.name)
    shutil.copy2(src / "userChrome.css", c_dir / "userChrome.css")

    # myfox.cfg checks this marker first and refuses to touch any profile
    # without it (see docs/logic.md, profile locality).
    marker.touch()
    return backed_up


def _user_pref(profile_dir: Path, name: str, value: str) -> None:
    """Pre-seeds a pref into user.js — a fresh profile hasn't run Firefox
    yet to have a prefs.js of its own. Idempotent: replaces an existing
    line for the pref instead of piling up duplicates on repeat installs
    against the same profile. `value` is the JavaScript literal."""
    f = profile_dir / "user.js"
    lines = []
    if f.is_file():
        lines = [ln for ln in f.read_text(encoding="utf-8").splitlines() if not ln.startswith(f'user_pref("{name}"')]
    lines.append(f'user_pref("{name}", {value});')
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")


def apply_theme_pref(profile_dir: Path, theme: str) -> None:
    _user_pref(profile_dir, "myfox.theme", f'"{theme}"')


def apply_doh_off(profile_dir: Path) -> None:
    """The tweaks turn on DNS over HTTPS at a profile's first start, unless
    this says not to."""
    _user_pref(profile_dir, "myfox.doh", "false")


# What MyFox takes from ddblm; its version is the newest commit touching them.
_DDBLM_PATHS = ("docs/blm_panel.css", "icons")


@dataclass(frozen=True)
class DdblmRelease:
    tag: str  # "ddblm-<commit time>", so it compares like the other tracks
    sha: str


def latest_ddblm_release() -> DdblmRelease | None:
    """ddblm has no releases: the newest master commit that changed the CSS
    or the icons stands in for one. None if there is none; OSError when
    GitHub can't be asked."""
    newest = None
    for path in _DDBLM_PATHS:
        url = f"https://api.github.com/repos/{DDBLM_REPO}/commits?sha={DDBLM_BRANCH}&path={path}&per_page=1"
        try:
            with urllib.request.urlopen(net.request(url), timeout=net.TIMEOUT) as resp:
                commits = json.loads(resp.read().decode("utf-8"))
            if not commits:
                continue
            sha, when = commits[0]["sha"], commits[0]["commit"]["committer"]["date"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise OSError(f"bad response from GitHub: {exc}") from exc
        tag = "ddblm-" + re.sub(r"\D", "", when)  # 2026-10-15T12:34:56Z -> 20261015123456
        if newest is None or tag > newest.tag:
            newest = DdblmRelease(tag, sha)
    return newest


def ddblm_display(tag: str | None) -> str:
    """"ddblm-20261015123456" -> "2026-10-15 12:34", like the themes."""
    m = re.fullmatch(r"ddblm-(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})\d*", tag or "")
    return f"{m[1]}-{m[2]}-{m[3]} {m[4]}:{m[5]}" if m else (tag or "—")


def _ddblm_fetch(rel: str, out: Path, local_dir: str | None, ref: str = DDBLM_BRANCH) -> bool:
    if local_dir:
        src = Path(local_dir) / rel
        if src.is_file():
            shutil.copy2(src, out)
            return True
    try:
        with urllib.request.urlopen(net.request(f"{DDBLM_RAW}/{ref}/{rel}"), timeout=net.TIMEOUT) as resp:
            out.write_bytes(resp.read())
        return True
    except (urllib.error.URLError, OSError):
        return False


_ICON_URL_RE = re.compile(r'url\("panel-icons/([^"]+)\.svg"\)')


def apply_bookmarklets(profile_dir: Path, local_dir: str | None = None, current: str | None = None,
                       release: DdblmRelease | None = None) -> str | None:
    """ddblm's CSS and icons into the profile's chrome/. Returns the ddblm
    version now there (to record; `current` when nothing new got in).

    From `release` (default: the latest), skipped when that is `current`
    and the CSS is there; all files from that one commit. If GitHub can't
    be asked, from master, unrecorded. Unreachable ddblm is a warning for
    the caller, never a hard failure. MYFOX_DDBLM_LOCAL (a checkout, dev
    use) records nothing."""
    c_dir = profile_dir / "chrome"
    c_dir.mkdir(parents=True, exist_ok=True)
    css = c_dir / "blm_panel.css"
    src_dir = Path(local_dir) if local_dir and (Path(local_dir) / "icons").is_dir() else None

    ref, tag = DDBLM_BRANCH, None
    if not local_dir:
        try:
            release = release or latest_ddblm_release()
        except OSError:
            release = None
        if release:
            if release.tag == current and css.is_file():
                return current
            ref, tag = release.sha, release.tag

    if not _ddblm_fetch("docs/blm_panel.css", css, local_dir, ref):
        return current

    icons_dir = c_dir / "panel-icons"
    icons_dir.mkdir(parents=True, exist_ok=True)
    if src_dir:
        for f in sorted(src_dir.glob("icons/*.svg")):
            shutil.copy2(f, icons_dir / f.name)
    else:
        names: set[str] = set()
        for css_file in (css, c_dir / "userChrome.css"):
            if css_file.is_file():
                names.update(_ICON_URL_RE.findall(css_file.read_text(encoding="utf-8")))
        names.add("import-bookmarklets")
        for name in sorted(names):
            # Best-effort per icon: a missing icon is no reason to abort.
            _ddblm_fetch(f"icons/{name}.svg", icons_dir / f"{name}.svg", local_dir, ref)

    return None if local_dir else (tag or current)


def reapply_tweaks(install_dir: Path, profile_dir: Path | None, state) -> None:
    """Applies the tweaks in paths.tweaks_dir() again (after reinstall or a
    tweaks update), with the choices the install saved in `state`."""
    from . import addons

    apply_autoconfig(install_dir)
    if profile_dir is None:
        return
    apply_chrome(profile_dir)
    apply_theme_pref(profile_dir, state.get("theme", "dark"))
    # Downloaded only if there's a newer release or a theme is missing.
    themes, _missing = addons.fetch_themes(profile_dir, local_dir=os.environ.get("MYFOX_TWEAKS_LOCAL"),
                                           current=state.get("themes_version"))
    state.set("themes_version", themes)
    if state.get("opt_plasma") and addons.is_plasma_session():
        addons.apply_amo_addons(profile_dir, [addons.MYFOX_ADDON_PLASMA])
    if state.get("opt_bl", True):
        # Downloaded only if ddblm changed or the CSS is missing.
        state.set("ddblm_version", apply_bookmarklets(profile_dir, local_dir=os.environ.get("MYFOX_DDBLM_LOCAL"),
                                                      current=state.get("ddblm_version")))
