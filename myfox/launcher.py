"""The installed copy of MyFox itself: ~/.local/share/myfox holds the
package, tweaks/ (tweaks.py), dearpygui/ (gui_deps.py) and, by default,
the browser in firefox/; ~/.local/bin/myfox is a symlink to its launcher
script.

Windows: %LOCALAPPDATA%\\myfox, with python\\ (the embeddable Python get.ps1
put there) besides; the launcher is bin\\myfox.cmd, and bin\\ is on the
user's PATH instead of a link.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from . import paths


def share_dir() -> Path:
    return paths.share_dir()


def launcher_path() -> Path:
    return share_dir() / "bin" / ("myfox.cmd" if paths.WINDOWS else "myfox")


def python_dir() -> Path:
    """Windows: the Python MyFox runs on."""
    return share_dir() / "python"


def link_path() -> Path:
    return Path(os.environ.get("MYFOX_BIN_DIR") or Path.home() / ".local" / "bin") / "myfox"


def install_self() -> Path:
    """Copies this MyFox into share_dir() and links `myfox` into the bin
    dir. Returns the launcher path (what the .desktop action runs)."""
    share, source = share_dir(), paths.myfox_root()
    if source.resolve() != share.resolve():
        # Only the package: the browser and the tweaks live next to it.
        shutil.rmtree(share / "myfox", ignore_errors=True)
        shutil.copytree(source / "myfox", share / "myfox",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "tests"))

    launcher = launcher_path()
    launcher.parent.mkdir(parents=True, exist_ok=True)
    if paths.WINDOWS:
        return _install_cmd(launcher)
    launcher.write_text(
        "#!/bin/sh\n"
        f'PYTHONPATH="{share}${{PYTHONPATH:+:$PYTHONPATH}}" exec python3 -m myfox "$@"\n',
        encoding="utf-8",
    )
    launcher.chmod(0o755)

    link = link_path()
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(launcher)
    return launcher


def _install_cmd(launcher: Path) -> Path:
    # Relative to itself; the Python MyFox installed, or (a run from a
    # checkout) the one running this.
    python = python_dir() / "python.exe"
    exe = r'"%~dp0..\python\python.exe"' if python.is_file() else f'"{sys.executable}"'
    # Text mode makes the \n the \r\n cmd wants.
    launcher.write_text(
        "@echo off\n"
        'set "PYTHONPATH=%~dp0..;%PYTHONPATH%"\n'
        # UTF-8 mode: what goes into a pipe (--json) isn't the ANSI code page's.
        f"{exe} -X utf8 -m myfox %*\n",
        encoding="utf-8",
    )
    # For pythonw (no console window): the Start menu's GUI shortcuts.
    gui_launcher(launcher).write_text(
        "import os, runpy, sys\n"
        "# UTF-8 into pipes (about:myfox reads --json): the ANSI code page otherwise.\n"
        "for stream in (sys.stdout, sys.stderr):\n"
        "    if stream is not None:\n"
        '        stream.reconfigure(encoding="utf-8")\n'
        "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n"
        'runpy.run_module("myfox", run_name="__main__", alter_sys=True)\n',
        encoding="utf-8",
    )
    from . import winapi

    winapi.add_to_user_path(launcher.parent)
    return launcher


def gui_launcher(launcher: Path) -> Path:
    """Windows: the script pythonw runs MyFox from, beside myfox.cmd."""
    return launcher.parent / "myfoxw.pyw"


def remove_self() -> None:
    """Removes the link only if it points into our copy — a `myfox` that
    belongs to something else stays."""
    if paths.WINDOWS:
        from . import winapi

        winapi.remove_from_user_path(launcher_path().parent)
        # The Python this may run on can't go while it runs, nor myfox.cmd
        # while cmd still reads it: those two go once it has exited.
        share = share_dir()
        for item in share.iterdir() if share.is_dir() else ():
            if item.name not in (python_dir().name, launcher_path().parent.name):
                shutil.rmtree(item, ignore_errors=True) if item.is_dir() else item.unlink()
        if share.exists():
            _remove_after_exit(share)
        return
    link = link_path()
    if link.is_symlink() and Path(os.readlink(link)).resolve() == launcher_path().resolve():
        link.unlink()
    shutil.rmtree(share_dir(), ignore_errors=True)


def _remove_after_exit(path: Path) -> None:
    """What's left of MyFox goes once this process and the myfox.cmd that
    started it have exited, by a detached PowerShell."""
    import subprocess

    quoted = str(path).replace("'", "''")
    script = (f"Wait-Process -Id {os.getpid()},{os.getppid()} -ErrorAction SilentlyContinue; "
              f"foreach ($i in 1..30) {{ Remove-Item -LiteralPath '{quoted}' -Recurse -Force "
              f"-ErrorAction SilentlyContinue; if (-not (Test-Path -LiteralPath '{quoted}')) {{ break }}; "
              "Start-Sleep 1 }")
    subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                     cwd=os.environ.get("SYSTEMROOT", "C:\\"), stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     # Not DETACHED_PROCESS: without a console PowerShell quits at once.
                     creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
