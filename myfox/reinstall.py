"""`myfox reinstall`: the tweaks (the installed release) and Firefox (same
language and channel, or stable switched to beta) downloaded again, Firefox swapped in once complete,
then the wrapper, shortcut, profile pin and tweaks put back. The profile itself (bookmarks, history, settings) stays.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import tempfile
from pathlib import Path

from . import apply, changelog, desktop, firefox, i18n, launcher, paths, profiles, sources, tweaks
from . import task as task_mod
from .install_form import Progress, settled
from .installer import Stages, firefox_progress
from .state import State


def can_restart(state: State) -> bool:
    """Firefox can be asked to quit (and keep its session) by the tweaks."""
    return bool(state.get("tweaks", True)) and not changelog.is_newer(firefox.QUIT_SINCE_TWEAKS,
                                                                       state.get("tweaks_version"))


def build(state: State, beta: bool = False, restart: bool = False) -> task_mod.Task:
    install_dir = Path(state.get("install_dir"))
    channel = {"stable": "wizard_channel_stable", "beta": "wizard_channel_beta"}.get(state.get("channel", "stable"))
    # Only that way: back to stable would hand the profile to an older Firefox.
    to_beta = task_mod.Option(i18n.t("reinstall_to_beta"), beta) if state.get("channel", "stable") == "stable" else None
    again = task_mod.Option(i18n.t("reinstall_restart"), restart) if can_restart(state) else None
    command_line = "myfox reinstall -y" + (" --beta" if to_beta and beta else "") + (" --restart" if again and restart else "")

    def recheck() -> str | None:
        if not firefox.running_pids(install_dir) or (again and again.value):
            return None
        return i18n.t("err_firefox_running_restart" if again else "err_firefox_running")

    return task_mod.Task(
        title=i18n.t("reinstall_title"),
        subtitle=i18n.t("reinstall_subtitle_tweaks" if state.get("tweaks", True) else "reinstall_subtitle"),
        rows=[
            (i18n.t("row_firefox"), state.get("firefox_version") or "–"),
            (i18n.t("form_channel"), i18n.t(channel) if channel else state.get("channel")),
            (i18n.t("form_dir"), paths.shown(install_dir)),
        ],
        lines=[i18n.t("reinstall_keeps_profile")],
        options=[o for o in (to_beta, again) if o],
        action=i18n.t("reinstall_action"),
        unconfirmed=[i18n.t("needs_yes_reinstall", command_line)]
        + ([i18n.t("needs_yes_reinstall_beta", command_line + " --beta")] if to_beta and not beta else [])
        + ([i18n.t("needs_yes_reinstall_restart", command_line + " --restart")]
           if again and not restart and firefox.running_pids(install_dir) else []),
        run=lambda progress: run(state, progress, beta=bool(to_beta and to_beta.value),
                                 restart=bool(again and again.value)),
        cancellable=True,
        recheck=recheck,
    )


def run(state: State, progress: Progress, beta: bool = False, restart: bool = False) -> None:
    """restart: this install's Firefox, if running, is closed once the new
    one is downloaded and started again at the end."""
    install_dir = Path(state.get("install_dir"))
    profile_dir = state.get("profile_dir")
    with_tweaks = state.get("tweaks", True)
    weights = [("tweaks_download", 5 if with_tweaks else 0), ("download", 70), ("extract", 15), ("profile", 5),
               ("tweaks", 10 if with_tweaks else 0)]
    stages = Stages(progress, weights)

    if with_tweaks:
        # Replaced whole once downloaded: stopping later leaves the same release.
        stages.report("tweaks_download", i18n.t("progress_tweaks_download"))
        tag = state.get("tweaks_version")
        local = os.environ.get("MYFOX_TWEAKS_LOCAL") or tag in (None, tweaks.LOCAL_TAG)
        state.set("tweaks_version", tweaks.install(None if local else tweaks.release(tag)))

    # Into a sibling first: a failed or stopped download leaves the current
    # Firefox alone.
    with contextlib.ExitStack() as running:
        new = Path(tempfile.mkdtemp(dir=install_dir.parent, prefix=f".{install_dir.name}-new-"))
        try:
            channel = "beta" if beta else state.get("channel", "stable")
            version = firefox.install_tarball(new, state.get("lang", "en-US"), channel, **firefox_progress(stages))
            # Swapped in: from here on, stopping would leave it half set up.
            stages = Stages(settled(progress), weights)
            if restart:
                # Only now: Firefox stays open through the long download.
                waiting = i18n.t("progress_firefox_quit")
                stages.report("profile", waiting)
                running.enter_context(firefox.closed(install_dir, lambda: stages.report("profile", waiting),
                                                     lambda: {state.get("profile_dir")}))
            old = Path(tempfile.mkdtemp(dir=install_dir.parent, prefix=f".{install_dir.name}-old-")) / "firefox"
            install_dir.rename(old)
            new.rename(install_dir)
            shutil.rmtree(old.parent, ignore_errors=True)
        finally:
            shutil.rmtree(new, ignore_errors=True)
        (install_dir / ".myfox-installed").touch()
        desktop.write_entry(install_dir, launcher.launcher_path())

        if profile_dir and with_tweaks:
            stages.report("profile", i18n.t("progress_profile"))
            pinned = profiles.pin_install(install_dir, Path(profile_dir), saved_hash=state.get("install_hash"))
            if pinned:
                state.set("install_hash", pinned)
            stages.report("tweaks", i18n.t("progress_refresh_tweaks_apply"))
            apply.reapply_tweaks(install_dir, sources.myfox_dirs(state), state)

        state.set("firefox_version", version)
        state.set("channel", channel)
        state.save()
    settled(progress)(i18n.t("reinstall_done", version), 1.0)
