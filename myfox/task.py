"""The confirm-then-run dialog behind refresh, reinstall and uninstall: what
is about to happen (rows, an optional list), one action button, progress,
then Close. A command builds a Task; ui/task_{gui,tui,plain}.py draw it and
show() picks one the way the install form does.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Callable

from . import gui_deps, i18n
from .install_form import Progress


@dataclass
class Option:
    """A checkbox under the rows; the task's run reads `value`."""
    label: str
    value: bool = False


@dataclass
class Task:
    title: str
    subtitle: str
    rows: list[tuple[str, str]]      # (label, value); a value may read "old → new"
    action: str                      # the button
    unconfirmed: list[str]           # what to run instead, when there's no terminal and no -y
    run: Callable[[Progress], None]
    heading: str = ""                # above `lines`, e.g. "What's new:"
    lines: list[str] = field(default_factory=list)
    options: list[Option] = field(default_factory=list)
    destructive: bool = False        # focus starts on Cancel
    blocked: str | None = None       # why the action can't run now; shown, button disabled

    def lines_shown(self, limit: int) -> list[str]:
        """At most `limit` lines, the last saying how many more there are."""
        if len(self.lines) <= limit:
            return list(self.lines)
        return self.lines[:limit - 1] + [i18n.t("refresh_more", len(self.lines) - limit + 1)]


def _notify_or_print(title: str, text: str) -> None:
    from .ui import notify

    if not notify.send(title, text):
        print(text, file=sys.stderr)


def show(task: Task, gui: bool = False, noninteractive: bool = False) -> bool:
    """True once the action ran through; False if cancelled, blocked or failed."""
    if noninteractive:
        if task.blocked:
            print(task.blocked, file=sys.stderr)
            return False
        from .ui import task_plain

        return task_plain.run(task, confirmed=True)

    from .ui import _has_tty

    if gui:
        try:
            gui_deps.prepare()
            from .ui import task_gui
        except (ImportError, OSError, RuntimeError) as exc:
            text = i18n.t("err_gui_unavailable", exc)
            if not _has_tty():
                # Started from the menu: a printed line would go nowhere.
                _notify_or_print(task.title, text)
                return False
            print(text, file=sys.stderr)
        else:
            return task_gui.run(task)
    if _has_tty():
        from .ui import task_tui

        return task_tui.run(task)
    from .ui import task_plain

    return task_plain.run(task, confirmed=False)
