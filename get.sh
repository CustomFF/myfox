#!/bin/sh
# MyFox: curl -fsSL https://raw.githubusercontent.com/CustomFF/myfox/master/get.sh | sh
#        (arguments: … | sh -s -- --gui)
# Fetches bootstrap.py and runs it; all the logic lives there.
set -e

url="${MYFOX_BOOTSTRAP_URL:-https://raw.githubusercontent.com/CustomFF/myfox/master/bootstrap.py}"

if ! command -v python3 >/dev/null 2>&1; then
    echo "MyFox needs python3." >&2
    exit 1
fi
# Tried again over a flaky network: curl's own --retry skips DNS failures
# and --retry-all-errors is too new for older systems.
for delay in 2 5 10 ""; do
    code=$(curl -fsSL "$url") && break
    [ -n "$delay" ] || exit 1
    sleep "$delay"
done

# Piped into sh, stdin is this script: hand the terminal to the installer.
if (exec </dev/tty) 2>/dev/null; then
    exec python3 -c "$code" "$@" </dev/tty
fi
exec python3 -c "$code" "$@"
