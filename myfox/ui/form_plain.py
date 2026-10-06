"""The install form without a tty: the same fields asked one by one with
input(), or none at all with -y (defaults). All decisions live in
install_form.InstallForm; this only asks.
"""

from __future__ import annotations

import sys

from .. import i18n
from ..install_form import Answers, Choice, InstallForm, Installer

_YES = ("y", "yes", "д", "да")


def _ask_choice(prompt: str, choices: list[Choice], current: str) -> str:
    print(prompt)
    for i, choice in enumerate(choices, 1):
        print(f"  {i}) {choice.label}{' *' if choice.value == current else ''}")
    raw = input(i18n.t("prompt_choice")).strip()
    if raw.isdigit() and 1 <= int(raw) <= len(choices):
        return choices[int(raw) - 1].value
    return current


def _ask_yes_no(prompt: str, current: bool) -> bool:
    marker = i18n.t("confirm_yes_no") if current else "[y/N]"
    raw = input(f"{prompt} {marker} ").strip().lower()
    return current if not raw else raw in _YES


def _ask_lang(form: InstallForm) -> None:
    a = form.answers
    by_code = {lang.code.lower(): lang for lang in form.langs}
    while True:
        raw = input(f"{i18n.t('wizard_lang_prompt')} [{by_code[a.lang.lower()].label()}]: ").strip()
        if not raw:
            return
        if raw.lower() in by_code:
            a.lang = by_code[raw.lower()].code
            return
        matches = form.filter_langs(raw)
        if not matches:
            print(i18n.t("form_lang_none"))
            continue
        if len(matches) == 1:
            a.lang = matches[0].code
            return
        a.lang = _ask_choice(i18n.t("wizard_lang_prompt"), [Choice(m.code, m.label()) for m in matches], a.lang)
        return


def _ask(form: InstallForm) -> None:
    a = form.answers
    default_dir = a.install_dir
    while True:
        raw = input(f"{i18n.t('wizard_dir_prompt')} [{default_dir}] ").strip()
        a.install_dir = raw or default_dir
        error = form.validate()
        if error is None:
            break
        print(error)
    a.channel = _ask_choice(i18n.t("wizard_channel_prompt"), form.channels, a.channel)
    if form.profiles:
        a.profile_dir = _ask_choice(i18n.t("wizard_profile_prompt"), form.profiles, a.profile_dir or "") or None
    a.tweaks = _ask_yes_no(i18n.t("wizard_tweaks_prompt"), a.tweaks)
    if form.theme_applies:
        a.theme = _ask_choice(i18n.t("wizard_theme_prompt"), form.themes, a.theme)
    _ask_lang(form)


def _printer():
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
    if not noninteractive:
        _ask(form)
    error = form.validate()
    if error:
        print(error, file=sys.stderr)
        return None
    try:
        install(form.answers, _printer())
    except Exception as exc:
        print(str(exc) or type(exc).__name__, file=sys.stderr)
        return None
    return form.answers
