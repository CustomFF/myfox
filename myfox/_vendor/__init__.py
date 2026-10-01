"""Vendored third-party source, committed to git instead of fetched from
PyPI at install time (see docs/python-rewrite-plan.md — no pip/venv in the
shipped product). Pinned to the last release of each that still supports
the project's Python 3.8 floor (confirmed live: their next releases all
require >=3.9):

- urwid 2.6.16 (LGPL-2.1, licenses/urwid.COPYING) — terminal UI toolkit.
- wcwidth 0.8.5 (MIT, licenses/wcwidth.LICENSE) — urwid's own dependency
  for East-Asian/combining-character column widths.
- typing_extensions 4.13.2 (PSF, licenses/typing_extensions.LICENSE) —
  urwid imports `Literal`/`Protocol`/etc. from it unconditionally at
  module level in several files, not just under TYPE_CHECKING, so this is
  a genuine runtime dependency, confirmed by import failing without it.

Unmodified upstream source. urwid's own imports expect to find these as
top-level packages (`import urwid`, `import wcwidth`), not nested under
`myfox._vendor` — so callers prepend this directory to sys.path via
ensure_on_path() instead of importing through this package.
"""

from __future__ import annotations

import sys
from pathlib import Path

_DIR = str(Path(__file__).parent)


def ensure_on_path() -> None:
    if _DIR not in sys.path:
        sys.path.insert(0, _DIR)
