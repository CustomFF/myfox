#!/usr/bin/env bash
# Builds MyFox-Setup.exe (Windows x64) into the given directory (build/setup by
# default). The Python it fetches, version and checksum, comes from get.ps1;
# its version information from myfox/__init__.py.
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
out=$(mkdir -p "${1:-$root/build/setup}" && cd "${1:-$root/build/setup}" && pwd)

python_version=$(sed -n "s/^ *\$version = '\([0-9][0-9.]*\)'\$/\1/p" "$root/get.ps1")
python_sha256=$(sed -n "s/^ *'amd64' = '\([0-9a-f]\{64\}\)'\$/\1/p" "$root/get.ps1")
if [[ -z "$python_version" || -z "$python_sha256" ]]; then
  echo "build-setup-exe: no Python version or amd64 checksum found in get.ps1" >&2
  exit 1
fi
version=$(python3 "$root/scripts/changelog_to_json.py" --package-version)

cd "$root/setup"
go run ./rsrc -icon "$root/myfox/ui/assets/icon.ico" -version "$version" -o rsrc_windows_amd64.syso
trap 'rm -f "$root/setup/rsrc_windows_amd64.syso"' EXIT
GOOS=windows GOARCH=amd64 CGO_ENABLED=0 go build -trimpath \
  -ldflags "-H windowsgui -s -w -buildid= -X main.pythonVersion=$python_version -X main.pythonSHA256=$python_sha256" \
  -o "$out/MyFox-Setup.exe" .
echo "$out/MyFox-Setup.exe (Python $python_version)"
