# shellcheck shell=bash
# common.sh — общие функции: логирование, цвета, работа с маркером (state), helpers.
# Подключается из install.sh / uninstall.sh и других lib-скриптов.
#
# Требования: bash 4+, Linux.

set -eo pipefail

# ─── Пути и константы ───────────────────────────────────────────────────────

MYFOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MYFOX_STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/myfox"
MYFOX_STATE_FILE="$MYFOX_STATE_DIR/install.json"

# Каталоги с артефактами твиков (внутри репо)
MYFOX_AUTOCONFIG_DIR="$MYFOX_ROOT/autoconfig"
MYFOX_CHROME_DIR="$MYFOX_ROOT/chrome"

# Прямые (raw) ссылки на твики букмарклетов из отдельного проекта DayDve/ddblm.
# myfox копирует готовый blm_panel.css и ВСЕ иконки оттуда, не требуя
# локальной установки ddbml (см. lib/apply.sh → apply_bookmarklets).
MYFOX_DDBLM_REPO="DayDve/ddblm"
MYFOX_DDBLM_BRANCH="master"
MYFOX_DDBLM_RAW="https://raw.githubusercontent.com/${MYFOX_DDBLM_REPO}/${MYFOX_DDBLM_BRANCH}"
MYFOX_DDBLM_GALLERY="https://daydve.github.io/ddblm/"

# Локальная копия ddblm (для тестирования твиков, пока репозиторий не запушен).
# Пустой (по умолчанию) — файлы берутся из raw github. Во время тестирования
# твиков задаём через переменную окружения, напр.
#   MYFOX_DDBLM_LOCAL=/home/daydve/development/ddblm ./install.sh ...
MYFOX_DDBLM_LOCAL="${MYFOX_DDBLM_LOCAL:-}"

# Целевой путь инсталляции по умолчанию
MYFOX_DEFAULT_PREFIX="$HOME/.local/share/firefox"

# Имя desktop-файла и человеко-читаемое имя ярлыка
MYFOX_DESKTOP_NAME="firefox-myfox.desktop"
MYFOX_DESKTOP_TITLE="Firefox (myfox)"

# ─── Цвета ──────────────────────────────────────────────────────────────────

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
BLUE=$'\033[0;34m'
BOLD=$'\033[1m'
NC=$'\033[0m'

# ─── Логирование ────────────────────────────────────────────────────────────
#
# По умолчанию — тихий режим: печатаются только warnings, ошибки, прогрессбар
# и итоговая сводка. Детальные [INF]/[OK] — при --verbose
# (MYFOX_VERBOSE=1; установка по env до запуска тоже работает).

: "${MYFOX_VERBOSE:=0}"

log()     { [[ "$MYFOX_VERBOSE" == "1" ]] && echo -e "${BLUE}[INF]${NC} $*" >&2 || true; }
success() { [[ "$MYFOX_VERBOSE" == "1" ]] && echo -e "${GREEN}[OK]${NC}  $*" >&2 || true; }
warn()    { echo -e "${YELLOW}[WRN]${NC} $*" >&2; }
error()   { echo -e "${RED}[ERR]${NC} $*" >&2; exit 1; }

# Приглашение yes/no. Возвращает 0 если «да» (регистронезависимый y/yes/д/да).
# Второй аргумент — ответ по умолчанию ("y"/"n").
#   default=y → приглашение «[Y/n]», пустой Enter = да
#   default=n → приглашение «[y/N]», пустой Enter = нет
# В неинтерактивном режиме (-y) всегда возвращает 0 (да), сохраняя прежнюю
# семантику «-y = согласиться на всё».
confirm() {
    local prompt="${1:-Continue?}" default="${2:-n}"
    [[ -n $MYFOX_NONINTERACTIVE ]] && return 0
    local marker
    case "${default,,}" in
        y|yes|true) default="y"; marker="[Y/n]" ;;
        *) default="n"; marker="[y/N]" ;;
    esac
    read -rp "$prompt $marker " ans
    ans="${ans,,}"
    case "$ans" in
        y|yes|д|да) return 0 ;;
        "") [[ "$default" == "y" ]] && return 0 || return 1 ;;
        *) return 1 ;;
    esac
}

# ─── TUI: альтернативный экран dialog/whiptail ────────────────────────────────
#
# dialog при запуске входит в альтернативный экран (ncurses), при выходе —
# выходит из него. На части терминалов (screen/tmux, консоль KDE, xterm без
# 1049) собственный smcup ломается: экран остаётся «синим». Решение: явно
# входим в альт-экран (tui_enter) ПЕРЕД диалогом и явно выходим (tui_reset)
# ПОСЛЕ. Если tput не даёт капсов (пустой smcup/rmcup) — fallback на прямые
# ESC-последовательности хterm (1049h/1049l), их понимает почти всё.
# Пишем в /dev/tty — dialog рисует туда; через pipe/capture stderr может уйти
# в /dev/null, а /dev/tty всегда ведёт на реальный терминал.
tui_enter() {
    [[ -n "$TERM" && "$TERM" != "dumb" ]] || return 0
    local s
    s=$(tput smcup 2>/dev/null) && [[ -n "$s" ]] || s=$'\033[?1049h'
    printf '%s' "$s" >/dev/tty 2>/dev/null || true
}

tui_reset() {
    [[ -n "$TERM" && "$TERM" != "dumb" ]] || return 0
    local s
    s=$(tput rmcup 2>/dev/null) && [[ -n "$s" ]] || s=$'\033[?1049l'
    printf '%s' "$s" >/dev/tty 2>/dev/null || true
    tput sgr0 2>/dev/null >/dev/tty || true
}

# dialog на КАЖДЫЙ вызов переключает альтернативный экран (ncurses берёт
# smcup/rmcup из terminfo), а при выходе выкидывает на главный экран — на миг
# видно шелл/промпт, отсюда мигание между диалогами. Опция --keep-tite этого не
# лечит. Гасим надёжно: собираем копию текущего terminfo БЕЗ smcup/rmcup (все
# прочие возможности, включая цвета, сохраняются) и подсовываем dialog'у через
# TERMINFO. Каталог кэшируется. Возврат: каталог TERMINFO или пусто.
myfox_terminfo_noalt() {
    local base="${TERM:-}" dir stamp src
    [[ -n "$base" && "$base" != "dumb" ]] || return 1
    command -v infocmp >/dev/null 2>&1 && command -v tic >/dev/null 2>&1 || return 1
    dir="${XDG_CACHE_HOME:-$HOME/.cache}/myfox/terminfo"
    stamp="$dir/.noalt-$base"
    if [[ ! -f "$stamp" ]]; then
        mkdir -p "$dir" || return 1
        src=$(mktemp) || return 1
        if ! infocmp -1 -x "$base" 2>/dev/null | grep -v -E '^[[:space:]]*(smcup|rmcup)=' > "$src" \
            || [[ ! -s "$src" ]] || ! tic -x -o "$dir" "$src" >/dev/null 2>&1; then
            rm -f "$src"
            return 1
        fi
        rm -f "$src"
        : > "$stamp"
    fi
    printf '%s\n' "$dir"
}

# Установить TERMINFO без alt-экрана (для dialog). Идемпотентно; возврат 0 если
# удалось (или уже установлено), 1 — нечем (тогда dialog будет мигать как раньше).
use_ui_terminfo_noalt() {
    local ti
    [[ -n "$MYFOX_TERMINFO_NOALT" ]] && return 0
    ti=$(myfox_terminfo_noalt) || return 1
    [[ -n "$ti" ]] || return 1
    MYFOX_TERMINFO_NOALT="$ti"
    export TERMINFO="$ti"
}

# Снять подмену TERMINFO (после мастера, чтобы дальше шёл обычный terminfo).
reset_ui_terminfo_noalt() {
    [[ -n "$MYFOX_TERMINFO_NOALT" ]] || return 0
    unset TERMINFO MYFOX_TERMINFO_NOALT
}

check_deps() {
    local deps=("curl" "tar" "grep" "awk")
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" >/dev/null 2>&1; then
            error "Dependency '$dep' not found. Please install it."
        fi
    done
}

# ─── Маркер установки (state) ───────────────────────────────────────────────

# Простой JSON без зависимостей. Значения экранируются минимально (нет слэшей/кавычек в путях,
# которые мы пишем). Используем jq если доступен, иначе python3.
state_get() {
    local key="$1"
    if [[ ! -f "$MYFOX_STATE_FILE" ]]; then
        return 0
    fi
    if command -v jq >/dev/null 2>&1; then
        jq -r --arg k "$key" '.[$k] // empty' "$MYFOX_STATE_FILE" 2>/dev/null || true
    elif command -v python3 >/dev/null 2>&1; then
        python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get(sys.argv[2], ""))' \
            "$MYFOX_STATE_FILE" "$key" 2>/dev/null || true
    else
        # Падение: jq/python3 нет — пытаемся парсить grep-ом (однострочный JSON).
        grep -o "\"$key\": *\"[^\"]*\"" "$MYFOX_STATE_FILE" 2>/dev/null | head -1 | cut -d'"' -f4 || true
    fi
    return 0
}

state_set() {
    local key="$1" value="$2"
    mkdir -p "$MYFOX_STATE_DIR"
    if [[ -f "$MYFOX_STATE_FILE" ]]; then
        if command -v jq >/dev/null 2>&1; then
            tmp="${MYFOX_STATE_FILE}.tmp"
            jq --arg k "$key" --arg v "$value" '.[$k] = $v' "$MYFOX_STATE_FILE" > "$tmp"
            mv "$tmp" "$MYFOX_STATE_FILE"
        elif command -v python3 >/dev/null 2>&1; then
            python3 -c 'import json,sys; f,p=sys.argv[1],sys.argv[2:]
d=json.load(open(f)); d[p[0]]=p[1]; open(f,"w").write(json.dumps(d,indent=2,ensure_ascii=False))' \
                "$MYFOX_STATE_FILE" "$key" "$value"
        else
            error "Cannot update state: jq or python3 required."
        fi
    else
        printf '{\n  "%s": "%s"\n}\n' "$key" "$value" > "$MYFOX_STATE_FILE"
    fi
}

state_remove() {
    local key="$1"
    [[ -f "$MYFOX_STATE_FILE" ]] || return 0
    if command -v jq >/dev/null 2>&1; then
        tmp="${MYFOX_STATE_FILE}.tmp"
        jq "del(.$key)" "$MYFOX_STATE_FILE" > "$tmp" 2>/dev/null || return 0
        mv "$tmp" "$MYFOX_STATE_FILE"
    else
        error "Cannot update state: jq required."
    fi
}

# Чтение JSON-значения ключа (объект/массив/число) — компактно, без кавычек на верхнем уровне.
# Пустой файл/отсутствующий ключ → пусто.
state_get_json() {
    local key="$1"
    [[ -f "$MYFOX_STATE_FILE" ]] || return 0
    if command -v jq >/dev/null 2>&1; then
        jq -c --arg k "$key" '.[$k] // empty' "$MYFOX_STATE_FILE" 2>/dev/null || true
    elif command -v python3 >/dev/null 2>&1; then
        python3 -c '
import json, sys
d = json.load(open(sys.argv[1]))
v = d.get(sys.argv[2])
print(json.dumps(v, ensure_ascii=False), end="") if v is not None else print("", end="")
' "$MYFOX_STATE_FILE" "$key" 2>/dev/null || true
    else
        return 0
    fi
    return 0
}

# Запись JSON-значения в ключ (значение — валидный JSON, напр. объект opts).
state_set_json() {
    local key="$1" value="$2"
    mkdir -p "$MYFOX_STATE_DIR"
    if [[ -f "$MYFOX_STATE_FILE" ]]; then
        if command -v jq >/dev/null 2>&1; then
            tmp="${MYFOX_STATE_FILE}.tmp"
            jq --arg k "$key" --argjson v "$value" '.[$k] = $v' "$MYFOX_STATE_FILE" > "$tmp"
            mv "$tmp" "$MYFOX_STATE_FILE"
        elif command -v python3 >/dev/null 2>&1; then
            python3 -c '
import json, sys
f, k = sys.argv[1], sys.argv[2]
d = json.load(open(f))
d[k] = json.loads(sys.argv[3])
json.dump(d, open(f, "w"), indent=2, ensure_ascii=False)
' "$MYFOX_STATE_FILE" "$key" "$value"
        else
            error "Cannot update state: jq or python3 required."
        fi
    else
        printf '{\n  "%s": %s\n}\n' "$key" "$value" > "$MYFOX_STATE_FILE"
    fi
}

# ─── Опции установки (объект opts в маркере) ─────────────────────────────────
#
# opts = { browser_only, lang, bl, addons, plasma } — дефолты для повторного
# запуска и для --update. На старых маркерах (без opts) работает неявный маппинг
# на дефолты ниже, поэтому фича обратно совместима.

opts_default() {
    case "$1" in
        browser_only) echo false ;;
        lang)         echo "" ;;
        bl)           echo true ;;
        addons)       echo true ;;
        plasma)       echo "" ;;
        *)            echo "" ;;
    esac
}

opts_get() {
    local key="$1" opts
    opts=$(state_get_json opts)
    if [[ -z "$opts" || "$opts" == "null" ]]; then
        opts_default "$key"
        return 0
    fi
    local def
    def=$(opts_default "$key")
    if command -v jq >/dev/null 2>&1; then
        jq -r --arg k "$key" --arg d "$def" 'if has($k) then .[$k] else $d end' <<< "$opts" 2>/dev/null || opts_default "$key"
    elif command -v python3 >/dev/null 2>&1; then
        python3 -c '
import json, sys
d = json.loads(sys.argv[1])
print(d.get(sys.argv[2], sys.argv[3]))
' "$opts" "$key" "$def" 2>/dev/null || opts_default "$key"
    else
        opts_default "$key"
    fi
}

# Есть ли в opts явно сохранённый выбор по ключу (в отличие от значения по умолчанию).
opts_has() {
    local key="$1" opts
    opts=$(state_get_json opts)
    [[ -z "$opts" || "$opts" == "null" ]] && return 1
    if command -v jq >/dev/null 2>&1; then
        jq -r --arg k "$key" 'has($k)' <<< "$opts" 2>/dev/null | grep -q true || return 1
    elif command -v python3 >/dev/null 2>&1; then
        python3 -c 'import json,sys; print("true" if sys.argv[2] in json.loads(sys.argv[1]) else "false")' \
            "$opts" "$key" 2>/dev/null | grep -q true || return 1
    else
        return 1
    fi
}

opts_set() {
    local key="$1" value="$2"
    local opts new
    opts=$(state_get_json opts)
    [[ -z "$opts" || "$opts" == "null" ]] && opts='{}'
    if command -v jq >/dev/null 2>&1; then
        new=$(jq -c --arg k "$key" --arg v "$value" '.[$k] = $v' <<< "$opts") || true
    elif command -v python3 >/dev/null 2>&1; then
        new=$(python3 -c '
import json, sys
d = json.loads(sys.argv[1]); d[sys.argv[2]] = sys.argv[3]
print(json.dumps(d, ensure_ascii=False))
' "$opts" "$key" "$value") || true
    else
        error "Cannot update state: jq or python3 required."
    fi
    [[ -n "$new" ]] || error "Cannot update state options."
    state_set_json opts "$new"
}

state_clear() {
    rm -f "$MYFOX_STATE_FILE"
}

has_marker() {
    # Маркер НАШЕЙ инсталляции лежит в install_dir (marker: .myfox-installed).
    # Если install.json есть и в нём install_dir — установка наша.
    state_get install_dir >/dev/null 2>&1
}

# Флаг-маркер внутри инсталляционного каталога (различает «нашу» vs «чужую» инсталляцию по пути).
INSTALL_MARKER_NAME=".myfox-installed"