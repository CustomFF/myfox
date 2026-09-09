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
# myfox скачивает готовый bookmarks_panel.css и иконки оттуда, не требуя
# локальной установки ddbml (см. lib/apply.sh → apply_bookmarklets).
MYFOX_DDBLM_REPO="DayDve/ddblm"
MYFOX_DDBLM_BRANCH="master"
MYFOX_DDBLM_RAW="https://raw.githubusercontent.com/${MYFOX_DDBLM_REPO}/${MYFOX_DDBLM_BRANCH}"
MYFOX_DDBLM_GALLERY="https://daydve.github.io/ddblm/"

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

log()     { echo -e "${BLUE}[INF]${NC} $*" >&2; }
success() { echo -e "${GREEN}[OK]${NC}  $*" >&2; }
warn()    { echo -e "${YELLOW}[WRN]${NC} $*" >&2; }
error()   { echo -e "${RED}[ERR]${NC} $*" >&2; exit 1; }

# Приглашение yes/no. Возвращает 0 если «да» (регистронезависимый y/yes/д/да).
confirm() {
    local prompt="${1:-Continue?}" default="${2:-n}"
    [[ -n $MYFOX_NONINTERACTIVE ]] && return 0
    local ans
    read -rp "$prompt [y/N] " ans
    case "${ans,,}" in
        y|yes|д|да) return 0 ;;
        *) return 1 ;;
    esac
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