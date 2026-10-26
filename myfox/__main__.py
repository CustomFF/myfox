"""python3 -m myfox <browser|refresh|reinstall|uninstall|help> [options]

The installed `myfox` command. No `install`: the install form only ever
runs from bootstrap.py's "not installed yet" branch.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__, command, i18n, refresh, reinstall, task, uninstall
from .state import State

LOGO = Path(__file__).resolve().parent / "ui" / "assets" / "logo.txt"


def _common_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("-y", "--yes", action="store_true", dest="noninteractive")
    return p


def build_parser() -> argparse.ArgumentParser:
    common = _common_parser()
    parser = argparse.ArgumentParser(prog="myfox", description=i18n.t("usage_title"))
    parser.add_argument("--version", action="version", version=f"MyFox {__version__}")
    sub = parser.add_subparsers(dest="command")

    # "browser" is intercepted in main() before argparse ever sees it (see
    # comment there) — not registered as a subparser, or --help would list
    # a command whose own flags argparse can never correctly describe.

    refresh_parser = sub.add_parser("refresh", parents=[common], help=i18n.t("cmd_refresh"))
    refresh_parser.add_argument("--force", action="store_true")
    refresh_parser.add_argument("--gui", action="store_true", help="graphical window instead of the terminal")

    reinstall_parser = sub.add_parser("reinstall", parents=[common], help=i18n.t("cmd_reinstall"))
    reinstall_parser.add_argument("--gui", action="store_true", help="graphical window instead of the terminal")
    uninstall_parser = sub.add_parser("uninstall", parents=[common], help=i18n.t("cmd_uninstall"))
    uninstall_parser.add_argument("--gui", action="store_true", help="graphical window instead of the terminal")
    uninstall_parser.add_argument("--remove-profile", action="store_true",
                                  help="also delete the profile (bookmarks, history, passwords)")
    uninstall_parser.add_argument("--no-restore-sync", action="store_true",
                                  help="leave the Firefox account an import moved into MyFox where it is")
    command_parser = sub.add_parser("command", parents=[common], help=i18n.t("cmd_command"))
    command_parser.add_argument("action", nargs="?", choices=("on", "off"))
    command_parser.add_argument("--gui", action="store_true", help="graphical window instead of the terminal")
    command_parser.add_argument("--keep-backup", action="store_true",
                                help="off: leave the firefox it replaced as firefox.myfox-backup")
    command_parser.add_argument("--json", action="store_true",
                                help="for programs: no questions, the state as JSON on stdout")
    sub.add_parser("help", parents=[common], help=i18n.t("cmd_help"))
    return parser


def _not_installed() -> None:
    print(i18n.t("err_not_installed"), file=sys.stderr)


def cmd_browser(firefox_args: list[str], state: State) -> int:
    install_dir = state.get("install_dir")
    if not install_dir:
        _not_installed()
        return 1
    wrapper = os.path.join(install_dir, "firefox-myfox")
    target = wrapper if os.access(wrapper, os.X_OK) else os.path.join(install_dir, "firefox")
    os.execv(target, [target, *firefox_args])  # never returns on success


def cmd_uninstall(state: State, noninteractive: bool, gui: bool = False, remove_profile: bool = False,
                  restore_sync: bool = True) -> int:
    if not state.get("install_dir"):
        _not_installed()
        return 0
    return 0 if task.show(uninstall.build(state, remove_profile, restore_sync), gui=gui, noninteractive=noninteractive) else 1


def cmd_reinstall(state: State, noninteractive: bool = False, gui: bool = False) -> int:
    if not state.get("install_dir"):
        _not_installed()
        return 1
    return 0 if task.show(reinstall.build(state), gui=gui, noninteractive=noninteractive) else 1


def cmd_refresh(state: State, force: bool, gui: bool, noninteractive: bool) -> int:
    if not state.get("install_dir"):
        _not_installed()
        return 1
    return refresh.run(state, gui=gui, noninteractive=noninteractive, force=force)


def print_top_help(parser: argparse.ArgumentParser) -> None:
    # Composed by hand, not parser.print_help(): "browser" isn't a real
    # subparser (see build_parser), so argparse's own listing can't include
    # it.
    print(i18n.t("usage_title"))
    print()
    print(i18n.t("usage_usage"))
    print(f"  myfox browser [firefox args...]   {i18n.t('cmd_browser')}")
    print(f"  myfox browser --myfox-restart     {i18n.t('cmd_restart')}")
    print(f"  myfox refresh [--force] [--gui]   {i18n.t('cmd_refresh')}")
    print(f"  myfox reinstall [--gui]           {i18n.t('cmd_reinstall')}")
    print(f"  myfox uninstall [--remove-profile] [--no-restore-sync] [--gui]\n"
          f"                                    {i18n.t('cmd_uninstall')}")
    print(f"  myfox command [on|off] [--gui]    {i18n.t('cmd_command')}")
    print(f"  myfox help                        {i18n.t('cmd_help')}")


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    state = State()
    # Always from the system locale, never saved — no state key for it,
    # and no coupling with --lang (that picks Firefox's own language,
    # a completely different, much larger code space; see firefox.pick_lang).
    i18n.load()

    # Bypasses argparse entirely: Firefox's own flags (e.g. --new-window)
    # can start with "-", which argparse.REMAINDER fails to capture as the
    # first token (confirmed CPython limitation) — and these need passing
    # through untouched anyway.
    if argv and argv[0] == "browser":
        return cmd_browser(argv[1:], state)
    # Internal: a refresh that has just installed this code asks it to
    # rewrite the files it renders (refresh.sync_from_new_core).
    if argv == [refresh.SYNC_COMMAND]:
        refresh.sync_shortcut(state)
        return 0
    # Unlisted on purpose.
    if argv == ["why"]:
        print(LOGO.read_text(encoding="utf-8"), end="")
        return 0

    parser = build_parser()

    # Top-level -h/--help goes through the same hand-composed listing as
    # bare `myfox`/`myfox help` — argparse's own would still be missing
    # "browser" (see build_parser). `myfox refresh -h` etc. still gets
    # argparse's normal per-subcommand help, that one's accurate.
    if argv and argv[0] in ("-h", "--help"):
        print_top_help(parser)
        return 0

    args = parser.parse_args(argv)
    noninteractive = getattr(args, "noninteractive", False)

    if args.command in (None, "help"):
        print_top_help(parser)
        return 0
    if args.command == "refresh":
        return cmd_refresh(state, force=args.force, gui=args.gui, noninteractive=noninteractive)
    if args.command == "reinstall":
        return cmd_reinstall(state, noninteractive, gui=args.gui)
    if args.command == "command":
        if not state.get("install_dir"):
            if args.json:
                # A program asked: it gets JSON whatever happens.
                print(json.dumps({"error": i18n.t("err_not_installed")}, ensure_ascii=False))
            else:
                _not_installed()
            return 1
        return command.run(state, args.action, gui=args.gui, noninteractive=noninteractive, as_json=args.json,
                           keep_backup=args.keep_backup)
    if args.command == "uninstall":
        return cmd_uninstall(state, noninteractive, gui=args.gui, remove_profile=args.remove_profile,
                             restore_sync=not args.no_restore_sync)

    print_top_help(parser)
    return 1


if __name__ == "__main__":
    sys.exit(main())
