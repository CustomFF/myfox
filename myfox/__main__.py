"""python3 -m myfox <browser|refresh|reinstall|uninstall|help> [options]

Installed entry point — replaces bin/myfox-core's option tables + case
dispatch. No `install`: the wizard only ever runs from bootstrap.py's own
"not installed yet" branch (see docs/python-rewrite-plan.md), never as a
subcommand here.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from . import addons, apply, firefox, i18n, profiles, version
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


def _reapply_tweaks(install_dir: Path, profile_dir: Path | None, state: State) -> None:
    """autoconfig/chrome/theme-pref from this local copy — never a network
    fetch of a *different* copy (that's refresh's job once the tweaks-track
    download exists; see cmd_refresh). Themes are the one exception: they're
    built+signed in CustomFF/tweaks' own CI, not bundled here, so
    fetch_themes() always goes to its releases (or a local tweaks checkout
    via MYFOX_TWEAKS_LOCAL, dev use)."""
    apply.apply_autoconfig(install_dir)
    if profile_dir is None:
        return
    apply.apply_chrome(profile_dir)
    apply.apply_theme_pref(profile_dir, state.get("theme", "dark"))
    addons.fetch_themes(profile_dir, local_dir=os.environ.get("MYFOX_TWEAKS_LOCAL"))
    if state.get("opt_plasma") and addons.is_plasma_session():
        addons.apply_amo_addons(profile_dir, [addons.MYFOX_ADDON_PLASMA])
    if state.get("opt_bl", True):
        apply.apply_bookmarklets(profile_dir, local_dir=os.environ.get("MYFOX_DDBLM_LOCAL"))


def cmd_uninstall(state: State, ui, noninteractive: bool) -> int:
    install_dir = state.get("install_dir")
    if not install_dir:
        ui.message(i18n.t("err_not_installed"))
        return 0
    if not noninteractive and not ui.confirm(i18n.t("confirm_uninstall", install_dir), default=False):
        return 1

    profile_dir = state.get("profile_dir")
    if profile_dir:
        profiles.remove_myfox_section(Path(profile_dir))
    install_hash = state.get("install_hash")
    if install_hash:
        profiles.unpin_install(install_hash)
    shutil.rmtree(install_dir, ignore_errors=True)

    state.clear()
    state.save()
    ui.message(i18n.t("uninstall_done"))
    return 0


def cmd_reinstall(state: State, ui) -> int:
    install_dir = state.get("install_dir")
    if not install_dir:
        ui.message(i18n.t("err_not_installed"))
        return 1
    install_dir = Path(install_dir)

    with ui.spin(i18n.t("reinstalling_firefox")):
        new_version = firefox.install_tarball(install_dir, state.get("lang", "en-US"), state.get("channel", "stable"))

    profile_dir = state.get("profile_dir")
    _reapply_tweaks(install_dir, Path(profile_dir) if profile_dir else None, state)

    state.set("firefox_version", new_version)
    state.save()
    ui.message(i18n.t("reinstall_done", new_version))
    return 0


def cmd_refresh(state: State, ui, force: bool) -> int:
    install_dir = state.get("install_dir")
    if not install_dir:
        ui.message(i18n.t("err_not_installed"))
        return 1
    install_dir = Path(install_dir)

    if force:
        profile_dir = state.get("profile_dir")
        _reapply_tweaks(install_dir, Path(profile_dir) if profile_dir else None, state)
        ui.message(i18n.t("refresh_forced_tweaks_done"))
    else:
        new_tweaks = version.tweaks_update_available(state.get("tweaks_version"))
        ui.message(
            i18n.t("refresh_tweaks_update_found_not_wired", new_tweaks)
            if new_tweaks else i18n.t("refresh_tweaks_up_to_date")
        )

    # Self-update (replacing ~/.local/share/myfox) isn't wired up yet either
    # way — building that now means inventing pass 5's release format early
    # (see docs/python-rewrite-plan.md); the tag check itself is already real.
    new_core = version.core_update_available(state.get("core_version"))
    ui.message(
        i18n.t("refresh_core_update_found_not_wired", new_core)
        if new_core else i18n.t("refresh_core_up_to_date")
    )
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
    # Always from the system locale, never saved — no state key for it,
    # and no coupling with --lang (that picks Firefox's own language,
    # a completely different, much larger code space; see firefox.pick_lang).
    i18n.load()

    # Bypasses argparse entirely: Firefox's own flags (e.g. --new-window)
    # can start with "-", which argparse.REMAINDER fails to capture as the
    # first token (confirmed CPython limitation) — and these need passing
    # through untouched anyway.
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
    noninteractive = getattr(args, "noninteractive", False)
    ui = get_backend(force_gui=getattr(args, "gui", False), noninteractive=noninteractive)

    if args.command in (None, "help"):
        print_top_help(parser)
        return 0
    if args.command == "refresh":
        return cmd_refresh(state, ui, force=args.force)
    if args.command == "reinstall":
        return cmd_reinstall(state, ui)
    if args.command == "uninstall":
        return cmd_uninstall(state, ui, noninteractive)

    print_top_help(parser)
    return 1


if __name__ == "__main__":
    sys.exit(main())
