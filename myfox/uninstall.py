"""`myfox uninstall`: Firefox, the shortcut, the `myfox` command and MyFox's
own copy go. The profile (bookmarks, history, passwords) stays on disk, only
unregistered from Firefox's profile list — unless deleting it is asked for
(a checkbox, off by default; --remove-profile).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from . import desktop, firefox, i18n, launcher, paths, profiles
from . import task as task_mod
from .install_form import Progress
from .state import State


def build(state: State, remove_profile: bool = False) -> task_mod.Task:
    install_dir = Path(state.get("install_dir"))
    profile_dir = state.get("profile_dir")
    rows = [
        (i18n.t("row_firefox"), paths.shown(install_dir)),
        ("MyFox:", paths.shown(launcher.share_dir())),
    ]
    options = []
    if profile_dir:
        rows.append((i18n.t("form_profile"), paths.shown(profile_dir)))
        options.append(task_mod.Option(i18n.t("uninstall_remove_profile"), remove_profile))
    return task_mod.Task(
        title=i18n.t("uninstall_title"),
        subtitle=i18n.t("uninstall_subtitle"),
        rows=rows,
        options=options,
        action=i18n.t("uninstall_action"),
        unconfirmed=[i18n.t("needs_yes_uninstall", "myfox uninstall -y --remove-profile" if remove_profile
                            else "myfox uninstall -y")]
        + ([i18n.t("needs_yes_uninstall_profile", "myfox uninstall -y --remove-profile")]
           if profile_dir and not remove_profile else []),
        run=lambda progress: run(state, progress, remove_profile=bool(options) and options[0].value),
        destructive=True,
        blocked=i18n.t("err_firefox_running") if firefox.running_pids(install_dir) else None,
    )


def run(state: State, progress: Progress, remove_profile: bool = False) -> None:
    install_dir = Path(state.get("install_dir"))
    profile_dir = Path(state.get("profile_dir")) if state.get("profile_dir") else None
    progress(i18n.t("progress_uninstall_profile"), 0.1)
    if profile_dir:
        profiles.remove_myfox_section(profile_dir)
    if state.get("install_hash"):
        profiles.unpin_install(state.get("install_hash"))
    # Only a profile MyFox created itself (profiles.create_new marks it),
    # never one it was merely pointed at.
    removing_profile = remove_profile and profile_dir is not None and (profile_dir / ".myfox-created").is_file()
    if removing_profile:
        progress(i18n.t("progress_uninstall_profile_files"), 0.25)
        shutil.rmtree(profile_dir, ignore_errors=True)
    progress(i18n.t("progress_uninstall_firefox"), 0.4)
    shutil.rmtree(install_dir, ignore_errors=True)
    progress(i18n.t("progress_uninstall_myfox"), 0.8)
    desktop.remove_entry()
    launcher.remove_self()
    state.clear()
    state.delete_file()
    progress(i18n.t("uninstall_done_profile" if removing_profile else "uninstall_done"), 1.0)
