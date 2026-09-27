#!/usr/bin/env bash
# sandbox.sh — изолированный тестовый полигон для install.sh / uninstall.sh.
#
# Запускает инсталлер с СОБСТВЕННЫМ $HOME и всеми $XDG_* каталогами под <sandbox>.
# Это перекрывает ВСЕ системные точки входа инсталлера:
#   state         → <sandbox>/state    (вместо ~/.local/state)
#   профили       → <sandbox>/home/.mozilla (вместо ~/.mozilla, flatpak, snap)
#   desktop entry → <sandbox>/home/.local/share/applications
#   установка     → <sandbox>/install  (--prefix, чтобы не свалиться в ~/.local/share/firefox)
# Реальный браузер, профиль, profiles.ini/installs.ini и desktop-ярлыки НЕ затрагиваются.
#
# Usage:
#   scratch/sandbox.sh <sandbox-dir> -- <install.sh args...>
#   scratch/sandbox.sh <sandbox-dir> --fresh -- <install.sh args...>   # очистить sandbox начисто
#
# Примеры:
#   scratch/sandbox.sh /tmp/myfox-sandbox -- ./install.sh -y --nobl --noaddons --noplasma
#   scratch/sandbox.sh /tmp/myfox-sandbox -- ./uninstall.sh -y
#
# Интерактивность сохраняется: мастер/dialog работает как обычно, но пишет
# только в песочницу (и на реальный /dev/tty — это не файловая запись).
# Если нужно полностью неинтерактивно — добавь -y сам.

set -eo pipefail

usage() {
    cat <<EOF
Usage: scratch/sandbox.sh <sandbox-dir> [--fresh] -- <install.sh|uninstall.sh args...>

Redirects HOME and all XDG dirs into <sandbox-dir>: real browser/profile/state/desktop
entries are never touched.
EOF
}

[[ $# -ge 3 ]] || { usage >&2; exit 1; }

SANDBOX="$1"; shift

FRESH=0
if [[ "$1" == "--fresh" ]]; then
    FRESH=1
    shift
fi

[[ "$1" == "--" ]] || { usage >&2; exit 1; }
shift

# Installer command. If it's an `install` run without an explicit --prefix,
# add one pointing into the sandbox, so it never targets the real
# $HOME/.local/share/firefox. --prefix is install-only (myfox-core rejects
# it for update/uninstall), so it's never added for those.
CMD=("$@")
HAS_PREFIX=0
for a in "${CMD[@]}"; do
    [[ "$a" == "--prefix" ]] && HAS_PREFIX=1
done
SUBCMD=install
for a in "${CMD[@]:1}"; do
    case "$a" in
        install|update|uninstall|help) SUBCMD="$a"; break ;;
        --) break ;;
    esac
done
if [[ "$HAS_PREFIX" == "0" && "$SUBCMD" == "install" ]]; then
    CMD+=("--prefix" "$SANDBOX/install")
fi

if [[ "$FRESH" == "1" ]]; then
    rm -rf "$SANDBOX"
fi

mkdir -p "$SANDBOX"
mkdir -p "$SANDBOX/home" "$SANDBOX/state" "$SANDBOX/config" "$SANDBOX/data" "$SANDBOX/cache" "$SANDBOX/runtime"

export HOME="$SANDBOX/home"
export XDG_STATE_HOME="$SANDBOX/state"
export XDG_CONFIG_HOME="$SANDBOX/config"
export XDG_DATA_HOME="$SANDBOX/data"
export XDG_CACHE_HOME="$SANDBOX/cache"
export XDG_RUNTIME_DIR="$SANDBOX/runtime"

# Чтобы не сработала ветка KDE Plasma (addons_is_plasma) — сессия в песочнице не Plasma,
# если только явно не попросили сохранить её (MYFOX_SANDBOX_KEEP_DESKTOP=1 — тестирование
# самой Plasma-ветки).
if [[ "${MYFOX_SANDBOX_KEEP_DESKTOP:-}" != "1" ]]; then
    unset XDG_CURRENT_DESKTOP KDE_FULL_SESSION DESKTOP_SESSION SESSION_MANAGER 2>/dev/null || true
fi

echo "[sandbox] HOME=$HOME" >&2
echo "[sandbox] XDG_STATE_HOME=$XDG_STATE_HOME" >&2
echo "[sandbox] XDG_DATA_HOME=$XDG_DATA_HOME" >&2
echo "[sandbox] XDG_CACHE_HOME=$XDG_CACHE_HOME" >&2
echo "[sandbox] install dir -> $SANDBOX/install" >&2
echo "[sandbox] running: ${CMD[*]}" >&2
echo "" >&2

exec "${CMD[@]}"