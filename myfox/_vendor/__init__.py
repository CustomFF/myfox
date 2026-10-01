"""Vendored third-party source, committed to git instead of fetched from
PyPI at install time (see docs/python-rewrite-plan.md — no pip/venv in the
shipped product).

- picotui 1.2.1 (MIT, licenses/picotui.LICENSE) — terminal UI widgets
  (Dialog/WButton/WListBox/WTextEntry/...). No dependencies of its own, no
  python_requires floor (just a `sys.version_info < (3, 0)` guard), so no
  Python-floor conflict the way urwid+wcwidth+typing_extensions had
  (tried first — see git history on this branch: urwid alone pulled in
  wcwidth's ~2MB of Unicode tables plus typing_extensions as a genuine
  runtime dependency, and its own Filler/Pile layout model made a dialog
  that actually looked like a dialog — bordered, centered, contrasting
  from the terminal behind it — real work to build, not the default).
  Known rough edges worth remembering if picotui itself needs debugging:
  Widget.loop() treats a literal `True` return as "nothing happened yet,
  keep looping", not "finished" — use ACTION_OK/ACTION_CANCEL (plain ints)
  for finish_dialog, never True/False. dialog_box()'s title placement and
  box fill color are also not centered/contrasting by default — see
  ui/picotui_backend.py's BoxDialog for the override.

Unmodified upstream source (+ the LICENSE file, missing from the PyPI
sdist — fetched from the GitHub repo instead). picotui's own imports
expect to find it as a top-level package (`from picotui.widgets import
...`), not nested under `myfox._vendor` — so callers prepend this
directory to sys.path via ensure_on_path() instead of importing through
this package.
"""

from __future__ import annotations

import sys
from pathlib import Path

_DIR = str(Path(__file__).parent)


def ensure_on_path() -> None:
    if _DIR not in sys.path:
        sys.path.insert(0, _DIR)
