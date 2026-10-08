"""The firefox-myfox wrapper and the .desktop entry (context-menu actions
include Restart and `myfox refresh --gui`), rendered from templates/ so a
core update brings its own versions of both.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from . import paths

DESKTOP_NAME = "firefox-myfox.desktop"
WRAPPER_NAME = "firefox-myfox"


def applications_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "applications"


def desktop_file() -> Path:
    return applications_dir() / DESKTOP_NAME


def _template(name: str) -> str:
    """templates/<name> of the installed MyFox when there is one: `myfox
    refresh` lays down a new core while the old code is still running, and
    the files it then writes should already be the new core's."""
    for base in (paths.share_dir() / "myfox", Path(__file__).resolve().parent):
        path = base / "templates" / name
        if path.is_file():
            return path.read_text(encoding="utf-8")
    raise FileNotFoundError(name)


def _render(name: str, **values: object) -> str:
    """@NAME@ placeholders: `$` is the shell's own in the wrapper."""
    text = _template(name)
    for key, value in values.items():
        text = text.replace(f"@{key.upper()}@", str(value))
    return text


def _write(path: Path, text: str) -> bool:
    """Writes only a change; True if it did."""
    try:
        if path.read_text(encoding="utf-8") == text:
            return False
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return True


def write_wrapper(install_dir: Path) -> Path:
    """<install>/firefox-myfox, what Exec= points at instead of the firefox
    binary or `env VAR=... firefox`:
    - the default-browser check matches the first Exec= token against
      Firefox's own path (nsGNOMEShellService KeyMatchesAppName);
      MOZ_APP_LAUNCHER makes Firefox treat this wrapper as itself;
    - MOZ_APP_REMOTINGNAME sets the GTK prgname, hence WM_CLASS/app_id, so
      this build doesn't group with a system Firefox in the task bar
      (must match the entry's StartupWMClass=).
    GTK_USE_PORTAL / MOZ_ENABLE_WAYLAND are deliberately not forced: the
    first breaks the default-browser check (mozilla bug 1516290), the
    second is auto-detected since Firefox 121."""
    wrapper = install_dir / WRAPPER_NAME
    _write(wrapper, _render(WRAPPER_NAME, wrapper=wrapper, firefox=install_dir / "firefox"))
    return wrapper


def _icon(install_dir: Path) -> str:
    for rel in ("browser/chrome/icons/default/default128.png", "chrome/icons/default/default128.png"):
        if (install_dir / rel).is_file():
            return str(install_dir / rel)
    return "firefox"


def write_entry(install_dir: Path, launcher: Path) -> Path:
    """The wrapper and the entry, from the templates. No --profile in Exec=:
    Firefox opens the Default= of its own [Install<HASH>] section (pinned by
    profiles.pin_install); a hard path would break a re-created profile.
    The Restart action's --myfox-restart is handled by the tweaks (158.1+):
    the running Firefox restarts itself, session restored; when it isn't
    running, it just starts."""
    wrapper = write_wrapper(install_dir)
    path = desktop_file()
    if _write(path, _render(DESKTOP_NAME, wrapper=wrapper, launcher=launcher, icon=_icon(install_dir))):
        _refresh_menu_cache()
    return path


def remove_entry() -> None:
    desktop_file().unlink(missing_ok=True)
    _refresh_menu_cache()


def _refresh_menu_cache() -> None:
    """Desktops pick up a new/removed entry faster when told; failing to
    tell them is harmless. The MIME cache and KDE's service cache are
    separate: both are refreshed, KDE's with whichever version exists."""
    kde = next((name for name in ("kbuildsycoca6", "kbuildsycoca5") if shutil.which(name)), None)
    for cmd in (["update-desktop-database", str(applications_dir())], [kde] if kde else None):
        if cmd and shutil.which(cmd[0]):
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
