#!/usr/bin/env bash
# get.sh — единственный публичный вход в MyFox, в двух ролях:
#
#   1) bootstrap:  curl -fsSL <url>/get.sh | bash                 (установка)
#                  curl -fsSL <url>/get.sh | bash -s -- uninstall (удаление)
#   2) лаунчер:    после установки та же сущность копируется в ~/.local/bin/myfox
#                  (myfox → запуск браузера офлайн; myfox update/uninstall → сеть)
#
# Специально НЕ подключает lib/*.sh — их ещё нет на диске при первом запуске
# (по пайпу). Вся тяжёлая логика — в bin/myfox-core, который качается вместе
# с дистрибутивом. Единственные зависимости здесь: bash, curl, tar, awk.
set -eo pipefail

DIST_URL="${MYFOX_DIST_URL:-https://example.invalid/myfox-dist.tar.gz}"
STATE_FILE="${XDG_STATE_HOME:-$HOME/.local/state}/myfox/state"
BIN_DIR="${MYFOX_BIN_DIR:-$HOME/.local/bin}"
LAUNCHER_PATH="$BIN_DIR/myfox"
# Постоянная копия core (bin/myfox-core+lib/+i18n/), которую install_launcher
# кладёт при установке/обновлении — uninstall работает из неё офлайн, без
# сети, даже если сервер/домен однажды пропадёт.
CORE_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/myfox/core"

_lang() { case "${LANG:-en}" in ru*) echo ru ;; *) echo en ;; esac; }

if [[ "$(_lang)" == ru ]]; then
    MSG_ALREADY="MyFox уже установлен. Запусти «myfox», используй ярлык в меню, или «myfox update» / «myfox uninstall»."
    MSG_NOT_INSTALLED="MyFox не установлен."
    MSG_NEED_CURL="Нужен curl."
    MSG_NEED_TAR="Нужен tar."
else
    MSG_ALREADY="MyFox is already installed. Run 'myfox', use the app shortcut, or 'myfox update' / 'myfox uninstall'."
    MSG_NOT_INSTALLED="MyFox is not installed."
    MSG_NEED_CURL="curl is required."
    MSG_NEED_TAR="tar is required."
fi

_state_get() {  # без common.sh (его ещё нет на диске) — прямой awk по key=value
    local key="$1"
    [[ -f "$STATE_FILE" ]] || return 0
    awk -F'=' -v k="$key" '$1==k { sub(/^[^=]*=/, ""); print; exit }' "$STATE_FILE"
}

_installed() { [[ -f "$STATE_FILE" ]]; }

# Мы и есть установленный ~/.local/bin/myfox (не bootstrap-вызов по пайпу)?
_is_launcher() {
    local self target
    self=$(readlink -f "$0" 2>/dev/null || printf '%s' "$0")
    target=$(readlink -f "$LAUNCHER_PATH" 2>/dev/null || printf '%s' "$LAUNCHER_PATH")
    [[ -n "$self" && "$self" == "$target" ]]
}

# /dev/tty только если его реально можно открыть (интерактивный curl|bash
# запущен из терминала) — stat-права (-r/-w) тут недостаточны: файл
# существует всегда, но open() без управляющего терминала падает с ENXIO
# (cron/CI). Полностью неинтерактивный запуск (-y) в этом случае не должен
# падать — клавиатурный ввод ему всё равно не нужен.
_exec_core() {  # <myfox-core path> <subcommand> <args...>
    local core="$1" sub="$2"; shift 2
    if ( exec 3</dev/tty ) 2>/dev/null; then
        bash "$core" "$sub" "$@" </dev/tty
    else
        bash "$core" "$sub" "$@"
    fi
}

# Стримом качает и распаковывает дистрибутив-тарбол во временный каталог,
# делегирует в myfox-core, чистит за собой.
_fetch_and_run() {  # <subcommand> <args...>
    local sub="$1"; shift
    command -v curl >/dev/null 2>&1 || { echo "$MSG_NEED_CURL" >&2; exit 1; }
    command -v tar  >/dev/null 2>&1 || { echo "$MSG_NEED_TAR" >&2; exit 1; }
    local tmp
    tmp=$(mktemp -d) || exit 1
    trap 'rm -rf "$tmp"' EXIT
    curl -fsSL "$DIST_URL" | tar -C "$tmp" -xz --strip-components=1
    _exec_core "$tmp/bin/myfox-core" "$sub" "$@"
}

SUB="install"
case "${1:-}" in
    uninstall) SUB="uninstall"; shift ;;
    update)    SUB="update"; shift ;;
    help|--help|-h) SUB="help"; shift ;;
esac

FORCE=false
for a in "$@"; do [[ "$a" == "--force" ]] && FORCE=true; done

case "$SUB" in
    uninstall)
        if [[ -x "$CORE_DIR/bin/myfox-core" ]]; then
            _exec_core "$CORE_DIR/bin/myfox-core" uninstall "$@"
        elif _installed; then
            # Старая установка без сохранённой копии core — фолбэк на сеть.
            _fetch_and_run uninstall "$@"
        else
            echo "$MSG_NOT_INSTALLED" >&2
        fi
        ;;
    update)
        _fetch_and_run update "$@"
        ;;
    help)
        # Справка не требует сети, если ядро уже стоит.
        if [[ -x "$CORE_DIR/bin/myfox-core" ]]; then
            _exec_core "$CORE_DIR/bin/myfox-core" help "$@"
        else
            _fetch_and_run help "$@"
        fi
        ;;
    install)
        if _installed && ! $FORCE; then
            if _is_launcher; then
                install_dir=$(_state_get install_dir)
                exec "$install_dir/firefox" "$@"
            fi
            echo "$MSG_ALREADY" >&2
            exit 0
        fi
        _fetch_and_run install "$@"
        ;;
esac
