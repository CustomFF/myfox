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

from . import __version__, command, i18n, profile_commands, refresh, reinstall, task, uninstall
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
    refresh_parser.add_argument("--json", action="store_true",
                                help="no questions, the result as one JSON line (for about:myfox)")

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
    profile_parser = sub.add_parser("profile", parents=[common], help=i18n.t("cmd_profile"))
    profile_sub = profile_parser.add_subparsers(dest="profile_command")
    list_parser = profile_sub.add_parser("list", help=i18n.t("cmd_profile_list"))
    list_parser.add_argument("--all", action="store_true", help="also other Firefoxes' profiles (import only)")
    list_parser.add_argument("--json", action="store_true", help="for programs: the profiles as JSON on stdout")
    gui = {"action": "store_true", "help": "graphical window instead of the terminal"}
    new_parser = profile_sub.add_parser("new", parents=[common], help=i18n.t("cmd_profile_new"))
    new_parser.add_argument("--use", action="store_true", help="our Firefox opens it from now on")
    new_parser.add_argument("--gui", **gui)
    import_parser = profile_sub.add_parser("import", parents=[common], help=i18n.t("cmd_profile_import"))
    import_parser.add_argument("profile", nargs="?", help="ID, name or folder (myfox profile list --all)")
    import_parser.add_argument("--sync", choices=("none", "copy", "move"), default="none",
                               help="the Firefox account: leave behind (default), copy, or move into the copy")
    import_parser.add_argument("--allow-downgrade", action="store_true",
                               help="import a profile a newer Firefox last opened, at your own risk")
    import_parser.add_argument("--use", action="store_true", help="our Firefox opens it from now on")
    import_parser.add_argument("--gui", **gui)
    for name, help_key in (("apply", "cmd_profile_apply"), ("use", "cmd_profile_use"),
                           ("remove", "cmd_profile_remove")):
        p = profile_sub.add_parser(name, parents=[common], help=i18n.t(help_key))
        p.add_argument("profile", nargs="?", help="ID or name (myfox profile list)")
        p.add_argument("--gui", **gui)
        if name == "apply":
            p.add_argument("--json", action="store_true", help="for programs: no questions, the result as JSON")
        if name == "remove":
            p.add_argument("--no-restore-sync", action="store_true",
                           help="leave the Firefox account an import moved into it where it is")
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
    print(f"  myfox profile list [--all] [--json]\n"
          f"                                    {i18n.t('cmd_profile_list')}")
    print(f"  myfox profile new [--use]         {i18n.t('cmd_profile_new')}")
    print(f"  myfox profile import <ID|folder> [--sync none|copy|move] [--allow-downgrade] [--use]\n"
          f"                                    {i18n.t('cmd_profile_import')}")
    print(f"  myfox profile apply <ID>          {i18n.t('cmd_profile_apply')}")
    print(f"  myfox profile use <ID>            {i18n.t('cmd_profile_use')}")
    print(f"  myfox profile remove <ID> [--no-restore-sync]\n"
          f"                                    {i18n.t('cmd_profile_remove')}")
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
        if args.json:
            if not state.get("install_dir"):
                print(json.dumps({"error": i18n.t("err_not_installed")}, ensure_ascii=False))
                return 1
            return refresh.run_json(state, force=args.force)
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
    if args.command == "profile":
        return profile_commands.run(state, args, gui=getattr(args, "gui", False),
                                    noninteractive=noninteractive)
    if args.command == "uninstall":
        return cmd_uninstall(state, noninteractive, gui=args.gui, remove_profile=args.remove_profile,
                             restore_sync=not args.no_restore_sync)

    print_top_help(parser)
    return 1


if __name__ == "__main__":
    sys.exit(main())
