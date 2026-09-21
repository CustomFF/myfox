#!/usr/bin/env bash
# uninstall.sh — снимает твики myfox и удаляет инсталляцию.
#
# Интерактивный мастер из двух экранов (dialog/whiptail, fallback — [y/N]):
#   1) «Remove the Firefox application?»  radio Yes/No, кнопки Next/Cancel.
#      No на этом экране = отмена всей деинсталляции.
#   2) «Delete the MyFox profile?»        radio Yes/No, кнопки Back/Cancel/Uninstall.
#      (для existing-профиля: «Remove MyFox tweaks from the profile?» —
#       папка существующего профиля НИКОГДА не удаляется)
# Если профиля в state нет — единственный экран с кнопкой Uninstall.
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
Removes the Firefox application installed by MyFox and (optionally) the MyFox profile.
In interactive mode you'll be asked: remove the application? remove the profile?

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
# created можно удалить целиком; existing — только снять твики (папку не трогаем).
PROFILE_TYPE=""
if [[ -n "$PROFILE_DIR" ]]; then
    if [[ -f "$PROFILE_DIR/.myfox-created" ]]; then
        PROFILE_TYPE="created"
    elif [[ -d "$PROFILE_DIR" ]]; then
        PROFILE_TYPE="existing"
    fi
fi

# ─── Диалог выбора Yes/No ────────────────────────────────────────────────────
#
# Menu с пунктами yes/no (default — no): выбор курсором (стрелки) + Enter,
# как во всех прочих меню мастера. Печатает в stdout выбранный tag и возвращает
# rc: 0 — OK (Next/Uninstall), 1 — Cancel, 3 — Back (extra-button, только
# dialog; у whiptail Back нет). Без tty/no GUI — plain [y/N].
_uninstall_radio() {
    local title="$1" oklabel="$2" back="$3" prompt="$4"
    local out=""
    if [[ -t 0 ]] && { command -v dialog >/dev/null 2>&1 || command -v whiptail >/dev/null 2>&1; }; then
        use_ui_terminfo_noalt || true
        tui_enter
        if command -v dialog >/dev/null 2>&1; then
            local args=(dialog --stdout --clear --title "$title" --ok-label "$oklabel" --cancel-label "Cancel")
            [[ "$back" == "1" ]] && args+=(--extra-button --extra-label "Back")
            args+=(--default-item "no" --no-tags --no-collapse \
                --menu "$prompt" 0 0 0 yes "Yes" no "No")
            out=$("${args[@]}")
        else
            local w=(whiptail --clear --title "$title" --ok-button "$oklabel" --cancel-button "Cancel")
            w+=(--default-item "no" \
                --menu "$prompt" 0 0 0 yes "Yes" no "No")
            out=$("${w[@]}" 3>&1 1>&2 2>&3)
        fi
        tui_reset
        reset_ui_terminfo_noalt
    else
        # Fallback: plain [y/N] / [Y/n] (без кнопки Cancel)
        read -rp "$prompt [y/N] " ans
        case "${ans,,}" in
            y|yes|д|да) printf '%s\n' "yes" && return 0 ;;
            *) printf '%s\n' "no"  && return 0 ;;
        esac
    fi
    printf '%s\n' "$out"
    return 0
}

# Отмена всего uninstall (в т.ч. через No на первом экране).
queued_cancel() {
    echo -e "${YELLOW}Uninstall cancelled.${NC}"
    exit 0
}

# ─── Мастер решений ─────────────────────────────────────────────────────────

DEL_APP="no"      # удалить ли install dir (вместе с desktop entry/autoconfig)
DEL_PROFILE="no"  # created: удалить ли папку профиля; existing: снять ли твики

if [[ -n $MYFOX_NONINTERACTIVE ]]; then
    # -y: согласие на всё. Для existing-профиля это значит «снять твики»,
    # папка существующего профиля и при -y не удаляется.
    DEL_APP="yes"
    DEL_PROFILE="yes"
else
    s1_oklabel="Next"
    [[ -z "$PROFILE_DIR" ]] && s1_oklabel="Uninstall"
    while :; do
        # ── Экран 1: Remove the Firefox application? ──
        out="$(_uninstall_radio "MyFox uninstaller" "$s1_oklabel" 0 \
            "Remove the Firefox application?" 2>/dev/null)" && rc=0 || rc=$?
        [[ "$rc" -eq 1 || "$rc" -eq 255 ]] && queued_cancel
        [[ "$out" == "yes" ]] || queued_cancel
        # Профиля нет — единственный экран, приступаем
        if [[ -z "$PROFILE_DIR" ]]; then
            DEL_APP="yes"
            break
        fi
        # ── Экран 2: профиль (только когда он есть) ──
        if [[ "$PROFILE_TYPE" == "existing" ]]; then
            q2="Remove MyFox tweaks from the profile?"
        else
            q2="Delete the MyFox profile completely (all its data)?"
        fi
        back_to_s1=0
        while :; do
            out="$(_uninstall_radio "MyFox uninstaller" "Uninstall" 1 \
                "$q2" 2>/dev/null)" && rc=0 || rc=$?
            [[ "$rc" -eq 1 || "$rc" -eq 255 ]] && queued_cancel
            if [[ "$rc" -eq 3 ]]; then  # Back → экран 1
                back_to_s1=1
                break
            fi
            DEL_APP="yes"
            DEL_PROFILE="$out"
            break
        done
        [[ "$back_to_s1" == "1" ]] && continue
        break
    done
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

# Профиль
# created + DEL_PROFILE=yes → удалить целиком (папка + запись из profiles.ini).
# created + DEL_PROFILE=no  → папку НЕ трогать, но запись убрать (см. требование
#   «папка остаётся, записи из ini удаляются»). existing — только снять твики.
if [[ "$PROFILE_TYPE" == "created" ]]; then
    if [[ "$DEL_PROFILE" == "yes" ]]; then
        rm -rf "$PROFILE_DIR"
        profile_remove_myfox_section
        success "Myfox profile deleted: $PROFILE_DIR"
    else
        log "Keeping the myfox profile at $PROFILE_DIR."
        profile_remove_myfox_section
    fi
elif [[ "$PROFILE_TYPE" == "existing" && "$DEL_PROFILE" == "yes" && -d "$PROFILE_DIR/chrome" ]]; then
    # Снять твики, восстановить защитные копии стилей (папку не трогаем).
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

# Add-ons (uBlock, theme, plasma-integration) installed per-profile:
# удаляем ТОЛЬКО их (по фиксированным ID). КАТЕГОРИЧЕСКИ НЕЛЬЗЯ сметать
# все *.xpi из extensions/: там живут пользовательские аддоны существующего
# профиля (до 70+ шт. у реальных пользователей).
# Для created+yes аддоны уходят вместе с папкой (rm -rf выше); для created+no
# профиль остаётся как есть — аддоны не трогаем.
MYFOX_ADDON_IDS=(
    "uBlock0@raymondhill.net"                 # uBlock Origin
    "{9631ec37-35f2-4719-815e-2f84ff28b901}"  # Google Chrome Dark (тема)
    "plasma-browser-integration@kde.org"      # KDE Plasma integration
)
if [[ "$PROFILE_TYPE" == "existing" && "$DEL_PROFILE" == "yes" && -n "$PROFILE_DIR" && -d "$PROFILE_DIR/extensions" ]]; then
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

# ─── Desktop entry ──────────────────────────────────────────────────────────

[[ -n "$DEL_APP" ]] && firefox_remove_desktop_entry

# ─── Браузер ────────────────────────────────────────────────────────────────

if [[ -d "$INSTALL_DIR" ]]; then
    rm -rf "$INSTALL_DIR"
    success "Removed $INSTALL_DIR"
fi

# ─── Маркер ─────────────────────────────────────────────────────────────────

state_clear

echo ""
if [[ "$DEL_PROFILE" == "no" && -n "$PROFILE_DIR" ]]; then
    echo -e "${GREEN}Application removed.${NC}"
    echo "  Firefox application uninstalled."
    echo "  MyFox profile kept at: $PROFILE_DIR"
else
    success "MyFox has been uninstalled."
    echo -e "${GREEN}MyFox uninstalled.${NC}"
fi