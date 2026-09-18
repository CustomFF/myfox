#!/usr/bin/env bash
# install.sh — MyFox installer.
#
# Ставит Firefox из официального тарбола и применяет на него твики myfox.
# Опционально применяет букмарклет-твики из отдельного проекта ddblm (raw-файлы).
#
# Использование:
#   install.sh                    полная установка; если уже установлено — меню
#   install.sh --prefix <path>    целевой путь инсталляции (по умолчанию ~/.local/share/firefox)
#   install.sh --reinstall        перекачать браузер заново (даже если инсталляция уже есть)
#   install.sh --browser-only     только тарбол + desktop entry (без профиля/твиков/аддонов)
#   install.sh --update           обновить только твики (из saved state)
#   install.sh --lang <code>      язык Firefox (см. --list-languages)
#   install.sh --list-languages   вывести список доступных языков и выйти
#   install.sh --profile <path>   явно указать профиль (переопределяет детекцию)
#   install.sh --nobl             не применять букмарклет-твики
#   install.sh -y/--yes           без подтверждений
#   install.sh -v/--verbose       подробный вывод (зачем-то)
#   install.sh -h/--help
#
# Повторный запуск без флагов (если состояние уже есть) — интерактивное меню:
#   1) обновить твики (default)  2) перекачать браузер  3) выйти.

set -eo pipefail

MYFOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Отладочный лог таймингов мастера (пишется всегда, если задан MYFOX_DEBUG).
# Использование: MYFOX_DEBUG=1 ./install.sh ...  →  файл ~/.local/state/myfox/debug.log
MYFOX_DEBUG_FILE="${MYFOX_DEBUG_FILE:-$HOME/.local/state/myfox/debug.log}"
MYFOX_DEBUG_START=0
myfox_debug() {  # <label>
    [[ -n "$MYFOX_DEBUG" ]] || return 0
    mkdir -p "$(dirname "$MYFOX_DEBUG_FILE")"
    [[ "$MYFOX_DEBUG_START" -eq 0 ]] && MYFOX_DEBUG_START=$(date +%s%3N)
    local now
    now=$(date +%s%3N)
    printf '%s\t%+dms\t%s\n' "$(date +%H:%M:%S.%3N)" "$(( now - MYFOX_DEBUG_START ))" "$*" \
        >> "$MYFOX_DEBUG_FILE"
}

usage() {
    cat <<EOF
MyFox installer — Firefox from tarball + tweaks.

Usage: $0 [options]

Modes (mutually exclusive):
  (none)             Full install (default). If already installed: interactive menu.
  --reinstall        Force re-download of the browser and re-apply everything
  --browser-only     Install only the tarball + desktop entry (no profile / tweaks)
  --update           Update tweaks only (uses the saved install & profile)
  --list-languages   Print available Firefox languages and exit

Options:
  --prefix <path>    Install directory (default: ~/.local/share/firefox)
  --profile <path>   Explicit Firefox profile directory (overrides detection)
  --lang <code>      Firefox language (validated against Mozilla; see --list-languages)
  --nobl             Skip bookmarklet tweaks
  --noaddons         Skip add-ons and browser theme installation (uBlock, theme)
  --plasma-integration  Force install KDE Plasma integration (no prompt)
  --noplasma         Skip KDE Plasma integration even under Plasma
  -y, --yes          Non-interactive (no prompts)
  -v, --verbose      Verbose output (per-step [INF]/[OK] logs)
  -h, --help         Show this help
EOF
}

# ─── Парсинг аргументов ─────────────────────────────────────────────────────

PREFIX=""
PROFILE_ARG=""
LANG_ARG=""
LIST_LANGUAGES=""
MODE=""
NOBL=false
NOADDONS=false
PLASMA_FORCE=false
NO_PLASMA=false
PLASMA_PKG_HINT=""  # команда установки системного пакета, если он не найден (для подсказки в конце)
MYFOX_NONINTERACTIVE="${MYFOX_NONINTERACTIVE:-}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --prefix)   PREFIX="$2"; shift 2 ;;
        --reinstall|--browser-only|--update)
            [[ -n "$MODE" ]] && { echo "Modes --reinstall / --browser-only / --update are mutually exclusive." >&2; exit 1; }
            MODE="${1#--}"; shift ;;
        --profile)  PROFILE_ARG="$2"; shift 2 ;;
        --lang)     LANG_ARG="$2"; shift 2 ;;
        --list-languages) LIST_LANGUAGES=1; shift ;;
        --nobl)     NOBL=true; shift ;;
        --noaddons) NOADDONS=true; shift ;;
        --plasma-integration) PLASMA_FORCE=true; shift ;;
        --noplasma) NO_PLASMA=true; shift ;;
        -y|--yes)   MYFOX_NONINTERACTIVE=1; shift ;;
        -v|--verbose) MYFOX_VERBOSE=1; shift ;;
        -h|--help)  usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
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
# shellcheck source=lib/addons.sh
. "$MYFOX_ROOT/lib/addons.sh"

check_deps

# --list-languages печатает список и выходит, игнорируя остальные флаги.
if [[ -n "$LIST_LANGUAGES" ]]; then
    firefox_list_languages
    exit 0
fi

# Валидация языка --lang (по каталогу Mozilla).
if [[ -n "$LANG_ARG" ]] && ! firefox_validate_lang "$LANG_ARG"; then
    error "Unknown Firefox language code: '$LANG_ARG' (see --list-languages)."
fi

# --lang/--profile несовместимы с --update.
if [[ "$MODE" == "update" && ( -n "$LANG_ARG" || -n "$PROFILE_ARG" ) ]]; then
    error "--lang / --profile are not valid with --update."
fi

# ─── Определение целевого пути инсталляции ─────────────────────────────────

if [[ -n "$PREFIX" ]]; then
    INSTALL_DIR="$PREFIX"
elif saved=$(state_get install_dir); [[ -n "$saved" ]]; then
    INSTALL_DIR="$saved"
else
    INSTALL_DIR="$MYFOX_DEFAULT_PREFIX"
fi

# ─── Функции режимов ────────────────────────────────────────────────────────

# Интерактивное меню повторного запуска (состояние уже есть).
menu_select_mode() {
    if [[ -n "$MYFOX_NONINTERACTIVE" ]]; then
        MODE="update"
        return 0
    fi
    log "MyFox is already installed at $INSTALL_DIR. What do you want to do?"
    local text="MyFox is already installed at ${INSTALL_DIR}.\nSelect an action:"
    # Меню через dialog/whiptail, когда есть GUI и stdin — tty (вне gauge).
    if [[ -t 0 && -z "${MYFOX_GAUGE_FD:-}" ]] \
        && { command -v dialog >/dev/null 2>&1 || command -v whiptail >/dev/null 2>&1; }; then
        local tag rc=0
        tui_enter
        if command -v dialog >/dev/null 2>&1; then
            tag=$(dialog --stdout --clear --ok-label "OK" --cancel-label "Quit" \
                --default-item "update" --menu "$text" 0 0 0 \
                "update"    "Update tweaks (default)" \
                "reinstall" "Reinstall the browser (re-download + re-apply everything)" \
                "quit"      "Quit") || rc=$?
        else
            tag=$(whiptail --clear --ok-button "OK" --default-item "update" \
                --menu "$text" 0 0 0 \
                "update"    "Update tweaks (default)" \
                "reinstall" "Reinstall the browser (re-download + re-apply everything)" \
                "quit"      "Quit" 3>&1 1>&2 2>&3) || rc=$?
        fi
        tui_reset
        case "${tag:-$rc}" in
            update) MODE="update" ;;
            reinstall) MODE="reinstall" ;;
            *) echo "Quit." >&2; exit 0 ;;
        esac
        return 0
    fi
    # Fallback: plain-меню
    echo ""
    echo "  ${BOLD}1) Update tweaks (default)${NC}"
    echo "  2) Reinstall the browser (re-download + re-apply everything)"
    echo "  3) Quit"
    echo ""
    local ans
    read -rp "Choice [1]: " ans
    case "${ans:-1}" in
        1) MODE="update" ;;
        2) MODE="reinstall" ;;
        3) echo "Quit." >&2; exit 0 ;;
        *) warn "Unknown choice — continuing with 'Update tweaks'."; MODE="update" ;;
    esac
}

# Выбор языка: --lang → сохранённый opts.lang → автодетект.
# Интерактивный выбор — только первая установка (нет saved opts).
resolve_lang() {
    local saved
    saved=$(opts_get lang)
    if [[ -n "$LANG_ARG" ]]; then
        LANG_CODE="$LANG_ARG"
    elif [[ -n "$saved" || -n "$MYFOX_NONINTERACTIVE" ]]; then
        LANG_CODE="${saved:-$(firefox_detect_lang)}"
    else
        LANG_CODE=$(firefox_interactive_lang) || { echo "Cancelled." >&2; exit 0; }
    fi
}

# Запуск tar-INSTALL из капчи; firefox_install_tarball вызывается в $(...),
# поэтому её exit нельзя распознать как выход всего скрипта:
#   rc 2 — пользователь отменил после баннера ("Cancelled." уже напечатан) → выход 0;
#   прочие rc != 0 — download/извлечение упали ([ERR] уже напечатан) → выход с тем же кодом.
fetch_tarball_version() {
    local rc=0
    FIREFOX_VERSION=$(firefox_install_tarball "$@") || rc=$?
    if [[ "$rc" -eq 2 ]]; then
        exit 0
    elif [[ "$rc" -ne 0 ]]; then
        exit "$rc"
    fi
}

# Установка/переинсталляция браузера из тарбола. Аргументы: <first_install: yes|no>
# Возвращает в переменную FIREFOX_VERSION номер версии.
install_browser_tarball() {
    local first_install="$1"
    FIREFOX_VERSION=""

    if [[ "$first_install" == "reinstall" ]]; then
        # Чужая занятая директория (не наша) — бэкап; наша — просто перекатываем.
        if [[ -d "$INSTALL_DIR" && -n "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]] \
           && [[ ! -f "$INSTALL_DIR/.myfox-installed" ]]; then
            warn "Something is already present in $INSTALL_DIR (hand-installed Firefox?)."
            local backup
            backup=$(backup_dir_nonempty "$INSTALL_DIR")
            if [[ -n "$backup" ]]; then
                success "Backup created: $backup"
                state_set backup_dir "$backup"
            fi
        fi
        log "Reinstalling Firefox cleanly..."
        find "$INSTALL_DIR" -mindepth 1 -delete 2>/dev/null || true
        fetch_tarball_version "$INSTALL_DIR" "$LANG_CODE" "$CHANNEL"
    elif [[ -f "$INSTALL_DIR/application.ini" && -f "$INSTALL_DIR/.myfox-installed" ]]; then
        log "Firefox already installed (myfox) at $INSTALL_DIR."
        FIREFOX_VERSION=$(firefox_local_version "$INSTALL_DIR")
    elif [[ -d "$INSTALL_DIR" && -n "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]]; then
        warn "Something is already present in $INSTALL_DIR (hand-installed Firefox?)."
        local backup
        backup=$(backup_dir_nonempty "$INSTALL_DIR")
        if [[ -n "$backup" ]]; then
            success "Backup created: $backup"
            state_set backup_dir "$backup"
        fi
        log "Reinstalling Firefox cleanly..."
        find "$INSTALL_DIR" -mindepth 1 -delete 2>/dev/null || true
        fetch_tarball_version "$INSTALL_DIR" "$LANG_CODE" "$CHANNEL"
    else
        fetch_tarball_version "$INSTALL_DIR" "$LANG_CODE" "$CHANNEL"
    fi

    touch "$INSTALL_DIR/.myfox-installed"
    [[ -n "$FIREFOX_VERSION" ]] && state_set firefox_version "$FIREFOX_VERSION"
}

# Обновление только твиков (autoconfig + chrome; букмарклеты если opts.bl=true).
run_update() {
    INSTALL_DIR=$(state_get install_dir)
    PROFILE_DIR=$(state_get profile_dir)
    if [[ -z "$INSTALL_DIR" || -z "$PROFILE_DIR" ]]; then
        error "No saved installation found — run ${0##*/} for a full install."
    fi
    if [[ ! -f "$INSTALL_DIR/application.ini" ]]; then
        error "Firefox not found at $INSTALL_DIR — run ${0##*/} --reinstall."
    fi
    if [[ ! -d "$PROFILE_DIR" ]]; then
        error "Profile not found at $PROFILE_DIR."
    fi

    log "Updating tweaks: install=$INSTALL_DIR profile=$PROFILE_DIR"
    apply_autoconfig "$INSTALL_DIR"
    apply_chrome "$PROFILE_DIR"

    if [[ "$(opts_get bl)" == "true" ]]; then
        local gallery
        gallery=$(apply_bookmarklets "$PROFILE_DIR") || true
        [[ -n "$gallery" ]] && log "Bookmarklet gallery: $gallery"
    else
        log "Bookmarklet tweaks skipped (saved opts.bl=false)."
    fi

    success "Tweaks updated."
    print_summary
}

# Первая строка любого режима — сразу видно, что происходит и куда
    # (обычный echo, а не log: в тихом режиме иначе экран молчит).
    install_banner() {
        echo -e "${BOLD}MyFox install${NC} → ${INSTALL_DIR}" >&2
    }

    # Только браузер: тарбол + desktop entry, без профиля/твиков. Свой профиль
    # Firefox создаст сам при первом запуске (дедикейтед).
    run_browser_only() {
    install_banner
    : "${CHANNEL:=${MYFOX_CHANNEL:-stable}}"
    resolve_lang

    if [[ -f "$INSTALL_DIR/application.ini" && -f "$INSTALL_DIR/.myfox-installed" ]]; then
        log "Firefox already installed at $INSTALL_DIR — refreshing state and desktop entry."
        FIREFOX_VERSION=$(firefox_local_version "$INSTALL_DIR")
    elif [[ -d "$INSTALL_DIR" && -n "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]]; then
        warn "Something is already present in $INSTALL_DIR (hand-installed Firefox?)."
        local backup
        backup=$(backup_dir_nonempty "$INSTALL_DIR")
        if [[ -n "$backup" ]]; then
            success "Backup created: $backup"
            state_set backup_dir "$backup"
        fi
        find "$INSTALL_DIR" -mindepth 1 -delete 2>/dev/null || true
        fetch_tarball_version "$INSTALL_DIR" "$LANG_CODE" "$CHANNEL"
    else
        fetch_tarball_version "$INSTALL_DIR" "$LANG_CODE" "$CHANNEL"
    fi

    touch "$INSTALL_DIR/.myfox-installed"
    [[ -n "$FIREFOX_VERSION" ]] && state_set firefox_version "$FIREFOX_VERSION"
    state_set install_dir "$INSTALL_DIR"
    state_set installed_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

    opts_set browser_only true
    opts_set lang "$LANG_CODE"

    firefox_create_desktop_entry "$INSTALL_DIR" "$MYFOX_DESKTOP_TITLE" "$MYFOX_DESKTOP_NAME"
    success "Firefox (browser-only) installed."
    print_summary
}

# ─── Интерактивный мастер установки (dialog/whiptail) ────────────────────────
#
# Шаги (всё на английском):
#   1) welcome — пояснение;  Continue / Cancel
#   2) language — выбор языка;  Continue / Cancel
#   3) tweaked profile — твики myfox (да/нет); если «да» — подвопрос про
#      букмарклеты;  Back / Continue / Cancel
#   4) firefox build — stable / beta;  Back / Cancel / Install
#
# Навигация: рс 0 = Continue/OK, 1 = No/Cancel, 3 = Back (dialog), 255 = Esc.
# dialog полностью; whiptail — те же шаги без кнопки Back. Если нет ни того,
# ни другого — мастер не запускается (работает старый последовательный поток).

wizard_available() {
    command -v dialog >/dev/null 2>&1 || command -v whiptail >/dev/null 2>&1
}

wizard_cancel() {
    unset MYFOX_TUI_FENCED
    tui_reset
    reset_ui_terminfo_noalt
    echo "Cancelled." >&2
    exit 0
}

# yes/no-диалог. <back:0|1> <text> [<no-label>]. Alt-screen'ом владеет wizard_full
# (одна пара tui_enter/tui_reset на все диалоги). От мигания между диалогами
# спасает не --keep-tite, а terminfo без smcup/rmcup (use_ui_terminfo_noalt),
# поэтому dialog рисует в текущий экран.
# Semantics кнопок: "Cancel" — всегда отмена всего мастера; "No" — отрицательный
# ответ на вопрос (выполнение продолжается); "Back" — к предыдущему шагу.
_wiz_yesno() {
    local back="$1" text="$2" nolabel="${3:-Cancel}" rc=0
    if command -v dialog >/dev/null 2>&1; then
        local args=(--stdout --clear --yes-label "Continue" --no-label "$nolabel")
        [[ "$back" == "1" ]] && args+=(--extra-button --extra-label "Back")
        dialog "${args[@]}" --yesno "$text" 0 0
        rc=$?
    else
        whiptail --clear --yes-button "Continue" --no-button "$nolabel" --yesno "$text" 0 0
        rc=$?
    fi
    return $rc
}

# меню. Устанавливает глобальную WIZ_TAG (выбранный tag).
# _wiz_menu <ok-label> <back:0|1> <default-tag> <text> tag label [tag label …]
_wiz_menu() {
    local oklabel="$1" back="$2" deftag="$3" text="$4"
    shift 4
    local items=()
    while [[ $# -gt 0 ]]; do
        items+=("$1" "$2")
        shift 2
    done
    WIZ_TAG=""
    local rc=0
    if command -v dialog >/dev/null 2>&1; then
        local args=(dialog --stdout --clear --ok-label "$oklabel")
        [[ -n "$deftag" ]] && args+=(--default-item "$deftag")
        [[ "$back" == "1" ]] && args+=(--extra-button --extra-label "Back")
        args+=(--menu "$text" 0 0 0 "${items[@]}")
        if WIZ_TAG=$("${args[@]}"); then
            rc=0
        else
            rc=$?
        fi
    else
        local args=(whiptail --clear)
        [[ -n "$deftag" ]] && args+=(--default-item "$deftag")
        args+=(--menu "$text" 0 0 0 "${items[@]}")
        if WIZ_TAG=$("${args[@]}" 3>&1 1>&2 2>&3); then
            rc=0
        else
            rc=$?
        fi
    fi
    return $rc
}

# Мастер устанавливает глобальные: LANG_CODE, TWEAKED_PROFILE, BL_ON, CHANNEL.
# Вход/выход из альтернативного экрана — ОДНА пара tui_enter/tui_reset на весь
# мастер. Чтобы dialog не переключал alt-экран между диалогами (иначе мигает
# главный экран с промптом), заранее ставим terminfo без smcup/rmcup
# (use_ui_terminfo_noalt).
wizard_full() {
    local step="welcome" rc=0
    LANG_CODE=""
    TWEAKED_PROFILE=true
    BL_ON=false
    CHANNEL="stable"
    WIZ_PROFILE=""        # выбранный существующий myfox-профиль (путь)
    WIZ_PROFILE_NEW=0     # 1 — мастер решил «создать новый myfox-N»
    # Шаг 4 заканчивается кнопкой Install — отдельный «Proceed?» не нужен.
    MYFOX_SKIP_CONFIRM=1

    # Список языков Mozilla строим ДО входа в альт-экран, синхронно (каталог
    # качается на обычном экране). К языковому шагу список всегда готов, поэтому
    # между диалогами мастера не выполняется ни одной операции и экраны не
    # мигают. Если сети нет — шаг lang честно покажет ошибку и прервёт мастер.
    myfox_debug "wizard: enter"
    firefox_prepare_lang_list || true
    use_ui_terminfo_noalt || true
    tui_enter
    export MYFOX_TUI_FENCED=1
    while true; do
        case "$step" in
            welcome)
                rc=0
                _wiz_yesno 0 \
"Welcome to MyFox installer.

This will:
  - download Firefox (Stable or Beta) from the official Mozilla tarball,
  - create a profile and, optionally, apply MyFox tweaks
      (Autoconfig, userChrome.css, preferences, bookmarklet icons),
  - install advisory add-ons (uBlock Origin + a dark theme).

Install target: ${INSTALL_DIR}

Continue?" || rc=$?
                myfox_debug "welcome dialog closed rc=$rc (Continue→0)"
                [[ "$rc" -eq 0 ]] && step="lang" || wizard_cancel
                ;;
            lang)
                myfox_debug "lang: step list=${MYFOX_LANG_LIST:-EMPTY} json=$(stat -c %s "${MYFOX_LANG_JSON:-}" 2>/dev/null || echo '?')B"
                if ! LANG_CODE=$(firefox_interactive_lang); then
                    wizard_cancel
                fi
                myfox_debug "lang: done code=$LANG_CODE"
                step="profile"
                ;;
            profile)
                # Шаг выбора профиля: показываем только наши myfox-профили
                # (чужие браузеры не пересекаем) + «создать новый» по умолчанию.
                # Если myfox-профилей нет — выбор пропускается.
                rc=0
                local prof_list="" prof_found=0
                prof_list=$(profile_list_myfox || true)
                if [[ -n "$prof_list" ]]; then
                    local prof_items=("new" "Create a new MyFox profile (recommended)")
                    local pp=""
                    while IFS='|' read -r pp _unused; do
                        [[ -z "$pp" ]] && continue
                        prof_found=1
                        prof_items+=("$pp" "Existing MyFox profile  ($(basename "$pp"))")
                    done <<< "$prof_list"
                    _wiz_menu "Continue" 1 "new" \
"Select the Firefox profile to use (only MyFox profiles are listed):" \
                        "${prof_items[@]}" || rc=$?
                    if [[ "$rc" -eq 3 ]]; then
                        step="lang"
                    elif [[ "$rc" -ne 0 || -z "$WIZ_TAG" ]]; then
                        wizard_cancel
                    else
                        if [[ "$WIZ_TAG" == "new" ]]; then
                            WIZ_PROFILE_NEW=1
                            WIZ_PROFILE=""
                        else
                            WIZ_PROFILE_NEW=0
                            WIZ_PROFILE="$WIZ_TAG"
                        fi
                        if [[ "$WIZ_PROFILE_NEW" == 1 ]]; then
                            step="profilestyle"
                        else
                            TWEAKED_PROFILE=true
                            step="bl"
                        fi
                    fi
                else
                    WIZ_PROFILE_NEW=1
                    WIZ_PROFILE=""
                    step="profilestyle"
                fi
                ;;
            profilestyle)
                rc=0
                _wiz_menu "Continue" 1 "tweaked" \
"Do you want to apply MyFox tweaks to the new Firefox profile?" \
"tweaked" "Yes — tweaked profile (Autoconfig, userChrome, prefs)" \
"clean"   "No — clean profile (unmodified)" || rc=$?
                if [[ "$rc" -eq 3 ]]; then
                    step="profile"
                elif [[ "$rc" -ne 0 || -z "$WIZ_TAG" ]]; then
                    wizard_cancel
                else
                    [[ "$WIZ_TAG" == "tweaked" ]] && TWEAKED_PROFILE=true
                    [[ "$WIZ_TAG" == "clean" ]] && TWEAKED_PROFILE=false
                    if [[ "$TWEAKED_PROFILE" == true ]]; then
                        step="bl"
                    else
                        step="version"
                    fi
                fi
                ;;
            bl)
                rc=0
                _wiz_yesno 1 \
"Apply bookmarklet tweaks (icons + hidden labels from the ddblm project)?" "No" \
                    || rc=$?
                case "$rc" in
                    0) BL_ON=true;  step="version" ;;
                    1) BL_ON=false; step="version" ;;
                    3) { [[ "$WIZ_PROFILE_NEW" == 1 ]] && step="profilestyle" || step="profile"; } ;;
                    *) wizard_cancel ;;
                esac
                ;;
            version)
                rc=0
                _wiz_menu "Install" 1 "stable" \
"Firefox build to download from Mozilla:" \
"stable" "Stable — latest release" \
"beta"   "Beta — next version" || rc=$?
                if [[ "$rc" -eq 3 ]]; then
                    if [[ "$TWEAKED_PROFILE" == true ]]; then
                        step="bl"
                    else
                        step="profile"
                    fi
                elif [[ "$rc" -ne 0 ]]; then
                    wizard_cancel
                else
                    [[ "$WIZ_TAG" == "beta" ]] && CHANNEL="beta" || CHANNEL="stable"
                    # Alt-экран НЕ покидаем: установка — финальный шаг мастера
                    # (gauge-прогресс), выход из alt-экрана и сводка — в конце,
                    # в _wizard_finish. Так пользователь не видит ни одного
                    # переключения экрана от старта до готового результата.
                    MYFOX_WIZARD_INSTALL=1
                    return 0
                fi
                ;;
        esac
    done
}

# Завершение установки в режиме мастера: закрыть gauge, выйти из alt-экрана и
# напечатать сводку УЖЕ на обычном экране — так она остаётся видимой. Для путей
# без мастера это просто print_summary (gauge не открыт, tui не активирован).
_wizard_finish() {
    gauge_close
    if [[ -n "$MYFOX_TUI_FENCED" ]]; then
        unset MYFOX_TUI_FENCED MYFOX_WIZARD_INSTALL
        tui_reset
        reset_ui_terminfo_noalt
    fi
    print_summary
}

# Аварийная очистка (EXIT-trap): если установка в мастере прервана ошибкой,
# нужно закрыть gauge и вернуть терминал из alt-экрана, иначе он останется
# «висящим». На нормальном завершении _wizard_finish уже всё снял — no-op.
_wizard_trap_cleanup() {
    local rc=$?
    gauge_close
    if [[ -n "$MYFOX_TUI_FENCED" ]]; then
        unset MYFOX_TUI_FENCED MYFOX_WIZARD_INSTALL
        tui_reset
        reset_ui_terminfo_noalt
    fi
    return "$rc"
}

# Полная установка или --reinstall: тарбол + профиль + пиннинг + твики + всё прочее.
run_full() {
    myfox_debug "run_full: begin"
    # Интерактивный (настоящий терминал, без -y) и есть dialog/whiptail → мастер.
    local wizard_run=false
    if [[ -z "$MYFOX_NONINTERACTIVE" && -t 0 ]] && wizard_available; then
        wizard_full
        wizard_run=true
    else
        install_banner
        resolve_lang
        TWEAKED_PROFILE=true
    fi
    : "${CHANNEL:=${MYFOX_CHANNEL:-stable}}"
    local do_bookmarklets=""

    # В мастере установка идёт внутри alt-экрана как его финальный шаг: держим
    # открытый dialog-gauge и обновляем его вместо текстовых логов.
    if [[ "$wizard_run" == true && -n "$MYFOX_WIZARD_INSTALL" ]]; then
        trap '_wizard_trap_cleanup' EXIT
        gauge_open "Installing Firefox (myfox)" 8 || true
    fi
    gauge_set 2 "Preparing installation…"

    if [[ "$MODE" == "reinstall" ]]; then
        install_browser_tarball reinstall
    else
        install_browser_tarball first
    fi
    gauge_set 72 "Preparing profile…"

    state_set install_dir "$INSTALL_DIR"
    state_set installed_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    opts_set browser_only false
    opts_set lang "$LANG_CODE"
    opts_set channel "$CHANNEL"

    # ─── Профиль ────────────────────────────────────────────────────────────
    # В мастере профиль уже выбран на шаге profile (до gauge): либо существующий
    # myfox-профиль (WIZ_PROFILE → --explicit), либо «создать новый»
    # (MYFOX_PROFILE_FORCE_NEW=1). Так в run_full не выполняется ни одного
    # интерактивного read поверх gauge/alt-экрана.
    if [[ "$WIZ_PROFILE_NEW" == "1" ]]; then
        PROFILE_DIR=$(MYFOX_PROFILE_FORCE_NEW=1 profile_resolve --explicit "$PROFILE_ARG")
    elif [[ -n "${WIZ_PROFILE:-}" ]]; then
        PROFILE_DIR=$(profile_resolve --explicit "$WIZ_PROFILE")
        log "Using selected profile: $WIZ_PROFILE"
    else
        PROFILE_DIR=$(profile_resolve --explicit "$PROFILE_ARG")
    fi
    state_set profile_dir "$PROFILE_DIR"
    log "Using Firefox profile: $PROFILE_DIR"

    if [[ "$TWEAKED_PROFILE" == "false" ]]; then
        # Чистый профиль: твики не применяются вообще (маркер .myfox не ставим,
        # firefox.cfg по guard не сработает), букмарклеты/аддоны — выкл.
        log "Clean profile — MyFox tweaks skipped."
firefox_create_desktop_entry "$INSTALL_DIR" "$MYFOX_DESKTOP_TITLE" "$MYFOX_DESKTOP_NAME"
        opts_set bl false
        opts_set addons false
        gauge_set 100 "Done"
        _wizard_finish
        return 0
    fi

    # ─── Пиннинг профиля на инсталляцию ────────────────────────────────────
    gauge_set 76 "Pinning profile to this installation…"
    local pin_hash
    pin_hash=$(profile_pin_install "$INSTALL_DIR" "$PROFILE_DIR") || true
    if [[ -n "$pin_hash" ]]; then
        state_set install_hash "$pin_hash"
    fi

    # ─── Твики ──────────────────────────────────────────────────────────────
    gauge_set 88 "Applying tweaks…"
    apply_autoconfig "$INSTALL_DIR"
    apply_chrome "$PROFILE_DIR"
    firefox_create_desktop_entry "$INSTALL_DIR" "$MYFOX_DESKTOP_TITLE" "$MYFOX_DESKTOP_NAME"

    # ─── Букмарклеты (опционально) ─────────────────────────────────────────
    if [[ "$NOBL" == true ]]; then
        opts_set bl false
        log "Bookmarklet tweaks skipped (--nobl)."
    elif [[ "$wizard_run" == true ]]; then
        if [[ "$BL_ON" == true ]]; then
            log "Bookmarklet tweaks: enabled (wizard choice)."
            do_bookmarklets="$PROFILE_DIR"
        else
            opts_set bl false
            log "Bookmarklet tweaks skipped (wizard choice)."
            do_bookmarklets=""
        fi
    elif opts_has bl; then
        if [[ "$(opts_get bl)" == "true" ]]; then
            log "Bookmarklet tweaks: enabled (saved choice)."
            do_bookmarklets="$PROFILE_DIR"
        else
            opts_set bl false
            log "Bookmarklet tweaks skipped (saved opts.bl=false)."
            do_bookmarklets=""
        fi
    elif confirm "Apply bookmarklet tweaks (icons + hidden labels from ddblm) and open the gallery page?" "true"; then
        do_bookmarklets="$PROFILE_DIR"
    else
        opts_set bl false
        log "Bookmarklet tweaks skipped."
        do_bookmarklets=""
    fi
    if [[ -n "$do_bookmarklets" ]]; then
        local gallery
        gauge_set 93 "Applying bookmarklet tweaks…"
        gallery=$(apply_bookmarklets "$do_bookmarklets") || true
        if [[ -n "$gallery" ]]; then
            log "Bookmarklet gallery: $gallery"
            log "Drag bookmarklet cards from there onto your Bookmarks Toolbar."
        fi
        opts_set bl true
    fi

    # ─── Дополнения (add-ons): uBlock, тема, plasma-integration ─────────────
    gauge_set 96 "Installing add-ons…"
    install_addons "$wizard_run"

    gauge_set 100 "Done"
    _wizard_finish
}

# Дополнения: uBlock + тема по умолчанию; KDE Plasma — если сессия Plasma /
# флаг (флаг перекрывает), с учётом сохранённого opts.plasma.
# Первый аргумент — `true`, если установка идёт через мастер (wizard): тогда
# подтверждение не спрашиваем, аддоны ставятся по умолчанию.
install_addons() {
    local wizard_run="${1:-false}"
    addons_list=()
    PLASMA_PKG_HINT=""

    if [[ "$NOADDONS" == true ]]; then
        opts_set addons false
        log "Add-on installation skipped (--noaddons)."
        return 0
    fi
    if [[ "$wizard_run" == true ]]; then
        opts_set addons true
        log "Add-ons: enabled (wizard default)."
    elif opts_has addons; then
        if [[ "$(opts_get addons)" != "true" ]]; then
            opts_set addons false
            log "Add-on installation skipped (saved opts.addons=false)."
            return 0
        fi
        log "Add-ons: enabled (saved choice)."
    elif confirm "Install add-ons (uBlock Origin + a dark theme)?" "true"; then
        true
    else
        opts_set addons false
        log "Add-on installation skipped."
        return 0
    fi
    opts_set addons true

    addons_list+=("$MYFOX_ADDON_UBLOCK")
    addons_list+=("$MYFOX_ADDON_THEME")

    # KDE Plasma integration: аддон ставится молча (вместе с твиками) в сессии
    # Plasma или при --plasma-integration; --noplasma гасит. Системный пакет
    # проверяется отдельно — если его нет, в конце установки печатаем команду.
    local plasma_opt
    plasma_opt=$(opts_get plasma)
    if [[ "$NO_PLASMA" == true ]]; then
        opts_set plasma false
        log "KDE Plasma integration skipped (--noplasma)."
    elif [[ "$PLASMA_FORCE" == true ]]; then
        opts_set plasma true
        maybe_add_plasma
    elif [[ -n "$plasma_opt" ]]; then
        if [[ "$plasma_opt" == "true" ]]; then
            log "KDE Plasma integration enabled (saved choice)."
            maybe_add_plasma
        else
            log "KDE Plasma integration skipped (saved choice)."
        fi
    elif addons_is_plasma; then
        opts_set plasma true
        log "KDE Plasma integration enabled (Plasma session)."
        maybe_add_plasma
    else
        opts_set plasma false
        log "KDE Plasma integration skipped (not a Plasma session)."
    fi

    if [[ ${#addons_list[@]} -gt 0 ]]; then
        addons_apply "$PROFILE_DIR" "${addons_list[@]}"
    fi
}

# Аддон plasma-integration кладём в addons_list БЕЗ подтверждений (ставится
# молча вместе с твиками), если активна сессия Plasma или задан --plasma-integration.
# Отдельно проверяем системный пакет (native host): если его нет — запоминаем
# команду установки для заметки в конце (в print_summary). Никаких sudo-запросов
# в разрыв диалогов/мастера. Возвращает 0.
maybe_add_plasma() {
    addons_list+=("$MYFOX_ADDON_PLASMA")
    if addons_pkg_installed; then
        log "System package 'plasma-browser-integration' already installed."
        return 0
    fi
    warn "System package 'plasma-browser-integration' is missing (native-messaging host)."
    PLASMA_PKG_HINT=$(addons_pkg_suggest) || true
    if [[ -z "$PLASMA_PKG_HINT" ]]; then
        log "Install 'plasma-browser-integration' manually to enable KDE integration."
    else
        log "Install the package later: ${PLASMA_PKG_HINT}"
    fi
    return 0
}

# Итоговая сводка.
print_summary() {
    echo ""
    echo -e "${BOLD}=== MyFox ===${NC}"
    echo "  Firefox:   ${INSTALL_DIR:-?} (${FIREFOX_VERSION:-latest}, lang ${LANG_CODE:-auto})"
    [[ -n "${PROFILE_DIR:-}" ]] && echo "  Profile:   $PROFILE_DIR"
    echo "  Desktop:   Firefox (myfox)"
    local backup
    backup=$(state_get backup_dir) || true
    [[ -n "$backup" ]] && echo "  Backup:    $backup"
    echo ""
    echo "Run 'firefox (myfox)' from your app menu, or:"
    if [[ -n "${PROFILE_DIR:-}" ]]; then
        echo "  ${INSTALL_DIR}/firefox --profile '${PROFILE_DIR}'"
    else
        echo "  ${INSTALL_DIR}/firefox"
    fi
    echo ""
    echo "To remove: ./uninstall.sh"
    if [[ -n "${PLASMA_PKG_HINT:-}" ]]; then
        echo ""
        echo -e "${BOLD}KDE Plasma integration:${NC} the system package for the browser"
        echo "bridge is missing. To enable it after installing the add-on, run:"
        echo "  ${PLASMA_PKG_HINT}"
    fi
}

# ─── Диспетчер режима ───────────────────────────────────────────────────────

if [[ -z "$MODE" ]]; then
    if [[ -f "$INSTALL_DIR/application.ini" && -f "$INSTALL_DIR/.myfox-installed" ]] \
       && [[ -n "$(state_get install_dir)" && -n "$(state_get profile_dir)" ]]; then
        menu_select_mode
    else
        MODE="install"
    fi
fi

case "$MODE" in
    browser-only) run_browser_only ;;
    update)       run_update ;;
    reinstall|install) run_full ;;
    *)            error "Unknown mode: $MODE" ;;
esac