"""`myfox reinstall`: Firefox downloaded again (same language and channel),
swapped in once complete, then the wrapper, shortcut, profile pin and
tweaks put back. The profile itself (bookmarks, history, settings) stays.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from . import apply, changelog, desktop, firefox, i18n, launcher, paths, profiles
from . import task as task_mod
from .install_form import Progress
from .installer import Stages
from .state import State

_MB = 1024 * 1024


def build(state: State) -> task_mod.Task:
    install_dir = Path(state.get("install_dir"))
    channel = {"stable": "wizard_channel_stable", "beta": "wizard_channel_beta"}.get(state.get("channel", "stable"))
    return task_mod.Task(
        title=i18n.t("reinstall_title"),
        subtitle=i18n.t("reinstall_subtitle"),
        rows=[
            (i18n.t("row_firefox"), changelog.display(state.get("firefox_version"))),
            (i18n.t("form_channel"), i18n.t(channel) if channel else state.get("channel")),
            (i18n.t("form_dir"), paths.shown(install_dir)),
        ],
        lines=[i18n.t("reinstall_keeps_profile")],
        action=i18n.t("reinstall_action"),
        confirm=i18n.t("reinstall_confirm"),
        run=lambda progress: run(state, progress),
        blocked=i18n.t("err_firefox_running") if firefox.running_pids(install_dir) else None,
    )


def run(state: State, progress: Progress) -> None:
    install_dir = Path(state.get("install_dir"))
    profile_dir = state.get("profile_dir")
    tweaks = state.get("tweaks", True)
    stages = Stages(progress, [("download", 70), ("extract", 15), ("profile", 5), ("tweaks", 10 if tweaks else 0)])

    def on_download(done: int, total: int | None) -> None:
        if total:
            stages.report("download", i18n.t("progress_firefox_download", f"{done / _MB:.1f}", f"{total / _MB:.0f}"),
                          done / total)
        else:
            stages.report("download", i18n.t("progress_firefox_download_size_unknown", f"{done / _MB:.1f}"))

    # Into a sibling first: a failed download leaves the current Firefox alone.
    new = Path(tempfile.mkdtemp(dir=install_dir.parent, prefix=f".{install_dir.name}-new-"))
    try:
        version = firefox.install_tarball(
            new, state.get("lang", "en-US"), state.get("channel", "stable"), on_download=on_download,
            on_extract=lambda done, total: stages.report("extract", i18n.t("progress_firefox_install"), done / total),
        )
        old = Path(tempfile.mkdtemp(dir=install_dir.parent, prefix=f".{install_dir.name}-old-")) / "firefox"
        install_dir.rename(old)
        new.rename(install_dir)
        shutil.rmtree(old.parent, ignore_errors=True)
    finally:
        shutil.rmtree(new, ignore_errors=True)
    (install_dir / ".myfox-installed").touch()
    desktop.write_entry(install_dir, launcher.launcher_path())

    if profile_dir and tweaks:
        stages.report("profile", i18n.t("progress_profile"))
        pinned = profiles.pin_install(install_dir, Path(profile_dir), saved_hash=state.get("install_hash"))
        if pinned:
            state.set("install_hash", pinned)
        stages.report("tweaks", i18n.t("progress_refresh_tweaks_apply"))
        apply.reapply_tweaks(install_dir, Path(profile_dir), state)

    state.set("firefox_version", version)
    state.save()
    progress(i18n.t("reinstall_done", version), 1.0)
