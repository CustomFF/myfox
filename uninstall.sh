#!/usr/bin/env bash
# uninstall.sh — удаляет твики myfox.
#
# Спрашивает, восстанавливать ли бэкап (если он был при установке).
# По умолчанию сам браузер не удаляет — спрашивает.
#
# Usage:
#   uninstall.sh [-y|--yes] [-h|--help]

set -eo pipefail

MYFOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

MYFOX_NONINTERACTIVE="${MYFOX_NONINTERACTIVE:-}"
for arg in "$@"; do
    case "$arg" in
        -y|--yes) MYFOX_NONINTERACTIVE=1 ;;
        -h|--help)
            cat <<EOF
MyFox uninstaller.
Removes tweaks applied by install.sh and optionally restores backup.

Usage: $0 [-y|--yes]
EOF
            exit 0 ;;
    esac
done

# shellcheck source=lib/common.sh
. "$MYFOX_ROOT/lib/common.sh"
# shellcheck source=lib/firefox.sh
. "$MYFOX_ROOT/lib/firefox.sh"
# shellcheck source=lib/profile.sh
. "$MYFOX_ROOT/lib/profile.sh"
# shellcheck source=lib/addons.sh
. "$MYFOX_ROOT/lib/addons.sh"

# ─── Проверка наличия установки ─────────────────────────────────────────────

if [[ ! -f "$MYFOX_STATE_FILE" ]]; then
    warn "No MyFox installation record found ($MYFOX_STATE_FILE)."
    warn "If you installed tweaks manually, remove autoconfig files and chrome styles by hand."
    exit 0
fi

INSTALL_DIR=$(state_get install_dir)
PROFILE_DIR=$(state_get profile_dir)

echo -e "${BOLD}MyFox uninstaller${NC}"
echo "  Firefox dir: $INSTALL_DIR"
echo "  Profile dir: $PROFILE_DIR"

# Тип профиля: created — создан инсталлером (маркер .myfox-created),
# existing — существующий, переданный через --profile / выбранный в мастере.
# Для created-профиля вопрос «Remove MyFox tweaks?» бессмыслен: твики удаляются
# вместе с профилем (или при его очистке), см. блок профиля ниже.
PROFILE_TYPE=""
if [[ -n "$PROFILE_DIR" ]]; then
    if [[ -f "$PROFILE_DIR/.myfox-created" ]]; then
        PROFILE_TYPE="created"
    elif [[ -d "$PROFILE_DIR" ]]; then
        PROFILE_TYPE="existing"
    fi
fi

# «Remove MyFox tweaks?» спрашиваем ТОЛЬКО для существующего профиля — там
# твики навешены на реальный профиль пользователя, и снятие — осознанная
# операция. Отказ здесь отменяет весь uninstall.
if [[ "$PROFILE_TYPE" == "existing" ]]; then
    if [[ -z $MYFOX_NONINTERACTIVE ]] && ! confirm "Remove MyFox tweaks?" "n"; then
        echo "Cancelled."
        exit 0
    fi
fi

# ─── Снятие пиннинга (профиль на инсталляцию) ───────────────────────────────

INSTALL_HASH=$(state_get install_hash)
if [[ -n "$INSTALL_HASH" ]]; then
    profile_unpin_install "$INSTALL_HASH"
else
    log "No pinned install hash — skipping profiles.ini/installs.ini unpin."
fi

# ─── Удаление твиков ────────────────────────────────────────────────────────

# Autoconfig
if [[ -d "$INSTALL_DIR" ]]; then
    rm -f "$INSTALL_DIR/defaults/pref/autoconfig.js" 2>/dev/null || true
    rm -f "$INSTALL_DIR/firefox.cfg" 2>/dev/null || true
    rm -f "$INSTALL_DIR/.myfox-installed" 2>/dev/null || true
    success "Autoconfig files removed from $INSTALL_DIR"
fi

# Chrome styles / удаление профиля
# Профиль, созданный инсталлером (маркер .myfox-created): удаляем целиком
# (каталог + запись) — это и есть «снятие твиков» для нашего профиля. Чужой
# профиль (existing) НЕ удаляем, только снимаем с него твики.
DELETE_PROFILE=false
if [[ "$PROFILE_TYPE" == "created" ]]; then
    if [[ -z $MYFOX_NONINTERACTIVE ]] && ! confirm "Delete the myfox profile completely (all its data)? $PROFILE_DIR" "n"; then
        log "Keeping the myfox profile at $PROFILE_DIR."
    else
        rm -rf "$PROFILE_DIR"
        profile_remove_myfox_section
        success "Myfox profile deleted: $PROFILE_DIR"
        DELETE_PROFILE=true
    fi
fi

if [[ "$DELETE_PROFILE" != "true" && -n "$PROFILE_DIR" && -d "$PROFILE_DIR/chrome" ]]; then
    # Восстановить защитные копии чужих стилей (созданные apply_chrome)
    for f in userChrome.css agent_overrides.css; do
        if [[ -f "$PROFILE_DIR/chrome/$f.myfox-backup" ]]; then
            rm -f "$PROFILE_DIR/chrome/$f"
            mv -f "$PROFILE_DIR/chrome/$f.myfox-backup" "$PROFILE_DIR/chrome/$f"
            success "Restored $f from .myfox-backup"
        else
            rm -f "$PROFILE_DIR/chrome/$f"
        fi
    done
    # Файлы букмарклет-твиков (blm_panel.css + panel-icons из ddblm)
    rm -f "$PROFILE_DIR/chrome/blm_panel.css" 2>/dev/null || true
    rm -rf "$PROFILE_DIR/chrome/panel-icons" 2>/dev/null || true
    rm -f "$PROFILE_DIR/.myfox" 2>/dev/null || true
    success "Chrome styles removed from $PROFILE_DIR"
fi

# Только если профиль остался: предложить убрать его запись из profiles.ini.
if [[ -n "$PROFILE_DIR" && -f "$PROFILE_DIR/.myfox-created" && "$DELETE_PROFILE" != "true" ]]; then
    if confirm "Remove the myfox profile entry from profiles.ini? (profile data is kept)" "n"; then
        profile_remove_myfox_section
    else
        log "Kept the myfox profile entry in profiles.ini."
    fi
fi

# Add-ons (uBlock, theme, plasma-integration) installed per-profile:
# удаляем ТОЛЬКО их (по фиксированным ID). КАТЕГОРИЧЕСКИ НЕЛЬЗЯ сметать
# все *.xpi из extensions/: там живут пользовательские аддоны существующего
# профиля (до 70+ шт. у реальных пользователей).
MYFOX_ADDON_IDS=(
    "uBlock0@raymondhill.net"                 # uBlock Origin
    "{9631ec37-35f2-4719-815e-2f84ff28b901}"  # Google Chrome Dark (тема)
    "plasma-browser-integration@kde.org"      # KDE Plasma integration
)
if [[ -n "$PROFILE_DIR" && -d "$PROFILE_DIR/extensions" ]]; then
    for id in "${MYFOX_ADDON_IDS[@]}"; do
        [[ -z "$id" ]] && continue
        # Упакованный XPI (как клали myfox) и распакованная Firefox-ом установка.
        rm -f "$PROFILE_DIR/extensions/$id.xpi" 2>/dev/null || true
        rm -rf "$PROFILE_DIR/extensions/$id" 2>/dev/null || true
    done
    # extensions.json НЕ трогаем — если аддон остался записан, Firefox сам
    # вычистит запись о недостающем файле. Каталог убираем только если пуст.
    rmdir "$PROFILE_DIR/extensions" 2>/dev/null || true
fi

# ─── Восстановление бэкапа ──────────────────────────────────────────────────

BACKUP=$(state_get backup_dir)
if [[ -n "$BACKUP" && -f "$BACKUP" ]]; then
    echo ""
    if [[ -z $MYFOX_NONINTERACTIVE ]] && ! confirm "A backup of a previously-occupied directory exists. Restore it?" "n"; then
        log "Backup not restored. It remains at: $BACKUP"
    else
        warn "Restoring backup to $INSTALL_DIR..."
        find "$INSTALL_DIR" -mindepth 1 -delete 2>/dev/null || true
        tar -xzf "$BACKUP" -C "$INSTALL_DIR"
        success "Backup restored."
    fi
fi

# ─── Desktop entry ──────────────────────────────────────────────────────────

firefox_remove_desktop_entry

# ─── Браузер ────────────────────────────────────────────────────────────────

if [[ -d "$INSTALL_DIR" ]]; then
    if [[ -z $MYFOX_NONINTERACTIVE ]] && ! confirm "Remove the Firefox browser itself at $INSTALL_DIR?" "n"; then
        log "Kept Firefox at $INSTALL_DIR."
    else
        rm -rf "$INSTALL_DIR"
        success "Removed $INSTALL_DIR"
    fi
fi

# ─── Маркер ─────────────────────────────────────────────────────────────────

state_clear
success "MyFox has been uninstalled."
echo -e "${GREEN}MyFox uninstalled.${NC}"