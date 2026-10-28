"""Every Firefox profile of this user MyFox can see: in our store (shared
with the system Firefox), the snap's and the flatpak's. Each has an ID, its
folder name ("snap:"/"flatpak:" in front for those stores), which the
profile commands take; plus which of them belong to MyFox, whether one is
in use, and the Firefox version that last opened it.
"""

from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from . import i18n, profiles

SNAP, FLATPAK = "snap", "flatpak"

# Who a profile belongs to.
MYFOX = "myfox"      # has our .myfox marker
OURS = "ours"        # last opened by our install (made with `firefox -p`), no tweaks yet
UNUSED = "unused"    # never opened by any Firefox
FOREIGN = "foreign"  # another Firefox's: only to import

_STORE_ID_RE = re.compile(r"^[0-9A-Za-z]+$")
_VERSION_RE = re.compile(r"(\d+(?:\.\d+)*)(?:([ab])(\d+))?")


class ProfileLookupError(ValueError):
    """A profile argument that names none or several: an i18n key + args."""

    def __init__(self, key: str, *args: object) -> None:
        super().__init__(i18n.t(key, *args))
        self.key = key


@dataclass(frozen=True)
class Store:
    kind: str  # "" for ours, SNAP, FLATPAK
    root: Path


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    path: Path
    store: str
    owner: str
    last_version: str | None  # "157.0", from compatibility.ini

    @property
    def related(self) -> bool:
        """MyFox may use it in place (use/apply); the rest only import."""
        return self.owner != FOREIGN


def _sandbox_store(home: Path) -> Path:
    # A sandboxed Firefox has its own home and picks its store by the same
    # rule as ours: the legacy path if it exists, else the XDG one.
    legacy = home / ".mozilla" / "firefox"
    xdg = home / "config" / "mozilla" / "firefox"
    return xdg if not legacy.is_dir() and xdg.is_dir() else legacy


def stores() -> list[Store]:
    result = [Store("", profiles.native_dir())]
    snap = Path.home() / "snap" / "firefox"
    if snap.is_dir():
        result.append(Store(SNAP, _sandbox_store(snap / "common")))
    flatpak = Path.home() / ".var" / "app" / "org.mozilla.firefox"
    if flatpak.is_dir():
        result.append(Store(FLATPAK, _sandbox_store(flatpak)))
    return result


def _group_profiles(root: Path, store_id: str) -> list[tuple[Path, str]]:
    """Firefox's newer profile groups keep their profiles (and the names
    shown for them) in a database, not all of them in profiles.ini."""
    db = root / "Profile Groups" / f"{store_id}.sqlite"
    if not _STORE_ID_RE.match(store_id) or not db.is_file():
        return []
    try:
        # immutable: no lock taken, a running Firefox is left alone.
        con = sqlite3.connect(f"{db.as_uri()}?immutable=1", uri=True)
        try:
            rows = con.execute("SELECT path, name FROM Profiles").fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return []
    return [(root / path, name) for path, name in rows if isinstance(path, str) and path]


def forget_in_groups(root: Path, profile_dir: Path) -> None:
    """Takes `profile_dir` out of the store's profile groups; with the
    owning Firefox closed. Best effort: a group row left behind only lists
    a profile that is gone."""
    for db in sorted((root / "Profile Groups").glob("*.sqlite")):
        try:
            con = sqlite3.connect(str(db))
            try:
                with con:
                    for path, in con.execute("SELECT path FROM Profiles").fetchall():
                        if isinstance(path, str) and root / path == profile_dir:
                            con.execute("DELETE FROM Profiles WHERE path = ?", (path,))
            finally:
                con.close()
        except sqlite3.Error:
            pass


def store_root(p: Profile) -> Path | None:
    return next((s.root for s in stores() if s.kind == p.store), None)


def _registered(root: Path) -> dict[Path, str]:
    """Profile folder -> name, from profiles.ini and its profile groups."""
    cp = profiles._read_ini(root / "profiles.ini")
    found: dict[Path, str] = {}
    store_ids = []
    for section in cp.sections():
        if not profiles._PROFILE_SECTION_RE.match(section):
            continue
        entry = profiles.ProfileEntry(
            section=section, path=cp.get(section, "Path", fallback=""), name=cp.get(section, "Name", fallback=""),
            is_default=False, is_relative=cp.get(section, "IsRelative", fallback="0") == "1",
        )
        if entry.path:
            found.setdefault(profiles.resolve_dir(root, entry), entry.name)
        store_id = cp.get(section, "StoreID", fallback="")
        if store_id and store_id not in store_ids:
            store_ids.append(store_id)
    for store_id in store_ids:
        for path, name in _group_profiles(root, store_id):
            found[path] = name  # the name the profile selector shows
    # Our own profiles stay ours once uninstall has unregistered them.
    if root.is_dir():
        for d in sorted(root.glob("myfox-*")):
            if d not in found and (d / ".myfox-created").is_file():
                found[d] = ""
    return found


def _compat(path: Path, key: str) -> str:
    return profiles._read_ini(path / "compatibility.ini").get("Compatibility", key, fallback="")


def last_version(path: Path) -> str | None:
    """"157.0_20260914090352/20260914090352" -> "157.0"."""
    return _compat(path, "LastVersion").split("_")[0] or None


def owner(path: Path, store: str, install_dir: Path | None) -> str:
    if (path / ".myfox").is_file():
        return MYFOX
    if store:
        return FOREIGN
    if not (path / "compatibility.ini").is_file():
        return UNUSED
    last = _compat(path, "LastPlatformDir")
    if install_dir is not None and last and Path(last).resolve() == install_dir.resolve():
        return OURS
    return FOREIGN


def _profile(path: Path, name: str, store: Store | None, install_dir: Path | None) -> Profile:
    kind = store.kind if store else ""
    # A folder outside its store could share a name with one inside: the
    # path is its ID then.
    inside = store is not None and path.parent == store.root
    pid = (f"{kind}:{path.name}" if kind else path.name) if inside else str(path)
    return Profile(id=pid, name=name or path.name, path=path, store=kind, owner=owner(path, kind, install_dir),
                   last_version=last_version(path))


def listing(install_dir: Path | None = None) -> list[Profile]:
    """Every profile that's there on disk, in store order."""
    result = []
    for store in stores():
        for path, name in _registered(store.root).items():
            if path.is_dir():
                result.append(_profile(path, name, store, install_dir))
    return result


def myfox_dirs(state) -> list[Path]:
    """The profiles the tweaks go into: our store's ones with the .myfox
    marker, and the one our Firefox opens, first. None for an install
    without the tweaks."""
    if not state.get("tweaks", True):
        return []
    found = [Path(state.get("profile_dir"))] if state.get("profile_dir") else []
    for p in listing():
        if p.owner == MYFOX and not p.store and p.path not in found:
            found.append(p.path)
    return found


def is_profile(path: Path) -> bool:
    return (path / "prefs.js").is_file() or (path / "times.json").is_file()


def resolve(arg: str, found: list[Profile], install_dir: Path | None = None) -> Profile:
    """An ID, a path, or a name that only one profile has. Raises
    ProfileLookupError saying why not."""
    for p in found:
        if p.id == arg:
            return p
    if "/" in arg or arg.startswith("~"):
        path = Path(arg).expanduser().resolve()
        for p in found:
            if p.path.resolve() == path:
                return p
        if not is_profile(path):
            raise ProfileLookupError("err_not_a_profile", arg)
        return _profile(path, "", None, install_dir)
    named = [p for p in found if p.name == arg]
    if len(named) == 1:
        return named[0]
    if named:
        raise ProfileLookupError("err_profile_ambiguous", arg, ", ".join(p.id for p in named))
    raise ProfileLookupError("err_profile_not_found", arg)


# ─── In use ──────────────────────────────────────────────────────────────

def _lock_pid(path: Path) -> int | None:
    """Firefox's lock is a symlink to "<ip>:+<pid>" while it runs."""
    try:
        target = os.readlink(path / "lock")
    except OSError:
        return None
    pid = target.rpartition("+")[2]
    return int(pid) if pid.isdigit() else None


def _is_firefox(pid: int) -> bool:
    # A lock left by a crash can point at a pid reused since.
    try:
        exe = os.readlink(f"/proc/{pid}/exe")
    except OSError:
        return False
    if exe.endswith(" (deleted)"):  # updated while running
        exe = exe[:-len(" (deleted)")]
    return Path(exe).name in ("firefox", "firefox-bin")


def _flatpak_running() -> bool:
    """The flatpak's own pid namespace makes its lock's pid meaningless out
    here; its processes are told by their cgroup instead."""
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            cgroup = (proc / "cgroup").read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "flatpak-org.mozilla.firefox" in cgroup:
            return True
    return False


def in_use(profile: Profile) -> bool:
    """A Firefox has it open (and so it can't be copied consistently)."""
    if profile.store == FLATPAK:
        return _flatpak_running()
    pid = _lock_pid(profile.path)
    return pid is not None and _is_firefox(pid)


# ─── Versions ────────────────────────────────────────────────────────────

def _version_key(version: str) -> tuple[int, ...] | None:
    """"159.0b5" < "159.0" < "159.0.1"; nightly "161.0a1" < "161.0b1"."""
    m = _VERSION_RE.match(version or "")
    if not m:
        return None
    nums = [int(n) for n in m.group(1).split(".")] + [0, 0]
    stage = {"a": 0, "b": 1}.get(m.group(2) or "", 2)
    return (*nums[:3], stage, int(m.group(3) or 0))


def is_downgrade(last: str | None, target: str | None) -> bool:
    """Opening a profile last run by `last` with the older `target`."""
    old, new = _version_key(last or ""), _version_key(target or "")
    return old is not None and new is not None and old > new
