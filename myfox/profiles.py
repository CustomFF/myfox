"""profiles.ini / installs.ini handling, headless install-hash pinning.

The profile store is *shared* with regular Firefox (~/.mozilla/firefox or
the XDG path Firefox 147+ uses) — every function here touches only the
sections it owns ([Install<HASH>], [ProfileN] Name=myfox), never someone
else's.

Firefox computes its own [Install<HASH>] with no public API for it, so the
only way to learn the hash is to run the install once (headless) and diff
profiles.ini/installs.ini before and after.

A running Firefox rewrites profiles.ini from the list it read at its start,
taking back whatever was added or removed meanwhile. So only the profile
our install opens is listed there (Firefox needs it to be); MyFox's other
profiles live outside it, opened by their folder, named by NAME_FILE, and
come and go with Firefox running.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path

_PROFILE_SECTION_RE = re.compile(r"^Profile\d+$")
# In a profile MyFox created: its name, whether profiles.ini lists it or not.
NAME_FILE = ".myfox-name"
CREATED_MARKER = ".myfox-created"
# Both capture just the inner name (no brackets) — callers only ever want
# the bare "Install<HASH>" or "<HASH>", never the bracket punctuation.
_INSTALL_SECTION_RE = re.compile(r"^\[(Install[0-9A-F]{1,16})\]$")
_HASH_SECTION_RE = re.compile(r"^\[([0-9A-F]{1,16})\]$")


def _read_ini(ini: Path) -> ConfigParser:
    cp = ConfigParser(strict=False)
    cp.optionxform = str  # preserve Firefox's PascalCase keys (Name, IsRelative, ...)
    if ini.is_file():
        cp.read(ini, encoding="utf-8")
    return cp


# ─── Locating profiles.ini ───────────────────────────────────────────────

def native_dir() -> Path:
    """Same rule Firefox itself uses: the legacy path if it already exists
    (an existing install keeps using it), else the XDG path (Firefox 147+
    on a system that never had the legacy layout)."""
    legacy = Path.home() / ".mozilla" / "firefox"
    if legacy.is_dir():
        return legacy
    xdg_config = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg_config) / "mozilla" / "firefox"


def search_dirs() -> list[Path]:
    """Ours, then the flatpak's and the snap's. Only for cleaning up: our
    Firefox reads ours alone, so nothing of ours is ever made in the others."""
    dirs = [native_dir()]
    flatpak = Path.home() / ".var" / "app" / "org.mozilla.firefox"
    if flatpak.is_dir():
        dirs.append(flatpak / ".mozilla" / "firefox")
    snap = Path.home() / "snap" / "firefox"
    if snap.is_dir():
        dirs.append(snap / "common" / ".mozilla" / "firefox")
    return dirs


def find_ini() -> Path | None:
    """Our Firefox's profiles.ini, if there is one yet."""
    candidate = native_dir() / "profiles.ini"
    return candidate if candidate.is_file() else None


# ─── Parsing profiles.ini ────────────────────────────────────────────────

@dataclass(frozen=True)
class ProfileEntry:
    section: str
    path: str
    name: str
    is_default: bool
    is_relative: bool


def parse_profiles(ini: Path) -> list[ProfileEntry]:
    cp = _read_ini(ini)
    entries = []
    for section in cp.sections():
        if not _PROFILE_SECTION_RE.match(section):
            continue
        entries.append(ProfileEntry(
            section=section,
            path=cp.get(section, "Path", fallback=""),
            name=cp.get(section, "Name", fallback=""),
            is_default=cp.get(section, "Default", fallback="0") == "1",
            is_relative=cp.get(section, "IsRelative", fallback="0") == "1",
        ))
    return entries


def resolve_dir(ini_dir: Path, entry: ProfileEntry) -> Path:
    if entry.is_relative:
        return ini_dir / entry.path
    p = Path(entry.path)
    return p if p.is_absolute() else ini_dir / entry.path


# ─── Creating a new profile ──────────────────────────────────────────────

def _next_profile_section(cp: ConfigParser) -> str:
    nums = [int(m.group(1)) for s in cp.sections() if (m := re.match(r"^Profile(\d+)$", s))]
    return f"Profile{(max(nums, default=-1) + 1)}"


def _append_profile_entry(ini: Path, path_value: str, is_relative: str, name: str = "myfox") -> str:
    """Appends a new [ProfileN] section, returns its name. A gap an older
    MyFox left in the numbering is closed first, or the new one would be
    past it, out of Firefox's sight."""
    if ini.is_file():
        text = ini.read_text(encoding="utf-8")
        healed = _renumber_profiles(text)
        if healed != text:
            ini.write_text(healed, encoding="utf-8")
    section = _next_profile_section(_read_ini(ini))
    prefix = "\n" if ini.is_file() and ini.stat().st_size > 0 else ""
    with ini.open("a", encoding="utf-8") as f:
        f.write(f"{prefix}[{section}]\nName={name}\nIsRelative={is_relative}\nPath={path_value}\n")
    return section


def read_name(profile_dir: Path) -> str | None:
    try:
        return " ".join((profile_dir / NAME_FILE).read_text(encoding="utf-8").split()) or None
    except OSError:
        return None


def write_name(profile_dir: Path, name: str) -> None:
    (profile_dir / NAME_FILE).write_text(" ".join(name.split()) + "\n", encoding="utf-8")


def create_new(name: str | None = None, register: bool = True) -> Path:
    """A new myfox-N named `name` (default "myfox"; "" for its folder name),
    listed in profiles.ini only if `register`."""
    ini = find_ini()
    if ini:
        ini_dir = ini.parent
    else:
        ini_dir = native_dir()
        ini_dir.mkdir(parents=True, exist_ok=True)
        ini = ini_dir / "profiles.ini"

    idx = 1
    while (ini_dir / f"myfox-{idx}").exists():
        idx += 1
    ppath = f"myfox-{idx}"
    profile_dir = ini_dir / ppath
    profile_dir.mkdir(parents=True)
    (profile_dir / CREATED_MARKER).write_text("", encoding="utf-8")
    name = "myfox" if name is None else (" ".join(name.split()) or ppath)
    write_name(profile_dir, name)
    if register:
        _append_profile_entry(ini, ppath, "1", name)
    return profile_dir


# ─── Raw section add/remove (line-based, not full re-serialization — a
#     minimal diff instead of configparser reformatting the whole file) ───

def _remove_section_text(text: str, section_name: str) -> str:
    lines = text.splitlines(keepends=True)
    out = []
    skip = False
    target = f"[{section_name}]"
    for line in lines:
        stripped = line.rstrip("\n")
        if stripped.startswith("["):
            skip = stripped == target
            if skip:
                continue
        if not skip:
            out.append(line)
    return "".join(out)


def _renumber_profiles(text: str) -> str:
    """Firefox reads [Profile0], [Profile1], … up to the first number
    missing: every profile after a gap would vanish for it."""
    numbers = sorted({int(m.group(1)) for line in text.splitlines()
                      if (m := re.match(r"^\[Profile(\d+)\]$", line.strip()))})
    renamed = {n: i for i, n in enumerate(numbers)}
    if all(n == i for n, i in renamed.items()):
        return text
    out = []
    for line in text.splitlines(keepends=True):
        m = re.match(r"^\[Profile(\d+)\]$", line.strip())
        out.append(f"[Profile{renamed[int(m.group(1))]}]" + line[len(line.rstrip("\r\n")):] if m else line)
    return "".join(out)


def remove_ini_section(ini: Path, section_name: str) -> None:
    text = ini.read_text(encoding="utf-8") if ini.is_file() else ""
    text = _remove_section_text(text, section_name)
    if ini.name == "profiles.ini":
        text = _renumber_profiles(text)
    ini.write_text(text, encoding="utf-8")


def write_install_section(ini: Path, section_name: str, profile_path: str) -> None:
    """Replaces [section_name] wholesale with Default=<profile_path> /
    Locked=1 — used for both profiles.ini's [Install<HASH>] and
    installs.ini's [<HASH>], same shape."""
    text = ini.read_text(encoding="utf-8") if ini.is_file() else ""
    text = _remove_section_text(text, section_name)
    text += f"\n[{section_name}]\nDefault={profile_path}\nLocked=1\n"
    ini.write_text(text, encoding="utf-8")


# ─── Registering a profile directory as a [ProfileN] entry ──────────────

def _find_entry_for_dir(ini: Path, target_dir: Path) -> ProfileEntry | None:
    ini_dir = ini.parent
    for entry in parse_profiles(ini):
        if resolve_dir(ini_dir, entry) == target_dir:
            return entry
    return None


def register_entry(ini: Path, profile_abs: Path) -> str:
    """Idempotent: reusing an existing [ProfileN] for this exact directory
    instead of piling up a duplicate on every repeated install/reinstall."""
    existing = _find_entry_for_dir(ini, profile_abs)
    if existing is not None:
        return existing.path

    ini_dir = ini.parent
    try:
        path_value = str(profile_abs.relative_to(ini_dir))
        is_relative = "1"
    except ValueError:
        path_value = str(profile_abs)
        is_relative = "0"

    _append_profile_entry(ini, path_value, is_relative, read_name(profile_abs) or "myfox")
    return path_value


def set_entry_name(profile_dir: Path, name: str) -> None:
    """Name= of this folder's [ProfileN], wherever it is listed."""
    for ini in _all_inis():
        entry = _find_entry_for_dir(ini, profile_dir)
        if entry is None or entry.name == name:
            continue
        out, inside = [], False
        for line in ini.read_text(encoding="utf-8").splitlines(keepends=True):
            stripped = line.strip()
            if stripped.startswith("["):
                inside = stripped == f"[{entry.section}]"
            elif inside and stripped.startswith("Name="):
                line = f"Name={name}" + line[len(line.rstrip("\r\n")):]
            out.append(line)
        ini.write_text("".join(out), encoding="utf-8")


def all_inis() -> list[Path]:
    return _all_inis()


def keep_one_entry(profile_dir: Path) -> None:
    """A folder Firefox came to list more than once: the first stays."""
    for ini in _all_inis():
        # One at a time: a removal renumbers the sections after it.
        while len(entries := [e for e in parse_profiles(ini) if resolve_dir(ini.parent, e) == profile_dir]) > 1:
            remove_ini_section(ini, entries[-1].section)


def is_registered(profile_dir: Path) -> bool:
    return any(_find_entry_for_dir(ini, profile_dir) for ini in _all_inis())


def unregister(profile_dir: Path) -> None:
    """Off profiles.ini, keeping the name it had there."""
    if read_name(profile_dir) is None:
        entries = [e for ini in _all_inis() if (e := _find_entry_for_dir(ini, profile_dir))]
        write_name(profile_dir, entries[0].name if entries and entries[0].name else profile_dir.name)
    remove_myfox_section(profile_dir)


def _all_inis() -> list[Path]:
    # An older MyFox registered in the flatpak's or the snap's profiles.ini
    # when ours didn't exist yet; cleaning up looks there too.
    return [d / "profiles.ini" for d in search_dirs() if (d / "profiles.ini").is_file()]


def remove_myfox_section(profile_dir: Path) -> None:
    """Scoped to this exact profile directory — never "any [ProfileN] named
    myfox", which would also rip out unrelated myfox installs elsewhere."""
    for ini in _all_inis():
        # Every one: a Firefox can list a folder more than once.
        while (entry := _find_entry_for_dir(ini, profile_dir)) is not None:
            remove_ini_section(ini, entry.section)


def forget_dir(ini: Path, profile_dir: Path) -> None:
    """Another Firefox's profiles.ini or installs.ini without `profile_dir`:
    its [ProfileN] and any install defaulting to it (that Firefox then picks
    or makes another default, as when a profile goes missing)."""
    cp = _read_ini(ini)
    gone = []
    for section in cp.sections():
        if _PROFILE_SECTION_RE.match(section):
            entry = next(e for e in parse_profiles(ini) if e.section == section)
            if resolve_dir(ini.parent, entry) == profile_dir:
                gone.append(section)
        elif cp.has_option(section, "Default") and cp.get(section, "Default"):
            default = Path(cp.get(section, "Default"))
            if (default if default.is_absolute() else ini.parent / default) == profile_dir:
                gone.append(section)
    if gone:
        text = ini.read_text(encoding="utf-8")
        for section in gone:
            text = _remove_section_text(text, section)
        ini.write_text(_renumber_profiles(text) if ini.name == "profiles.ini" else text, encoding="utf-8")


# ─── Headless pinning ────────────────────────────────────────────────────

def _matching_sections(ini: Path | None, pattern: re.Pattern) -> set[str]:
    """Section names matching `pattern`, brackets and any fixed prefix
    already stripped by the pattern's own capture group."""
    if ini is None or not ini.is_file():
        return set()
    matches = (pattern.match(ln.strip()) for ln in ini.read_text(encoding="utf-8").splitlines())
    return {m.group(1) for m in matches if m}


def _install_sections(ini: Path | None) -> set[str]:
    return _matching_sections(ini, _INSTALL_SECTION_RE)


def _hash_sections(ini: Path | None) -> set[str]:
    return _matching_sections(ini, _HASH_SECTION_RE)


def _store_profile_dirs(store_dir: Path) -> set[str]:
    if not store_dir.is_dir():
        return set()
    return {d.name for d in store_dir.iterdir() if d.is_dir() and (d / "prefs.js").is_file()}


def _cache_store() -> Path:
    """Firefox keeps a profile's cache in <this>/<the profile's dir name>."""
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "mozilla" / "firefox"


def _missing_top(path: Path) -> Path | None:
    top = None
    for p in (path, *path.parents):
        if p.exists():
            break
        top = p
    return top


def _purge_headless_strays(store_dir: Path | None, ini: Path | None, our_dir: Path, before_names: set[str]) -> None:
    if store_dir is None or not store_dir.is_dir():
        return
    for name in _store_profile_dirs(store_dir):
        abs_path = store_dir / name
        if abs_path == our_dir or name in before_names:
            continue
        if ini is not None and ini.is_file():
            entry = _find_entry_for_dir(ini, abs_path)
            if entry:
                remove_ini_section(ini, entry.section)
        shutil.rmtree(abs_path, ignore_errors=True)
        shutil.rmtree(_cache_store() / name, ignore_errors=True)


def _remove_first_run_dirs(home_before: set[str], cache_top: Path | None) -> None:
    """A first start also makes the cache directories and the downloads
    folder; those the headless pass made go, if left empty."""
    if cache_top is not None:
        p = _cache_store()
        while True:
            try:
                p.rmdir()
            except OSError:
                break
            if p == cache_top:
                break
            p = p.parent
    home = Path.home()
    if not home.is_dir():
        return
    for name in set(os.listdir(home)) - home_before:
        p = home / name
        if p.is_dir() and not p.is_symlink() and not any(p.iterdir()):
            p.rmdir()


def headless_once(install_dir: Path, our_profile: Path) -> str | None:
    """Runs `firefox --headless --screenshot` (throwaway) up to twice and
    diffs profiles.ini/installs.ini before/after for a new [Install<HASH>]
    or [<HASH>] section Firefox itself wrote — that's the only way to learn
    the hash, there's no API for it. Cleans up whatever stray first-run
    profile that headless pass created along the way."""
    binary = install_dir / "firefox"
    if not os.access(binary, os.X_OK):
        return None

    ini = find_ini()
    ini_before = _install_sections(ini)
    inst_ini = (ini.parent / "installs.ini") if ini else None
    inst_before = _hash_sections(inst_ini)

    store_dir = ini.parent if ini else (search_dirs()[0] if search_dirs() else None)
    before_names = _store_profile_dirs(store_dir) if store_dir else set()
    home_before = set(os.listdir(Path.home())) if Path.home().is_dir() else set()
    cache_top = _missing_top(_cache_store())

    found_hash: str | None = None
    for _attempt in range(2):
        with tempfile.NamedTemporaryFile(suffix=".myfox-shot.png") as shot:
            try:
                subprocess.run(
                    [str(binary), "--headless", "--screenshot", shot.name, "about:blank"],
                    timeout=180, env=_headless_env(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except (subprocess.SubprocessError, OSError):
                break

        new_install = sorted(n[len("Install"):] for n in (_install_sections(ini) - ini_before))
        if new_install:
            found_hash = new_install[0]
            break
        new_hash = sorted(_hash_sections(inst_ini) - inst_before)
        if new_hash:
            found_hash = new_hash[0]
            break

    if store_dir:
        _purge_headless_strays(store_dir, ini, our_profile, before_names)
    _remove_first_run_dirs(home_before, cache_top)
    return found_hash


def _headless_env() -> dict[str, str]:
    """The environment without the display: headless Firefox needs none, and
    a foreign or broken one can still stop it (e.g. root with a user's
    XAUTHORITY: "running Firefox as root in a regular user's session")."""
    return {k: v for k, v in os.environ.items() if k not in ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY")}


def install_hash_fresh(install_dir: Path) -> str | None:
    """Fallback for headless_once: runs Firefox with a throwaway $HOME so
    whatever hash it computes lands in a profiles.ini we can just read, no
    diffing needed."""
    binary = install_dir / "firefox"
    if not os.access(binary, os.X_OK):
        return None
    with tempfile.TemporaryDirectory() as tmp_home:
        tmp = Path(tmp_home)
        shot = tmp / ".myfox-shot.png"
        env = _headless_env()
        env.update(HOME=str(tmp), XDG_CONFIG_HOME=str(tmp / ".config"), XDG_DATA_HOME=str(tmp / ".local" / "share"),
                   XDG_CACHE_HOME=str(tmp / ".cache"))
        try:
            subprocess.run(
                [str(binary), "--headless", "--screenshot", str(shot), "about:blank"],
                timeout=180, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except (subprocess.SubprocessError, OSError):
            return None
        for candidate in (tmp / ".mozilla" / "firefox" / "profiles.ini", tmp / ".config" / "mozilla" / "firefox" / "profiles.ini"):
            sections = _install_sections(candidate)
            if sections:
                return sorted(sections)[0][len("Install"):]
    return None


def pin_install(install_dir: Path, profile_abs: Path, saved_hash: str | None) -> str | None:
    """Ensures [Install<HASH>] (profiles.ini) and [<HASH>] (installs.ini)
    both point Default= at this profile. Returns the hash on success, None
    if pinning genuinely couldn't be determined (caller decides whether
    that's fatal)."""
    ini = find_ini()
    if not ini:
        return None

    if saved_hash and f"Install{saved_hash}" in _install_sections(ini):
        hash_ = saved_hash
    else:
        hash_ = headless_once(install_dir, profile_abs) or install_hash_fresh(install_dir)
        if not hash_:
            existing = _install_sections(ini)
            if len(existing) != 1:
                return None
            hash_ = next(iter(existing))[len("Install"):]

    existing_entry = _find_entry_for_dir(ini, profile_abs)
    profile_path = existing_entry.path if existing_entry else register_entry(ini, profile_abs)

    write_install_section(ini, f"Install{hash_}", profile_path)
    write_install_section(ini.parent / "installs.ini", hash_, profile_path)
    return hash_


def unpin_install(hash_: str) -> None:
    """The hash is our install's own, so its sections are ours wherever
    they are."""
    if not hash_:
        return
    for ini in _all_inis():
        if f"Install{hash_}" in _install_sections(ini):
            remove_ini_section(ini, f"Install{hash_}")
        installs_ini = ini.parent / "installs.ini"
        if hash_ in _hash_sections(installs_ini):
            remove_ini_section(installs_ini, hash_)
