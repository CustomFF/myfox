"""The task dialog (task.Task) without a tty: what will happen, then a line
per stage. It never asks — a question printed into a pipe reaches nobody —
so without -y it only says which command does it.
"""

from __future__ import annotations

import sys

from .. import i18n
from ..install_form import Cancelled
from ..task import Task
from .form_plain import _say, printer, run_stoppable


def run(task: Task, confirmed: bool) -> bool:
    if task.choices:
        return False  # a picker is never shown here: the commands print the list instead
    print(task.title)
    for label, value in task.rows:
        print(f"  {label} {value}")
    if task.lines:
        if task.heading:
            print(task.heading)
        for line in task.lines:
            print(f"  - {line}")
    for option in task.options:
        print(f"  [{'x' if option.value else ' '}] {option.label}")
    sys.stdout.flush()  # the summary before the stderr line below, even in a pipe
    if task.blocked:
        print(task.blocked, file=sys.stderr)
        return False
    if not confirmed:
        for line in task.unconfirmed:
            print(line, file=sys.stderr)
        return False
    try:
        if task.cancellable:
            run_stoppable(task.run)
        else:
            task.run(printer())
    except Cancelled:
        _say(i18n.t("task_cancelled"))
        return False
    except Exception as exc:
        print(str(exc) or type(exc).__name__, file=sys.stderr)
        return False
    return True
