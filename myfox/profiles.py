"""profiles.ini / installs.ini handling, headless install-hash pinning.

Port of lib/profile.sh. The profile store is *shared* with regular Firefox
(~/.mozilla/firefox or the XDG path Firefox 147+ uses) — every function here
touches only the sections it owns ([Install<HASH>], [ProfileN] Name=myfox),
never someone else's.

The headless-pinning dance (profile_headless_once / profile_install_hash_fresh)
is genuine domain logic, not bash-specific: Firefox computes its own
[Install<HASH>] itself with no public API for it, so the only way to learn
the hash is to actually run Firefox once and diff profiles.ini/installs.ini
before and after. That does not get simpler in another language.
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
_INSTALL_SECTION_RE = re.compile(r"^\[Install[0-9A-F]{1,16}\]$")
_HASH_SECTION_RE = re.compile(r"^\[[0-9A-F]{1,16}\]$")


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
    dirs = [native_dir()]
    flatpak = Path.home() / ".var" / "app" / "org.mozilla.firefox"
    if flatpak.is_dir():
        dirs.append(flatpak / ".mozilla" / "firefox")
    snap = Path.home() / "snap" / "firefox"
    if snap.is_dir():
        dirs.append(snap / "common" / ".mozilla" / "firefox")
    return dirs


def find_ini() -> Path | None:
    for d in search_dirs():
        candidate = d / "profiles.ini"
        if candidate.is_file():
            return candidate
    return None


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


def list_myfox() -> list[tuple[Path, str]]:
    """Our own profiles only: (path, name) pairs — [ProfileN] entries under
    a myfox-* directory, plus orphaned myfox-* directories carrying
    .myfox-created but no profiles.ini entry (kept that way by uninstall so
    a later reinstall can find them again)."""
    seen: set[Path] = set()
    result: list[tuple[Path, str]] = []

    ini = find_ini()
    if ini:
        ini_dir = ini.parent
        for entry in parse_profiles(ini):
            abs_path = resolve_dir(ini_dir, entry)
            if abs_path in seen:
                continue
            if abs_path.name.startswith("myfox-") and abs_path.is_dir():
                seen.add(abs_path)
                result.append((abs_path, entry.name))

    for base_dir in search_dirs():
        if not base_dir.is_dir():
            continue
        for d in sorted(base_dir.glob("myfox-*")):
            if not d.is_dir() or d in seen:
                continue
            if not (d / ".myfox-created").is_file():
                continue
            seen.add(d)
            result.append((d, ""))
    return result


# ─── Creating a new profile ──────────────────────────────────────────────

def _next_profile_section(cp: ConfigParser) -> str:
    nums = [int(m.group(1)) for s in cp.sections() if (m := re.match(r"^Profile(\d+)$", s))]
    return f"Profile{(max(nums, default=-1) + 1)}"


def create_new() -> Path:
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
    (profile_dir / ".myfox-created").write_text("", encoding="utf-8")

    cp = _read_ini(ini)
    section = _next_profile_section(cp)
    prefix = "\n" if ini.is_file() and ini.stat().st_size > 0 else ""
    with ini.open("a", encoding="utf-8") as f:
        f.write(f"{prefix}[{section}]\nName=myfox\nIsRelative=1\nPath={ppath}\n")

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


def remove_ini_section(ini: Path, section_name: str) -> None:
    text = ini.read_text(encoding="utf-8") if ini.is_file() else ""
    ini.write_text(_remove_section_text(text, section_name), encoding="utf-8")


def write_install_section(ini: Path, section_name: str, profile_path: str) -> None:
    """Replaces [section_name] wholesale with Default=<profile_path> /
    Locked=1 — used for both profiles.ini's [Install<HASH>] and
    installs.ini's [<HASH>], same shape."""
    text = ini.read_text(encoding="utf-8") if ini.is_file() else ""
    text = _remove_section_text(text, section_name)
    text += f"\n[{section_name}]\nDefault={profile_path}\nLocked=1\n"
    ini.write_text(text, encoding="utf-8")


# ─── Registering a profile directory as a [ProfileN] entry ──────────────

def _entry_path_for(ini: Path, target_dir: Path) -> str | None:
    ini_dir = ini.parent
    for entry in parse_profiles(ini):
        if resolve_dir(ini_dir, entry) == target_dir:
            return entry.path
    return None


def register_entry(ini: Path, profile_abs: Path) -> str:
    """Idempotent: reusing an existing [ProfileN] for this exact directory
    instead of piling up a duplicate on every repeated install/reinstall."""
    existing = _entry_path_for(ini, profile_abs)
    if existing is not None:
        return existing

    ini_dir = ini.parent
    try:
        path_value = str(profile_abs.relative_to(ini_dir))
        is_relative = "1"
    except ValueError:
        path_value = str(profile_abs)
        is_relative = "0"

    cp = _read_ini(ini)
    section = _next_profile_section(cp)
    prefix = "\n" if ini.is_file() and ini.stat().st_size > 0 else ""
    with ini.open("a", encoding="utf-8") as f:
        f.write(f"{prefix}[{section}]\nName=myfox\nIsRelative={is_relative}\nPath={path_value}\n")
    return path_value


def _section_for_dir(ini: Path, target_dir: Path) -> str | None:
    ini_dir = ini.parent
    for entry in parse_profiles(ini):
        if resolve_dir(ini_dir, entry) == target_dir:
            return entry.section
    return None


def remove_myfox_section(profile_dir: Path) -> None:
    """Scoped to this exact profile directory — never "any [ProfileN] named
    myfox", which would also rip out unrelated myfox installs elsewhere."""
    ini = find_ini()
    if not ini:
        return
    section = _section_for_dir(ini, profile_dir)
    if section:
        remove_ini_section(ini, section)


# ─── Headless pinning ────────────────────────────────────────────────────

def _install_sections(ini: Path | None) -> set[str]:
    if ini is None or not ini.is_file():
        return set()
    return {ln.strip() for ln in ini.read_text(encoding="utf-8").splitlines() if _INSTALL_SECTION_RE.match(ln.strip())}


def _hash_sections(ini: Path | None) -> set[str]:
    if ini is None or not ini.is_file():
        return set()
    return {ln.strip() for ln in ini.read_text(encoding="utf-8").splitlines() if _HASH_SECTION_RE.match(ln.strip())}


def _store_profile_dirs(store_dir: Path) -> set[str]:
    if not store_dir.is_dir():
        return set()
    return {d.name for d in store_dir.iterdir() if d.is_dir() and (d / "prefs.js").is_file()}


def _purge_headless_strays(store_dir: Path | None, ini: Path | None, our_dir: Path, before_names: set[str]) -> None:
    if store_dir is None or not store_dir.is_dir():
        return
    for name in _store_profile_dirs(store_dir):
        abs_path = store_dir / name
        if abs_path == our_dir or name in before_names:
            continue
        if ini is not None and ini.is_file():
            section = _section_for_dir(ini, abs_path)
            if section:
                remove_ini_section(ini, section)
        shutil.rmtree(abs_path, ignore_errors=True)


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

    found_token: str | None = None
    for _attempt in range(2):
        with tempfile.NamedTemporaryFile(suffix=".myfox-shot.png") as shot:
            try:
                subprocess.run(
                    [str(binary), "--headless", "--screenshot", shot.name, "about:blank"],
                    timeout=180, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except (subprocess.SubprocessError, OSError):
                break

        ini_after = _install_sections(ini)
        new_install = sorted(ini_after - ini_before)
        if new_install:
            found_token = new_install[0]
            break
        inst_after = _hash_sections(inst_ini)
        new_hash = sorted(inst_after - inst_before)
        if new_hash:
            found_token = new_hash[0]
            break

    if store_dir:
        _purge_headless_strays(store_dir, ini, our_profile, before_names)

    if not found_token:
        return None
    inner = found_token[1:-1]  # strip [ ]
    return inner[len("Install"):] if inner.startswith("Install") else inner


def install_hash_fresh(install_dir: Path) -> str | None:
    """Fallback for headless_once: runs Firefox with a throwaway $HOME so
    whatever hash it computes lands in a profiles.ini we can just read,
    no diffing needed — used when the real profile store already had
    exactly this [Install<HASH>] from some earlier run headless_once
    didn't catch (see profile_pin_install's adoption fallbacks)."""
    binary = install_dir / "firefox"
    if not os.access(binary, os.X_OK):
        return None
    with tempfile.TemporaryDirectory() as tmp_home:
        tmp = Path(tmp_home)
        shot = tmp / ".myfox-shot.png"
        env = dict(os.environ)
        env.update(HOME=str(tmp), XDG_CONFIG_HOME=str(tmp / ".config"), XDG_DATA_HOME=str(tmp / ".local" / "share"))
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
                inner = sorted(sections)[0][1:-1]
                return inner[len("Install"):]
    return None


def pin_install(install_dir: Path, profile_abs: Path, saved_hash: str | None) -> str | None:
    """Ensures [Install<HASH>] (profiles.ini) and [<HASH>] (installs.ini)
    both point Default= at this profile. Returns the hash on success, None
    if pinning genuinely couldn't be determined (caller decides whether
    that's fatal)."""
    ini = find_ini()
    if not ini:
        return None

    section: str | None = None
    if saved_hash and f"[Install{saved_hash}]" in _install_sections(ini):
        section = f"Install{saved_hash}"

    if not section:
        hash_ = headless_once(install_dir, profile_abs)
        if not hash_:
            hash_ = install_hash_fresh(install_dir)
            if not hash_:
                existing = _install_sections(ini)
                if len(existing) == 1:
                    hash_ = next(iter(existing))[len("[Install"):-1]
                else:
                    return None
        section = f"Install{hash_}"

    hash_out = section[len("Install"):]
    profile_path = _entry_path_for(ini, profile_abs) or register_entry(ini, profile_abs)

    write_install_section(ini, section, profile_path)
    installs_ini = ini.parent / "installs.ini"
    write_install_section(installs_ini, hash_out, profile_path)
    return hash_out


def unpin_install(hash_: str) -> None:
    if not hash_:
        return
    ini = find_ini()
    if not ini:
        return
    remove_ini_section(ini, f"Install{hash_}")
    installs_ini = ini.parent / "installs.ini"
    if installs_ini.is_file():
        remove_ini_section(installs_ini, hash_)
