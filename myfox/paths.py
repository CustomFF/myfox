"""Where things live relative to this copy of myfox/.

The tweaks (autoconfig/ + chrome/) aren't part of MyFox: tweaks.py fetches
them from CustomFF/tweaks' releases into share_dir()/tweaks, and apply.py
copies them from there into the install and the profile. Themes come from
the same repo's releases straight into the profile (addons.py).
"""

from __future__ import annotations

import os
from pathlib import Path


def myfox_root() -> Path:
    return Path(__file__).resolve().parent.parent


def share_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "myfox"


def tweaks_dir() -> Path:
    return share_dir() / "tweaks"


def autoconfig_dir() -> Path:
    return tweaks_dir() / "autoconfig"


def chrome_dir() -> Path:
    return tweaks_dir() / "chrome"


def shown(path: str | Path) -> str:
    """A path for people to read: the home directory as ~."""
    home, p = str(Path.home()), str(path)
    return "~" + p[len(home):] if p == home or p.startswith(home + "/") else p
