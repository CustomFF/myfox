"""The first-install form, independent of how it is drawn: the GUI and the
TUI show it as one window, the plain frontend asks the same fields one by
one. Runs only from bootstrap.py's "not installed yet" branch — there is
no `install` subcommand (see docs/python-rewrite-plan.md).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import firefox, i18n
from . import profiles as profiles_mod

DEFAULT_INSTALL_DIR = str(Path.home() / ".local" / "share" / "firefox")

# (message, overall fraction 0..1) — how an install reports progress.
Progress = Callable[[str, float], None]
Installer = Callable[["Answers", Progress], None]


@dataclass
class Answers:
    install_dir: str = DEFAULT_INSTALL_DIR
    channel: str = "stable"
    lang: str = "en-US"
    profile_dir: str | None = None  # None = create a new one
    tweaks: bool = True
    theme: str = "dark"


@dataclass(frozen=True)
class Choice:
    value: str
    label: str


@dataclass(frozen=True)
class Lang:
    code: str
    english: str
    native: str

    def label(self, show_native: bool = True) -> str:
        if show_native and self.native != self.english:
            return f"{self.native} — {self.english} ({self.code})"
        return f"{self.english} ({self.code})"

    def matches(self, query: str) -> bool:
        query = query.strip().lower()
        return not query or query in f"{self.english} {self.native} {self.code}".lower()


@dataclass
class InstallForm:
    langs: list[Lang]
    profiles: list[Choice]  # empty: no existing MyFox profile, nothing to ask
    answers: Answers = field(default_factory=Answers)
    # Set when Mozilla is unreachable: Firefox can't be downloaded either,
    # so the form shows it and refuses to install.
    error: str | None = None

    @classmethod
    def load(cls) -> InstallForm:
        existing = profiles_mod.list_myfox()
        profiles = [Choice("", i18n.t("wizard_profile_new"))] if existing else []
        profiles += [Choice(str(path), name or path.name) for path, name in existing]
        try:
            names = firefox.fetch_lang_names()
        except OSError as exc:
            reason = getattr(exc, "reason", exc)
            return cls(langs=[], profiles=profiles, error=i18n.t("err_mozilla_unreachable", reason))
        langs = sorted((Lang(code, english, native) for code, (english, native) in names.items()),
                       key=lambda lang: lang.english)
        answers = Answers(lang=firefox.pick_lang({lang.code: lang.english for lang in langs}))
        return cls(langs=langs, profiles=profiles, answers=answers)

    @property
    def channels(self) -> list[Choice]:
        return [Choice("stable", i18n.t("wizard_channel_stable")), Choice("beta", i18n.t("wizard_channel_beta"))]

    @property
    def themes(self) -> list[Choice]:
        return [Choice("dark", i18n.t("wizard_theme_dark")), Choice("light", i18n.t("wizard_theme_light"))]

    @property
    def theme_applies(self) -> bool:
        return self.answers.tweaks

    def filter_langs(self, query: str) -> list[Lang]:
        return [lang for lang in self.langs if lang.matches(query)]

    def validate(self) -> str | None:
        """A message to show, or None — then answers.install_dir is normalized."""
        if self.error:
            return self.error
        try:
            path = firefox.validate_install_dir(self.answers.install_dir)
        except firefox.InstallDirError as exc:
            return i18n.t(exc.key, *exc.args_for_message)
        self.answers.install_dir = str(path)
        return None


def simulate_install(answers: Answers, progress: Progress) -> None:
    """Stand-in for the real install until bootstrap.py wires its steps
    (pass 5): walks the same stages with the same messages, touches nothing."""
    firefox_mb = 82
    stages = [("progress_firefox_download", 4.0), ("progress_firefox_install", 2.0)]
    if answers.tweaks:
        stages += [
            ("progress_tweaks_styles_download", 1.0),
            ("progress_tweaks_styles_unpack", 0.6),
            ("progress_tweaks_themes_download", 1.0),
            ("progress_tweaks_addons", 1.0),
        ]
    total = sum(seconds for _key, seconds in stages)
    done = 0.0
    for key, seconds in stages:
        steps = max(1, int(seconds * 20))
        for step in range(steps):
            part = step / steps
            if key == "progress_firefox_download":
                message = i18n.t(key, f"{firefox_mb * part:.1f}", firefox_mb)
            else:
                message = i18n.t(key)
            progress(message, (done + seconds * part) / total)
            time.sleep(seconds / steps)
        done += seconds
    progress(i18n.t("progress_done"), 1.0)
