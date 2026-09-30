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
import platform
import tarfile
import tempfile
import urllib.error
import urllib.request
from configparser import ConfigParser
from pathlib import Path

LANGUAGES_URL = "https://product-details.mozilla.org/1.0/languages.json"
_UA = "myfox"  # Mozilla's CDN doesn't care, but an empty/default UA is rude.


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


def detect_lang(env_lang: str | None = None) -> str:
    """Full locale (e.g. $LANG) -> Mozilla language code for the download
    URL. Faithful port of firefox_detect_lang's case table: most languages
    just drop the region, a handful (pt, zh, en, nb/no) keep it because
    Mozilla ships region-specific builds for those."""
    import os

    lang = env_lang if env_lang is not None else os.environ.get("LANG", "en_US.UTF-8")
    base = lang.split("@", 1)[0].split(".", 1)[0]  # strip @modifier, then encoding
    low = base.lower()

    if low.startswith("pt_br"):
        return "pt-BR"
    if low.startswith("pt"):
        return "pt-PT"
    if low == "zh" or low.startswith(("zh_cn", "zh_sg")):
        return "zh-CN"
    if low.startswith(("zh_tw", "zh_hk")):
        return "zh-TW"
    if low.startswith("en_gb"):
        return "en-GB"
    if low.startswith(("nb", "no")):
        return "nb-NO"
    if low.startswith("nn"):
        return "nn-NO"
    if low.startswith("hi"):
        return "hi-IN"
    if low.startswith("sv"):
        return "sv-SE"
    if low.startswith("es"):
        return "es-ES"

    simple = {
        "ru": "ru", "de": "de", "fr": "fr", "it": "it", "uk": "uk", "ja": "ja",
        "pl": "pl", "nl": "nl", "cs": "cs", "sk": "sk", "hu": "hu", "tr": "tr",
        "he": "he", "ar": "ar", "fi": "fi", "da": "da", "el": "el", "bg": "bg",
        "hr": "hr", "ro": "ro", "sl": "sl", "sr": "sr", "vi": "vi", "th": "th",
        "ko": "ko", "id": "id", "en": "en-US",
    }
    prefix = low.split("_", 1)[0]
    return simple.get(prefix, "en-US")


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
    import os
    return os.access(path, os.W_OK | os.X_OK)


def dir_claim_state(path: Path) -> str:
    """ours | foreign | empty — same three states as firefox_dir_claim_state."""
    if (path / "application.ini").is_file() and is_myfox_dir(path):
        return "ours"
    if path.is_dir() and any(path.iterdir()):
        return "ours" if is_myfox_dir(path) else "foreign"
    return "empty"


def fetch_lang_catalog() -> dict[str, str]:
    """code -> English name, straight from Mozilla's own JSON — no scraping."""
    with urllib.request.urlopen(
        urllib.request.Request(LANGUAGES_URL, headers={"User-Agent": _UA}), timeout=30
    ) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    return {code: info["English"] for code, info in raw.items()}


def validate_lang(code: str) -> bool:
    return code in fetch_lang_catalog()


def _download_url(arch: str, lang: str, channel: str) -> str:
    product = "firefox-beta-latest-ssl" if channel == "beta" else "firefox-latest-ssl"
    return f"https://download.mozilla.org/?product={product}&os={_mozilla_arch(arch)}&lang={lang}"


def resolve_download(arch: str, lang: str, channel: str) -> tuple[str, str]:
    """Follows the download.mozilla.org redirect without downloading the
    tarball — gives the real file URL and the version parsed out of it,
    the same trick the bash version used (curl -w '%{url_effective}')."""
    req = urllib.request.Request(_download_url(arch, lang, channel), headers={"User-Agent": _UA}, method="HEAD")
    with urllib.request.urlopen(req, timeout=30) as resp:
        effective_url = resp.geturl()
    if arch == "arm64":
        effective_url = effective_url.replace("linux-x86_64", "linux-aarch64")
    import re

    m = re.search(r"firefox-([^/]+)\.tar", effective_url)
    version = m.group(1) if m else "unknown"
    return effective_url, version


def download_and_extract(url: str, install_dir: Path, progress=None) -> None:
    """Streams the tarball to a temp file, then extracts it with
    --strip-components=1 semantics (Mozilla's tarball has one top-level
    "firefox/" directory). `progress`, if given, is called with the number
    of bytes written so far — a spinner doesn't need more than "still
    alive", same as the bash version's plain tui_spin."""
    install_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".tar.xz", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=60) as resp:
                written = 0
                while chunk := resp.read(1024 * 1024):
                    tmp.write(chunk)
                    written += len(chunk)
                    if progress:
                        progress(written)
            tmp.flush()
            with tarfile.open(tmp_path, mode="r:xz") as tf:
                members = tf.getmembers()
                top_dirs = {m.name.split("/", 1)[0] for m in members}
                if len(top_dirs) != 1:
                    raise RuntimeError(f"unexpected tarball layout: {top_dirs!r}")
                prefix = next(iter(top_dirs)) + "/"
                for member in members:
                    if member.name == prefix.rstrip("/"):
                        continue
                    member.name = member.name[len(prefix):]
                    tf.extract(member, install_dir)
        finally:
            tmp_path.unlink(missing_ok=True)


def install_tarball(install_dir: Path, lang: str, channel: str, progress=None) -> str:
    """Downloads + extracts, returns the installed version. Raises on
    failure (unsupported arch, network error) — the caller decides what to
    tell the user."""
    arch = detect_arch()
    if arch is None:
        raise RuntimeError("unsupported_arch")
    url, version = resolve_download(arch, lang, channel)
    download_and_extract(url, install_dir, progress=progress)
    (install_dir / ".myfox-version").write_text(version + "\n", encoding="utf-8")
    return version
