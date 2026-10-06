#!/bin/sh
# build-core-dist.sh [out-dir] — myfox-core.tar.gz for a core-* release:
# myfox/ (without tests), autoconfig/, chrome/ at the archive root.
set -e
root=$(cd "$(dirname "$0")/.." && pwd)
out=${1:-$root/dist}
mkdir -p "$out"
tar -czf "$out/myfox-core.tar.gz" -C "$root" \
    --exclude='__pycache__' --exclude='*.pyc' --exclude='myfox/tests' \
    myfox autoconfig chrome
echo "$out/myfox-core.tar.gz"
