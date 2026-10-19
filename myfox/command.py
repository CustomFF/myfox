"""`firefox` on the command line for this install: a symlink next to `myfox`
(~/.local/bin/firefox) to <install>/firefox-myfox. A symlink, not a shell
alias, so scripts and other programs get it too; the wrapper, not the
binary, so a running MyFox Firefox takes the URL instead of a system one.

A `firefox` already there that isn't ours is kept as firefox.myfox-backup
and put back when the command is turned off. Whether `firefox` will then
actually find ours depends on PATH: check() says what stands in the way.
Shell aliases and functions in the user's rc files can't be seen from here.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import i18n, launcher, paths
from . import task as task_mod
from .install_form import Progress
from .state import State

NAME = "firefox"
WRAPPER_NAME = "firefox-myfox"


def link_path() -> Path:
    return launcher.link_path().parent / NAME


def backup_path() -> Path:
    return link_path().with_name(NAME + ".myfox-backup")


def wrapper(install_dir: Path) -> Path:
    return install_dir / WRAPPER_NAME


def _ours(target: str) -> bool:
    """A link to some MyFox install's wrapper (this one, or one gone)."""
    return Path(target).name == WRAPPER_NAME


def is_on(install_dir: Path) -> bool:
    link = link_path()
    return link.is_symlink() and Path(os.readlink(link)) == wrapper(install_dir)


def foreign() -> str | None:
    """What a `firefox` in our bin dir that isn't ours is (its target, or
    the file itself); None when there's nothing there."""
    link = link_path()
    if link.is_symlink():
        target = os.readlink(link)
        return None if _ours(target) else target
    return str(link) if link.exists() else None


def _executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def shadow() -> tuple[str, str | None]:
    """Whether `firefox` in this PATH would find the one in our bin dir:
    ("ok", None), ("not_in_path", None) or ("shadowed", the one found first)."""
    ours = link_path().parent.resolve()
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry:
            continue
        directory = Path(entry).expanduser()
        try:
            if directory.resolve() == ours:
                return "ok", None
        except OSError:
            continue
        if _executable(directory / NAME):
            return "shadowed", str(directory / NAME)
    return "not_in_path", None


def check(install_dir: Path) -> list[str]:
    """What to tell the user before (or after) turning the command on."""
    notes = []
    other = None if is_on(install_dir) else foreign()
    if other:
        notes.append(i18n.t("command_replaces", paths.shown(link_path()), other, paths.shown(backup_path())))
    status, found = shadow()
    if status == "not_in_path":
        notes.append(i18n.t("command_not_in_path", paths.shown(link_path().parent)))
    elif status == "shadowed":
        notes.append(i18n.t("command_shadowed", found, paths.shown(link_path().parent)))
    return notes


def enable(install_dir: Path) -> None:
    link = link_path()
    if is_on(install_dir):
        return
    link.parent.mkdir(parents=True, exist_ok=True)
    backup = backup_path()
    if link.is_symlink() or link.exists():
        # Only a foreign one is kept, and never over an older backup: that
        # one is what the user had first.
        if foreign() and not (backup.is_symlink() or backup.exists()):
            link.rename(backup)
        else:
            link.unlink()
    link.symlink_to(wrapper(install_dir))


def disable(install_dir: Path) -> bool:
    """Removes our link and puts back what it replaced; False if the
    `firefox` there isn't ours (then nothing is touched)."""
    if not is_on(install_dir):
        return False
    link_path().unlink()
    backup = backup_path()
    if backup.is_symlink() or backup.exists():
        backup.rename(link_path())
    return True


def build(state: State, on: bool) -> task_mod.Task:
    """The confirm-then-run dialog of `myfox command on|off`."""
    install_dir = Path(state.get("install_dir"))
    shown = paths.shown(link_path())
    if on:
        notes = check(install_dir)
        rows = [(i18n.t("command_row"), f"{shown} → {paths.shown(wrapper(install_dir))}")]

        def run(progress: Progress) -> None:
            enable(install_dir)
            progress(i18n.t("command_on_done"), 1.0)
    else:
        backup = backup_path()
        notes = [i18n.t("command_restores", shown)] if backup.is_symlink() or backup.exists() else []
        rows = [(i18n.t("command_row"), shown)]

        def run(progress: Progress) -> None:
            disable(install_dir)
            progress(i18n.t("command_off_done"), 1.0)
    return task_mod.Task(
        title=i18n.t("command_title"),
        subtitle=i18n.t("command_subtitle_on" if on else "command_subtitle_off"),
        rows=rows,
        heading=i18n.t("command_notes") if notes else "",
        lines=notes,
        action=i18n.t("command_on" if on else "command_off"),
        unconfirmed=[i18n.t("needs_yes_command", f"myfox command {'on' if on else 'off'} -y")],
        run=run,
        # Replacing someone else's `firefox` deserves a second look.
        destructive=on and foreign() is not None,
    )


def status(install_dir: Path) -> dict:
    """The state for a program (about:myfox): the notes are the same,
    already in the user's language, the rest is for deciding."""
    path, found = shadow()
    return {
        "on": is_on(install_dir),
        "link": str(link_path()),
        "target": str(wrapper(install_dir)),
        "replaces": None if is_on(install_dir) else foreign(),
        "path": path,
        "found_first": found,
        "notes": check(install_dir),
    }


def run(state: State, action: str | None, gui: bool = False, noninteractive: bool = False,
        as_json: bool = False) -> int:
    """`myfox command` alone tells whether it's on and what's in its way;
    on/off asks first, unless there's nothing to do. With --json nothing is
    asked (the caller has shown the notes) and the outcome is the status,
    or {"error": …}, as JSON on stdout."""
    install_dir = Path(state.get("install_dir"))
    if as_json:
        try:
            if action is not None:
                (enable if action == "on" else disable)(install_dir)
        except OSError as exc:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(status(install_dir), ensure_ascii=False))
        return 0
    on = is_on(install_dir)
    if action is None or (action == "on") == on:
        print(i18n.t("command_is_on" if on else "command_is_off", paths.shown(link_path())))
        for note in check(install_dir) if on else []:
            print(note)
        return 0
    return 0 if task_mod.show(build(state, action == "on"), gui=gui, noninteractive=noninteractive) else 1
