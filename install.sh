#!/usr/bin/env bash
# install.sh — MyFox installer.
#
# Ставит Firefox из официального тарбола и применяет на него твики myfox.
# Опционально применяет букмарклет-твики из submodule ddbml (blm).
#
# Использование:
#   install.sh                    установка по умолчанию (тарбол + твики)
#   install.sh --prefix <path>    целевой путь инсталляции (по умолчанию ~/.local/share/firefox)
#   install.sh --reinstall        перекачать браузер заново (даже если инсталляция уже есть)
#   install.sh --profile <path>   явно указать профиль (переопределяет детекцию)
#   install.sh --noblm            не применять букмарклет-твики
#   install.sh -y/--yes           без подтверждений
#   install.sh -h/--help
#
# Повторный запуск:
#   - не перекачивает браузер, если инсталляция уже есть (маркер);
#   - использует профиль, сохранённый в маркере;
#   - обновляет твики из текущего checkout.

set -eo pipefail

MYFOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat <<EOF
MyFox installer — Firefox from tarball + tweaks.

Usage: $0 [options]

Options:
  --prefix <path>    Install directory (default: ~/.local/share/firefox)
  --reinstall        Force re-download of the browser even if already installed
  --profile <path>   Explicit Firefox profile directory (overrides detection)
  --noblm            Skip bookmarklet tweaks (blm)
  -y, --yes          Non-interactive (no prompts)
  -h, --help         Show this help
EOF
    exit 0
}

# ─── Парсинг аргументов ─────────────────────────────────────────────────────

PREFIX=""
REINSTALL=false
PROFILE_ARG=""
NOBLM=false
MYFOX_NONINTERACTIVE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --prefix)  PREFIX="$2"; shift 2 ;;
        --reinstall) REINSTALL=true; shift ;;
        --profile) PROFILE_ARG="$2"; shift 2 ;;
        --noblm)   NOBLM=true; shift ;;
        -y|--yes)  MYFOX_NONINTERACTIVE=1; shift ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# ─── Загрузка библиотек ─────────────────────────────────────────────────────

# shellcheck source=lib/common.sh
. "$MYFOX_ROOT/lib/common.sh"
# shellcheck source=lib/firefox.sh
. "$MYFOX_ROOT/lib/firefox.sh"
# shellcheck source=lib/profile.sh
. "$MYFOX_ROOT/lib/profile.sh"
# shellcheck source=lib/apply.sh
. "$MYFOX_ROOT/lib/apply.sh"

check_deps

# ─── Определение целевого пути инсталляции ─────────────────────────────────

if [[ -n "$PREFIX" ]]; then
    INSTALL_DIR="$PREFIX"
elif saved=$(state_get install_dir); [[ -n "$saved" ]]; then
    INSTALL_DIR="$saved"
else
    INSTALL_DIR="$MYFOX_DEFAULT_PREFIX"
fi

# ─── Браузер ────────────────────────────────────────────────────────────────

if [[ -f "$INSTALL_DIR/application.ini" && -f "$INSTALL_DIR/.myfox-installed" && "$REINSTALL" == false ]]; then
    log "Firefox already installed (myfox) at $INSTALL_DIR — updating tweaks only."
    firefox_version=$(firefox_local_version "$INSTALL_DIR")
elif [[ -d "$INSTALL_DIR" && -n "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]]; then
    warn "Something is already present in $INSTALL_DIR (hand-installed Firefox?)."
    backup=$(backup_dir_nonempty "$INSTALL_DIR")
    if [[ -n "$backup" ]]; then
        success "Backup created: $backup"
        state_set backup_dir "$backup"
    fi
    log "Reinstalling Firefox cleanly..."
    # Очистить директорию и поставить заново.
    find "$INSTALL_DIR" -mindepth 1 -delete 2>/dev/null || true
    firefox_version=$(firefox_install_tarball "$INSTALL_DIR")
    touch "$INSTALL_DIR/.myfox-installed"
    state_set firefox_version "$firefox_version"
else
    firefox_version=$(firefox_install_tarball "$INSTALL_DIR")
    touch "$INSTALL_DIR/.myfox-installed"
    state_set firefox_version "$firefox_version"
fi

# ─── Профиль ────────────────────────────────────────────────────────────────

PROFILE_DIR=$(profile_resolve --explicit "$PROFILE_ARG")
state_set profile_dir "$PROFILE_DIR"
log "Using Firefox profile: $PROFILE_DIR"

# ─── Применение твиков ──────────────────────────────────────────────────────

apply_autoconfig "$INSTALL_DIR"
apply_chrome "$PROFILE_DIR"

# ─── Desktop entry ──────────────────────────────────────────────────────────

firefox_create_desktop_entry "$INSTALL_DIR" "$MYFOX_DESKTOP_TITLE" "$MYFOX_DESKTOP_NAME"

# ─── Сохранение маркера ─────────────────────────────────────────────────────

state_set install_dir "$INSTALL_DIR"
state_set installed_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# ─── Букмарклеты (опционально) ──────────────────────────────────────────────

if [[ "$NOBLM" == false ]]; then
    if confirm "Apply bookmarklet tweaks (blm) and open the gallery page?" "n"; then
        gallery=$(apply_bookmarklets "$PROFILE_DIR") || true
        if [[ -n "$gallery" && -f "$gallery" ]]; then
            log "Gallery written to: $gallery"
            log "Drag bookmarklet cards from there onto your Bookmarks Toolbar."
        fi
    else
        log "Skipping bookmarklet tweaks."
    fi
else
    log "Bookmarklet tweaks skipped (--noblm)."
fi

# ─── Сводка ─────────────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}=== MyFox installed successfully ===${NC}"
echo "  Firefox:   ${INSTALL_DIR} (${firefox_version:-latest})"
echo "  Profile:   ${PROFILE_DIR}"
echo "  Desktop:   Firefox (myfox)"
state_get backup_dir >/dev/null 2>&1 || true
[[ -n "$(state_get backup_dir)" ]] && echo "  Backup:    $(state_get backup_dir)"
echo ""
echo "Run 'firefox (myfox)' from your app menu, or:"
echo "  ${INSTALL_DIR}/firefox --profile '${PROFILE_DIR}'"
echo ""
echo "To remove: ./uninstall.sh"