"""The first install behind the install form: Firefox from the tarball,
the profile, the tweaks, the shortcut and the `myfox` command, then the
state file. Reports progress
the same way simulate_install does, so the form doesn't care which runs.
Stopped or failed halfway, it takes back what it created.
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import addons, apply, command, desktop, firefox, gui_deps, i18n, importer, launcher, net, profiles, tweaks
from . import __version__
from .install_form import Answers, Progress, settled
from .state import State


class Stages:
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


def firefox_progress(stages: Stages) -> dict[str, Callable]:
    """The on_download/on_wait/on_extract of firefox.install_tarball, onto
    the "download" and "extract" stages."""
    downloaded = [0.0]

    def on_download(done: int, total: int | None) -> None:
        downloaded[0] = done / total if total else 0.0
        stages.report("download", i18n.t("progress_firefox_download"), downloaded[0])

    def on_wait(seconds: int) -> None:
        message = i18n.t("progress_network_silent", i18n.t("progress_firefox_download"), seconds, net.TIMEOUT)
        stages.report("download", message, downloaded[0])

    def on_extract(done: int, total: int) -> None:
        stages.report("extract", i18n.t("progress_firefox_install"), done / total)

    return {"on_download": on_download, "on_wait": on_wait, "on_extract": on_extract}


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path, ignore_errors=True)


class _Undo:
    """What this install created, taken back in reverse order."""

    def __init__(self) -> None:
        self._steps: list[Callable[[], None]] = []

    def add(self, step: Callable[[], None]) -> None:
        self._steps.append(step)

    def created(self, path: Path) -> None:
        """`path` is about to be made: it goes, with the parents made for it."""
        top = None
        for p in (path, *path.parents):
            if p.exists() or p.is_symlink():
                break
            top = p
        if top is not None:
            self.add(lambda: _remove(top))

    def new_entries(self, path: Path) -> None:
        """Whatever appears in directory `path` goes; what was there stays."""
        if not path.is_dir():
            self.created(path)
            return
        before = {child.name for child in path.iterdir()}
        self.add(lambda: [_remove(child) for child in path.iterdir() if child.name not in before])

    def run(self) -> None:
        for step in reversed(self._steps):
            try:
                step()
            except OSError:
                pass  # the rest still goes


def install(answers: Answers, progress: Progress) -> None:
    undo = _Undo()
    try:
        _install(answers, progress, undo)
    except BaseException:
        undo.run()
        raise
    settled(progress)(i18n.t("progress_done"), 1.0)


def _install(answers: Answers, progress: Progress, undo: _Undo) -> None:
    install_dir = Path(answers.install_dir)
    reuse = firefox.dir_claim_state(install_dir) == "ours"
    weights = [("download", 0 if reuse else 60), ("extract", 0 if reuse else 15), ("profile", 10)]
    if answers.import_from:
        weights += [("import", 20)]
    plasma = answers.tweaks and addons.is_plasma_session()
    if answers.tweaks:
        weights += [("tweaks", 3), ("styles", 2), ("themes", 5), ("bookmarklets", 3)]
    if plasma:
        weights += [("plasma", 3)]
    weights += [("gui", 5), ("shortcut", 2)] + ([("command", 1)] if answers.firefox_command else [])
    stages = Stages(progress, weights)
    undo.new_entries(launcher.share_dir())

    # Firefox: an install of ours already there is reused.
    if reuse:
        version = firefox.local_version(install_dir)
    else:
        # Validated: missing, or an empty directory.
        if install_dir.is_dir():
            undo.new_entries(install_dir)
        else:
            undo.created(install_dir)
        version = firefox.install_tarball(install_dir, answers.lang, answers.channel, **firefox_progress(stages))
    (install_dir / ".myfox-installed").touch()

    # Profile: an existing MyFox one, or a new myfox-N.
    stages.report("profile", i18n.t("progress_profile"))
    ini = profiles.find_ini()
    store = ini.parent if ini else profiles.native_dir()
    undo.created(store / "profiles.ini")
    undo.created(store / "installs.ini")
    if answers.profile_dir:
        profile_dir = Path(answers.profile_dir)
    else:
        profile_dir = profiles.create_new()
        undo.add(lambda: (profiles.remove_myfox_section(profile_dir), _remove(profile_dir)))
    source = Path(answers.import_from) if answers.import_from else None
    if source is not None:
        def on_copy(done: int, total: int) -> None:
            mb = 1024 * 1024
            stages.report("import", i18n.t("progress_import", done // mb, total // mb), done / total if total else 1.0)

        stages.report("import", i18n.t("progress_import_start"))
        importer.copy_profile(source, profile_dir, answers.sync, on_copy=on_copy)
        if answers.allow_downgrade:
            # Firefox refuses a profile from a newer version without it, once.
            importer.accept_downgrade(install_dir, profile_dir)
    install_hash = tweaks_version = themes_version = ddblm_version = None
    if answers.tweaks:
        stages.report("tweaks", i18n.t("progress_tweaks_download"))
        tweaks_version = tweaks.install()

        # Pinning runs the install headless once, so it can take a while.
        install_hash = profiles.pin_install(install_dir, profile_dir, saved_hash=None)
        if install_hash is None:
            answers.notes.append(i18n.t("note_pin_failed"))
        else:
            undo.add(lambda: profiles.unpin_install(install_hash))

        stages.report("styles", i18n.t("progress_tweaks_styles"))
        apply.apply_autoconfig(install_dir)
        apply.apply_chrome(profile_dir)
        apply.apply_theme_pref(profile_dir, answers.theme)
        if source is not None:
            # The copy keeps its own theme: the tweaks switch it once.
            (profile_dir / importer.THEME_MARKER).touch()
        if not answers.doh:
            apply.apply_doh_off(profile_dir)

        stages.report("themes", i18n.t("progress_tweaks_themes_download"))
        themes_version, _missing = addons.fetch_themes(profile_dir, local_dir=os.environ.get("MYFOX_TWEAKS_LOCAL"))

        stages.report("bookmarklets", i18n.t("progress_tweaks_bookmarklets"))
        ddblm_version = apply.apply_bookmarklets(profile_dir, local_dir=os.environ.get("MYFOX_DDBLM_LOCAL"))

    if plasma:
        stages.report("plasma", i18n.t("progress_tweaks_plasma"))
        if addons.apply_amo_addons(profile_dir, [addons.MYFOX_ADDON_PLASMA]):
            answers.notes.append(i18n.t("note_plasma_addon_failed"))
        if not addons.pkg_installed():
            hint = addons.pkg_install_hint()
            answers.notes.append(i18n.t("note_plasma_pkg_missing", hint) if hint
                                 else i18n.t("note_plasma_pkg_missing_manual"))

    undo.created(launcher.link_path())
    launcher_path = launcher.install_self()
    stages.report("gui", i18n.t("progress_gui"))
    try:
        gui_deps.install_into(launcher.share_dir())
    except (OSError, RuntimeError) as exc:
        answers.notes.append(i18n.t("note_gui_failed", exc))

    stages.report("shortcut", i18n.t("progress_shortcut"))
    if not desktop.desktop_file().exists():
        undo.add(desktop.remove_entry)
    desktop.write_entry(install_dir, launcher_path)

    if answers.firefox_command:
        stages.report("command", i18n.t("progress_command"))
        # Said before it's done: afterwards a replaced `firefox` is no
        # longer in sight.
        answers.notes += command.check(install_dir)
        undo.add(lambda: command.disable(install_dir))
        command.enable(install_dir)

    backups: list[Path] = []
    if source is not None and answers.sync == importer.SYNC_MOVE and importer.has_account(source):
        # Last: the only change to the other Firefox's profile.
        undo.add(lambda: importer.restore_sync(source))
        backups = importer.move_sync_out(source)
    if source is not None:
        importer.write_origin(profile_dir, source, answers.sync, backups)

    state = State()
    for key, value in (
        ("install_dir", str(install_dir)), ("profile_dir", str(profile_dir)), ("firefox_version", version),
        ("install_hash", install_hash), ("installed_at", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")),
        ("lang", answers.lang), ("channel", answers.channel), ("theme", answers.theme),
        ("tweaks", answers.tweaks), ("opt_bl", answers.tweaks), ("opt_plasma", plasma),
        ("core_version", __version__), ("tweaks_version", tweaks_version), ("themes_version", themes_version),
        ("ddblm_version", ddblm_version), ("doh", answers.doh),
    ):
        state.set(key, value)
    state.save()
    answers.profile_dir, answers.firefox_version = str(profile_dir), version
