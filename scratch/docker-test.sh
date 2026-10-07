#!/usr/bin/env bash
# docker-test.sh — MyFox in a clean container: get.sh -y, checks, uninstall.
#
# Usage:
#   scratch/docker-test.sh [--arch amd64|arm64] [--release] <image>...
#
#   --arch      the container's architecture (default: the host's). A foreign
#               one runs under qemu: on a Debian/Ubuntu host that's
#               `sudo apt install qemu-user-static`.
#   --release   install the published MyFox (get.sh from GitHub, the latest
#               core-* release) instead of this working copy.
#
# Examples:
#   scratch/docker-test.sh debian:13 ubuntu:26.04
#   scratch/docker-test.sh --arch arm64 debian:13
#   scratch/docker-test.sh --release fedora:latest
#
# Images with apt, dnf, zypper or pacman work. The script installs python3,
# curl and what a desktop has for Firefox to start (GTK 3, ALSA, X11-xcb), so
# the headless profile pinning runs as on a real system. Nothing outside the
# container is written: the working copy is mounted read-only.

set -eo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCH=""
RELEASE=0
IMAGES=()

usage() {
    sed -n '/^# Usage:/,/^# Images/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//' >&2
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --arch) ARCH="$2"; shift 2 ;;
        --arch=*) ARCH="${1#*=}"; shift ;;
        --release) RELEASE=1; shift ;;
        -h|--help) usage; exit 0 ;;
        -*) usage; exit 1 ;;
        *) IMAGES+=("$1"); shift ;;
    esac
done
[[ ${#IMAGES[@]} -gt 0 ]] || { usage; exit 1; }

case "$(uname -m)" in
    x86_64) HOST_ARCH=amd64 ;;
    aarch64) HOST_ARCH=arm64 ;;
    *) HOST_ARCH="$(uname -m)" ;;
esac
ARCH="${ARCH:-$HOST_ARCH}"
case "$ARCH" in
    amd64) QEMU=qemu-x86_64 ;;
    arm64) QEMU=qemu-aarch64 ;;
    *) echo "unsupported --arch: $ARCH (amd64 or arm64)" >&2; exit 1 ;;
esac
if [[ "$ARCH" != "$HOST_ARCH" && ! -e "/proc/sys/fs/binfmt_misc/$QEMU" ]]; then
    echo "no $QEMU emulation registered on this host: sudo apt install qemu-user-static" >&2
    exit 1
fi

# Runs inside the container, as root.
read -r -d '' INNER <<'EOF' || true
set -e
if command -v apt-get >/dev/null; then
    apt-get update -qq
    # Newer releases renamed some libraries to *t64; the old name is then a
    # virtual package apt won't pick by itself.
    pkgs=""
    for p in libgtk-3-0 libasound2; do
        if apt-cache show "${p}t64" >/dev/null 2>&1; then pkgs="$pkgs ${p}t64"; else pkgs="$pkgs $p"; fi
    done
    # shellcheck disable=SC2086
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3 curl ca-certificates libx11-xcb1 $pkgs >/dev/null
elif command -v dnf >/dev/null; then
    dnf install -y -q python3 curl gtk3 alsa-lib libX11-xcb >/dev/null
elif command -v zypper >/dev/null; then
    zypper -q -n install python3 curl libgtk-3-0 libasound2 libX11-xcb1 >/dev/null
elif command -v pacman >/dev/null; then
    pacman -Sy --noconfirm --quiet python curl gtk3 alsa-lib >/dev/null
else
    echo "no known package manager in this image" >&2; exit 1
fi
echo "== $(uname -m), $(. /etc/os-release && echo "$PRETTY_NAME"), $(python3 --version)"

cd /tmp
if [ "$MYFOX_RELEASE" = 1 ]; then
    curl -fsSL https://raw.githubusercontent.com/CustomFF/myfox/master/get.sh | sh -s -- -y
else
    MYFOX_BOOTSTRAP_URL=file:///src/bootstrap.py MYFOX_CORE_DIR=/src sh /src/get.sh -y
fi

export PATH="$HOME/.local/bin:$PATH"
echo "== myfox: $(myfox --version)"
python3 - <<'PY'
import json, os
d = json.load(open(os.path.expanduser("~/.local/state/myfox/state.json")))
print("== state:", {k: d.get(k) for k in ("firefox_version", "core_version", "tweaks_version", "install_hash")})
PY
echo "== firefox: $(myfox browser --version 2>&1 | tail -1)"
# Only the import: anything more needs a context and a display.
PYTHONPATH="$HOME/.local/share/myfox" python3 -c "import dearpygui.dearpygui" \
    && echo "== dearpygui: $(cat ~/.local/share/myfox/dearpygui/.myfox-wheel)" \
    || echo "== dearpygui: import failed"

myfox uninstall -y --remove-profile | tail -1
left=$(ls -d ~/.local/share/myfox ~/.local/bin/myfox ~/.local/state/myfox/state.json 2>/dev/null || true)
[ -z "$left" ] && echo "== removed cleanly" || { echo "== left behind: $left"; exit 1; }
EOF

status=0
for image in "${IMAGES[@]}"; do
    echo "### $image ($ARCH)"
    ref="$image"
    if [[ "$ARCH" != "$HOST_ARCH" ]]; then
        # By that platform's own manifest digest: pulling a foreign variant
        # by tag would replace the local host-arch image under the tag (and
        # the whole index's digest already belongs to that image).
        digest=$(docker buildx imagetools inspect "$image" --raw | ARCH="$ARCH" python3 -c '
import json, os, sys
for m in json.load(sys.stdin).get("manifests", []):
    if m.get("platform", {}).get("architecture") == os.environ["ARCH"]:
        print(m["digest"]); break')
        [[ -n "$digest" ]] || { echo "### $image has no $ARCH variant" >&2; status=1; continue; }
        name="$image"
        [[ "${image##*/}" == *:* ]] && name="${image%:*}"
        ref="$name@$digest"
    fi
    if ! docker run --rm --platform "linux/$ARCH" \
            -v "$ROOT:/src:ro" -e MYFOX_RELEASE="$RELEASE" -e LANG=C.UTF-8 \
            "$ref" sh -c "$INNER"; then
        echo "### $image ($ARCH): FAILED" >&2
        status=1
    fi
done
exit $status
