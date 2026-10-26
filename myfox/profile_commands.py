"""`myfox profile …`: the profiles MyFox can see and what it does with them.

list shows the ones related to MyFox (ours, made with `firefox -p` from our
install, never run); --all adds every other Firefox's, which can only be
imported. The ID column is what the other subcommands take.
"""

from __future__ import annotations

import json
import shlex
import sys
import unicodedata
from pathlib import Path

from . import i18n, importer, paths, sources
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


def _status(p: sources.Profile, used: Path | None, found: list[sources.Profile]) -> list[str]:
    parts = []
    if used is not None and p.path == used:
        parts.append(i18n.t("profile_status_used"))
    if p.owner == sources.MYFOX:
        origin = importer.read_origin(p.path)
        if origin is not None:
            source = Path(origin["source"])
            shown = next((q.id for q in found if q.path == source), paths.shown(source))
            parts.append(i18n.t("profile_status_imported", shown))
    elif p.owner == sources.OURS:
        parts.append(i18n.t("profile_status_ours"))
    elif p.owner == sources.UNUSED:
        parts.append(i18n.t("profile_status_unused"))
    else:
        parts.append(i18n.t({sources.SNAP: "profile_status_snap", sources.FLATPAK: "profile_status_flatpak"}
                            .get(p.store, "profile_status_foreign")))
    if sources.in_use(p):
        parts.append(i18n.t("profile_status_open"))
    return parts


def _record(p: sources.Profile, used: Path | None) -> dict:
    origin = importer.read_origin(p.path) if p.owner == sources.MYFOX else None
    return {
        "id": p.id, "name": p.name, "path": str(p.path), "store": p.store or "myfox", "owner": p.owner,
        "tweaks": p.owner == sources.MYFOX, "used": used is not None and p.path == used, "open": sources.in_use(p),
        "last_version": p.last_version, "imported_from": origin["source"] if origin else None,
    }


def list_profiles(state: State, show_all: bool = False, as_json: bool = False) -> int:
    found = sources.listing(_install_dir(state))
    shown = found if show_all else [p for p in found if p.related]
    used = Path(state.get("profile_dir")) if state.get("profile_dir") else None
    if as_json:
        print(json.dumps([_record(p, used) for p in shown], ensure_ascii=False, indent=2))
        return 0
    if not shown:
        print(i18n.t("profile_list_none"))
    else:
        head = [i18n.t("profile_col_id"), i18n.t("profile_col_name"), i18n.t("profile_col_tweaks"),
                i18n.t("profile_col_status")]
        rows = [[p.id, p.name, i18n.t("summary_yes" if p.owner == sources.MYFOX else "summary_no"),
                 ", ".join(_status(p, used, found))] for p in shown]
        widths = [max(_width(r[i]) for r in [head] + rows) for i in range(3)]
        for r in [head] + rows:
            print("  ".join(_pad(cell, widths[i]) for i, cell in enumerate(r[:3])) + "  " + r[3])
    hidden = len(found) - len(shown)
    if hidden:
        print()
        print(i18n.t("profile_list_hidden", hidden, "myfox profile list --all"))
    return 0


def run(state: State, args) -> int:
    if args.profile_command == "list":
        return list_profiles(state, show_all=args.all, as_json=args.json)
    print(i18n.t("profile_usage"), file=sys.stderr)
    return 1
