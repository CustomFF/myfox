"""`myfox profile …`: the profiles MyFox can see and what it does with them.

list shows the ones related to MyFox (ours, made with `firefox -p` from our
install, never run); --all adds every other Firefox's, which can only be
imported. The ID column is what the other subcommands take.
"""

from __future__ import annotations

import json
import shlex
import shutil
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import apply, firefox, i18n, importer, paths, profiles, sources
from . import task as task_mod
from .install_form import Progress, settled
from .state import State


def _install_dir(state: State) -> Path | None:
    return Path(state.get("install_dir")) if state.get("install_dir") else None


def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def _pad(text: str, width: int) -> str:
    return text + " " * (width - _width(text))


def quoted(arg: str) -> str:
    """An ID as it goes into a printed command."""
    return shlex.quote(arg)


def _registered() -> set[Path]:
    ini = profiles.find_ini()
    return {profiles.resolve_dir(ini.parent, e) for e in profiles.parse_profiles(ini)} if ini else set()


def _status(p: sources.Profile, used: Path | None, found: list[sources.Profile], registered: set[Path]) -> list[str]:
    if p.owner == sources.MYFOX:
        parts = [i18n.t("profile_status_myfox")]
        if used is not None and p.path == used:
            parts.append(i18n.t("profile_status_used"))
        origin = importer.read_origin(p.path)
        if origin is not None:
            source = Path(origin["source"])
            shown = next((q.id for q in found if q.path == source), paths.shown(source))
            parts.append(i18n.t("profile_status_moved" if origin.get("moved") else "profile_status_imported", shown))
        if not p.store and p.path not in registered:
            parts.append(i18n.t("profile_status_unregistered"))
    elif p.owner == sources.OURS:
        parts = [i18n.t("profile_status_ours")]
    elif p.owner == sources.UNUSED:
        parts = [i18n.t("profile_status_unused")]
    else:
        parts = [i18n.t({sources.SNAP: "profile_status_snap", sources.FLATPAK: "profile_status_flatpak"}
                        .get(p.store, "profile_status_foreign"))]
    if p.owner != sources.MYFOX and used is not None and p.path == used:
        parts.append(i18n.t("profile_status_used"))
    if sources.in_use(p):
        parts.append(i18n.t("profile_status_open"))
    return parts


def last_used(path: Path) -> str | None:
    """When a Firefox last opened it: every start touches .parentlock (an
    import leaves it behind, so a copy not opened yet has none)."""
    try:
        mtime = (path / ".parentlock").stat().st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _record(p: sources.Profile, used: Path | None) -> dict:
    origin = importer.read_origin(p.path) if p.owner == sources.MYFOX else None
    return {
        "id": p.id, "name": p.name, "path": str(p.path), "store": p.store or "myfox", "owner": p.owner,
        "tweaks": p.owner == sources.MYFOX, "used": used is not None and p.path == used, "open": sources.in_use(p),
        "created": not p.store and (p.path / ".myfox-created").is_file(), "last_used": last_used(p.path),
        "last_version": p.last_version, "imported_from": origin["source"] if origin else None,
        "moved": bool(origin and origin.get("moved")), "account": importer.has_account(p.path),
    }


def list_profiles(state: State, show_all: bool = False, as_json: bool = False) -> int:
    used = Path(state.get("profile_dir")) if state.get("profile_dir") else None
    if as_json:
        # For about:myfox: one line, whatever happens.
        try:
            found = sources.listing(_install_dir(state))
            records = [_record(p, used) for p in found if show_all or p.related]
        except OSError as exc:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(records, ensure_ascii=False))
        return 0
    found = sources.listing(_install_dir(state))
    shown = found if show_all else [p for p in found if p.related]
    if not shown:
        print(i18n.t("profile_list_none"))
    else:
        registered = _registered()
        head = [i18n.t("profile_col_id"), i18n.t("profile_col_name"), i18n.t("profile_col_tweaks"),
                i18n.t("profile_col_status")]
        rows = [[p.id, p.name, i18n.t("summary_yes" if p.owner == sources.MYFOX else "summary_no"),
                 ", ".join(_status(p, used, found, registered))] for p in shown]
        widths = [max(_width(r[i]) for r in [head] + rows) for i in range(3)]
        for r in [head] + rows:
            print("  ".join(_pad(cell, widths[i]) for i, cell in enumerate(r[:3])) + "  " + r[3])
    hidden = len(found) - len(shown)
    if hidden:
        print()
        print(i18n.t("profile_list_hidden", hidden, "myfox profile list --all"))
    return 0


# ─── Changing them ───────────────────────────────────────────────────────

class Refused(Exception):
    """Why a subcommand can't go ahead at all (printed, exit 1)."""


def _row(p: sources.Profile) -> tuple[str, str]:
    return i18n.t("form_profile"), f"{p.id} ({paths.shown(p.path)})" if p.id != str(p.path) else paths.shown(p.path)


def _tweaks_row(p: sources.Profile) -> tuple[str, str]:
    return i18n.t("profile_col_tweaks") + ":", i18n.t("summary_yes" if p.owner == sources.MYFOX else "summary_no")


def _find(state: State, arg: str) -> sources.Profile:
    install_dir = _install_dir(state)
    try:
        return sources.resolve(arg, sources.listing(install_dir), install_dir)
    except sources.ProfileLookupError as exc:
        raise Refused(str(exc)) from None


def _related(p: sources.Profile) -> sources.Profile:
    if not p.related:
        raise Refused(i18n.t("err_profile_foreign", p.id, "myfox profile import " + quoted(p.id)))
    return p


def _first(*checks: Callable[[], str | None]) -> Callable[[], str | None]:
    def recheck() -> str | None:
        for check in checks:
            blocked = check()
            if blocked:
                return blocked
        return None
    return recheck


def _ours_closed(state: State) -> Callable[[], str | None]:
    # Our Firefox rewrites profiles.ini as it knows it when it exits.
    install_dir = _install_dir(state)
    return lambda: i18n.t("err_firefox_running") if firefox.running_pids(install_dir) else None


def _closed(p: sources.Profile) -> Callable[[], str | None]:
    return lambda: i18n.t("err_profile_open", p.id) if sources.in_use(p) else None


def _use(state: State, profile_dir: Path) -> None:
    """Our install opens this one from now on."""
    install_hash = profiles.pin_install(_install_dir(state), profile_dir, saved_hash=state.get("install_hash"))
    if install_hash is None:
        raise OSError(i18n.t("err_profile_pin_failed"))
    state.set("install_hash", install_hash)
    state.set("profile_dir", str(profile_dir))
    state.save()


def _tweak(state: State, profile_dir: Path, progress: Progress, at: float) -> None:
    if state.get("tweaks", True):
        progress(i18n.t("progress_refresh_tweaks_apply"), at)
        apply.tweak_profile(profile_dir, state)
        state.save()


def _new_profile(undo: list[Callable[[], None]], name: str = "") -> Path:
    # A name of its own: the profile manager lists them by name.
    profile_dir = profiles.create_new(" ".join(name.split()))
    undo.append(lambda: (profiles.remove_myfox_section(profile_dir), shutil.rmtree(profile_dir, ignore_errors=True)))
    return profile_dir


def _undoing(work: Callable[[list], None]) -> None:
    undo: list[Callable[[], None]] = []
    try:
        work(undo)
    except BaseException:
        for step in reversed(undo):
            try:
                step()
            except OSError:
                pass
        raise


def _move_away(source: sources.Profile, undo: list) -> Callable[[], None]:
    """Takes the source out of its Firefox: the folder set aside, its
    profiles.ini entry and any install defaulting to it gone. Undone like
    the rest until the returned finish() deletes it for good."""
    root = sources.store_root(source)
    for ini in ([root / "profiles.ini", root / "installs.ini"] if root else []):
        if ini.is_file():
            text = ini.read_text(encoding="utf-8")
            undo.append(lambda ini=ini, text=text: ini.write_text(text, encoding="utf-8"))
            profiles.forget_dir(ini, source.path)
    aside = source.path.with_name(f".{source.path.name}.myfox-moving")
    source.path.rename(aside)
    undo.append(lambda: aside.rename(source.path))

    def finish() -> None:
        if root:
            sources.forget_in_groups(root, source.path)
        shutil.rmtree(aside, ignore_errors=True)
    return finish


def _relaunching(state: State, task: task_mod.Task, opened: Callable[[], Path | None] = lambda: None) \
        -> task_mod.Task:
    """For about:myfox, where everything was chosen already: runs at once,
    closing this install's Firefox first and starting it again afterwards,
    also after a failure or a cancel (then all is as it was). opened(): a
    profile to open beside it once done."""
    install_dir = _install_dir(state)
    work = task.run

    def run(progress: Progress) -> None:
        waiting = i18n.t("progress_firefox_quit")
        progress(waiting, 0.0)
        # Every MyFox profile open now, each in an instance of its own:
        # all of them go, and come back afterwards.
        open_dirs = [p.path for p in sources.listing(install_dir) if p.related and sources.in_use(p)]
        default = state.get("profile_dir")
        was_running = firefox.quit_and_wait(install_dir, open_dirs, lambda: progress(waiting, 0.0))
        try:
            work(progress)
        finally:
            if was_running:
                # The default one (maybe a new one now) in the usual way.
                firefox.start(install_dir)
                for profile_dir in open_dirs:
                    if str(profile_dir) not in (default, state.get("profile_dir")):
                        firefox.start(install_dir, profile_dir)
        extra = opened()
        if extra is not None:
            firefox.start(install_dir, extra)

    task.run = run
    task.autorun = True
    task.closes = lambda: True
    return task


def _command(*parts: str) -> str:
    return " ".join(["myfox", "profile", *parts, "-y"])


def new_task(state: State, use: bool = False) -> task_mod.Task:
    use_option = task_mod.Option(i18n.t("profile_opt_use"), use)

    def run(progress: Progress) -> None:
        def work(undo: list) -> None:
            progress(i18n.t("progress_profile"), 0.1)
            profile_dir = _new_profile(undo)
            _tweak(state, profile_dir, progress, 0.3)
            if use_option.value:
                _use(state, profile_dir)
            settled(progress)(i18n.t("profile_new_done", profile_dir.name), 1.0)
        _undoing(work)

    return task_mod.Task(
        title=i18n.t("profile_new_title"), subtitle=i18n.t("profile_new_subtitle"),
        rows=[(i18n.t("profile_col_tweaks") + ":", i18n.t("summary_yes" if state.get("tweaks", True) else "summary_no"))],
        options=[use_option], action=i18n.t("profile_new_action"),
        unconfirmed=[i18n.t("needs_yes_profile", _command("new", *(["--use"] if use else [])))],
        run=run, recheck=_ours_closed(state),
    )


def apply_task(state: State, arg: str) -> task_mod.Task:
    p = _related(_find(state, arg))
    if not state.get("tweaks", True):
        raise Refused(i18n.t("err_profile_no_tweaks"))

    def run(progress: Progress) -> None:
        apply.tweak_profile(p.path, state)
        state.save()
        progress(i18n.t("profile_apply_done", p.id), 1.0)

    return task_mod.Task(
        title=i18n.t("profile_apply_title"), subtitle=i18n.t("profile_apply_subtitle"),
        rows=[_row(p), _tweaks_row(p)], action=i18n.t("profile_apply_action"),
        unconfirmed=[i18n.t("needs_yes_profile", _command("apply", quoted(p.id)))],
        run=run, recheck=_closed(p),
    )


def use_task(state: State, arg: str, relaunch: bool = False) -> task_mod.Task:
    p = _related(_find(state, arg))
    if state.get("profile_dir") and Path(state.get("profile_dir")) == p.path:
        raise Refused(i18n.t("profile_use_already", p.id))
    lines = [i18n.t("profile_use_no_tweaks", "myfox profile apply " + quoted(p.id))] \
        if p.owner != sources.MYFOX and state.get("tweaks", True) else []

    def run(progress: Progress) -> None:
        _use(state, p.path)
        progress(i18n.t("profile_use_done", p.id), 1.0)

    task = task_mod.Task(
        title=i18n.t("profile_use_title"), subtitle=i18n.t("profile_use_subtitle"),
        rows=[_row(p), _tweaks_row(p)], lines=lines, action=i18n.t("profile_use_action"),
        unconfirmed=[i18n.t("needs_yes_profile", _command("use", quoted(p.id)))],
        run=run, recheck=None if relaunch else _ours_closed(state),
    )
    return _relaunching(state, task) if relaunch else task


def remove_task(state: State, arg: str, restore_sync: bool = True) -> task_mod.Task:
    p = _find(state, arg)
    if p.store or not (p.path / ".myfox-created").is_file():
        raise Refused(i18n.t("err_profile_not_created", p.id))
    if state.get("profile_dir") and Path(state.get("profile_dir")) == p.path:
        raise Refused(i18n.t("err_profile_used", p.id, "myfox profile use"))
    options = []
    source_path = importer.restorable_source(p.path)
    source = None
    if source_path is not None:
        try:
            source = sources.resolve(str(source_path), sources.listing())
        except sources.ProfileLookupError:
            pass
    restore = None
    if source is not None:
        restore = task_mod.Option(i18n.t("uninstall_restore_sync", paths.shown(source.path)), restore_sync)
        options.append(restore)

    def source_closed() -> str | None:
        if restore is not None and restore.value and sources.in_use(source):
            return i18n.t("err_restore_sync_in_use", paths.shown(source.path))
        return None

    def run(progress: Progress) -> None:
        if restore is not None and restore.value:
            progress(i18n.t("progress_uninstall_restore_sync"), 0.1)
            importer.restore_sync(source.path)
        progress(i18n.t("progress_uninstall_profile_files"), 0.3)
        profiles.remove_myfox_section(p.path)
        shutil.rmtree(p.path, ignore_errors=True)
        progress(i18n.t("profile_remove_done", p.id), 1.0)

    keep = " --no-restore-sync" if restore is not None and not restore_sync else ""
    return task_mod.Task(
        title=i18n.t("profile_remove_title"), subtitle=i18n.t("profile_remove_subtitle"),
        rows=[_row(p)], options=options, action=i18n.t("profile_remove_action"),
        unconfirmed=[i18n.t("needs_yes_profile", _command("remove", quoted(p.id)) + keep)]
        + ([i18n.t("needs_yes_uninstall_keep_sync", _command("remove", quoted(p.id)) + " --no-restore-sync")]
           if restore is not None and restore_sync else []),
        run=run, destructive=True, recheck=_first(_ours_closed(state), _closed(p), source_closed),
    )


def import_task(state: State, arg: str, sync: str = importer.SYNC_NONE, allow_downgrade: bool = False,
                use: bool = False, name: str | None = None, move: bool = False, open_after: bool = False,
                relaunch: bool = False) -> task_mod.Task:
    """move: the source goes, account and all (no sync choice), and leaves
    its Firefox's profile list. open_after: started beside our Firefox
    once done (with use our Firefox opens it anyway). relaunch: see
    _relaunching."""
    source = _find(state, arg)
    if not sources.is_profile(source.path):
        raise Refused(i18n.t("err_not_a_profile", arg))
    if move:
        sync = importer.SYNC_COPY if importer.has_account(source.path) else importer.SYNC_NONE
    elif sync != importer.SYNC_NONE and not importer.has_account(source.path):
        sync = importer.SYNC_NONE  # nothing to carry over
    # Not the same name as the original: that one would stop being a name
    # to call either by.
    name = " ".join((name or "").split()) or f"{source.name} (MyFox)"
    version = state.get("firefox_version")
    in_use = [lambda: i18n.t("err_import_in_use", source.id) if sources.in_use(source) else None]
    options, checks = [], in_use if relaunch else [_ours_closed(state), *in_use]
    created: list[Path] = []
    use_option = task_mod.Option(i18n.t("profile_opt_use"), use)
    options.append(use_option)
    downgrade = None
    if sources.is_downgrade(source.last_version, version):
        downgrade = task_mod.Option(i18n.t("profile_opt_downgrade", source.last_version, version), allow_downgrade)
        options.append(downgrade)
        checks.append(lambda: None if downgrade.value else i18n.t("err_profile_downgrade", source.last_version,
                                                                   version))

    def run(progress: Progress) -> None:
        def work(undo: list) -> None:
            progress(i18n.t("progress_import_start"), 0.0)
            profile_dir = _new_profile(undo, name)

            def on_copy(done: int, total: int) -> None:
                mb = 1024 * 1024
                progress(i18n.t("progress_import", done // mb, total // mb), 0.8 * done / total if total else 0.8)

            importer.copy_profile(source.path, profile_dir, sync, on_copy=on_copy)
            if downgrade is not None and downgrade.value:
                importer.accept_downgrade(_install_dir(state), profile_dir)
            done = settled(progress)  # past the copy: no stopping halfway
            if state.get("tweaks", True):
                # The copy keeps its own theme, over which the tweaks look
                # wrong: the MyFox one that looks like it, switched to once.
                theme = importer.mark_theme(profile_dir, source.path)
                if theme:
                    apply.apply_theme_pref(profile_dir, theme)
            _tweak(state, profile_dir, done, 0.85)
            backups: list[Path] = []
            if sync == importer.SYNC_MOVE and importer.has_account(source.path):
                undo.append(lambda: importer.restore_sync(source.path))
                backups = importer.move_sync_out(source.path)
            importer.write_origin(profile_dir, source.path, sync, backups, moved=move)
            finish = _move_away(source, undo) if move else None
            if use_option.value:
                _use(state, profile_dir)
            if finish:
                done(i18n.t("progress_import_move"), 0.95)
                finish()
            created.append(profile_dir)
            done(i18n.t("profile_import_done", source.id, profile_dir.name), 1.0)
        _undoing(work)

    flags = [quoted(source.id)] + (["--move"] if move else []) \
        + (["--sync", sync] if sync != importer.SYNC_NONE and not move else []) \
        + (["--name", quoted(name)] if name != f"{source.name} (MyFox)" else []) \
        + (["--allow-downgrade"] if downgrade is not None else []) + (["--use"] if use else []) \
        + (["--open"] if open_after else [])
    rows = [(i18n.t("summary_moved" if move else "summary_imported"), _row(source)[1]),
            (i18n.t("form_name"), name)]
    if not move:
        rows.append((i18n.t("form_sync"), i18n.t("form_sync_" + sync)))
    rows.append((i18n.t("profile_col_tweaks") + ":", i18n.t("summary_yes" if state.get("tweaks", True)
                                                            else "summary_no")))
    task = task_mod.Task(
        title=i18n.t("profile_import_title"), subtitle=i18n.t("profile_move_subtitle" if move
                                                               else "profile_import_subtitle"),
        rows=rows, options=options, action=i18n.t("profile_import_action"),
        unconfirmed=[i18n.t("needs_yes_profile", _command("import", *flags))],
        run=run, cancellable=True, recheck=_first(*checks),
    )

    def opened() -> Path | None:
        # With use, our Firefox opens it itself.
        return created[0] if open_after and created and not use_option.value else None

    if relaunch:
        return _relaunching(state, task, opened)
    if open_after:
        work = task.run

        def run_and_open(progress: Progress) -> None:
            work(progress)
            firefox.start(_install_dir(state), opened())

        task.run = run_and_open
    return task


def apply_json(state: State, arg: str) -> int:
    """`apply --json`, for about:myfox: no questions; {"ok": true, "id": …}
    or {"error": …} on stdout."""
    try:
        task = apply_task(state, arg)
        if task.blocked:
            raise Refused(task.blocked)
        task.run(lambda message, fraction: None)
    except (Refused, OSError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, "id": _find(state, arg).id}, ensure_ascii=False))
    return 0


def candidates(state: State, command: str) -> list[sources.Profile]:
    """What `command` can take: related profiles for apply and use, the
    removable ones for remove, every other one for import."""
    found = sources.listing(_install_dir(state))
    used = Path(state.get("profile_dir")) if state.get("profile_dir") else None
    if command == "import":
        return [p for p in found if p.owner != sources.MYFOX]
    if command == "remove":
        return [p for p in found if not p.store and p.path != used and (p.path / ".myfox-created").is_file()]
    if command == "use":
        return [p for p in found if p.related and p.path != used]
    return [p for p in found if p.related]


def pick(state: State, command: str, gui: bool) -> str | None:
    """The picker for a subcommand run without an ID; the chosen ID."""
    found = candidates(state, command)
    if not found:
        print(i18n.t("profile_pick_none"), file=sys.stderr)
        return None
    choices = [(p.id, p.id if p.name in (p.id, p.path.name) else f"{p.name} ({p.id})") for p in found]
    picker = task_mod.Task(
        title=i18n.t(f"profile_{command}_title"), subtitle=i18n.t("profile_pick_subtitle"), rows=[],
        action=i18n.t("profile_pick_action"), unconfirmed=[], run=lambda progress: None, choices=choices,
    )
    return picker.choice if task_mod.show(picker, gui=gui) else None


def run(state: State, args, gui: bool = False, noninteractive: bool = False) -> int:
    command = args.profile_command
    if command == "list":
        return list_profiles(state, show_all=args.all, as_json=args.json)
    if command is None:
        print(i18n.t("profile_usage"), file=sys.stderr)
        return 1
    if command == "apply" and getattr(args, "json", False):
        if not state.get("install_dir"):
            print(json.dumps({"error": i18n.t("err_not_installed")}, ensure_ascii=False))
            return 1
        if not args.profile:
            print(json.dumps({"error": i18n.t("err_profile_missing", "myfox profile apply <ID> --json")},
                             ensure_ascii=False))
            return 1
        return apply_json(state, args.profile)
    if not state.get("install_dir"):
        print(i18n.t("err_not_installed"), file=sys.stderr)
        return 1
    profile = getattr(args, "profile", None)
    if command != "new" and not profile:
        from .ui import _has_tty

        if noninteractive or not (gui or _has_tty()):
            # Without the ID, what there is to pick from.
            list_profiles(state, show_all=command == "import")
            print(file=sys.stderr)
            print(i18n.t("err_profile_missing", f"myfox profile {command} <ID>"), file=sys.stderr)
            return 1
        profile = pick(state, command, gui)
        if profile is None:
            return 1
    try:
        if command == "new":
            task = new_task(state, use=args.use)
        elif command == "apply":
            task = apply_task(state, profile)
        elif command == "use":
            task = use_task(state, profile, relaunch=args.relaunch)
        elif command == "remove":
            task = remove_task(state, profile, restore_sync=not args.no_restore_sync)
        else:
            task = import_task(state, profile, sync=args.sync, allow_downgrade=args.allow_downgrade,
                               use=args.use, name=args.name, move=args.move, open_after=args.open,
                               relaunch=args.relaunch)
    except Refused as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0 if task_mod.show(task, gui=gui, noninteractive=noninteractive) else 1
