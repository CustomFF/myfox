"""`myfox uninstall`: Firefox, the shortcut, the `myfox` command and MyFox's
own copy go. The profile (bookmarks, history, passwords) stays on disk, only
unregistered from Firefox's profile list — unless deleting it is asked for
(a checkbox, off by default; --remove-profile). A profile imported with its
Firefox account moved along gets the account back (another checkbox, on by
default; --no-restore-sync), and the MyFox copy, if kept, is signed out.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from . import command, desktop, firefox, i18n, importer, launcher, paths, profiles, sources
from . import task as task_mod
from .install_form import Progress
from .state import State


def sync_source(state: State) -> sources.Profile | None:
    """The profile an import moved the account out of, while it can still
    take it back."""
    source = state.get("import_source")
    if state.get("import_sync") != importer.SYNC_MOVE or not source or not importer.can_restore_sync(Path(source)):
        return None
    try:
        return sources.resolve(source, sources.listing())
    except sources.ProfileLookupError:
        return None


def build(state: State, remove_profile: bool = False, restore_sync: bool = True) -> task_mod.Task:
    install_dir = Path(state.get("install_dir"))
    profile_dir = state.get("profile_dir")
    rows = [
        (i18n.t("row_firefox"), paths.shown(install_dir)),
        ("MyFox:", paths.shown(launcher.share_dir())),
    ]
    options = []
    remove = restore = None
    if profile_dir:
        rows.append((i18n.t("form_profile"), paths.shown(profile_dir)))
        remove = task_mod.Option(i18n.t("uninstall_remove_profile"), remove_profile)
        options.append(remove)
    source = sync_source(state)
    if source is not None:
        restore = task_mod.Option(i18n.t("uninstall_restore_sync", paths.shown(source.path)), restore_sync)
        options.append(restore)

    def recheck() -> str | None:
        if firefox.running_pids(install_dir):
            return i18n.t("err_firefox_running")
        if restore is not None and restore.value and sources.in_use(source):
            return i18n.t("err_restore_sync_in_use", paths.shown(source.path))
        return None

    command_line = "myfox uninstall -y" + (" --remove-profile" if remove_profile else "") \
        + (" --no-restore-sync" if source is not None and not restore_sync else "")
    return task_mod.Task(
        title=i18n.t("uninstall_title"),
        subtitle=i18n.t("uninstall_subtitle"),
        rows=rows,
        options=options,
        action=i18n.t("uninstall_action"),
        unconfirmed=[i18n.t("needs_yes_uninstall", command_line)]
        + ([i18n.t("needs_yes_uninstall_profile", command_line + " --remove-profile")]
           if profile_dir and not remove_profile else [])
        + ([i18n.t("needs_yes_uninstall_keep_sync", command_line + " --no-restore-sync")]
           if source is not None and restore_sync else []),
        run=lambda progress: run(state, progress, remove_profile=remove is not None and remove.value,
                                 restore_sync=restore is not None and restore.value),
        destructive=True,
        recheck=recheck,
    )


def run(state: State, progress: Progress, remove_profile: bool = False, restore_sync: bool = False) -> None:
    install_dir = Path(state.get("install_dir"))
    profile_dir = Path(state.get("profile_dir")) if state.get("profile_dir") else None
    # First, while nothing is removed yet: a failure leaves MyFox whole.
    if restore_sync and state.get("import_source"):
        progress(i18n.t("progress_uninstall_restore_sync"), 0.05)
        importer.restore_sync(Path(state.get("import_source")))
        if profile_dir is not None and profile_dir.is_dir():
            importer.sign_out(profile_dir)  # one account, one device: not both
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
    command.disable(install_dir)  # puts back a `firefox` it replaced
    launcher.remove_self()
    state.clear()
    state.delete_file()
    progress(i18n.t("uninstall_done_profile" if removing_profile else "uninstall_done"), 1.0)
