#!/bin/bash
# build-themes.sh [out-dir] — zips themes/<name>/ into unsigned .xpi files
# (default out-dir: build/themes). Unsigned XPIs only install on a build
# with xpinstall.signatures.required=false (dev/sandbox use); the
# installer ships signed copies obtained separately through AMO.
set -eo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
out_dir="${1:-build/themes}"
mkdir -p "$out_dir"

for dir in themes/*/; do
    name=$(basename "$dir")
    out="$out_dir/$name.xpi"
    rm -f "$out"
    (cd "$dir" && zip -q -X -r "../../$out" .)
    echo "build-themes: $out"
done
