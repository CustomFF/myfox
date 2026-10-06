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
import time
from dataclasses import dataclass, field
from typing import Callable

from . import i18n, version
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

    @property
    def label(self) -> str:
        return i18n.t(self.track.label_key)

    @property
    def has_update(self) -> bool:
        return self.latest is not None and self.latest != self.current

    def describe(self) -> str:
        """"151.2 → 151.3" when it changes, else just the version (forced)."""
        if self.has_update:
            return i18n.t("refresh_version_change", self.current or "—", self.latest)
        return self.current or self.latest or "—"


@dataclass
class RefreshPlan:
    tracks: list[TrackState] = field(default_factory=list)
    force: bool = False
    error: str | None = None  # the check itself failed

    @classmethod
    def check(cls, state: State, force: bool = False) -> RefreshPlan:
        tracks = []
        for track in TRACKS:
            try:
                latest = version.find_latest_tag(track.tag, repo=track.repo)
            except OSError as exc:
                return cls(force=force, error=i18n.t("refresh_check_failed", getattr(exc, "reason", exc)))
            tracks.append(TrackState(track, state.get(track.key), latest))
        return cls(tracks=tracks, force=force)

    @property
    def todo(self) -> list[TrackState]:
        """What gets updated: everything with --force, else only what's new."""
        return list(self.tracks) if self.force else [t for t in self.tracks if t.has_update]

    @property
    def needed(self) -> bool:
        return bool(self.todo)


Updater = Callable[[RefreshPlan, Progress], None]


def simulate_refresh(plan: RefreshPlan, progress: Progress) -> None:
    """Stand-in until the release formats exist (pass 5): walks the stages
    with the same messages, touches nothing."""
    stages = []
    for t in plan.todo:
        tag = t.latest or t.current or ""
        if t.track.key == "tweaks_version":
            stages += [(i18n.t("progress_refresh_tweaks_download", tag), 2.0),
                       (i18n.t("progress_refresh_tweaks_apply"), 1.0)]
        else:
            stages += [(i18n.t("progress_refresh_core_download", tag), 2.0),
                       (i18n.t("progress_refresh_core_replace"), 0.5)]
    total = sum(seconds for _message, seconds in stages) or 1.0
    done = 0.0
    for message, seconds in stages:
        steps = max(1, int(seconds * 20))
        for step in range(steps):
            progress(message, (done + seconds * step / steps) / total)
            time.sleep(seconds / steps)
        done += seconds
    progress(i18n.t("progress_refresh_done"), 1.0)


def run(state: State, gui: bool = False, noninteractive: bool = False, force: bool = False,
        update: Updater = simulate_refresh) -> int:
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
            from .ui import refresh_gui
        except ImportError as exc:
            print(i18n.t("err_gui_unavailable", exc), file=sys.stderr)
            return 1
        return 0 if refresh_gui.run(plan, update) else 1
    from .ui import _has_tty

    if _has_tty():
        from .ui import refresh_tui

        return 0 if refresh_tui.run(plan, update) else 1
    from .ui import refresh_plain

    return 0 if refresh_plain.run(plan, update) else 1
