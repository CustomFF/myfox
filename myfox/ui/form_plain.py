"""The install form without a tty: no questions — a question printed into a
pipe reaches nobody. With -y it installs with the defaults, otherwise it
shows them and the command that installs. All decisions live in
install_form.InstallForm.
"""

from __future__ import annotations

import sys

from .. import i18n
from ..install_form import INSTALL_COMMAND, Answers, Choice, InstallForm, Installer


def _label(choices: list[Choice], value: str) -> str:
    return next((c.label for c in choices if c.value == value), value)


def _summary(form: InstallForm) -> None:
    a = form.answers
    rows = [(i18n.t("form_dir"), a.install_dir), (i18n.t("form_channel"), _label(form.channels, a.channel))]
    if form.profiles:
        rows.append((i18n.t("form_profile"), _label(form.profiles, a.profile_dir or "")))
    rows.append((i18n.t("form_tweaks"), i18n.t("summary_yes" if a.tweaks else "summary_no")))
    if form.theme_applies:
        rows.append((i18n.t("form_theme"), _label(form.themes, a.theme)))
    lang = next((lang for lang in form.langs if lang.code == a.lang), None)
    rows.append((i18n.t("form_lang"), lang.label() if lang else a.lang))
    print(i18n.t("form_title"))
    for label, value in rows:
        print(f"  {label} {value}")


def printer():
    """Prints a line per stage, not per progress tick."""
    last = {"stage": None}

    def progress(message: str, fraction: float) -> None:
        stage = message.split("…")[0]
        if stage != last["stage"]:
            last["stage"] = stage
            print(message, flush=True)

    return progress


def run(form: InstallForm, install: Installer, noninteractive: bool = False) -> Answers | None:
    if form.error:
        print(form.error, file=sys.stderr)
        return None
    error = form.validate()
    if error:
        print(error, file=sys.stderr)
        return None
    if not noninteractive:
        _summary(form)
        sys.stdout.flush()  # the summary before the stderr line, even in a pipe
        print(i18n.t("needs_yes_install", INSTALL_COMMAND), file=sys.stderr)
        return None
    try:
        install(form.answers, printer())
    except Exception as exc:
        print(str(exc) or type(exc).__name__, file=sys.stderr)
        return None
    return form.answers
