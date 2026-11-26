"""Firefox itself: the tarball (download, extract, version), language and
architecture detection, install-dir validation, running processes.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
from configparser import ConfigParser
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from . import archive, i18n, net

LANGUAGES_URL = "https://product-details.mozilla.org/1.0/languages.json"
VERSIONS_URL = "https://product-details.mozilla.org/1.0/firefox_versions.json"


class InstallDirError(ValueError):
    """Raised by validate_install_dir with an i18n message key + args,
    the way the rest of this codebase reports user-facing problems."""

    def __init__(self, key: str, *args: object) -> None:
        super().__init__(key)
        self.key = key
        self.args_for_message = args


def detect_arch() -> str | None:
    """amd64 | arm64 | None (unsupported – 32-bit and exotic arches)."""
    machine = platform.machine()
    if machine in ("x86_64", "AMD64"):
        return "amd64"
    if machine in ("aarch64", "arm64"):
        return "arm64"
    return None


def _mozilla_arch(arch: str) -> str:
    if os.name == "nt":
        return {"amd64": "win64", "arm64": "win64-aarch64"}[arch]
    return {"amd64": "linux64", "arm64": "linux64-aarch64"}[arch]


def pick_lang(catalog: dict[str, str], env_lang: str | None = None) -> str:
    """Full locale (e.g. $LANG) -> Mozilla language code, matched against
    `catalog` (fetch_lang_catalog()'s result) – never a hardcoded guess.
    Mozilla renames/adds/drops regional codes over time (checked live: 40
    of them right now, e.g. 4 Spanish variants, 6 English ones) – a fixed
    table drifts out of sync with that; the catalog is the only thing that
    can't."""
    if env_lang is not None:
        lang = env_lang
    elif os.name == "nt" and not os.environ.get("LANG"):
        lang = i18n.windows_language() or "en_US"
    else:
        lang = os.environ.get("LANG", "en_US.UTF-8")
    base = lang.split("@", 1)[0].split(".", 1)[0]  # strip @modifier, then encoding
    # POSIX locales are "language_REGION" (region already uppercase);
    # Mozilla's codes are "language-REGION" – same string, "_" for "-".
    # Try the specific region first ("es_AR" -> "es-AR"), then the bare
    # language ("es") – some languages have one, some don't.
    candidates = [base.replace("_", "-"), base.partition("_")[0]]
    lower_catalog = {code.lower(): code for code in catalog}
    for candidate in candidates:
        if candidate.lower() in lower_catalog:
            return lower_catalog[candidate.lower()]
    # No match at all, or a bare language ("zh", "pt", "no") that only
    # exists in region-specific flavors Mozilla doesn't otherwise
    # disambiguate for us – the honest fallback, not a guessed region.
    return "en-US"


def local_version(install_dir: Path) -> str | None:
    """Version=... from application.ini's [App] section."""
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
    """Normalizes and validates a prospective install directory; raises
    InstallDirError for the form to show. Only stats the filesystem."""
    p = raw.strip()
    if not p:
        raise InstallDirError("err_installdir_empty")
    if p in ("~", ) or p.startswith("~/") or p.startswith("~" + os.sep):
        p = str(Path.home()) + p[1:]
    path = Path(p)
    if not path.is_absolute():
        raise InstallDirError("err_installdir_relative", p)
    # "/" (or C:\), which Path() leaves as it is.
    if path == Path(path.anchor):
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
    """ours | foreign | empty – same three states as firefox_dir_claim_state."""
    if (path / "application.ini").is_file() and is_myfox_dir(path):
        return "ours"
    if path.is_dir() and any(path.iterdir()):
        return "ours" if is_myfox_dir(path) else "foreign"
    return "empty"


def fetch_lang_names() -> dict[str, tuple[str, str]]:
    """code -> (English name, native name), straight from Mozilla's own
    JSON – no scraping. Native falls back to English if ever missing."""
    with net.urlopen(net.request(LANGUAGES_URL)) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    return {code: (info["English"], info.get("native") or info["English"]) for code, info in raw.items()}


def latest_versions() -> dict[str, str]:
    """channel -> the version its tarball has now ("158.0.1", "159.0b5").
    Raises OSError when it can't be asked."""
    with net.urlopen(net.request(VERSIONS_URL)) as resp:
        try:
            raw = json.loads(resp.read().decode("utf-8"))
        except ValueError as exc:
            raise OSError(f"bad response from Mozilla: {exc}") from exc
    keys = {"stable": "LATEST_FIREFOX_VERSION", "beta": "LATEST_FIREFOX_DEVEL_VERSION"}
    return {channel: raw[key] for channel, key in keys.items() if raw.get(key)}


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
    tarball – gives the real file URL and the version parsed out of it."""
    req = net.request(_download_url(arch, lang, channel), method="HEAD")
    with net.urlopen(req) as resp:
        effective_url = resp.geturl()
    # .../firefox-158.0.tar.xz; Windows: .../releases/158.0/win64/ru/Firefox%20Setup%20158.0.exe
    m = re.search(r"firefox-([^/]+)\.tar", effective_url) or re.search(r"/releases/([^/]+)/", effective_url)
    version = m.group(1) if m else "unknown"
    return effective_url, version


def _extract_installer(installer: Path, install_dir: Path) -> None:
    """Windows: Mozilla has no archive there, only installers. The full one
    unpacks itself with /ExtractDir, no admin rights and nothing installed;
    its core folder is the Firefox."""
    with tempfile.TemporaryDirectory(dir=install_dir.parent, prefix=".firefox-unpack-") as tmp:
        subprocess.run([str(installer), f"/ExtractDir={tmp}"], check=True, timeout=600,
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        core = Path(tmp) / "core"
        if not (core / "firefox.exe").is_file():
            raise RuntimeError("unexpected installer layout: no core\\firefox.exe")
        for item in core.iterdir():
            target = install_dir / item.name
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
            item.replace(target)


def download_and_extract(url: str, install_dir: Path, on_download=None, on_extract=None, on_wait=None) -> None:
    """Streams the tarball to a temp file, then extracts it with
    --strip-components=1 semantics (Mozilla's tarball has one top-level
    "firefox/" directory). on_download(bytes_done, bytes_total or None),
    on_wait(seconds the network has been silent) and
    on_extract(archive_bytes_done, archive_bytes_total) report progress if
    given; any of them may raise to stop."""
    install_dir.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        with tempfile.TemporaryDirectory(prefix="myfox-") as tmp:
            installer = Path(tmp) / "firefox-setup.exe"
            with open(installer, "wb") as out:
                net.download(url, out, on_data=on_download, on_wait=on_wait)
            if on_extract:
                on_extract(0, 1)
            _extract_installer(installer, install_dir)
            if on_extract:
                on_extract(1, 1)
        return
    with tempfile.NamedTemporaryFile(suffix=".tar.xz", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        try:
            net.download(url, tmp, on_data=on_download, on_wait=on_wait)
            tmp.flush()
            # One streamed pass: listing the members first decompresses the
            # whole archive once more, a long pause with nothing to report.
            size = tmp_path.stat().st_size
            with open(tmp_path, "rb") as raw, tarfile.open(fileobj=raw, mode="r|xz") as tf:
                top = None
                for member in tf:
                    head, _, rest = member.name.partition("/")
                    if top is None:
                        top = head
                    elif head != top:
                        raise RuntimeError(f"unexpected tarball layout: {member.name!r}")
                    if rest:
                        member.name = rest
                        archive.extract(tf, member, install_dir)
                    if on_extract:
                        on_extract(raw.tell(), size)
        finally:
            tmp_path.unlink(missing_ok=True)


def running_pids(install_dir: Path) -> list[int]:
    """Processes running a binary from this install (Firefox and its
    helpers), found through /proc/<pid>/exe."""
    root = install_dir.resolve()
    if os.name == "nt":
        from . import winapi

        return [pid for pid, exe in winapi.processes() if root in exe.parents]
    pids = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            exe = Path(os.readlink(proc / "exe"))
        except OSError:
            continue
        if root in exe.parents:
            pids.append(int(proc.name))
    return pids


def executable(install_dir: Path) -> Path:
    """What starts this install's Firefox: its wrapper (see
    desktop.write_wrapper); on Windows firefox.exe itself, which needs none."""
    return install_dir / ("firefox.exe" if os.name == "nt" else "firefox-myfox")


def _launch(install_dir: Path, *args: str) -> None:
    """This install's Firefox through its wrapper: a running one gets the
    arguments by Firefox's remoting. Detached, so closing MyFox's window
    doesn't take it along."""
    detached = ({"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
                if os.name == "nt" else {"start_new_session": True})
    subprocess.Popen([str(executable(install_dir)), *args], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **detached)


def request_restart(install_dir: Path) -> None:
    """Asks this install's running Firefox to restart: the tweaks'
    command-line handler restarts it the way Firefox's own Restart does
    (prompts, session restored)."""
    _launch(install_dir, "--myfox-restart")


def open_url(install_dir: Path, url: str) -> None:
    """Opens `url` in this install's Firefox, starting it if needed."""
    _launch(install_dir, url)


# How long a quit may take: Firefox may first ask about unsaved forms or
# running downloads, and the user may say no.
QUIT_TIMEOUT = 60


def quit_and_wait(install_dir: Path, profile_dirs: list[Path] = (), on_wait=None,
                  timeout: float = QUIT_TIMEOUT) -> bool:
    """Asks this install's running Firefox to quit (the tweaks' handler
    keeps the session for the next start), one instance per profile in
    `profile_dirs` (Firefox runs one per profile and hands a command to
    the one with that profile), and waits for all of it to be gone. False
    if none was running. on_wait() comes about twice a second and may
    raise to stop waiting. Raises OSError if it is still up."""
    if not running_pids(install_dir):
        return False
    for profile_dir in profile_dirs or [None]:
        _launch(install_dir, *(["--profile", str(profile_dir)] if profile_dir else []), "--myfox-quit")
    deadline = time.monotonic() + timeout
    while running_pids(install_dir):
        if time.monotonic() > deadline:
            raise OSError(i18n.t("err_firefox_did_not_quit"))
        if on_wait:
            on_wait()
        time.sleep(0.5)
    return True


# The first tweaks release whose autoconfig handles --myfox-quit.
QUIT_SINCE_TWEAKS = "160.2"


@contextmanager
def closed(install_dir: Path, on_wait=None, defaults: Callable[[], set[str]] = set) -> Iterator[None]:
    """This install's Firefox closed for the work inside, and started again
    afterwards, also after a failure, if it was running. Every MyFox
    profile open now (each runs an instance of its own) comes back; the
    default one (`defaults()`, read at the end: the work may change it)
    in the usual way."""
    from . import sources

    open_dirs = [p.path for p in sources.listing(install_dir) if p.related and sources.in_use(p)]
    was_running = quit_and_wait(install_dir, open_dirs, on_wait)
    try:
        yield
    finally:
        if was_running:
            start(install_dir)
            for profile_dir in open_dirs:
                if str(profile_dir) not in defaults():
                    start(install_dir, profile_dir)


def start(install_dir: Path, profile_dir: Path | None = None) -> None:
    """This install's Firefox with its own profile, or `profile_dir` as an
    instance of its own beside it. Not --no-remote: such an instance takes
    no commands, so --myfox-quit couldn't close it later."""
    _launch(install_dir, *(["--profile", str(profile_dir)] if profile_dir else []))


def install_tarball(install_dir: Path, lang: str, channel: str, on_download=None, on_extract=None,
                    on_wait=None) -> str:
    """Downloads + extracts, returns the installed version. Raises on
    failure (unsupported arch, network error) – the caller decides what to
    tell the user."""
    arch = detect_arch()
    if arch is None:
        raise RuntimeError("unsupported_arch")
    url, version = resolve_download(arch, lang, channel)
    download_and_extract(url, install_dir, on_download=on_download, on_extract=on_extract, on_wait=on_wait)
    (install_dir / ".myfox-version").write_text(version + "\n", encoding="utf-8")
    return version
