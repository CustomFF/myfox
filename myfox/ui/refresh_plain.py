"""The refresh dialog without a tty: what will be updated, one question
(none with -y), then a line per stage."""

from __future__ import annotations

import sys

from .. import i18n
from ..refresh import RefreshPlan, Updater
from .form_plain import printer
from .plain_backend import PlainBackend


def run(plan: RefreshPlan, update: Updater, ask: bool = True) -> bool:
    print(i18n.t("refresh_title"))
    for t in plan.todo:
        print(f"  {t.label} {t.describe()}")
    if ask and not PlainBackend().confirm(i18n.t("refresh_confirm"), default=True):
        return False
    try:
        update(plan, printer())
    except Exception as exc:
        print(str(exc) or type(exc).__name__, file=sys.stderr)
        return False
    return True
