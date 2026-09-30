"""Where things live relative to this installed copy of myfox/ — the
equivalent of lib/common.sh's MYFOX_ROOT and its derived paths.

autoconfig/chrome/assets/themes ship as a separate release track (see
docs/python-rewrite-plan.md) but land as siblings of myfox/ in the same
installed tree, exactly like today's ~/.local/share/myfox layout — refresh
updates each track independently, but apply.py etc. always find them next
to itself, never needing to know which track last touched them.
"""

from __future__ import annotations

from pathlib import Path


def myfox_root() -> Path:
    return Path(__file__).resolve().parent.parent


def autoconfig_dir() -> Path:
    return myfox_root() / "autoconfig"


def chrome_dir() -> Path:
    return myfox_root() / "chrome"


def themes_dir() -> Path:
    return myfox_root() / "assets" / "themes"
