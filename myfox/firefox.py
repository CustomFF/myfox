"""Firefox tarball download/extract, language/arch detection, .desktop entry.

Port of lib/firefox.sh. urllib.request instead of curl, tarfile instead of
tar/xz, json instead of an awk regex scraper for languages.json — none of
that changes the actual behaviour, it's genuinely simpler in Python. What
doesn't get simpler: install-dir validation rules and the .desktop/wrapper
quirks (MOZ_APP_LAUNCHER, WM_CLASS) are Firefox/freedesktop knowledge, not
bash-specific, and carry over almost line for line.
"""

from __future__ import annotations

import json
import os
import platform
import re
import tarfile
import tempfile
import urllib.error
import urllib.request
from configparser import ConfigParser
from pathlib import Path

from . import archive, net

LANGUAGES_URL = "https://product-details.mozilla.org/1.0/languages.json"


class InstallDirError(ValueError):
    """Raised by validate_install_dir with an i18n message key + args,
    the way the rest of this codebase reports user-facing problems."""

    def __init__(self, key: str, *args: object) -> None:
        super().__init__(key)
        self.key = key
        self.args_for_message = args


def detect_arch() -> str | None:
    """amd64 | arm64 | None (unsupported — 32-bit and exotic arches)."""
    machine = platform.machine()
    if machine in ("x86_64", "AMD64"):
        return "amd64"
    if machine in ("aarch64", "arm64"):
        return "arm64"
    return None


def _mozilla_arch(arch: str) -> str:
    return {"amd64": "linux64", "arm64": "linux-aarch64"}[arch]


def pick_lang(catalog: dict[str, str], env_lang: str | None = None) -> str:
    """Full locale (e.g. $LANG) -> Mozilla language code, matched against
    `catalog` (fetch_lang_catalog()'s result) — never a hardcoded guess.
    Mozilla renames/adds/drops regional codes over time (checked live: 40
    of them right now, e.g. 4 Spanish variants, 6 English ones) — a fixed
    table drifts out of sync with that; the catalog is the only thing that
    can't."""
    lang = env_lang if env_lang is not None else os.environ.get("LANG", "en_US.UTF-8")
    base = lang.split("@", 1)[0].split(".", 1)[0]  # strip @modifier, then encoding
    # POSIX locales are "language_REGION" (region already uppercase);
    # Mozilla's codes are "language-REGION" — same string, "_" for "-".
    # Try the specific region first ("es_AR" -> "es-AR"), then the bare
    # language ("es") — some languages have one, some don't.
    candidates = [base.replace("_", "-"), base.partition("_")[0]]
    lower_catalog = {code.lower(): code for code in catalog}
    for candidate in candidates:
        if candidate.lower() in lower_catalog:
            return lower_catalog[candidate.lower()]
    # No match at all, or a bare language ("zh", "pt", "no") that only
    # exists in region-specific flavors Mozilla doesn't otherwise
    # disambiguate for us — the honest fallback, not a guessed region.
    return "en-US"


def local_version(install_dir: Path) -> str | None:
    """Version=... from application.ini's [App] section — genuine INI,
    configparser reads it directly (the bash version's awk one-liner did
    the same job the hard way)."""
    ini = install_dir / "application.ini"
    if not ini.is_file():
        return None
    parser = ConfigParser()
    parser.read(ini, encoding="utf-8")
    return parser.get("App", "Version", fallback=None)


_INSTALL_MARKER_NAMES = (".myfox-installed", ".myfox-version")


def is_myfox_dir(path: Path) -> bool:
    return any((path / name).is_file() for name in _INSTALL_MARKER_NAMES)


def validate_install_dir(raw: str) -> Path:
    """Normalizes and validates a prospective install directory. Raises
    InstallDirError (never touches the filesystem beyond stat'ing) instead
    of the bash version's "print message, return 1" — the caller decides
    how to surface it (message() today, a dialog once wizard.py exists)."""
    p = raw.strip()
    if not p:
        raise InstallDirError("err_installdir_empty")
    if p in ("~", ) or p.startswith("~/"):
        p = str(Path.home()) + p[1:]
    if not p.startswith("/"):
        raise InstallDirError("err_installdir_relative", p)
    path = Path(p)
    # Path() already collapses a trailing slash; "/" itself needs its own check.
    if str(path) == "/":
        raise InstallDirError("err_installdir_root")

    if path.exists():
        if not path.is_dir():
            raise InstallDirError("err_installdir_not_dir", str(path))
        if not (os_access_w_x(path)):
            raise InstallDirError("err_installdir_not_writable", str(path))
        if any(path.iterdir()) and not is_myfox_dir(path):
            raise InstallDirError("err_installdir_foreign", str(path))
    else:
        parent = path
        while not parent.exists():
            parent = parent.parent
        if not parent.is_dir() or not os_access_w_x(parent):
            raise InstallDirError("err_installdir_cannot_create", str(parent))
    return path


def os_access_w_x(path: Path) -> bool:
    return os.access(path, os.W_OK | os.X_OK)


def dir_claim_state(path: Path) -> str:
    """ours | foreign | empty — same three states as firefox_dir_claim_state."""
    if (path / "application.ini").is_file() and is_myfox_dir(path):
        return "ours"
    if path.is_dir() and any(path.iterdir()):
        return "ours" if is_myfox_dir(path) else "foreign"
    return "empty"


def fetch_lang_names() -> dict[str, tuple[str, str]]:
    """code -> (English name, native name), straight from Mozilla's own
    JSON — no scraping. Native falls back to English if ever missing."""
    with urllib.request.urlopen(net.request(LANGUAGES_URL), timeout=30) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    return {code: (info["English"], info.get("native") or info["English"]) for code, info in raw.items()}


def fetch_lang_catalog() -> dict[str, str]:
    """code -> English name."""
    return {code: english for code, (english, _native) in fetch_lang_names().items()}


def validate_lang(code: str) -> bool:
    return code in fetch_lang_catalog()


def _download_url(arch: str, lang: str, channel: str) -> str:
    product = "firefox-beta-latest-ssl" if channel == "beta" else "firefox-latest-ssl"
    return f"https://download.mozilla.org/?product={product}&os={_mozilla_arch(arch)}&lang={lang}"


def resolve_download(arch: str, lang: str, channel: str) -> tuple[str, str]:
    """Follows the download.mozilla.org redirect without downloading the
    tarball — gives the real file URL and the version parsed out of it,
    the same trick the bash version used (curl -w '%{url_effective}')."""
    req = net.request(_download_url(arch, lang, channel), method="HEAD")
    with urllib.request.urlopen(req, timeout=30) as resp:
        effective_url = resp.geturl()
    if arch == "arm64":
        effective_url = effective_url.replace("linux-x86_64", "linux-aarch64")
    m = re.search(r"firefox-([^/]+)\.tar", effective_url)
    version = m.group(1) if m else "unknown"
    return effective_url, version


def download_and_extract(url: str, install_dir: Path, on_download=None, on_extract=None) -> None:
    """Streams the tarball to a temp file, then extracts it with
    --strip-components=1 semantics (Mozilla's tarball has one top-level
    "firefox/" directory). on_download(bytes_done, bytes_total or None) and
    on_extract(files_done, files_total) report progress if given."""
    install_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".tar.xz", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        try:
            with urllib.request.urlopen(net.request(url), timeout=60) as resp:
                total = int(resp.headers.get("Content-Length") or 0) or None
                written = 0
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    tmp.write(chunk)
                    written += len(chunk)
                    if on_download:
                        on_download(written, total)
            tmp.flush()
            with tarfile.open(tmp_path, mode="r:xz") as tf:
                members = tf.getmembers()
                top_dirs = {m.name.split("/", 1)[0] for m in members}
                if len(top_dirs) != 1:
                    raise RuntimeError(f"unexpected tarball layout: {top_dirs!r}")
                prefix = next(iter(top_dirs)) + "/"
                for i, member in enumerate(members, 1):
                    if member.name != prefix.rstrip("/"):
                        member.name = member.name[len(prefix):]
                        archive.extract(tf, member, install_dir)
                    if on_extract:
                        on_extract(i, len(members))
        finally:
            tmp_path.unlink(missing_ok=True)


def install_tarball(install_dir: Path, lang: str, channel: str, on_download=None, on_extract=None) -> str:
    """Downloads + extracts, returns the installed version. Raises on
    failure (unsupported arch, network error) — the caller decides what to
    tell the user."""
    arch = detect_arch()
    if arch is None:
        raise RuntimeError("unsupported_arch")
    url, version = resolve_download(arch, lang, channel)
    download_and_extract(url, install_dir, on_download=on_download, on_extract=on_extract)
    (install_dir / ".myfox-version").write_text(version + "\n", encoding="utf-8")
    return version
