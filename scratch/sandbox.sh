#!/usr/bin/env bash
# sandbox.sh — runs a command with its own $HOME and every $XDG_* directory
# under <sandbox-dir>, so MyFox never touches the real browser, profile,
# state, desktop entries or ~/.local/share/myfox.
#
#   state          → <sandbox>/state/myfox/state.json
#   profiles       → <sandbox>/config/mozilla/firefox (or <sandbox>/home/.mozilla)
#   MyFox, Firefox → <sandbox>/data/myfox
#   desktop entry  → <sandbox>/data/applications
#   `myfox`        → <sandbox>/home/.local/bin/myfox
#
# Usage:
#   scratch/sandbox.sh <sandbox-dir> [--fresh] -- <command...>
#
# Examples:
#   scratch/sandbox.sh /tmp/mf --fresh -- python3 -m myfox.wizard -y
#   scratch/sandbox.sh /tmp/mf -- bash -c 'cd /tmp && ~/.local/bin/myfox refresh'
#   scratch/sandbox.sh /tmp/mf --fresh -- bash -c "cat $PWD/get.sh | \
#       MYFOX_BOOTSTRAP_URL=file://$PWD/bootstrap.py MYFOX_CORE_DIR=$PWD sh -s -- -y"
#
# The terminal stays interactive (the TUI works); only file writes are redirected.
# --fresh wipes <sandbox-dir> first.

set -eo pipefail

usage() {
    sed -n '/^# Usage:/,/^#$/p' "$0" | sed 's/^# \{0,1\}//' >&2
}

[[ $# -ge 3 ]] || { usage; exit 1; }

SANDBOX="$1"; shift

FRESH=0
if [[ "$1" == "--fresh" ]]; then
    FRESH=1
    shift
fi

[[ "$1" == "--" ]] || { usage; exit 1; }
shift

if [[ "$FRESH" == "1" ]]; then
    rm -rf "$SANDBOX"
fi

mkdir -p "$SANDBOX/home" "$SANDBOX/state" "$SANDBOX/config" "$SANDBOX/data" "$SANDBOX/cache" "$SANDBOX/runtime"

export HOME="$SANDBOX/home"
export XDG_STATE_HOME="$SANDBOX/state"
export XDG_CONFIG_HOME="$SANDBOX/config"
export XDG_DATA_HOME="$SANDBOX/data"
export XDG_CACHE_HOME="$SANDBOX/cache"
export XDG_RUNTIME_DIR="$SANDBOX/runtime"

# The sandbox isn't a Plasma session unless asked (MYFOX_SANDBOX_KEEP_DESKTOP=1,
# for testing the Plasma integration itself).
if [[ "${MYFOX_SANDBOX_KEEP_DESKTOP:-}" != "1" ]]; then
    unset XDG_CURRENT_DESKTOP KDE_FULL_SESSION DESKTOP_SESSION SESSION_MANAGER 2>/dev/null || true
fi

echo "[sandbox] HOME=$HOME" >&2
echo "[sandbox] XDG_{STATE,CONFIG,DATA,CACHE}_HOME under $SANDBOX" >&2
echo "[sandbox] running: $*" >&2
echo "" >&2

exec "$@"
