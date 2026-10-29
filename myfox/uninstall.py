"""`myfox uninstall`: Firefox, the shortcut, the `myfox` command and MyFox's
own copy go. The profile (bookmarks, history, passwords) stays on disk, only
unregistered from Firefox's profile list — unless deleting it is asked for
(a checkbox, off by default; --remove-profile), and then only those MyFox
created. That holds for every MyFox profile, not just the one our Firefox
opens. A profile imported with its Firefox account moved along gives the
account back (a checkbox each, on by default; --no-restore-sync), and the
MyFox copy, if kept, is signed out.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from . import command, completion, desktop, firefox, i18n, importer, launcher, paths, profiles, sources
from . import task as task_mod
from .install_form import Progress
from .state import State


def _profiles(state: State) -> list[Path]:
    """The one our Firefox opens and every other MyFox profile."""
    found = sources.myfox_dirs(state)
    used = state.get("profile_dir")
    if used and Path(used) not in found:
        found.insert(0, Path(used))
    return found


def _sync_sources(dirs: list[Path]) -> list[tuple[Path, sources.Profile]]:
    """(MyFox copy, the profile its account came from) where that one can
    take it back."""
    found = sources.listing()
    result = []
    for copy in dirs:
        source = importer.restorable_source(copy)
        if source is None:
            continue
        try:
            result.append((copy, sources.resolve(str(source), found)))
        except sources.ProfileLookupError:
            pass
    return result


def build(state: State, remove_profile: bool = False, restore_sync: bool = True) -> task_mod.Task:
    install_dir = Path(state.get("install_dir"))
    dirs = _profiles(state)
    rows = [
        (i18n.t("row_firefox"), paths.shown(install_dir)),
        ("MyFox:", paths.shown(launcher.share_dir())),
    ]
    options = []
    remove = None
    for i, profile_dir in enumerate(dirs):
        rows.append((i18n.t("form_profile") if i == 0 else "", paths.shown(profile_dir)))
    if dirs:
        remove = task_mod.Option(i18n.t("uninstall_remove_profile" if len(dirs) == 1
                                        else "uninstall_remove_profiles"), remove_profile)
        options.append(remove)
    restores = []
    for copy, source in _sync_sources(dirs):
        option = task_mod.Option(i18n.t("uninstall_restore_sync", paths.shown(source.path)), restore_sync)
        restores.append((copy, source, option))
        options.append(option)

    def recheck() -> str | None:
        if firefox.running_pids(install_dir):
            return i18n.t("err_firefox_running")
        for _copy, source, option in restores:
            if option.value and sources.in_use(source):
                return i18n.t("err_restore_sync_in_use", paths.shown(source.path))
        return None

    command_line = "myfox uninstall -y" + (" --remove-profile" if remove_profile else "") \
        + (" --no-restore-sync" if restores and not restore_sync else "")
    return task_mod.Task(
        title=i18n.t("uninstall_title"),
        subtitle=i18n.t("uninstall_subtitle"),
        rows=rows,
        options=options,
        action=i18n.t("uninstall_action"),
        unconfirmed=[i18n.t("needs_yes_uninstall", command_line)]
        + ([i18n.t("needs_yes_uninstall_profile", command_line + " --remove-profile")]
           if dirs and not remove_profile else [])
        + ([i18n.t("needs_yes_uninstall_keep_sync", command_line + " --no-restore-sync")]
           if restores and restore_sync else []),
        run=lambda progress: run(state, progress, remove_profile=remove is not None and remove.value,
                                 restore_sync=[copy for copy, _source, option in restores if option.value]),
        destructive=True,
        recheck=recheck,
    )


def run(state: State, progress: Progress, remove_profile: bool = False, restore_sync: list[Path] = ()) -> None:
    """restore_sync: the MyFox copies whose account goes back where it came
    from."""
    install_dir = Path(state.get("install_dir"))
    dirs = _profiles(state)
    # First, while nothing is removed yet: a failure leaves MyFox whole.
    for copy in restore_sync:
        source = importer.restorable_source(copy)
        if source is None:
            continue
        progress(i18n.t("progress_uninstall_restore_sync"), 0.05)
        importer.restore_sync(source)
        importer.sign_out(copy)  # one account, one device: not both
    progress(i18n.t("progress_uninstall_profile"), 0.1)
    used = Path(state.get("profile_dir")) if state.get("profile_dir") else None
    # Only profiles MyFox created itself (profiles.create_new marks them),
    # never one it was merely pointed at: the profile manager keeps those.
    created = [d for d in dirs if (d / ".myfox-created").is_file()]
    for profile_dir in dirs:
        if profile_dir == used or profile_dir in created:
            profiles.remove_myfox_section(profile_dir)
    if state.get("install_hash"):
        profiles.unpin_install(state.get("install_hash"))
    removing_profile = remove_profile and bool(created)
    if removing_profile:
        progress(i18n.t("progress_uninstall_profile_files"), 0.25)
        for profile_dir in created:
            shutil.rmtree(profile_dir, ignore_errors=True)
    progress(i18n.t("progress_uninstall_firefox"), 0.4)
    shutil.rmtree(install_dir, ignore_errors=True)
    progress(i18n.t("progress_uninstall_myfox"), 0.8)
    desktop.remove_entry()
    command.disable(install_dir)  # puts back a `firefox` it replaced
    completion.remove(state.get("completions"))
    launcher.remove_self()
    state.clear()
    state.delete_file()
    progress(i18n.t("uninstall_done_profile" if removing_profile else "uninstall_done"), 1.0)
