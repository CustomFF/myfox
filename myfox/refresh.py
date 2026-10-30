"""`myfox refresh`: updates what MyFox ships besides the browser, each from
its own releases — the tweaks (look and config) and the themes (both from
CustomFF/myfox-tweaks), the bookmarklet styling (ddblm) and MyFox's own logic
(core, CustomFF/myfox). The browser updates itself; forcing it is
`myfox reinstall`.

The check comes first. Nothing new (and no --force): no dialog, just one
line in a terminal or a desktop notification for --gui. Otherwise a dialog
lists what will be updated — unless -y, which updates without asking.
--force downloads everything again.

Like install_form, this holds the logic; the dialog is a task.Task, shown
by ui/task_{gui,tui,plain}.py.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import addons, apply, changelog, completion, core, desktop, firefox, i18n, launcher, profile_commands, sources, tweaks
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
    Track("ddblm_version", "refresh_track_bookmarklets", lambda: apply.latest_ddblm_release(), apply.ddblm_display),
    Track("core_version", "refresh_track_core", lambda: core.latest_release()),
)


@dataclass
class TrackState:
    track: Track
    current: str | None
    latest: str | None
    release: object = None  # the track's release (tweaks.Release, core.Release, ...)
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
            # The themes and the bookmarklet styling come with the tweaks, into the profile.
            with_tweaks = state.get("tweaks", True) and sources.myfox_dirs(state)
            if track.key == "themes_version" and not with_tweaks:
                continue
            if track.key == "ddblm_version" and not (with_tweaks and state.get("opt_bl", True)):
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

# `myfox <this>`: what sync_from_new_core runs; not in the help, not for people.
SYNC_COMMAND = "_sync"

# The first tweaks release whose autoconfig handles --myfox-restart.
RESTART_SINCE_TWEAKS = "158.1"
# The first tweaks release with about:myfox, whose #changelog is the full one.
CHANGELOG_SINCE_TWEAKS = "159.3"
CHANGELOG_URL = "about:myfox#changelog"


def restart_offer(plan: RefreshPlan, state: State) -> Callable[[], None] | None:
    """Everything but the core takes effect when Firefox starts: if this
    install's Firefox is running with tweaks that can restart it, how to
    do that."""
    install_dir = state.get("install_dir")
    if not install_dir or not any(t.track.key != "core_version" for t in plan.todo):
        return None
    running = state.get("tweaks_version")
    if changelog.is_newer(RESTART_SINCE_TWEAKS, running) or not firefox.running_pids(Path(install_dir)):
        return None
    return lambda: firefox.request_restart(Path(install_dir))


def changelog_opener(state: State) -> Callable[[], None] | None:
    """How to show the full changelog: about:myfox in this install's
    Firefox, when the tweaks there (not the ones about to come) have it."""
    install_dir = state.get("install_dir")
    if not install_dir or not state.get("tweaks", True) or not state.get("profile_dir"):
        return None
    if changelog.is_newer(CHANGELOG_SINCE_TWEAKS, state.get("tweaks_version")):
        return None
    return lambda: firefox.open_url(Path(install_dir), CHANGELOG_URL)


def apply_updates(plan: RefreshPlan, progress: Progress) -> None:
    """Tweaks: download, apply to the install and the profile, record the
    version. Themes, bookmarklet styling: into the profile. Core last (TRACKS order):
    replace the installed package, which takes effect on the next start."""
    state = State()
    install_dir, profile_dirs = state.get("install_dir"), sources.myfox_dirs(state)
    todo = plan.todo
    for i, t in enumerate(todo):
        base, share = i / len(todo), 1 / len(todo)
        tag = t.track.display(t.latest or t.current)
        if t.track.key == "themes_version":
            progress(i18n.t("progress_refresh_themes_download", tag), base)
            # Forced: downloaded again even if it's the recorded release.
            current, installed = None if plan.force else state.get("themes_version"), state.get("themes_version")
            for profile_dir in profile_dirs:
                installed, _missing = addons.fetch_themes(profile_dir, tag=t.release.tag, current=current)
            state.set("themes_version", installed)
            state.save()
        elif t.track.key == "ddblm_version":
            progress(i18n.t("progress_refresh_bookmarklets_download", tag), base)
            current, installed = None if plan.force else state.get("ddblm_version"), state.get("ddblm_version")
            for profile_dir in profile_dirs:
                installed = apply.apply_bookmarklets(profile_dir, release=t.release, current=current)
            state.set("ddblm_version", installed)
            state.save()
        elif t.track.key == "tweaks_version":
            progress(i18n.t("progress_refresh_tweaks_download", tag), base)
            installed = tweaks.install(t.release)
            progress(i18n.t("progress_refresh_tweaks_apply"), base + share / 2)
            apply.reapply_tweaks(Path(install_dir), profile_dirs, state)
            state.set("tweaks_version", installed)
            state.save()
        else:
            progress(i18n.t("progress_refresh_core_download", tag), base)
            installed = core.install(t.release)
            state.set("core_version", installed)
            state.save()
            sync_from_new_core(state)
    forget_updates(state, [JSON_NAMES[t.track.key] for t in todo])
    progress(i18n.t("progress_refresh_done"), 1.0)


def sync_shortcut(state: State) -> None:
    """Rewrites the wrapper, the entry and the completion scripts where they
    differ from what the installed MyFox would write, and tidies the
    profile list while our Firefox is closed; a failure is no reason to
    fail the run."""
    install_dir = state.get("install_dir")
    if install_dir and Path(install_dir).is_dir():
        try:
            desktop.write_entry(Path(install_dir), launcher.launcher_path())
        except OSError:
            pass
        # Earlier ones stay recorded: zsh's may have moved, uninstall takes both.
        recorded = state.get("completions") or []
        known = sorted({str(p) for p in completion.install(recorded=recorded)} | set(recorded))
        if known != recorded:
            state.set("completions", known)
            state.save()
        try:
            profile_commands.tidy(state)
        except (OSError, sqlite3.Error):
            pass


def sync_from_new_core(state: State) -> None:
    """Right after the core is replaced, the shortcut, the wrapper and
    myfox.json are rewritten by the new core in its own process: this one
    still runs the old code, which knows only the old files and fields.
    If that can't run, the old code does what it can."""
    try:
        done = subprocess.run([str(launcher.launcher_path()), SYNC_COMMAND], stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60).returncode == 0
    except (OSError, subprocess.SubprocessError):
        done = False
    if not done:
        sync_shortcut(state)


def to_task(plan: RefreshPlan, update: Updater, restart: Callable[[], None] | None = None,
            more: Callable[[], None] | None = None) -> task_mod.Task:
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
        more=more,
        # Firefox restarting is what's left to see.
        closes=lambda: bool(options and options[0].value),
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
    task = to_task(plan, update, restart_offer(plan, state), changelog_opener(state))
    return 0 if task_mod.show(task, gui=gui, noninteractive=noninteractive) else 1


# What --json calls each track.
JSON_NAMES = {"tweaks_version": "tweaks", "themes_version": "themes", "ddblm_version": "bookmarklets",
              "core_version": "core"}


def run_json(state: State, force: bool = False, update: Updater = apply_updates) -> int:
    """`refresh --json`, for about:myfox: no questions, updates what's new
    (all with force), then one line on stdout: {"ok": true, "updated":
    [{"track", "from", "to"}], "restart": …} or {"error": …}. Firefox is
    left running: "restart" says it has to restart to take the update
    (everything but the core is read when it starts)."""
    try:
        sync_shortcut(state)
        plan = RefreshPlan.check(state, force)
        if plan.error:
            raise RuntimeError(plan.error)
        if plan.needed:
            update(plan, lambda message, fraction: None)
    except Exception as exc:  # a program asked: it gets JSON whatever happens
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1
    updated = [{"track": JSON_NAMES[t.track.key], "from": t.track.display(t.current) if t.current else None,
                "to": t.track.display(t.latest)} for t in plan.todo]
    restart = any(t.track.key != "core_version" for t in plan.todo)
    print(json.dumps({"ok": True, "updated": updated, "restart": restart}, ensure_ascii=False))
    return 0


# <install>/myfox-updates.json: the last check's findings, for about:myfox
# to show again without asking the network (and MyFox) every time.
UPDATES_FILE = "myfox-updates.json"


def _updates_file(state: State) -> Path | None:
    install_dir = state.get("install_dir")
    return Path(install_dir) / UPDATES_FILE if install_dir else None


def forget_updates(state: State, tracks: list[str]) -> None:
    """The tracks just updated leave the saved check: they're installed."""
    path = _updates_file(state)
    try:
        found = json.loads(path.read_text(encoding="utf-8")) if path else None
    except (OSError, ValueError):
        return
    if isinstance(found, dict) and isinstance(found.get("updates"), list):
        found["updates"] = [u for u in found["updates"] if u.get("track") not in tracks]
        try:
            path.write_text(json.dumps(found, ensure_ascii=False) + "\n", encoding="utf-8")
        except OSError:
            pass


def check(state: State, as_json: bool = False) -> int:
    """`refresh --check`: what an update would bring, installing nothing.
    Saved to myfox-updates.json too; --json prints the same one line:
    {"checked": "<UTC>", "updates": [{"track", "from", "to", "changes"}]}
    or {"error": …} (the saved check stays then)."""
    plan = RefreshPlan.check(state)
    if plan.error:
        if as_json:
            print(json.dumps({"error": plan.error}, ensure_ascii=False))
        else:
            print(plan.error, file=sys.stderr)
        return 1
    found = {
        "checked": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "updates": [{"track": JSON_NAMES[t.track.key], "from": t.track.display(t.current) if t.current else None,
                     "to": t.track.display(t.latest), "changes": t.changes} for t in plan.todo],
    }
    path = _updates_file(state)
    if path is not None and path.parent.is_dir():
        try:
            path.write_text(json.dumps(found, ensure_ascii=False) + "\n", encoding="utf-8")
        except OSError:
            pass
    if as_json:
        print(json.dumps(found, ensure_ascii=False))
    elif not plan.needed:
        print(i18n.t("refresh_none"))
    else:
        width = max(len(t.label) for t in plan.todo)
        for t in plan.todo:
            print(f"{t.label.ljust(width)}  {t.describe()}")
        if plan.changes:
            print()
            print(i18n.t("refresh_whats_new"))
            for line in plan.changes:
                print(f"  - {line}")
        print()
        print(i18n.t("refresh_check_install", "myfox refresh"))
    return 0
