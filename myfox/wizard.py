"""First-install wizard: welcome -> dir -> channel -> lang -> profile ->
tweaks -> theme -> summary, with Back. Runs only from bootstrap.py's own
"not installed yet" branch (see docs/python-rewrite-plan.md: there's no
`install` subcommand) — wizard.run(ui) returns an Answers, or None if
cancelled.

An explicit stack of (page index, how we arrived) pairs — Back pops it,
Next pushes the next index — replaces bin/myfox-core's install_wizard, a
step-name string driven by tui_choose_kv/tui_confirm return codes 0/1/3
(next/cancel/back). Every page function takes the direction it was
entered from and returns where to go next; pages with no precondition
(most of them) just ignore it. This exists for the two pages that can be
skipped (profile, theme): skipping must continue in whichever direction
the wizard was already travelling, or hitting Back from the page right
after a skipped one would silently re-skip forward instead of actually
going back.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import firefox, i18n
from . import profiles as profiles_mod
from .ui import Backend

NEXT, BACK, CANCEL = "next", "back", "cancel"

_DEFAULT_INSTALL_DIR = str(Path.home() / ".local" / "share" / "firefox")


@dataclass
class Answers:
    install_dir: str = _DEFAULT_INSTALL_DIR
    channel: str = "stable"
    lang: str = "en-US"
    profile_dir: str | None = None  # None = create a new one
    tweaks: bool = True
    theme: str = "dark"


def _page_welcome(answers: Answers, ui: Backend, direction: str) -> str:
    # no_label=None: there's no distinct "no" here, just proceed or don't —
    # a second button alongside Continue would just restate Cancel.
    confirmed = ui.confirm(i18n.t("wizard_welcome"), default=True, yes_label=i18n.t("wizard_continue"), no_label=None)
    return NEXT if confirmed else CANCEL


def _page_dir(answers: Answers, ui: Backend, direction: str) -> str:
    while True:
        raw = ui.input_dir(i18n.t("wizard_dir_prompt"), answers.install_dir, next_label=i18n.t("wizard_next"))
        if raw is None:
            return BACK
        try:
            path = firefox.validate_install_dir(raw)
        except firefox.InstallDirError as exc:
            ui.message(i18n.t(exc.key, *exc.args_for_message))
            continue
        answers.install_dir = str(path)
        return NEXT


def _page_channel(answers: Answers, ui: Backend, direction: str) -> str:
    options = [("stable", i18n.t("wizard_channel_stable")), ("beta", i18n.t("wizard_channel_beta"))]
    value = ui.choose(i18n.t("wizard_channel_prompt"), options, default=answers.channel, next_label=i18n.t("wizard_next"))
    if value is None:
        return BACK
    answers.channel = value
    return NEXT


def _page_lang(answers: Answers, ui: Backend, direction: str) -> str:
    with ui.spin(i18n.t("wizard_lang_fetching")):
        try:
            catalog = firefox.fetch_lang_catalog()
        except OSError:
            catalog = {}
    if not catalog:
        ui.message(i18n.t("wizard_lang_fetch_failed"))
        answers.lang = "en-US"
        return NEXT

    options = sorted(((code, f"{name} ({code})") for code, name in catalog.items()), key=lambda pair: pair[1])
    value = ui.choose(
        i18n.t("wizard_lang_prompt"), options, default=firefox.pick_lang(catalog), next_label=i18n.t("wizard_next"),
    )
    if value is None:
        return BACK
    answers.lang = value
    return NEXT


def _page_profile(answers: Answers, ui: Backend, direction: str) -> str:
    existing = profiles_mod.list_myfox()
    if not existing:
        answers.profile_dir = None
        return direction  # nothing to ask — pass through, see module docstring

    options = [("", i18n.t("wizard_profile_new"))]
    options += [(str(path), name or path.name) for path, name in existing]
    value = ui.choose(i18n.t("wizard_profile_prompt"), options, default="", next_label=i18n.t("wizard_next"))
    if value is None:
        return BACK
    answers.profile_dir = value or None
    return NEXT


def _page_tweaks(answers: Answers, ui: Backend, direction: str) -> str:
    # toggle(), not confirm()'s yes/no or a two-item choose() list — a
    # single on/off setting is a checkbox, not a filterable search box and
    # scrollable listbox built for picking one of several named options
    # (a live review called this out directly after an earlier choose()-
    # based attempt). Same Back/Next/Cancel row as every other middle page.
    result = ui.toggle(i18n.t("wizard_tweaks_prompt"), default=answers.tweaks, next_label=i18n.t("wizard_next"))
    if result is None:
        return BACK
    answers.tweaks = result
    return NEXT


def _page_theme(answers: Answers, ui: Backend, direction: str) -> str:
    if not answers.tweaks:
        return direction  # nothing to ask — pass through, see module docstring

    options = [("dark", i18n.t("wizard_theme_dark")), ("light", i18n.t("wizard_theme_light"))]
    value = ui.choose(i18n.t("wizard_theme_prompt"), options, default=answers.theme, next_label=i18n.t("wizard_next"))
    if value is None:
        return BACK
    answers.theme = value
    return NEXT


def _page_summary(answers: Answers, ui: Backend, direction: str) -> str:
    lines = [
        i18n.t("wizard_summary_dir", answers.install_dir),
        i18n.t("wizard_summary_channel", answers.channel),
        i18n.t("wizard_summary_lang", answers.lang),
        i18n.t("wizard_summary_tweaks", i18n.t("wizard_yes") if answers.tweaks else i18n.t("wizard_no")),
    ]
    if answers.tweaks:
        lines.append(i18n.t("wizard_summary_theme", answers.theme))
    text = i18n.t("wizard_summary_title") + "\n\n" + "\n".join(lines)
    # show_back, not no_label: declining here means "let me change
    # something" — the same None-means-Back every other page uses, not a
    # second labeled-"Back" button sitting in the no_label slot (which put
    # it in a different position than every other page's actual Back
    # button — found live).
    confirmed = ui.confirm(text, default=True, yes_label=i18n.t("wizard_install"), no_label=None, show_back=True)
    return NEXT if confirmed else BACK


_PAGES: list[Callable[[Answers, Backend, str], str]] = [
    _page_welcome,
    _page_dir,
    _page_channel,
    _page_lang,
    _page_profile,
    _page_tweaks,
    _page_theme,
    _page_summary,
]


def run(ui: Backend) -> Answers | None:
    answers = Answers()
    stack = [0]
    direction = NEXT
    while stack:
        index = stack[-1]
        if index >= len(_PAGES):
            return answers
        outcome = _PAGES[index](answers, ui, direction)
        if outcome == CANCEL:
            return None
        direction = outcome
        if outcome == NEXT:
            stack.append(index + 1)
        else:
            stack.pop()
    return None
