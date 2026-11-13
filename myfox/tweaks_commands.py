"""`myfox tweaks …`: which version of the tweaks this install runs.

The tweaks are tagged by the Firefox beta major they were made on (161.3);
they are checked on that beta and on the stable before it (160), so a
Firefox more than one major behind its tweaks may misbehave. `use` puts
an older version (or the latest again) in place and pins it: refresh
leaves pinned tweaks alone. A Firefox major is a version too, its newest
release: the tweaks have no fixes for an old major once the next has begun.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from . import apply, changelog, firefox, i18n, refresh, sources, tweaks
from . import task as task_mod
from .install_form import Progress
from .state import State


def firefox_major(state: State) -> int | None:
    install_dir = state.get("install_dir")
    return tweaks.major(firefox.local_version(Path(install_dir))) if install_dir else None


def best_major(found: list[str], ff_major: int | None) -> int | None:
    """The tweaks that fit that Firefox: those made on its beta, or on the
    next one's (checked on this stable too), whichever is newest."""
    if ff_major is None:
        return None
    return max((m for m in map(tweaks.major, found) if m is not None and m <= ff_major + 1), default=None)


def too_new(tag: str | None, ff_major: int | None) -> bool:
    m = tweaks.major(tag) if tag else None
    return m is not None and ff_major is not None and m > ff_major + 1


def _warnings(tag: str, ff_major: int | None, best: int | None) -> list[str]:
    m = tweaks.major(tag)
    if ff_major is None or m is None:
        return []
    if m > ff_major + 1:
        return [i18n.t("tweaks_warn_too_new", changelog.display(tag), ff_major, best or ff_major)]
    if best is not None and m < best:
        return [i18n.t("tweaks_warn_too_old", changelog.display(tag), ff_major)]
    return []


def status(state: State) -> int:
    """`myfox tweaks`: the installed version, the pin, the Firefox, and
    what's newer (if GitHub answers)."""
    current, pin, ff_major = state.get("tweaks_version"), tweaks.pinned(state), firefox_major(state)
    install_dir = state.get("install_dir")
    ff = firefox.local_version(Path(install_dir)) if install_dir else None
    shown = changelog.display(current)
    if pin:
        shown = i18n.t("tweaks_pinned", shown)
    rows = [(i18n.t("refresh_track_tweaks"), shown), ("Firefox:", ff or "—")]
    width = max(len(label) for label, _ in rows)
    for label, value in rows:
        print(f"{label.ljust(width)}  {value}")
    try:
        latest = tweaks.latest_release()
    except OSError:
        latest = None
    if latest is not None and changelog.is_newer(latest.tag, current):
        print(i18n.t("tweaks_latest", changelog.display(latest.tag),
                     "myfox tweaks use latest" if pin else "myfox refresh"))
    if too_new(current, ff_major):
        print(i18n.t("tweaks_hint_older", changelog.display(current), ff_major, f"myfox tweaks use {ff_major}"))
    print(i18n.t("tweaks_hint_versions", "myfox tweaks versions"))
    return 0


def versions(state: State, show_all: bool = False, as_json: bool = False) -> int:
    """`myfox tweaks versions`: a line per Firefox major (its newest release;
    --all: every one); --json every release as records."""
    current, pin, ff_major = state.get("tweaks_version"), tweaks.pinned(state), firefox_major(state)
    try:
        found = tweaks.tags()
    except OSError as exc:
        text = i18n.t("tweaks_list_failed", getattr(exc, "reason", exc))
        print(json.dumps({"error": text}, ensure_ascii=False) if as_json else text,
              file=sys.stdout if as_json else sys.stderr)
        return 1
    best = best_major(found, ff_major)
    if as_json:
        print(json.dumps([{"version": t, "firefox": tweaks.major(t), "installed": t == current, "pinned": t == pin,
                           "fits": tweaks.major(t) == best} for t in found], ensure_ascii=False))
        return 0
    if not found:
        print(i18n.t("tweaks_list_none"))
        return 1
    by_major: dict[int, list[str]] = {}
    for tag in found:
        by_major.setdefault(tweaks.major(tag), []).append(tag)
    head = (i18n.t("tweaks_col_firefox"), i18n.t("tweaks_col_versions" if show_all else "tweaks_col_latest"))
    rows = []
    for m, tags in by_major.items():
        # The installed one is always shown, even when it isn't its major's newest.
        shown = tags if show_all else tags[:1] + [t for t in tags[1:] if t == current]
        rows.append((current in tags, str(m), ", ".join(_marked(t, current, pin) for t in shown),
                     i18n.t("tweaks_fits") if m == best else ""))
    width = max(len(r[1]) for r in rows + [(False, head[0], "", "")])
    width2 = max(len(r[2]) for r in rows + [(False, "", head[1], "")])
    print(f"  {head[0].ljust(width)}  {head[1]}")
    for mine, m, shown, note in rows:
        print(f"{'●' if mine else ' '} {m.ljust(width)}  {shown.ljust(width2)}  {note}".rstrip())
    print()
    if not show_all:
        print(i18n.t("tweaks_list_all", "myfox tweaks versions --all"))
    print(i18n.t("tweaks_list_use", "myfox tweaks use <N>", "myfox tweaks use latest"))
    return 0


def _marked(tag: str, current: str | None, pin: str | None) -> str:
    if tag == pin:
        return i18n.t("tweaks_pinned", changelog.display(tag))
    if tag == current:
        return i18n.t("tweaks_installed", changelog.display(tag))
    return changelog.display(tag)


def _refused(state: State) -> str | None:
    if os.environ.get("MYFOX_TWEAKS_LOCAL"):
        return i18n.t("tweaks_local", "MYFOX_TWEAKS_LOCAL")
    if not state.get("tweaks", True) or not sources.myfox_dirs(state):
        return i18n.t("tweaks_off")
    return None


def build(state: State, release: tweaks.Release, pin: str | None, wanted: str,
          found: list[str] = ()) -> task_mod.Task:
    """The confirm-then-run dialog of `myfox tweaks use`."""
    install_dir = Path(state.get("install_dir"))
    current, ff_major = state.get("tweaks_version"), firefox_major(state)
    # The running tweaks restart Firefox, as after a refresh.
    running = firefox.running_pids(install_dir) and not changelog.is_newer(refresh.RESTART_SINCE_TWEAKS, current)
    options = [task_mod.Option(i18n.t("refresh_restart_firefox"), True)] if running else []
    rows = [(i18n.t("refresh_track_tweaks"),
             i18n.t("refresh_version_change", changelog.display(current), changelog.display(release.tag))),
            (i18n.t("tweaks_row_pin"), i18n.t("tweaks_pin_on", changelog.display(pin)) if pin
             else i18n.t("tweaks_pin_off"))]
    if ff_major is not None:
        rows.append(("Firefox:", firefox.local_version(install_dir) or "—"))
    warnings = _warnings(release.tag, ff_major, best_major(list(found), ff_major))

    def run(progress: Progress) -> None:
        progress(i18n.t("progress_refresh_tweaks_download", changelog.display(release.tag)), 0.0)
        installed = tweaks.install(release)
        progress(i18n.t("progress_refresh_tweaks_apply"), 0.5)
        live = State()
        apply.reapply_tweaks(install_dir, sources.myfox_dirs(live), live)
        live.set("tweaks_version", installed)
        live.set(tweaks.PIN, pin)
        live.save()
        refresh.forget_updates(live, [refresh.JSON_NAMES["tweaks_version"]])
        progress(i18n.t("progress_refresh_done"), 1.0)
        if options and options[0].value:
            firefox.request_restart(install_dir)

    return task_mod.Task(
        title=i18n.t("tweaks_title"),
        subtitle=i18n.t("tweaks_subtitle"),
        rows=rows,
        heading=i18n.t("tweaks_warning") if warnings else "",
        lines=warnings,
        options=options,
        action=i18n.t("tweaks_install"),
        unconfirmed=[i18n.t("needs_yes_tweaks", f"myfox tweaks use {wanted} -y")],
        run=run,
        closes=lambda: bool(options and options[0].value),
    )


def use(state: State, wanted: str | None, noninteractive: bool = False) -> int:
    """`myfox tweaks use <latest|N|N.M>`: installs that version and pins it
    (latest: unpins). Only pinning or unpinning what's installed asks nothing."""
    if not wanted:
        print(i18n.t("tweaks_use_what", "myfox tweaks versions"), file=sys.stderr)
        return 1
    wanted = wanted.strip()
    refused = _refused(state)
    if refused:
        print(refused, file=sys.stderr)
        return 1
    try:
        found = tweaks.tags()
        release = tweaks.resolve(wanted, found)
    except OSError as exc:
        print(i18n.t("tweaks_list_failed", getattr(exc, "reason", exc)), file=sys.stderr)
        return 1
    if release is None:
        print(i18n.t("tweaks_unknown", wanted, "{}.{}".format(*tweaks.OLDEST),
                     "myfox tweaks versions"), file=sys.stderr)
        return 1
    pin = None if wanted == "latest" else release.tag
    if release.tag == state.get("tweaks_version"):
        if pin == tweaks.pinned(state):
            print(i18n.t("tweaks_already", changelog.display(release.tag)))
        else:
            state.set(tweaks.PIN, pin)
            state.save()
            print(i18n.t("tweaks_now_pinned" if pin else "tweaks_now_unpinned", changelog.display(release.tag)))
        return 0
    return 0 if task_mod.show(build(state, release, pin, wanted, found), noninteractive=noninteractive) else 1


def run(state: State, args, noninteractive: bool = False) -> int:
    if not state.get("install_dir"):
        print(i18n.t("err_not_installed"), file=sys.stderr)
        return 1
    if args.tweaks_command == "versions":
        return versions(state, show_all=args.all, as_json=args.json)
    if args.tweaks_command == "use":
        return use(state, args.version, noninteractive=noninteractive)
    return status(state)
