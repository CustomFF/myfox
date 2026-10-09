"""`myfox refresh`: updates what MyFox ships besides the browser, each from
its own releases — the tweaks (look and config) and the themes (both from
CustomFF/tweaks) and MyFox's own logic (core, CustomFF/myfox). The browser
updates itself; forcing it is `myfox reinstall`.

The check comes first. Nothing new (and no --force): no dialog, just one
line in a terminal or a desktop notification for --gui. Otherwise a dialog
lists what will be updated — unless -y, which updates without asking.
--force downloads everything again.

Like install_form, this holds the logic; the dialog is a task.Task, shown
by ui/task_{gui,tui,plain}.py.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import addons, apply, changelog, core, desktop, firefox, i18n, launcher, tweaks
from . import task as task_mod
from .install_form import Progress
from .state import State


@dataclass(frozen=True)
class Track:
    key: str                                  # state key holding the installed version
    label_key: str                            # i18n key of its row label
    latest: Callable[[], object]              # its newest release (has .tag), None; OSError
    display: Callable[[str | None], str] = changelog.display


# Applied in this order; core last, its new code runs from the next start.
TRACKS = (
    Track("tweaks_version", "refresh_track_tweaks", lambda: tweaks.latest_release()),
    Track("themes_version", "refresh_track_themes", lambda: addons.latest_themes_release(), addons.themes_display),
    Track("core_version", "refresh_track_core", lambda: core.latest_release()),
)


@dataclass
class TrackState:
    track: Track
    current: str | None
    latest: str | None
    release: tweaks.Release | core.Release | None = None
    changes: list[str] = field(default_factory=list)  # what's new, from the changelog

    @property
    def label(self) -> str:
        return i18n.t(self.track.label_key)

    @property
    def has_update(self) -> bool:
        """Only to a newer version (numbers, not tag text)."""
        return changelog.is_newer(self.latest, self.current)

    def describe(self) -> str:
        """"1.0.0 → 1.1.0" when it changes, else just the version (forced)."""
        show = self.track.display
        if self.has_update:
            return i18n.t("refresh_version_change", show(self.current), show(self.latest))
        return show(self.current or self.latest)


@dataclass
class RefreshPlan:
    tracks: list[TrackState] = field(default_factory=list)
    force: bool = False
    error: str | None = None  # the check itself failed

    @classmethod
    def check(cls, state: State, force: bool = False) -> RefreshPlan:
        tracks = []
        for track in TRACKS:
            # The themes come with the tweaks, into the profile.
            if track.key == "themes_version" and not (state.get("tweaks", True) and state.get("profile_dir")):
                continue
            release = None
            try:
                release = track.latest()
                latest = release.tag if release else None
            except OSError as exc:
                return cls(force=force, error=i18n.t("refresh_check_failed", getattr(exc, "reason", exc)))
            t = TrackState(track, state.get(track.key), latest, release)
            if t.has_update and getattr(release, "changelog_url", None):
                try:
                    t.changes = changelog.changes_since(release.changelog_url, t.current)
                except OSError:
                    pass  # no "what's new" is no reason not to update
            tracks.append(t)
        return cls(tracks=tracks, force=force)

    @property
    def changes(self) -> list[str]:
        return [line for t in self.todo for line in t.changes]

    @property
    def todo(self) -> list[TrackState]:
        """What gets updated: with --force every track that has a release to
        download, else only what's new."""
        if self.force:
            return [t for t in self.tracks if t.release is not None]
        return [t for t in self.tracks if t.has_update]

    @property
    def needed(self) -> bool:
        return bool(self.todo)


Updater = Callable[[RefreshPlan, Progress], None]

# The first tweaks release whose autoconfig handles --myfox-restart.
RESTART_SINCE_TWEAKS = "158.1"


def restart_offer(plan: RefreshPlan, state: State) -> Callable[[], None] | None:
    """New tweaks and themes take effect when Firefox starts: if this install's
    Firefox is running with tweaks that can restart it, how to do that."""
    install_dir = state.get("install_dir")
    if not install_dir or not any(t.track.key in ("tweaks_version", "themes_version") for t in plan.todo):
        return None
    running = state.get("tweaks_version")
    if changelog.is_newer(RESTART_SINCE_TWEAKS, running) or not firefox.running_pids(Path(install_dir)):
        return None
    return lambda: firefox.request_restart(Path(install_dir))


def apply_updates(plan: RefreshPlan, progress: Progress) -> None:
    """Tweaks: download, apply to the install and the profile, record the
    version. Themes: both into the profile. Core last (TRACKS order):
    replace the installed package, which takes effect on the next start."""
    state = State()
    install_dir, profile_dir = state.get("install_dir"), state.get("profile_dir")
    todo = plan.todo
    for i, t in enumerate(todo):
        base, share = i / len(todo), 1 / len(todo)
        tag = t.track.display(t.latest or t.current)
        if t.track.key == "themes_version":
            progress(i18n.t("progress_refresh_themes_download", tag), base)
            # Forced: downloaded again even if it's the recorded release.
            installed, _missing = addons.fetch_themes(Path(profile_dir), tag=t.release.tag,
                                                      current=None if plan.force else state.get("themes_version"))
            state.set("themes_version", installed)
            state.save()
        elif t.track.key == "tweaks_version":
            progress(i18n.t("progress_refresh_tweaks_download", tag), base)
            installed = tweaks.install(t.release)
            progress(i18n.t("progress_refresh_tweaks_apply"), base + share / 2)
            apply.reapply_tweaks(Path(install_dir), Path(profile_dir) if profile_dir else None, state)
            state.set("tweaks_version", installed)
            state.save()
        else:
            progress(i18n.t("progress_refresh_core_download", tag), base)
            installed = core.install(t.release)
            state.set("core_version", installed)
            state.save()
            # From the new core's templates: new menu actions arrive with it.
            sync_shortcut(state)
    progress(i18n.t("progress_refresh_done"), 1.0)


def sync_shortcut(state: State) -> None:
    """Rewrites the wrapper and the entry where they differ from what the
    installed MyFox would write; a failure is no reason to fail the run."""
    install_dir = state.get("install_dir")
    if install_dir and Path(install_dir).is_dir():
        try:
            desktop.write_entry(Path(install_dir), launcher.launcher_path())
        except OSError:
            pass


def to_task(plan: RefreshPlan, update: Updater, restart: Callable[[], None] | None = None) -> task_mod.Task:
    options = [task_mod.Option(i18n.t("refresh_restart_firefox"), True)] if restart else []

    def run(progress: Progress) -> None:
        update(plan, progress)
        if restart and options[0].value:
            restart()

    return task_mod.Task(
        title=i18n.t("refresh_title"),
        subtitle=i18n.t("refresh_subtitle_force" if plan.force else "refresh_subtitle"),
        rows=[(t.label, t.describe()) for t in plan.todo],
        heading=i18n.t("refresh_whats_new") if plan.changes else "",
        lines=plan.changes,
        options=options,
        action=i18n.t("refresh_update"),
        unconfirmed=[i18n.t("needs_yes_refresh", "myfox refresh --force -y" if plan.force else "myfox refresh -y")],
        run=run,
    )


def run(state: State, gui: bool = False, noninteractive: bool = False, force: bool = False,
        update: Updater = apply_updates) -> int:
    """Checks, then shows (or skips) the dialog the way the session allows.
    The shortcut is brought up to date first, whatever the check finds: an
    update done by an older MyFox didn't."""
    sync_shortcut(state)
    plan = RefreshPlan.check(state, force)
    if plan.error or not plan.needed:
        text = plan.error or i18n.t("refresh_none")
        if gui:
            from .ui import notify

            if notify.send(i18n.t("refresh_title"), text):
                return 1 if plan.error else 0
        print(text, file=sys.stderr if plan.error else sys.stdout)
        return 1 if plan.error else 0
    task = to_task(plan, update, restart_offer(plan, state))
    return 0 if task_mod.show(task, gui=gui, noninteractive=noninteractive) else 1
