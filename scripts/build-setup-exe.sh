#!/usr/bin/env bash
# Builds MyFox-Setup.exe (Windows x64) into the given directory (build/setup by
# default) with MinGW-w64 (Debian/Ubuntu: gcc-mingw-w64-x86-64). The Python it
# fetches, version and checksum, comes from get.ps1; its version information
# from myfox/__init__.py.
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
out=$(mkdir -p "${1:-$root/build/setup}" && cd "${1:-$root/build/setup}" && pwd)
cc=${MINGW_PREFIX:-x86_64-w64-mingw32-}

python_version=$(sed -n "s/^ *\$version = '\([0-9][0-9.]*\)'\$/\1/p" "$root/get.ps1")
python_sha256=$(sed -n "s/^ *'amd64' = '\([0-9a-f]\{64\}\)'\$/\1/p" "$root/get.ps1")
if [[ -z "$python_version" || -z "$python_sha256" ]]; then
  echo "build-setup-exe: no Python version or amd64 checksum found in get.ps1" >&2
  exit 1
fi
version=$(python3 "$root/scripts/changelog_to_json.py" --package-version)
if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "build-setup-exe: version $version is not major.minor.patch" >&2
  exit 1
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
printf '#define VERSION_COMMAS %s,0\n#define VERSION_TEXT "%s"\n' "${version//./,}" "$version" > "$work/version.h"

"${cc}windres" -I "$work" -I "$root/setup" -I "$root/myfox/ui/assets" \
  "$root/setup/setup.rc" -O coff -o "$work/resources.o"
"${cc}gcc" -std=c11 -Os -Wall -Wextra -Werror -municode -mwindows -static-libgcc \
  -DUNICODE -D_UNICODE -D_WIN32_WINNT=0x0A00 \
  "-DPYTHON_VERSION=\"$python_version\"" "-DPYTHON_SHA256=\"$python_sha256\"" \
  "$root/setup/setup.c" "$work/resources.o" \
  -s -Wl,--no-insert-timestamp -lwinhttp -lbcrypt -lcomctl32 \
  -o "$out/MyFox-Setup.exe"
echo "$out/MyFox-Setup.exe (Python $python_version)"
