"""The firefox-myfox wrapper and the .desktop entry, with a context-menu
action that opens `myfox refresh --gui`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

DESKTOP_NAME = "firefox-myfox.desktop"
TITLE = "Firefox (myfox)"
WM_CLASS = "firefox-myfox"


def applications_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "applications"


def desktop_file() -> Path:
    return applications_dir() / DESKTOP_NAME


def write_wrapper(install_dir: Path) -> Path:
    """<install>/firefox-myfox, what Exec= points at instead of the firefox
    binary or `env VAR=... firefox`:
    - the default-browser check matches the first Exec= token against
      Firefox's own path (nsGNOMEShellService KeyMatchesAppName);
      MOZ_APP_LAUNCHER makes Firefox treat this wrapper as itself;
    - MOZ_APP_REMOTINGNAME sets the GTK prgname, hence WM_CLASS/app_id, so
      this build doesn't group with a system Firefox in the task bar
      (must match StartupWMClass=).
    GTK_USE_PORTAL / MOZ_ENABLE_WAYLAND are deliberately not forced: the
    first breaks the default-browser check (mozilla bug 1516290), the
    second is auto-detected since Firefox 121."""
    wrapper = install_dir / "firefox-myfox"
    wrapper.write_text(
        "#!/bin/sh\n"
        f'export MOZ_APP_LAUNCHER="{wrapper}"\n'
        f'export MOZ_APP_REMOTINGNAME="{WM_CLASS}"\n'
        f'exec "{install_dir / "firefox"}" "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    return wrapper


def _icon(install_dir: Path) -> str:
    for rel in ("browser/chrome/icons/default/default128.png", "chrome/icons/default/default128.png"):
        if (install_dir / rel).is_file():
            return str(install_dir / rel)
    return "firefox"


def write_entry(install_dir: Path, launcher: Path) -> Path:
    """No --profile in Exec=: Firefox opens the Default= of its own
    [Install<HASH>] section (pinned by profiles.pin_install); a hard path
    would break a re-created profile."""
    wrapper = write_wrapper(install_dir)
    actions = [
        ("new-window", f"{wrapper} --new-window", "window-new-symbolic", "New Window", "Новое окно"),
        ("new-tab", f"{wrapper} --new-tab about:newtab", "tab-new-symbolic", "New Tab", "Новая вкладка"),
        ("new-private-window", f"{wrapper} --private-window", "view-private-symbolic",
         "New Private Window", "Новое приватное окно"),
        ("preferences", f"{wrapper} --preferences", "settings-configure-symbolic", "Preferences", "Настройки"),
        ("profile-manager", f"{wrapper} --ProfileManager", "user-group-properties-symbolic",
         "Profile Manager", "Менеджер профилей"),
        # Handled by the tweaks (158.1+): the running Firefox restarts itself,
        # session restored; when it isn't running, this just starts it.
        ("restart", f"{wrapper} --myfox-restart", "view-refresh-symbolic", "Restart", "Перезапустить"),
        ("myfox-refresh", f"{launcher} refresh --gui", "system-software-update", "Update MyFox", "Обновить MyFox"),
    ]
    lines = [
        "[Desktop Entry]",
        "Actions=" + "".join(f"{key};" for key, *_ in actions),
        "Categories=Network;WebBrowser;Browser",
        f"Comment={TITLE} Web Browser",
        "Encoding=UTF-8",
        f"Exec={wrapper} %u",
        f"GenericName={TITLE} Web Browser",
        f"Icon={_icon(install_dir)}",
        "MimeType=video/webm;text/html;image/png;image/jpeg;image/gif;application/xml;application/xhtml+xml;"
        "application/x-xpinstall;application/rss+xml;application/rdf+xml;application/pdf;application/xhtml_xml;"
        "image/webp;text/xml;x-scheme-handler/http;x-scheme-handler/https;",
        f"Name={TITLE}",
        f"Name[ru_RU]={TITLE}",
        "NoDisplay=false",
        "StartupNotify=true",
        f"StartupWMClass={WM_CLASS}",
        "Terminal=false",
        "Type=Application",
        "Version=1.0",
    ]
    for key, exec_, icon, name, name_ru in actions:
        lines += ["", f"[Desktop Action {key}]", f"Exec={exec_}", f"Icon={icon}", f"Name={name}", f"Name[ru_RU]={name_ru}"]

    path = desktop_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o755)
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
