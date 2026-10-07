"""The views: form_{gui,tui,plain}.py draw the install form,
task_{gui,tui,plain}.py the command dialogs; wizard.py and task.show() pick
one. picotui_base.py is what the terminal views share.
"""

from __future__ import annotations

import sys


def _has_tty() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()
