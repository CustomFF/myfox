"""The real first install behind the install form (port of bin/myfox-core's
run_install): Firefox from the tarball, the profile, the tweaks, the
shortcut and the `myfox` command, then the state file. Reports progress
the same way simulate_install does, so the form doesn't care which runs.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from . import addons, apply, desktop, firefox, i18n, launcher, profiles
from .install_form import Answers, Progress
from .state import State

_MB = 1024 * 1024


class _Stages:
    """Maps each stage's own 0..1 onto one overall bar, by weight."""

    def __init__(self, progress: Progress, weights: list[tuple[str, float]]):
        self._progress = progress
        total = sum(w for _name, w in weights)
        self._start, offset = {}, 0.0
        for name, w in weights:
            self._start[name] = (offset / total, w / total)
            offset += w

    def report(self, name: str, message: str, done: float = 0.0) -> None:
        start, share = self._start[name]
        self._progress(message, start + share * min(1.0, done))


def install(answers: Answers, progress: Progress) -> None:
    install_dir = Path(answers.install_dir)
    reuse = firefox.dir_claim_state(install_dir) == "ours"
    weights = [("download", 0 if reuse else 60), ("extract", 0 if reuse else 15), ("profile", 10)]
    plasma = answers.tweaks and addons.is_plasma_session()
    if answers.tweaks:
        weights += [("styles", 2), ("themes", 5), ("bookmarklets", 3)]
    if plasma:
        weights += [("plasma", 3)]
    weights += [("shortcut", 5)]
    stages = _Stages(progress, weights)

    # Firefox: an install of ours already there is reused, as before.
    if reuse:
        version = firefox.local_version(install_dir)
    else:
        def on_download(done: int, total: int | None) -> None:
            if total:
                stages.report("download", i18n.t("progress_firefox_download", f"{done / _MB:.1f}",
                                                  f"{total / _MB:.0f}"), done / total)
            else:
                stages.report("download", i18n.t("progress_firefox_download_size_unknown", f"{done / _MB:.1f}"))

        version = firefox.install_tarball(
            install_dir, answers.lang, answers.channel, on_download=on_download,
            on_extract=lambda done, total: stages.report("extract", i18n.t("progress_firefox_install"), done / total),
        )
    (install_dir / ".myfox-installed").touch()

    # Profile: an existing MyFox one, or a new myfox-N.
    stages.report("profile", i18n.t("progress_profile"))
    profile_dir = Path(answers.profile_dir) if answers.profile_dir else profiles.create_new()
    install_hash = None
    if answers.tweaks:
        # Pinning runs the install headless once, so it can take a while.
        install_hash = profiles.pin_install(install_dir, profile_dir, saved_hash=None)

        stages.report("styles", i18n.t("progress_tweaks_styles"))
        apply.apply_autoconfig(install_dir)
        apply.apply_chrome(profile_dir)
        apply.apply_theme_pref(profile_dir, answers.theme)

        stages.report("themes", i18n.t("progress_tweaks_themes_download"))
        addons.fetch_themes(profile_dir, local_dir=os.environ.get("MYFOX_TWEAKS_LOCAL"))

        stages.report("bookmarklets", i18n.t("progress_tweaks_bookmarklets"))
        apply.apply_bookmarklets(profile_dir, local_dir=os.environ.get("MYFOX_DDBLM_LOCAL"))

    if plasma:
        stages.report("plasma", i18n.t("progress_tweaks_plasma"))
        if addons.apply_amo_addons(profile_dir, [addons.MYFOX_ADDON_PLASMA]):
            answers.notes.append(i18n.t("note_plasma_addon_failed"))
        if not addons.pkg_installed():
            hint = addons.pkg_install_hint()
            answers.notes.append(i18n.t("note_plasma_pkg_missing", hint) if hint
                                 else i18n.t("note_plasma_pkg_missing_manual"))

    stages.report("shortcut", i18n.t("progress_shortcut"))
    desktop.write_entry(install_dir, launcher.install_self())

    state = State()
    for key, value in (
        ("install_dir", str(install_dir)), ("profile_dir", str(profile_dir)), ("firefox_version", version),
        ("install_hash", install_hash), ("installed_at", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")),
        ("lang", answers.lang), ("channel", answers.channel), ("theme", answers.theme),
        ("tweaks", answers.tweaks), ("opt_bl", answers.tweaks), ("opt_plasma", plasma),
    ):
        state.set(key, value)
    state.save()
    progress(i18n.t("progress_done"), 1.0)
