"""Where things live relative to this installed copy of myfox/ — the
equivalent of lib/common.sh's MYFOX_ROOT and its derived paths.

autoconfig/chrome ship from the CustomFF/tweaks repo (see
docs/python-rewrite-plan.md) but land as siblings of myfox/ in the same
installed tree, exactly like today's ~/.local/share/myfox layout — refresh
updates each track independently, but apply.py etc. always find them next
to itself, never needing to know which track last touched them. Themes are
the exception: addons.py fetches their signed .xpi straight from
CustomFF/tweaks' releases into the profile, never landing under myfox_root()
at all.
"""

from __future__ import annotations

from pathlib import Path


def myfox_root() -> Path:
    return Path(__file__).resolve().parent.parent


def autoconfig_dir() -> Path:
    return myfox_root() / "autoconfig"


def chrome_dir() -> Path:
    return myfox_root() / "chrome"
