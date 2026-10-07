"""`myfox refresh`: updates the two things MyFox ships besides the browser,
each from its own source — the tweaks (look and config, CustomFF/tweaks)
and MyFox's own logic (core, CustomFF/myfox). The browser updates itself;
forcing it is `myfox reinstall`.

The check comes first. Nothing new (and no --force): no dialog, just one
line in a terminal or a desktop notification for --gui. Otherwise a dialog
lists what will be updated — unless -y, which updates without asking.
--force downloads everything again.

Like install_form, this holds the logic; ui/refresh_{gui,tui,plain}.py
only show it.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import apply, changelog, core, gui_deps, i18n, tweaks, version
from .addons import TWEAKS_REPO
from .install_form import Progress
from .state import State


@dataclass(frozen=True)
class Track:
    key: str           # state key holding the installed version
    label_key: str     # i18n key of its row label
    repo: str
    tag: re.Pattern


TRACKS = (
    Track("tweaks_version", "refresh_track_tweaks", TWEAKS_REPO, version.TWEAKS_TAG_RE),
    Track("core_version", "refresh_track_core", version.GITHUB_REPO, version.CORE_TAG_RE),
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
        if self.has_update:
            return i18n.t("refresh_version_change", changelog.display(self.current), changelog.display(self.latest))
        return changelog.display(self.current or self.latest)


@dataclass
class RefreshPlan:
    tracks: list[TrackState] = field(default_factory=list)
    force: bool = False
    error: str | None = None  # the check itself failed

    @classmethod
    def check(cls, state: State, force: bool = False) -> RefreshPlan:
        tracks = []
        for track in TRACKS:
            release = None
            try:
                release = (tweaks if track.key == "tweaks_version" else core).latest_release()
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

    def changes_shown(self, limit: int) -> list[str]:
        """At most `limit` lines of what's new, the last one saying how many
        more there are when they don't fit."""
        changes = self.changes
        if len(changes) <= limit:
            return changes
        return changes[:limit - 1] + [i18n.t("refresh_more", len(changes) - limit + 1)]

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


def apply_updates(plan: RefreshPlan, progress: Progress) -> None:
    """Tweaks: download, apply to the install and the profile, record the
    version. Core last (TRACKS order): replace the installed package, which
    takes effect on the next start."""
    state = State()
    install_dir, profile_dir = state.get("install_dir"), state.get("profile_dir")
    todo = plan.todo
    for i, t in enumerate(todo):
        base, share = i / len(todo), 1 / len(todo)
        tag = t.latest or t.current or ""
        if t.track.key == "tweaks_version":
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
    progress(i18n.t("progress_refresh_done"), 1.0)


def run(state: State, gui: bool = False, noninteractive: bool = False, force: bool = False,
        update: Updater = apply_updates) -> int:
    """Checks, then shows (or skips) the dialog the way the session allows."""
    plan = RefreshPlan.check(state, force)
    if plan.error or not plan.needed:
        text = plan.error or i18n.t("refresh_none")
        if gui:
            from .ui import notify

            if notify.send(i18n.t("refresh_title"), text):
                return 1 if plan.error else 0
        print(text, file=sys.stderr if plan.error else sys.stdout)
        return 1 if plan.error else 0

    if noninteractive:
        from .ui import refresh_plain

        return 0 if refresh_plain.run(plan, update, ask=False) else 1
    if gui:
        try:
            gui_deps.prepare()
            from .ui import refresh_gui
        except (ImportError, OSError, RuntimeError) as exc:
            # Likely started from the menu: nobody would see a printed line.
            text = i18n.t("err_gui_unavailable", exc)
            from .ui import notify

            if not notify.send(i18n.t("refresh_title"), text):
                print(text, file=sys.stderr)
            return 1
        return 0 if refresh_gui.run(plan, update) else 1
    from .ui import _has_tty

    if _has_tty():
        from .ui import refresh_tui

        return 0 if refresh_tui.run(plan, update) else 1
    from .ui import refresh_plain

    return 0 if refresh_plain.run(plan, update) else 1
