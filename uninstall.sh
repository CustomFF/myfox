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

MYFOX_NONINTERACTIVE=""
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
if [[ -z $MYFOX_NONINTERACTIVE ]] && ! confirm "Remove MyFox tweaks?" "n"; then
    echo "Cancelled."
    exit 0
fi

# ─── Удаление твиков ────────────────────────────────────────────────────────

# Autoconfig
if [[ -d "$INSTALL_DIR" ]]; then
    rm -f "$INSTALL_DIR/defaults/pref/autoconfig.js" 2>/dev/null || true
    rm -f "$INSTALL_DIR/firefox.cfg" 2>/dev/null || true
    rm -f "$INSTALL_DIR/.myfox-installed" 2>/dev/null || true
    success "Autoconfig files removed from $INSTALL_DIR"
fi

# Chrome styles
if [[ -n "$PROFILE_DIR" && -d "$PROFILE_DIR/chrome" ]]; then
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
    # Симлинки/файлы букмарклет-твиков (blm patchff)
    rm -f "$PROFILE_DIR/chrome/bookmarks_panel.css" 2>/dev/null || true
    rm -f "$PROFILE_DIR/chrome/panel-icons" 2>/dev/null || true
    success "Chrome styles removed from $PROFILE_DIR"
fi

# Add-ons (uBlock, theme, plasma-integration) placed into distribution/extensions
if [[ -d "$INSTALL_DIR/distribution/extensions" ]]; then
    for f in "$INSTALL_DIR"/distribution/extensions/*.xpi; do
        [[ -f "$f" ]] || continue
        rm -f "$f"
        success "Removed add-on distribution file: $(basename "$f")"
    done
    rmdir "$INSTALL_DIR/distribution/extensions" 2>/dev/null || true
    rmdir "$INSTALL_DIR/distribution" 2>/dev/null || true
fi

# Distribution add-ons are copied into the profile by Firefox on first start;
# remove those copies too (unless the browser was never started with them).
if [[ -n "$PROFILE_DIR" && -d "$PROFILE_DIR/extensions" ]]; then
    for f in "$PROFILE_DIR"/extensions/*.xpi; do
        [[ -f "$f" ]] || continue
        rm -f "$f"
        success "Removed add-on from profile: $(basename "$f")"
    done
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
    if [[ -z $MYFOX_NONINTERACTIVE ]] && ! confirm "Remove the Firefox browser itself at $INSTALL_DIR? [y/N]" "n"; then
        log "Kept Firefox at $INSTALL_DIR."
    else
        rm -rf "$INSTALL_DIR"
        success "Removed $INSTALL_DIR"
    fi
fi

# ─── Маркер ─────────────────────────────────────────────────────────────────

state_clear
success "MyFox has been uninstalled."