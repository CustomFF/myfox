"""Copying another Firefox's profile into a new MyFox one. The source is
only read, except when the sync account moves along: then its account
files are backed up next to themselves first and can be put back
(restore_sync), by `myfox uninstall` or by hand.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from . import i18n, profiles

SYNC_NONE, SYNC_MOVE, SYNC_COPY = "none", "move", "copy"
SYNC_MODES = (SYNC_NONE, SYNC_MOVE, SYNC_COPY)

# Left behind, at the profile's top: locks, caches Firefox rebuilds, crash
# dumps, our markers, and chrome/ (the tweaks bring their own).
SKIP = {
    "lock", ".parentlock", "parent.lock", "startupCache", "cache2", "OfflineCache", "shader-cache",
    "safebrowsing", "crashes", "minidumps", "chrome", ".myfox", ".myfox-created", ".myfox-import",
    ".myfox-theme", profiles.NAME_FILE,
}
ACCOUNT = "signedInUser.json"
SYNC_STATE = "weave"
BACKUP_SUFFIX = ".myfox-backup"
# In the copy: where it came from, so the account can go back later.
ORIGIN = ".myfox-import"
# In the copy: the tweaks switch to the MyFox theme over the copied one
# once, at its first start, then delete it.
THEME_MARKER = ".myfox-theme"
_CHUNK = 1024 * 1024


def _is_sync_pref(line: str) -> bool:
    """The account's and this device's identity; which engines to sync is
    the user's choice and stays."""
    if not line.startswith('user_pref("services.sync.'):
        return False
    return not line.startswith(('user_pref("services.sync.engine.', 'user_pref("services.sync.declinedEngines"'))


def _files(src: Path, skip: set[str]) -> list[Path]:
    """Regular files and symlinks (a socket or a fifo would hang the copy)."""
    found = []
    for root, dirs, files in os.walk(src):
        top = Path(root) == src
        dirs[:] = sorted(d for d in dirs if not (top and d in skip))
        for name in sorted(files):
            path = Path(root) / name
            if not (top and name in skip) and (stat.S_ISREG(path.lstat().st_mode) or path.is_symlink()):
                found.append(path)
    return found


def copy_profile(src: Path, dest: Path, sync: str = SYNC_NONE,
                 on_copy: Callable[[int, int], None] | None = None) -> None:
    """Copies src into the (existing, empty but for our markers) dest.
    on_copy(done, total) comes per chunk and may raise to stop; whatever is
    half-copied then is the caller's to remove."""
    skip = set(SKIP)
    if sync == SYNC_NONE:
        skip |= {ACCOUNT, SYNC_STATE}
    files = _files(src, skip)
    total = sum(f.lstat().st_size for f in files if not f.is_symlink())
    if shutil.disk_usage(dest).free < total:
        raise OSError(i18n.t("err_no_space", dest, total // (1024 * 1024)))
    done = 0
    for f in files:
        target = dest / f.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        if f.is_symlink():
            os.symlink(os.readlink(f), target)
            continue
        with f.open("rb") as fin, target.open("wb") as fout:
            while True:
                chunk = fin.read(_CHUNK)
                if not chunk:
                    break
                fout.write(chunk)
                done += len(chunk)
                if on_copy:
                    on_copy(done, total)
        shutil.copystat(f, target)
    if sync == SYNC_NONE:
        _strip_sync_prefs(dest / "prefs.js")
    leave_group(dest)


def _strip_prefs(prefs: Path, matches: Callable[[str], bool]) -> None:
    if not prefs.is_file():
        return
    lines = prefs.read_text(encoding="utf-8", errors="surrogateescape").splitlines(keepends=True)
    kept = [line for line in lines if not matches(line)]
    if len(kept) != len(lines):
        prefs.write_text("".join(kept), encoding="utf-8", errors="surrogateescape")


def _strip_sync_prefs(prefs: Path) -> None:
    _strip_prefs(prefs, _is_sync_pref)


def leave_group(profile: Path) -> None:
    """Out of the Firefox profile group its prefs name (a copy would join
    the original's, whose Firefox then lists it in profiles.ini as its
    own). The group's database is the caller's (sources.forget_in_groups)."""
    _strip_prefs(profile / "prefs.js", lambda line: line.startswith('user_pref("toolkit.profiles.storeID"'))


def write_origin(copy: Path, source: Path, sync: str, backups: list[Path], moved: bool = False) -> None:
    (copy / ORIGIN).write_text(json.dumps({"source": str(source), "sync": sync, "moved": moved,
                                           "backups": [str(b) for b in backups]}, indent=2) + "\n",
                               encoding="utf-8")


def read_origin(copy: Path) -> dict | None:
    try:
        data = json.loads((copy / ORIGIN).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("source"), str) else None


def restorable_source(copy: Path) -> Path | None:
    """The profile an import moved the account out of, while it can still
    take it back."""
    origin = read_origin(copy)
    if origin is None or origin.get("sync") != SYNC_MOVE:
        return None
    source = Path(origin["source"])
    return source if can_restore_sync(source) else None


def _backup(path: Path) -> Path:
    return path.with_name(path.name + BACKUP_SUFFIX)


def has_account(profile: Path) -> bool:
    return (profile / ACCOUNT).is_file()


def move_sync_out(src: Path) -> list[Path]:
    """Signs the source out after its account went into the copy: backs up
    signedInUser.json and prefs.js beside themselves (replacing an older
    backup: the account now is the one to restore), then removes the account and its sync identity. Returns the
    backups."""
    account = src / ACCOUNT
    if not account.is_file():
        return []
    backups = []
    for path in (account, src / "prefs.js"):
        if path.is_file():
            backup = _backup(path)
            shutil.copy2(path, backup)
            backups.append(backup)
    account.unlink()
    _strip_sync_prefs(src / "prefs.js")
    return backups


def sign_out(profile: Path) -> None:
    """Drops the account and the device's sync identity, keeps no backup."""
    try:
        (profile / ACCOUNT).unlink()
    except FileNotFoundError:
        pass
    _strip_sync_prefs(profile / "prefs.js")


def can_restore_sync(src: Path) -> bool:
    """A backup is there and the source hasn't been signed in again since
    (that account would be overwritten)."""
    return _backup(src / ACCOUNT).is_file() and not (src / ACCOUNT).exists()


def restore_sync(src: Path) -> None:
    """Puts the moved account back into the source: signedInUser.json from
    its backup, and the sync prefs from prefs.js's backup into the current
    prefs.js (whatever else changed there since stays). The backups go."""
    account_backup = _backup(src / ACCOUNT)
    prefs, prefs_backup = src / "prefs.js", _backup(src / "prefs.js")
    if prefs_backup.is_file():
        saved = [line for line in prefs_backup.read_text(encoding="utf-8", errors="surrogateescape")
                 .splitlines(keepends=True) if _is_sync_pref(line)]
        current = prefs.read_text(encoding="utf-8", errors="surrogateescape").splitlines(keepends=True) \
            if prefs.is_file() else []
        kept = [line for line in current if not _is_sync_pref(line)]
        if kept and not kept[-1].endswith("\n"):
            kept[-1] += "\n"
        prefs.write_text("".join(kept + saved), encoding="utf-8", errors="surrogateescape")
        prefs_backup.unlink()
    if account_backup.is_file():
        os.replace(account_backup, src / ACCOUNT)


def accept_downgrade(install_dir: Path, profile: Path) -> None:
    """Opens the profile once, headless, with --allow-downgrade: afterwards
    it's this Firefox's and starts without the "newer version" refusal."""
    with tempfile.NamedTemporaryFile(suffix=".myfox-shot.png") as shot:
        try:
            subprocess.run(
                [str(install_dir / "firefox"), "--headless", "--allow-downgrade", "--no-remote", "--profile",
                 str(profile), "--screenshot", shot.name, "about:blank"],
                timeout=180, env=profiles._headless_env(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except (subprocess.SubprocessError, OSError):
            pass


def source_theme(profile: Path) -> str | None:
    """"dark" or "light", as the profile's own theme looks: Firefox records
    that for any theme (built-in or not) in browser.theme.toolbar-theme,
    0 dark, 1 light, 2 as the system. None when it follows the system or
    says nothing."""
    try:
        text = (profile / "prefs.js").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = re.search(r'^user_pref\("browser\.theme\.toolbar-theme", (\d+)\);', text, re.M)
    return {"0": "dark", "1": "light"}.get(m.group(1)) if m else None


def system_theme() -> str | None:
    """The desktop's color scheme through the freedesktop portal (GNOME,
    KDE and others), else GNOME's own setting; None if neither says."""
    for cmd, parse in (
        (["gdbus", "call", "--session", "--timeout", "3", "--dest", "org.freedesktop.portal.Desktop",
          "--object-path", "/org/freedesktop/portal/desktop", "--method", "org.freedesktop.portal.Settings.ReadOne",
          "org.freedesktop.appearance", "color-scheme"],
         lambda out: {"1": "dark", "2": "light"}.get((re.search(r"uint32 (\d)", out) or [None, None])[1])),
        (["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
         lambda out: "dark" if "prefer-dark" in out else "light" if "prefer-light" in out else None),
    ):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=True).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        theme = parse(out)
        if theme:
            return theme
    return None


def mark_theme(copy: Path, source: Path) -> str | None:
    """The MyFox theme that looks like the source's (or the system's), for
    the tweaks to switch the copy to at its first start; None if unknown."""
    theme = source_theme(source) or system_theme()
    if theme:
        (copy / THEME_MARKER).touch()
    return theme
