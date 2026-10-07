#!/usr/bin/env python3
"""CHANGELOG.md -> changelog.json (the core release asset `myfox refresh` reads).

Usage:
    changelog_to_json.py [-o FILE]       validate CHANGELOG.md, write changelog.json
                                         (stdout by default)
    changelog_to_json.py --check VERSION fail unless CHANGELOG.md has a
                                         non-empty section for VERSION
    changelog_to_json.py --notes VERSION print VERSION's section (release notes)
    changelog_to_json.py --package-version
                                         print myfox/__init__.py's __version__

Every mode validates the whole file first. --changelog PATH reads another
file (for testing).

CHANGELOG.md: sections '## <major>.<minor>.<patch> — <YYYY-MM-DD>', newest
first, each holding only '- ' items; an optional '## Unreleased' goes on top
and is left out of the JSON. changelog.json is {"versions": [{"version",
"date", "changes": [...]}]}, newest first — the same format as the tweaks'
(CustomFF/tweaks), which this script was adapted from.
"""
import argparse
import datetime
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
HEADER_RE = re.compile(r"^## (\S+) — (\S+)$")


class ChangelogError(Exception):
    pass


def version_key(version):
    return tuple(int(part) for part in version.split("."))


def parse(path):
    """Returns the released versions, newest first:
    [{"version", "date", "changes": [...]}]. ## Unreleased is skipped."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError as e:
        raise ChangelogError(f"cannot read {path}: {e}")

    errors = []
    versions = []
    # The section being read: None before the first one; a throwaway dict for
    # ## Unreleased and for a broken header (their items go nowhere).
    current = None
    seen_title = False
    seen_unreleased = False
    for n, line in enumerate(lines, 1):
        where = f"{os.path.basename(path)}:{n}"
        if not line.strip():
            continue
        if line.startswith("## "):
            if line == "## Unreleased":
                if versions or seen_unreleased:
                    errors.append(f"{where}: '## Unreleased' must be the first section")
                seen_unreleased = True
                current = {"changes": []}
                continue
            m = HEADER_RE.match(line)
            if not m:
                errors.append(f"{where}: bad header {line!r}, expected '## <major>.<minor>.<patch> — <YYYY-MM-DD>'")
                current = {"changes": []}
                continue
            version, date = m.groups()
            if not VERSION_RE.match(version):
                errors.append(f"{where}: bad version {version!r}, expected <major>.<minor>.<patch>")
            try:
                if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
                    raise ValueError
                datetime.date.fromisoformat(date)
            except ValueError:
                errors.append(f"{where}: bad date {date!r}, expected YYYY-MM-DD")
            current = {"version": version, "date": date, "changes": [], "line": where}
            versions.append(current)
        elif line.startswith("- "):
            if current is None:
                errors.append(f"{where}: list item before any '## ' section")
            elif line[2:].strip():
                current["changes"].append(line[2:].strip())
            else:
                errors.append(f"{where}: empty list item")
        elif line.startswith("# ") and not seen_title and current is None:
            seen_title = True
        else:
            errors.append(f"{where}: unexpected line {line!r} (sections hold only '- ' items)")

    for v in versions:
        if not v["changes"]:
            errors.append(f"{v['line']}: section {v['version']} has no items")
    valid = [v for v in versions if VERSION_RE.match(v["version"])]
    for newer, older in zip(valid, valid[1:]):
        if version_key(newer["version"]) <= version_key(older["version"]):
            errors.append(f"{older['line']}: {older['version']} must be older than "
                          f"{newer['version']} above it (newest first, no duplicates)")
    if errors:
        raise ChangelogError("\n".join(errors))
    return [{"version": v["version"], "date": v["date"], "changes": v["changes"]} for v in versions]


def find(versions, tag):
    for v in versions:
        if v["version"] == tag:
            return v
    raise ChangelogError(f"CHANGELOG.md has no section for {tag}")


def package_version():
    path = os.path.join(ROOT, "myfox", "__init__.py")
    try:
        with open(path, encoding="utf-8") as f:
            m = re.search(r'^__version__\s*=\s*"([^"]+)"', f.read(), re.M)
    except OSError as e:
        raise ChangelogError(f"cannot read {path}: {e}")
    if not m:
        raise ChangelogError(f"no __version__ in {path}")
    return m.group(1)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--changelog", default=os.path.join(ROOT, "CHANGELOG.md"))
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--check", metavar="VERSION")
    mode.add_argument("--notes", metavar="VERSION")
    mode.add_argument("--package-version", action="store_true")
    p.add_argument("-o", "--output", metavar="FILE")
    args = p.parse_args()

    try:
        if args.package_version:
            print(package_version())
            return
        versions = parse(args.changelog)
        if args.check:
            find(versions, args.check)
        elif args.notes:
            for change in find(versions, args.notes)["changes"]:
                print(f"- {change}")
        else:
            text = json.dumps({"versions": versions}, ensure_ascii=False, indent=2) + "\n"
            if args.output:
                with open(args.output, "w", encoding="utf-8") as f:
                    f.write(text)
            else:
                sys.stdout.write(text)
    except ChangelogError as e:
        print(f"changelog_to_json: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
