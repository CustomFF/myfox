"""The installed copy of MyFox itself: ~/.local/share/myfox holds the
package plus autoconfig/ and chrome/ (what update/uninstall/refresh need
offline), and ~/.local/bin/myfox is a symlink to its launcher script.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from . import paths


def share_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "myfox"


def launcher_path() -> Path:
    return share_dir() / "bin" / "myfox"


def link_path() -> Path:
    return Path(os.environ.get("MYFOX_BIN_DIR") or Path.home() / ".local" / "bin") / "myfox"


def install_self() -> Path:
    """Copies this MyFox into share_dir() and links `myfox` into the bin
    dir. Returns the launcher path (what the .desktop action runs)."""
    share, source = share_dir(), paths.myfox_root()
    if source.resolve() != share.resolve():
        shutil.rmtree(share, ignore_errors=True)
        ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "tests")
        shutil.copytree(source / "myfox", share / "myfox", ignore=ignore)
        for name in ("autoconfig", "chrome"):
            shutil.copytree(source / name, share / name, ignore=ignore)

    launcher = launcher_path()
    launcher.parent.mkdir(parents=True, exist_ok=True)
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


def remove_self() -> None:
    """Removes the link only if it points into our copy — a `myfox` that
    belongs to something else stays."""
    link = link_path()
    if link.is_symlink() and Path(os.readlink(link)).resolve() == launcher_path().resolve():
        link.unlink()
    shutil.rmtree(share_dir(), ignore_errors=True)
