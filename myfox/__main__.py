"""python3 -m myfox <browser|refresh|reinstall|uninstall|help> [options]

Installed entry point — replaces bin/myfox-core's option tables + case
dispatch. No `install`: the wizard only ever runs from bootstrap.py's own
"not installed yet" branch (see docs/python-rewrite-plan.md), never as a
subcommand here.
"""

from __future__ import annotations

import argparse
import os
import sys

from . import i18n
from .state import State
from .ui import get_backend


def _common_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("-y", "--yes", action="store_true", dest="noninteractive")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--gui", action="store_true", help="force the graphical backend")
    return p


def build_parser() -> argparse.ArgumentParser:
    common = _common_parser()
    parser = argparse.ArgumentParser(prog="myfox", description=i18n.t("usage_title"))
    sub = parser.add_subparsers(dest="command")

    # "browser" is intercepted in main() before argparse ever sees it (see
    # comment there) — not registered as a subparser, or --help would list
    # a command whose own flags argparse can never correctly describe.

    sub.add_parser("refresh", parents=[common], help=i18n.t("cmd_refresh")) \
        .add_argument("--force", action="store_true")

    sub.add_parser("reinstall", parents=[common], help=i18n.t("cmd_reinstall"))
    sub.add_parser("uninstall", parents=[common], help=i18n.t("cmd_uninstall"))
    sub.add_parser("help", parents=[common], help=i18n.t("cmd_help"))
    return parser


def cmd_browser(firefox_args: list[str], state: State, ui) -> int:
    install_dir = state.get("install_dir")
    if not install_dir:
        ui.message(i18n.t("err_not_installed"))
        return 1
    wrapper = os.path.join(install_dir, "firefox-myfox")
    target = wrapper if os.access(wrapper, os.X_OK) else os.path.join(install_dir, "firefox")
    os.execv(target, [target, *firefox_args])  # never returns on success


def _not_implemented(name: str, ui) -> int:
    ui.message(i18n.t("not_implemented", name))
    return 0


def print_top_help(parser: argparse.ArgumentParser) -> None:
    # Composed by hand, not parser.print_help(): "browser" isn't a real
    # subparser (see build_parser), so argparse's own listing can't include
    # it. Wording is a placeholder — full copy pass is later (see plan).
    print(i18n.t("usage_title"))
    print()
    print(i18n.t("usage_usage"))
    print(f"  myfox browser [firefox args...]   {i18n.t('cmd_browser')}")
    print(f"  myfox refresh [--force]           {i18n.t('cmd_refresh')}")
    print(f"  myfox reinstall                   {i18n.t('cmd_reinstall')}")
    print(f"  myfox uninstall                   {i18n.t('cmd_uninstall')}")
    print(f"  myfox help                        {i18n.t('cmd_help')}")


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    state = State()
    i18n.load(state.get("opt_lang"))

    # Handed off before argparse ever sees it: Firefox's own flags (e.g.
    # --new-window) can start with "-" as the very first token, which
    # argparse.REMAINDER fails to capture (a known CPython argparse
    # limitation, confirmed independent of this parser's own setup) — and
    # "browser" needs to pass them through completely untouched anyway,
    # exactly like get.sh's `exec "$install_dir/firefox-myfox" "$@"` did.
    if argv and argv[0] == "browser":
        ui = get_backend(noninteractive=True)
        return cmd_browser(argv[1:], state, ui)

    parser = build_parser()

    # Top-level -h/--help goes through the same hand-composed listing as
    # bare `myfox`/`myfox help` — argparse's own would still be missing
    # "browser" (see build_parser). `myfox refresh -h` etc. still gets
    # argparse's normal per-subcommand help, that one's accurate.
    if argv and argv[0] in ("-h", "--help"):
        print_top_help(parser)
        return 0

    args = parser.parse_args(argv)
    ui = get_backend(force_gui=getattr(args, "gui", False), noninteractive=getattr(args, "noninteractive", False))

    if args.command in (None, "help"):
        print_top_help(parser)
        return 0
    if args.command in ("refresh", "reinstall", "uninstall"):
        return _not_implemented(args.command, ui)

    print_top_help(parser)
    return 1


if __name__ == "__main__":
    sys.exit(main())
