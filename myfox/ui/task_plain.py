"""The task dialog (task.Task) without a tty: what will happen, its
questions (none with -y), then a line per stage."""

from __future__ import annotations

import sys

from ..task import Task
from .form_plain import printer
from .plain_backend import PlainBackend


def run(task: Task, ask: bool = True) -> bool:
    print(task.title)
    for label, value in task.rows:
        print(f"  {label} {value}")
    if task.lines:
        if task.heading:
            print(task.heading)
        for line in task.lines:
            print(f"  - {line}")
    if task.blocked:
        print(task.blocked, file=sys.stderr)
        return False
    if ask:
        backend = PlainBackend()
        for option in task.options:
            option.value = backend.confirm(option.label, default=option.value)
        if not backend.confirm(task.confirm, default=not task.destructive):
            return False
    else:
        for option in task.options:
            print(f"  [{'x' if option.value else ' '}] {option.label}")
    try:
        task.run(printer())
    except Exception as exc:
        print(str(exc) or type(exc).__name__, file=sys.stderr)
        return False
    return True
