"""The first-install form, independent of how it is drawn: the GUI and the
TUI show it as one window, the plain view prints it (it never asks). Runs
only from bootstrap.py's "not installed yet" branch — there is no `install`
subcommand.
"""

from __future__ import annotations

import signal
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

from . import addons, firefox, i18n, importer, launcher, paths, sources


def default_install_dir() -> str:
    """The browser lives with MyFox's own copy by default."""
    return str(launcher.share_dir() / "firefox")


# (message, overall fraction 0..1) — how an install reports progress.
Progress = Callable[[str, float], None]
Installer = Callable[["Answers", Progress], None]


class Cancelled(Exception):
    """Raised through running work once the user asked to stop it."""


class Cancel:
    """A stop request from the view. The work sees it the next time it
    reports progress, which it does at least once a second while waiting
    for the network."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def request(self) -> None:
        self._event.set()

    @property
    def requested(self) -> bool:
        return self._event.is_set()

    def checked(self, progress: Progress) -> Progress:
        def report(message: str, fraction: float) -> None:
            progress(message, fraction)
            if self.requested:
                raise Cancelled()
        return report


def settled(progress: Progress) -> Progress:
    """For work past the point where stopping would leave it halfway: a
    stop request no longer interrupts it."""
    def report(message: str, fraction: float) -> None:
        try:
            progress(message, fraction)
        except Cancelled:
            pass
    return report


@contextmanager
def signals_to(handler: Callable[[int], None]) -> Iterator[None]:
    """While running work, ^C, a kill or a closed terminal go to `handler`
    instead of ending the process halfway through. Main thread only."""
    caught = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
    previous = {sig: signal.signal(sig, lambda signum, _frame: handler(signum)) for sig in caught}
    try:
        yield
    finally:
        for sig, old in previous.items():
            signal.signal(sig, old)


@dataclass
class Answers:
    install_dir: str = field(default_factory=default_install_dir)
    channel: str = "stable"
    lang: str = "en-US"
    profile_dir: str | None = None  # None = create a new one; after the install, the one used
    import_from: str | None = None  # another Firefox's profile to copy into the new one
    sync: str = importer.SYNC_NONE  # with import_from: what happens to its sync account
    allow_downgrade: bool = False  # import_from was last run by a newer Firefox, go on anyway
    tweaks: bool = True
    theme: str = "dark"
    doh: bool = True  # off: the tweaks leave DNS over HTTPS alone (myfox.doh)
    firefox_command: bool = False  # `firefox` on the command line runs this one (command.py)
    # Filled by the install: things to tell the user in the terminal once
    # the form is closed (the TUI owns the terminal while it's open).
    notes: list[str] = field(default_factory=list)
    firefox_version: str = ""


# What a user runs to install without questions (no terminal to ask in).
INSTALL_COMMAND = "curl -fsSL https://raw.githubusercontent.com/CustomFF/myfox/master/get.sh | sh -s -- -y"


@dataclass(frozen=True)
class Choice:
    value: str
    label: str


# The profile field's values besides "" (new) and a MyFox profile's path.
IMPORT = "import:"  # + the path of the profile to import
OTHER = "other"     # pick a folder to import from


def import_choice(profile: sources.Profile, duplicate: bool = False) -> Choice:
    if profile.id == str(profile.path):  # a folder of its own, outside any store
        shown = paths.shown(profile.path)
    else:
        shown = profile.name + (f" ({profile.id})" if duplicate or profile.store else "")
    return Choice(IMPORT + str(profile.path), i18n.t("form_profile_import", shown))


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
    profiles: list[Choice]  # empty: nothing to choose but a new profile, nothing to ask
    answers: Answers = field(default_factory=Answers)
    # Set when Mozilla is unreachable: Firefox can't be downloaded either,
    # so the form shows it and refuses to install.
    error: str | None = None
    versions: dict[str, str] = field(default_factory=dict)  # channel -> the version it installs
    _downgrade_warned: tuple[str, str] | None = None

    @classmethod
    def load(cls) -> InstallForm:
        # Used in place: MyFox's own and those only our Firefox has opened
        # (or none has); every other Firefox's profile is only imported.
        found = sources.listing(Path(default_install_dir()))
        existing = [p for p in found if p.related and not p.store]
        others = [p for p in found if p not in existing]
        names = [p.name for p in existing]
        profiles = [Choice(str(p.path), p.name + (f" ({p.id})" if names.count(p.name) > 1 else ""))
                    for p in existing]
        names = [p.name for p in others]
        profiles += [import_choice(p, names.count(p.name) > 1) for p in others]
        profiles = [Choice("", i18n.t("wizard_profile_new"))] + profiles + [Choice(OTHER, i18n.t("form_profile_other"))]
        try:
            names = firefox.fetch_lang_names()
            versions = firefox.latest_versions()
        except OSError as exc:
            reason = getattr(exc, "reason", exc)
            return cls(langs=[], profiles=profiles, error=i18n.t("err_mozilla_unreachable", reason))
        langs = sorted((Lang(code, english, native) for code, (english, native) in names.items()),
                       key=lambda lang: lang.english)
        answers = Answers(lang=firefox.pick_lang({lang.code: lang.english for lang in langs}))
        return cls(langs=langs, profiles=profiles, answers=answers, versions=versions)

    @property
    def profile_value(self) -> str:
        """The profile field's value for the answers as they are."""
        a = self.answers
        return IMPORT + a.import_from if a.import_from else a.profile_dir or ""

    def pick_profile(self, value: str) -> None:
        """New (""), a MyFox profile's path, or IMPORT + a path. OTHER is
        for the view to turn into a folder (add_import)."""
        a = self.answers
        a.profile_dir = a.import_from = None
        a.allow_downgrade = False
        if value.startswith(IMPORT):
            a.import_from = value[len(IMPORT):]
            a.sync = importer.SYNC_NONE
        elif value and value != OTHER:
            a.profile_dir = value

    def add_import(self, folder: str) -> str:
        """A picked folder as a profile choice (once): its value. Raises
        sources.ProfileLookupError if it's no profile."""
        found = sources.resolve(str(Path(folder).expanduser()), sources.listing())
        choice = import_choice(found)
        if choice.value not in [c.value for c in self.profiles]:
            self.profiles.insert(len(self.profiles) - 1, choice)
        return choice.value

    @property
    def syncs(self) -> list[Choice]:
        return [Choice(mode, i18n.t(f"form_sync_{mode}")) for mode in importer.SYNC_MODES]

    @property
    def sync_applies(self) -> bool:
        """Importing a profile that has a sync account."""
        a = self.answers
        return bool(a.import_from) and importer.has_account(Path(a.import_from))

    @property
    def channels(self) -> list[Choice]:
        return [Choice("stable", i18n.t("wizard_channel_stable")), Choice("beta", i18n.t("wizard_channel_beta"))]

    @property
    def themes(self) -> list[Choice]:
        return [Choice("dark", i18n.t("wizard_theme_dark")), Choice("light", i18n.t("wizard_theme_light"))]

    @property
    def theme_applies(self) -> bool:
        return self.answers.tweaks

    @property
    def doh_applies(self) -> bool:
        return self.answers.tweaks

    def filter_langs(self, query: str) -> list[Lang]:
        return [lang for lang in self.langs if lang.matches(query)]

    def validate(self, asks: bool = True) -> str | None:
        """A message to show, or None — then answers.install_dir is normalized.
        Without `asks` (no form to press Install again in) a newer profile
        to import needs answers.allow_downgrade set beforehand."""
        if self.error:
            return self.error
        try:
            path = firefox.validate_install_dir(self.answers.install_dir)
        except firefox.InstallDirError as exc:
            return i18n.t(exc.key, *exc.args_for_message)
        self.answers.install_dir = str(path)
        return self._validate_import(asks)

    def _validate_import(self, asks: bool) -> str | None:
        a = self.answers
        if not a.import_from:
            return None
        source = Path(a.import_from)
        if not sources.is_profile(source):
            return i18n.t("err_not_a_profile", paths.shown(source))
        found = sources.resolve(str(source), sources.listing())
        if sources.in_use(found):
            return i18n.t("err_import_in_use", found.name)
        if not self.sync_applies:
            a.sync = importer.SYNC_NONE
        target = self.versions.get(a.channel)
        if a.allow_downgrade or not sources.is_downgrade(found.last_version, target):
            return None
        if not asks:
            return i18n.t("warn_import_downgrade_cli", found.last_version, target)
        # Asked once: the same Install again means "at my own risk".
        if self._downgrade_warned == (a.import_from, target):
            a.allow_downgrade = True
            return None
        self._downgrade_warned = (a.import_from, target)
        return i18n.t("warn_import_downgrade", found.last_version, target)


def summary(answers: Answers) -> list[str]:
    """What got installed, printed once the form is closed."""
    rows = [(i18n.t("summary_firefox"), answers.firefox_version)] if answers.firefox_version else []
    rows += [
        (i18n.t("form_dir"), answers.install_dir),
        (i18n.t("form_profile"), answers.profile_dir or i18n.t("wizard_profile_new")),
    ]
    if answers.import_from:
        rows.append((i18n.t("summary_imported"), answers.import_from))
        rows.append((i18n.t("form_sync"), i18n.t(f"form_sync_{answers.sync}")))
    rows += [
        (i18n.t("form_channel"), i18n.t(f"wizard_channel_{answers.channel}")),
        (i18n.t("form_tweaks"), i18n.t("summary_yes" if answers.tweaks else "summary_no")),
    ]
    if answers.tweaks:
        rows.append((i18n.t("form_theme"), i18n.t(f"wizard_theme_{answers.theme}")))
        rows.append((i18n.t("form_doh"), i18n.t("summary_yes" if answers.doh else "summary_no")))
    rows.append((i18n.t("form_lang"), answers.lang))
    rows.append((i18n.t("form_command"), i18n.t("summary_yes" if answers.firefox_command else "summary_no")))
    width = max(len(label) for label, _value in rows)
    return [i18n.t("install_done"), *(f"  {label.ljust(width)} {value}" for label, value in rows), i18n.t("install_done_run")]


def simulate_install(answers: Answers, progress: Progress) -> None:
    """The real install's stages and messages without doing anything
    (`python3 -m myfox.wizard --dry-run`), to try the form safely."""
    stages = [("progress_firefox_download", 4.0), ("progress_firefox_install", 2.0), ("progress_profile", 1.0)]
    if answers.tweaks:
        stages += [
            ("progress_tweaks_download", 0.6),
            ("progress_tweaks_styles", 0.6),
            ("progress_tweaks_themes_download", 1.0),
            ("progress_tweaks_bookmarklets", 0.6),
        ]
        if addons.is_plasma_session():
            stages += [("progress_tweaks_plasma", 0.6)]
    stages += [("progress_gui", 0.6), ("progress_shortcut", 0.4)]
    if answers.firefox_command:
        stages += [("progress_command", 0.2)]
    total = sum(seconds for _key, seconds in stages)
    done = 0.0
    for key, seconds in stages:
        steps = max(1, int(seconds * 20))
        for step in range(steps):
            part = step / steps
            progress(i18n.t(key), (done + seconds * part) / total)
            time.sleep(seconds / steps)
        done += seconds
    progress(i18n.t("progress_done"), 1.0)
