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

# ─── Colors ─────────────────────────────────────────────────────────────────
#
# [tag]...[/tag] markup instead of ${COLOR}...${NC} interpolation at every
# call site, printed by cprintf() below. Colors auto-disable off a tty,
# under NO_COLOR, or TERM=dumb — this used to be unconditional, so a run
# redirected to a file or piped filled the log with raw escape codes.
# RED/GREEN/BOLD/NC stay around as plain vars too (tui.sh's spinner colors
# one glyph inline, not a sentence worth tagging) — they're just derived
# from the same table so there's one source of truth.

MYFOX_USE_COLOR=0
[[ -t 2 && -z "${NO_COLOR:-}" && "${TERM:-}" != dumb ]] && MYFOX_USE_COLOR=1

declare -A _MYFOX_TAGS=(
    [bold]=$'\033[1m'      [/bold]=$'\033[22m'
    [red]=$'\033[0;31m'    [/red]=$'\033[0m'
    [green]=$'\033[0;32m'  [/green]=$'\033[0m'
    [yellow]=$'\033[1;33m' [/yellow]=$'\033[0m'
    [blue]=$'\033[0;34m'   [/blue]=$'\033[0m'
)

if [[ "$MYFOX_USE_COLOR" == 1 ]]; then
    RED="${_MYFOX_TAGS[red]}" GREEN="${_MYFOX_TAGS[green]}" YELLOW="${_MYFOX_TAGS[yellow]}"
    BLUE="${_MYFOX_TAGS[blue]}" BOLD="${_MYFOX_TAGS[bold]}" NC=$'\033[0m'
else
    RED="" GREEN="" YELLOW="" BLUE="" BOLD="" NC=""
fi

# cprintf <text> — expands [tag]/[/tag] pairs (or strips them when color is
# off) and prints with a trailing newline; the caller adds >&2 as needed.
# Plain bash substitution, not a sed pipeline — the pattern side of
# ${text//"[$tag]"/...} is quoted, so it's a literal match, not a glob, and
# the caller's own interpolated text can safely contain '[' / ']'.
cprintf() {
    local text="$1" tag code
    for tag in "${!_MYFOX_TAGS[@]}"; do
        code=""
        [[ "$MYFOX_USE_COLOR" == 1 ]] && code="${_MYFOX_TAGS[$tag]}"
        text="${text//"[$tag]"/$code}"
    done
    printf '%s\n' "$text"
}

# ─── Logging ─────────────────────────────────────────────────────────────────
#
# Quiet by default: log/success stay silent without --verbose
# (MYFOX_VERBOSE=1). warn/error always print. Messages arrive already
# translated (via t(), see lib/i18n.sh) — common.sh only prints them.

: "${MYFOX_VERBOSE:=0}"

log()     { [[ "$MYFOX_VERBOSE" == "1" ]] && cprintf "[blue][INF][/blue] $*" >&2; return 0; }
success() { [[ "$MYFOX_VERBOSE" == "1" ]] && cprintf "[green][OK][/green]  $*" >&2; return 0; }
warn()    { cprintf "[yellow][WRN][/yellow] $*" >&2; }
error()   { cprintf "[red][ERR][/red] $*" >&2; exit 1; }

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
        theme)        echo dark ;;
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

opts_has() { local key="$1"; [[ -n "$(state_get "opt_${key}")" ]]; }

opts_set() { state_set "opt_${1}" "$2"; }
