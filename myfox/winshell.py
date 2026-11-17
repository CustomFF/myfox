"""Windows: what the .desktop entry is on Linux. A MyFox folder in the
Start menu with Firefox, "Update MyFox" and "Uninstall MyFox", and an entry
in the system's list of installed apps (Settings → Apps), both per user,
no admin rights needed. desktop.write_entry/remove_entry call here.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
from pathlib import Path

from . import i18n

UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\MyFox"


def start_menu_dir() -> Path:
    appdata = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    return appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "MyFox"


def _powershell(script: str) -> None:
    # Encoded: the names may be in any language, the console's code page not.
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded], check=True,
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60,
                   creationflags=subprocess.CREATE_NO_WINDOW)


def _shortcuts(install_dir: Path, launcher: Path, app_name: str) -> list[dict]:
    """With the GUI (dearpygui next to MyFox) its window, without a console;
    without it (Windows on ARM) the console's."""
    from . import launcher as launcher_mod

    firefox = str(install_dir / "firefox.exe")
    helper = install_dir / "uninstall" / "helper.exe"
    pythonw = launcher_mod.python_dir() / "pythonw.exe"
    script = launcher_mod.gui_launcher(launcher)
    gui = (launcher_mod.share_dir() / "dearpygui").is_dir() and pythonw.is_file() and script.is_file()

    def myfox(command: str) -> dict:
        if gui:
            return {"target": str(pythonw), "args": f'"{script}" {command} --gui'}
        return {"target": str(launcher), "args": command}

    return [
        {"name": app_name, "target": firefox, "args": "", "dir": str(install_dir), "icon": firefox},
        {"name": i18n.t("desktop_action_refresh"), **myfox("refresh"), "dir": str(launcher.parent), "icon": firefox},
        {"name": i18n.t("shortcut_uninstall"), **myfox("uninstall"), "dir": str(launcher.parent),
         "icon": str(helper) if helper.is_file() else firefox},
    ]


def write(install_dir: Path, launcher: Path, app_name: str, version: str) -> None:
    folder = start_menu_dir()
    # Rewritten whole: a shortcut named in another language before goes.
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True, exist_ok=True)
    shortcuts = _shortcuts(install_dir, launcher, app_name)
    items = json.dumps([{**s, "path": str(folder / f"{s['name']}.lnk")} for s in shortcuts])
    _powershell(
        "$shell = New-Object -ComObject WScript.Shell\n"
        f"foreach ($s in ('{_ps(items)}' | ConvertFrom-Json)) {{\n"
        "  $l = $shell.CreateShortcut($s.path)\n"
        "  $l.TargetPath = $s.target; $l.Arguments = $s.args; $l.WorkingDirectory = $s.dir\n"
        "  $l.IconLocation = $s.icon + ',0'; $l.Save()\n"
        "}\n")
    uninstall = shortcuts[-1]
    _write_uninstall_entry(install_dir, launcher, version, f'"{uninstall["target"]}" {uninstall["args"]}')


def _ps(text: str) -> str:
    """For a single-quoted PowerShell string."""
    return text.replace("'", "''")


def _write_uninstall_entry(install_dir: Path, launcher: Path, version: str, command: str) -> None:
    import winreg

    values = {
        "DisplayName": "MyFox", "DisplayVersion": version, "Publisher": "CustomFF",
        "DisplayIcon": str(install_dir / "firefox.exe"), "InstallLocation": str(launcher.parent.parent),
        "UninstallString": command, "URLInfoAbout": "https://github.com/CustomFF/myfox",
    }
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
        for name, value in values.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        for name in ("NoModify", "NoRepair"):
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, 1)


def remove() -> None:
    import winreg

    shutil.rmtree(start_menu_dir(), ignore_errors=True)
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except FileNotFoundError:
        pass
