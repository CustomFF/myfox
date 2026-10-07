#!/bin/sh
# build-core-dist.sh [out-dir] — the core-* release assets: myfox-core.tar.gz
# (myfox/ without tests at the archive root) and changelog.json. The tweaks come from
# CustomFF/tweaks' own releases, not from here.
set -e
root=$(cd "$(dirname "$0")/.." && pwd)
out=${1:-$root/dist}
mkdir -p "$out"
python3 "$root/scripts/changelog_to_json.py" -o "$out/changelog.json"
tar -czf "$out/myfox-core.tar.gz" -C "$root" \
    --exclude='__pycache__' --exclude='*.pyc' --exclude='myfox/tests' \
    myfox
echo "$out/myfox-core.tar.gz"
echo "$out/changelog.json"
