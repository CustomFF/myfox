# shellcheck shell=bash
# common.sh — пути, логирование, state (плоский key=value), детект архитектуры.
# Требует: MYFOX_ROOT выставлен вызывающим (bin/myfox-core). Без внешних
# зависимостей (никакого jq/python3) — только bash + awk.

set -eo pipefail

: "${MYFOX_ROOT:?MYFOX_ROOT must be set before sourcing common.sh}"

# ─── Пути и константы ───────────────────────────────────────────────────────

MYFOX_STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/myfox"
MYFOX_STATE_FILE="$MYFOX_STATE_DIR/state"

MYFOX_AUTOCONFIG_DIR="$MYFOX_ROOT/autoconfig"
MYFOX_CHROME_DIR="$MYFOX_ROOT/chrome"

# Твики букмарклетов — отдельный проект DayDve/ddblm, копируем готовые файлы.
MYFOX_DDBLM_REPO="DayDve/ddblm"
MYFOX_DDBLM_BRANCH="master"
MYFOX_DDBLM_RAW="https://raw.githubusercontent.com/${MYFOX_DDBLM_REPO}/${MYFOX_DDBLM_BRANCH}"
MYFOX_DDBLM_GALLERY="https://daydve.github.io/ddblm/"
MYFOX_DDBLM_LOCAL="${MYFOX_DDBLM_LOCAL:-}"

MYFOX_DEFAULT_PREFIX="$HOME/.local/share/firefox"
MYFOX_BIN_DIR="${MYFOX_BIN_DIR:-$HOME/.local/bin}"
MYFOX_LAUNCHER_PATH="$MYFOX_BIN_DIR/myfox"
# Постоянная локальная копия bin/myfox-core+lib/+i18n/ — чтобы `myfox
# uninstall` работал полностью офлайн (без повторного скачивания тарбола),
# даже если сервер/домен когда-нибудь пропадёт. `myfox update` её обновляет.
MYFOX_CORE_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/myfox/core"

MYFOX_DESKTOP_NAME="firefox-myfox.desktop"
MYFOX_DESKTOP_TITLE="Firefox (myfox)"

INSTALL_MARKER_NAME=".myfox-installed"

# ─── Цвета ──────────────────────────────────────────────────────────────────

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
BLUE=$'\033[0;34m'
BOLD=$'\033[1m'
NC=$'\033[0m'

# ─── Логирование ────────────────────────────────────────────────────────────
#
# Тихий режим по умолчанию: log/success молчат без --verbose (MYFOX_VERBOSE=1).
# warn/error печатаются всегда. Сообщения приходят уже переведёнными (через
# t(), см. lib/i18n.sh) — common.sh только печатает.

: "${MYFOX_VERBOSE:=0}"

log()     { [[ "$MYFOX_VERBOSE" == "1" ]] && echo -e "${BLUE}[INF]${NC} $*" >&2; return 0; }
success() { [[ "$MYFOX_VERBOSE" == "1" ]] && echo -e "${GREEN}[OK]${NC}  $*" >&2; return 0; }
warn()    { echo -e "${YELLOW}[WRN]${NC} $*" >&2; }
error()   { echo -e "${RED}[ERR]${NC} $*" >&2; exit 1; }

# ─── Зависимости и архитектура ──────────────────────────────────────────────

check_deps() {
    local dep
    for dep in curl tar awk; do
        command -v "$dep" >/dev/null 2>&1 || error "$(t err_dep_missing "$dep")"
    done
}

# amd64 | arm64, иначе ошибка (32-бит и экзотические архитектуры не поддерживаем).
myfox_arch() {
    case "$(uname -m)" in
        x86_64)  echo amd64 ;;
        aarch64) echo arm64 ;;
        *)       return 1 ;;
    esac
}

# myfox_pad <string> <width> — right-pad до <width> СИМВОЛОВ (не байт).
# printf '%-Ns' считает байты — с кириллицей (2 байта/символ в UTF-8) это
# ломает выравнивание таблиц с переведёнными заголовками. ${#s} в bash под
# UTF-8-локалью считает символы правильно.
myfox_pad() {
    local s="$1" w="$2" len
    len=${#s}
    if (( len >= w )); then
        printf '%s' "$s"
    else
        printf '%s%*s' "$s" "$((w - len))" ""
    fi
}

# myfox_shorten_home <path> — заменяет $HOME-префикс на ~ (только для показа;
# для файловых операций использовать исходный абсолютный путь).
myfox_shorten_home() {
    local p="$1"
    if [[ "$p" == "$HOME"/* || "$p" == "$HOME" ]]; then
        printf '~%s' "${p#"$HOME"}"
    else
        printf '%s' "$p"
    fi
}

# ─── State: плоский key=value ($MYFOX_STATE_FILE) ───────────────────────────
#
# Один awk-проход на операцию, без jq/python3. Значения — только безопасные
# скаляры (пути, булевы, хэши, даты), которые пишет исключительно сам
# инсталлятор, поэтому конфликтов с '=' в значении не бывает.

state_get() {
    local key="$1"
    [[ -f "$MYFOX_STATE_FILE" ]] || return 0
    awk -F'=' -v k="$key" '$1==k { sub(/^[^=]*=/, ""); print; exit }' "$MYFOX_STATE_FILE"
}

state_set() {
    local key="$1" value="$2"
    mkdir -p "$MYFOX_STATE_DIR"
    touch "$MYFOX_STATE_FILE"
    awk -F'=' -v k="$key" -v v="$value" '
        $1 == k { print k "=" v; done = 1; next }
        { print }
        END { if (!done) print k "=" v }
    ' "$MYFOX_STATE_FILE" > "$MYFOX_STATE_FILE.tmp" && mv "$MYFOX_STATE_FILE.tmp" "$MYFOX_STATE_FILE"
}

state_remove() {
    local key="$1"
    [[ -f "$MYFOX_STATE_FILE" ]] || return 0
    awk -F'=' -v k="$key" '$1 != k' "$MYFOX_STATE_FILE" > "$MYFOX_STATE_FILE.tmp" \
        && mv "$MYFOX_STATE_FILE.tmp" "$MYFOX_STATE_FILE"
}

state_clear() { rm -f "$MYFOX_STATE_FILE"; }

has_marker() { [[ -n "$(state_get install_dir)" ]]; }

# is_myfox_dir <dir> — true, если каталог принадлежит myfox-инсталляции.
is_myfox_dir() {
    local dir="$1"
    [[ -f "$dir/$INSTALL_MARKER_NAME" || -f "$dir/.myfox-version" ]]
}

# ─── Опции установки (opt_* поля в state) ────────────────────────────────────
#
# Раньше — вложенный JSON-объект opts; теперь — обычные ключи state с
# префиксом opt_. opts_get/opts_set/opts_has сохраняют прежний интерфейс
# вызова, так что весь остальной код (install/update-логика) не меняется.

opts_default() {
    case "$1" in
        browser_only) echo false ;;
        bl)           echo true ;;
        addons)       echo true ;;
        channel)      echo stable ;;
        *)            echo "" ;;
    esac
}

opts_get() {
    local key="$1" val
    val=$(state_get "opt_${key}")
    if [[ -n "$val" ]]; then
        printf '%s' "$val"
    else
        opts_default "$key"
    fi
}

opts_has() { [[ -n "$(state_get "opt_${key:=$1}")" ]]; }

opts_set() { state_set "opt_${1}" "$2"; }
