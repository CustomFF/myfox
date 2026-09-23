# shellcheck shell=bash
# tui.sh — dialog (полностью) / whiptail (без кнопки «Назад» — extra-button
# у него нет) / примитивный bash-фолбэк (read + нумерованный список), если
# нет ни того ни другого. Ничего не качаем — оба инструмента почти всегда
# уже стоят в системе; если нет — просто работаем в примитивном режиме.
# Требует common.sh (цвета, MYFOX_ROOT) и i18n.sh (t()).

MYFOX_TUI_BACKEND_CHECKED=0
MYFOX_TUI_BACKEND=""

# dialog | whiptail | "" (кэш на процесс).
tui_backend() {
    if [[ "$MYFOX_TUI_BACKEND_CHECKED" == 0 ]]; then
        MYFOX_TUI_BACKEND_CHECKED=1
        if command -v dialog >/dev/null 2>&1; then
            MYFOX_TUI_BACKEND=dialog
        elif command -v whiptail >/dev/null 2>&1; then
            MYFOX_TUI_BACKEND=whiptail
        fi
    fi
    printf '%s' "$MYFOX_TUI_BACKEND"
}

MYFOX_TUI_MAX_WIDTH=90

# Ширина диалогового окна: min(ширина терминала - отступы, MYFOX_TUI_MAX_WIDTH)
# — иначе dialog/whiptail с width=0 (авто) растягиваются почти во весь экран
# на широких терминалах, что для простого confirm/меню выглядит нелепо.
_tui_box_width() {
    local cols
    read -r _ cols < <(stty size </dev/tty 2>/dev/null)
    if [[ -z "$cols" ]]; then
        printf '%s' "$MYFOX_TUI_MAX_WIDTH"
        return 0
    fi
    local w=$(( cols - 4 ))
    (( w > MYFOX_TUI_MAX_WIDTH )) && w=$MYFOX_TUI_MAX_WIDTH
    (( w < 20 )) && w=20
    printf '%s' "$w"
}

# Высота диалогового окна по числу строк текста + запас под рамку/кнопки.
# height=0 (авто) у dialog при явно заданной (не авто) ширине после
# --no-collapse иногда даёт слишком маленькую высоту и текст уходит в
# скролл-режим (виден только "0%" в углу и пустое тело) — считаем сами.
_tui_box_height() {  # <text>
    local text="$1" width raw_lines h rows
    raw_lines=$(printf '%s\n' "$text" | wc -l)
    read -r rows _ < <(stty size </dev/tty 2>/dev/null)
    if (( raw_lines > 15 )); then
        # Большой контент (напр. с лого) — не пытаемся точно посчитать
        # перенос по ширине (у некоторых Unicode-символов wcwidth/fold
        # считают ширину не так, как реально рисует терминал — уже
        # проверенная другим способом ширина ненадёжна для точной высоты).
        # Просто берём почти всю доступную высоту — места достаточно,
        # раз мы вообще решили показывать такой большой блок текста.
        if [[ -n "$rows" ]]; then
            h=$(( rows - 2 ))
        else
            h=$(( raw_lines + 10 ))
        fi
    else
        width=$(_tui_box_width)
        # wc -l считает логические строки — dialog короткие переносит по
        # ширине бокса, fold -s -w эмулирует это для обычных (не-лого) строк.
        local wrapped
        wrapped=$(printf '%s\n' "$text" | fold -s -w "$(( width - 2 ))" | wc -l)
        h=$(( wrapped + 8 ))
        if [[ -n "$rows" ]]; then
            (( h > rows - 2 )) && h=$(( rows - 2 ))
        fi
    fi
    (( h < 7 )) && h=7
    printf '%s' "$h"
}

# То же самое, но для --menu: сверху ещё нужно место под сам список (menu_h
# строк), не только под текст заголовка.
_tui_menu_box_height() {  # <header-text> <menu_h>
    local text="$1" menu_h="$2" width lines h rows
    width=$(_tui_box_width)
    lines=$(printf '%s\n' "$text" | fold -s -w "$(( width - 2 ))" | wc -l)
    h=$(( lines + menu_h + 8 ))
    read -r rows _ < <(stty size </dev/tty 2>/dev/null)
    if [[ -n "$rows" ]]; then
        (( h > rows - 2 )) && h=$(( rows - 2 ))
    fi
    (( h < 7 )) && h=7
    printf '%s' "$h"
}

# ─── Alt-screen ─────────────────────────────────────────────────────────────
#
# dialog/whiptail сами входят/выходят из альтернативного экрана (ncurses
# smcup/rmcup) на КАЖДЫЙ вызов. Если этого не сдерживать, на части терминалов
# rmcup не восстанавливает исходный экран корректно — после мастера остаётся
# залитый цветом "мёртвый" экран. Решение: сами один раз входим в alt-screen
# (tui_enter, жёсткая ESC-последовательность, не зависит от terminfo) перед
# ПОСЛЕДОВАТЕЛЬНОСТЬЮ экранов, подсовываем dialog/whiptail копию terminfo без
# smcup/rmcup (они тогда просто рисуют в уже открытый нами экран, не мигая
# между собой), и один раз выходим в конце — эта пара гарантированно
# восстанавливает терминал, что бы ни намудрил dialog внутри.
#
# tui_session_begin/tui_session_end — вокруг ЦЕЛОЙ последовательности экранов
# (напр. install_wizard). Одиночные вызовы (tui_confirm/tui_choose_kv/
# tui_pick_dir вне сессии) сами себя оборачивают через _tui_fence_begin/end.

MYFOX_TUI_FENCED=""
MYFOX_TERMINFO_NOALT=""

tui_enter() {
    [[ -n "$TERM" && "$TERM" != "dumb" ]] || return 0
    printf '\033[?1049h' >/dev/tty 2>/dev/null || true
}

tui_leave() {
    [[ -n "$TERM" && "$TERM" != "dumb" ]] || return 0
    printf '\033[?1049l' >/dev/tty 2>/dev/null || true
    tput sgr0 2>/dev/null >/dev/tty || true
}

# Копия terminfo без smcup/rmcup (остальные возможности, включая цвета,
# сохраняются), кэшируется в ~/.cache/myfox/terminfo. Возврат: путь или пусто.
_tui_terminfo_noalt() {
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

_tui_use_noalt() {
    [[ -n "$MYFOX_TERMINFO_NOALT" ]] && return 0
    local ti
    ti=$(_tui_terminfo_noalt) || return 1
    [[ -n "$ti" ]] || return 1
    MYFOX_TERMINFO_NOALT="$ti"
    export TERMINFO="$ti"
}

_tui_reset_noalt() {
    [[ -n "$MYFOX_TERMINFO_NOALT" ]] || return 0
    unset TERMINFO
    MYFOX_TERMINFO_NOALT=""
}

# Один экран вне сессии: входим/выходим сами. Внутри уже открытой сессии
# (install_wizard и т.п.) — no-op, всем владеет tui_session_begin/end.
_tui_fence_begin() {
    [[ "$MYFOX_TUI_FENCED" == "1" ]] && return 1
    tui_enter
    _tui_use_noalt || true
    return 0
}
_tui_fence_end() {
    _tui_reset_noalt
    tui_leave
}

# Оборачивает последовательность из нескольких экранов одной парой
# enter/leave — вызывающий код обязан гарантировать tui_session_end (в т.ч.
# через EXIT-trap), иначе терминал останется в alt-screen при аварийном выходе.
tui_session_begin() {
    [[ "$MYFOX_TUI_FENCED" == "1" ]] && return 0
    tui_enter
    _tui_use_noalt || true
    MYFOX_TUI_FENCED=1
}
tui_session_end() {
    [[ "$MYFOX_TUI_FENCED" != "1" ]] && return 0
    MYFOX_TUI_FENCED=""
    _tui_reset_noalt
    tui_leave
}

# ─── Виджеты ────────────────────────────────────────────────────────────────

# Переносит пару <default-value> в начало массивов values/labels (по месту).
# Нужно только примитивному bash-фолбэку — у dialog/whiptail есть родной
# --default-item, реордер списка им не требуется.
_tui_move_default_first() {  # <default-value> <values-array-name> <labels-array-name>
    local default="$1" vname="$2" lname="$3"
    [[ -z "$default" ]] && return 0
    local -n _v="$vname" _l="$lname"
    local i
    for i in "${!_v[@]}"; do
        if [[ "${_v[$i]}" == "$default" && "$i" != "0" ]]; then
            local dv="${_v[$i]}" dl="${_l[$i]}"
            unset '_v[i]' '_l[i]'
            _v=("$dv" "${_v[@]}")
            _l=("$dl" "${_l[@]}")
            return 0
        fi
    done
}

# tui_confirm <prompt> [default: yes|no] → rc 0=да 1=нет/отмена.
# -y (MYFOX_NONINTERACTIVE) всегда «да», как и раньше.
tui_confirm() {
    local prompt="$1" default="${2:-yes}" back="${3:-0}" \
        yeslabel="${4:-$(t opt_yes)}" nolabel="${5:-$(t opt_no)}" \
        height_override="${6:-}" width_override="${7:-}"
    [[ -n "${MYFOX_NONINTERACTIVE:-}" ]] && return 0
    local backend defno=""
    backend=$(tui_backend)
    [[ "$default" == "no" ]] && defno="--defaultno"
    if [[ -n "$backend" ]]; then
        local fenced_here=0
        _tui_fence_begin && fenced_here=1
        local rc=0 h w
        h="${height_override:-$(_tui_box_height "$prompt")}"
        w="${width_override:-$(_tui_box_width)}"
        if [[ "$backend" == "dialog" ]]; then
            local -a args=(--clear --no-collapse --yes-label "$yeslabel" --no-label "$nolabel")
            [[ "$back" == "1" ]] && args+=(--extra-button --extra-label "$(t tui_back_option)")
            dialog "${args[@]}" $defno --yesno "$prompt" "$h" "$w" || rc=$?
        else
            whiptail --clear --yes-button "$yeslabel" --no-button "$nolabel" \
                $defno --yesno "$prompt" "$h" "$w" || rc=$?
        fi
        [[ "$fenced_here" == 1 ]] && _tui_fence_end
        case "$rc" in
            0) return 0 ;;
            3) [[ "$backend" == "dialog" && "$back" == "1" ]] && return 3 || return 1 ;;
            *) return 1 ;;
        esac
    fi
    local marker ans
    [[ "$default" == "yes" ]] && marker="[Y/n]" || marker="[y/N]"
    read -rp "$prompt $marker " ans </dev/tty
    ans="${ans,,}"
    case "$ans" in
        y|yes|д|да) return 0 ;;
        "")         [[ "$default" == "yes" ]] && return 0 || return 1 ;;
        *)          return 1 ;;
    esac
}

MYFOX_BACK_TAG="__myfox_back__"
MYFOX_HEADER_TAG="__myfox_header__"

# tui_choose_kv <header> <default-value> <back:0|1> <notags:0|1> <value1> <label1> [...]
# stdout: выбранный value. rc 0=выбор, 1=отмена, 3=«Назад» (только dialog).
# notags=1 — для табличных списков (профили): скрывает колонку тега у dialog
# (--no-tags), первая пара в kv тогда должна быть строкой заголовка колонок
# с тегом MYFOX_HEADER_TAG — выбор такой строки просто перерисовывает меню.
tui_choose_kv() {
    local header="$1" default="$2" back="$3" notags="$4"; shift 4
    local -a values=() labels=()
    while [[ $# -gt 0 ]]; do
        values+=("$1"); labels+=("$2"); shift 2
    done

    local backend; backend=$(tui_backend)
    if [[ -n "$backend" ]]; then
        # menu-height (3-й числовой параметр --menu) — по факту числа пунктов,
        # иначе при auto (0) dialog/whiptail разводят пустое место под список
        # с запасом на много больше строк, чем реально есть.
        local menu_h=${#values[@]}
        (( menu_h > 12 )) && menu_h=12
        (( menu_h < 1 )) && menu_h=1
        while true; do
            local -a items=()
            local i
            for i in "${!values[@]}"; do items+=("${values[$i]}" "${labels[$i]}"); done
            local fenced_here=0
            _tui_fence_begin && fenced_here=1
            local tag rc=0
            if [[ "$backend" == "dialog" ]]; then
                local -a args=(--stdout --clear --ok-label "$(t opt_ok)" --cancel-label "$(t opt_cancel)")
                [[ -n "$default" ]] && args+=(--default-item "$default")
                [[ "$back" == "1" ]] && args+=(--extra-button --extra-label "$(t tui_back_option)")
                [[ "$notags" == "1" ]] && args+=(--no-tags --no-collapse)
                tag=$(dialog "${args[@]}" --menu "$header" "$(_tui_menu_box_height "$header" "$menu_h")" "$(_tui_box_width)" "$menu_h" "${items[@]}") || rc=$?
            else
                local -a args=(--clear --ok-button "$(t opt_ok)" --cancel-button "$(t opt_cancel)")
                [[ -n "$default" ]] && args+=(--default-item "$default")
                tag=$(whiptail "${args[@]}" --menu "$header" "$(_tui_menu_box_height "$header" "$menu_h")" "$(_tui_box_width)" "$menu_h" "${items[@]}" 3>&1 1>&2 2>&3) || rc=$?
            fi
            [[ "$fenced_here" == 1 ]] && _tui_fence_end
            case "$rc" in
                0)
                    [[ "$tag" == "$MYFOX_HEADER_TAG" ]] && continue
                    printf '%s' "$tag"
                    return 0
                    ;;
                3) [[ "$backend" == "dialog" ]] && return 3 || return 1 ;;
                *) return 1 ;;
            esac
        done
    fi

    _tui_move_default_first "$default" values labels
    echo -e "${BOLD}${header}${NC}" >&2
    local i
    for i in "${!labels[@]}"; do
        [[ "${values[$i]}" == "$MYFOX_HEADER_TAG" ]] && continue
        printf '  %d) %s\n' "$((i + 1))" "${labels[$i]}" >&2
    done
    [[ "$back" == "1" ]] && printf '  b) %s\n' "$(t tui_back_option)" >&2
    local ans
    read -rp "$(t tui_choice_prompt) " ans </dev/tty
    [[ -z "$ans" ]] && ans=1
    if [[ "$back" == "1" && "${ans,,}" == "b" ]]; then
        return 3
    fi
    [[ "$ans" =~ ^[0-9]+$ ]] && (( ans >= 1 && ans <= ${#labels[@]} )) || return 1
    printf '%s' "${values[$((ans - 1))]}"
}

# tui_filter_kv <header> <default-value> <back:0|1> <value1> <label1> [...] —
# для длинных списков (языки). dialog/whiptail --menu сам прокручивает
# длинные списки — используем тот же tui_choose_kv (без табличных тегов).
# В примитивном фолбэке — подстроковый фильтр (read), затем нумерованный выбор.
tui_filter_kv() {
    local header="$1" default="$2" back="$3"; shift 3
    if [[ -n "$(tui_backend)" ]]; then
        tui_choose_kv "$header" "$default" "$back" 0 "$@"
        return $?
    fi
    local -a values=() labels=()
    while [[ $# -gt 0 ]]; do
        values+=("$1"); labels+=("$2"); shift 2
    done
    local q=""
    echo -e "${BOLD}${header}${NC}" >&2
    read -rp "$(t tui_filter_placeholder) " q </dev/tty
    local -a fvalues=() flabels=() kv=()
    local i
    for i in "${!labels[@]}"; do
        if [[ -z "$q" || "${labels[$i],,}" == *"${q,,}"* ]]; then
            fvalues+=("${values[$i]}"); flabels+=("${labels[$i]}")
        fi
    done
    [[ ${#flabels[@]} -eq 0 ]] && return 1
    for i in "${!flabels[@]}"; do kv+=("${fvalues[$i]}" "${flabels[$i]}"); done
    tui_choose_kv "$header" "$default" "$back" 0 "${kv[@]}"
}

# tui_pick_dir <initial-path> → stdout: путь. rc 1 = отмена.
# Простой --inputbox с путём по умолчанию, а не файловый браузер (--dselect
# у dialog ожидает уже существующий путь для навигации по дереву — целевой
# каталог установки обычно ещё не существует, дерево там бесполезно и
# неудобно). Работает одинаково в dialog и whiptail.
tui_pick_dir() {
    local initial="${1:-$HOME/}"
    local backend; backend=$(tui_backend)
    if [[ -n "$backend" ]]; then
        local fenced_here=0
        _tui_fence_begin && fenced_here=1
        local out rc=0
        if [[ "$backend" == "dialog" ]]; then
            out=$(dialog --stdout --clear --title "$(t installdir_dselect_title)" \
                --inputbox "$(t installdir_input_prompt)" "$(_tui_box_height "$(t installdir_input_prompt)")" "$(_tui_box_width)" "$initial") || rc=$?
        else
            out=$(whiptail --clear --title "$(t installdir_dselect_title)" \
                --inputbox "$(t installdir_input_prompt)" "$(_tui_box_height "$(t installdir_input_prompt)")" "$(_tui_box_width)" "$initial" 3>&1 1>&2 2>&3) || rc=$?
        fi
        [[ "$fenced_here" == 1 ]] && _tui_fence_end
        [[ "$rc" -ne 0 ]] && return 1
        printf '%s' "$out"
        return 0
    fi
    local ans
    read -rp "$(t installdir_input_prompt) [$initial] " ans </dev/tty
    printf '%s' "${ans:-$initial}"
}

# tui_spin <title> -- <cmd...> — печатает заголовок и просто выполняет
# команду (curl/tar) с их собственным нормальным выводом (у curl это его
# родной --progress-bar) — никакой отдельной анимации/гейджа не рисуем.
tui_spin() {
    local title="$1"; shift
    [[ "${1:-}" == "--" ]] && shift
    echo -e "${BLUE}[..]${NC} $title" >&2
    "$@"
}

# tui_style <text...> — обычный жирный баннер (stderr, как log/warn/success).
tui_style() {
    echo -e "${BOLD}$*${NC}" >&2
}

# assets/logo.txt — статический файл, размер не меняется, поэтому не
# перемеряем его на каждый вызов (wc -l/-L), а держим готовыми константами.
MYFOX_LOGO_HEIGHT=21
MYFOX_LOGO_WIDTH=47

# tui_logo_fits — ТОЛЬКО если лого реально помещается в текущий терминал
# (по строкам/столбцам, с запасом под текст экрана и кнопки). stty size
# (а не tput) — надёжнее определяет реальный размер терминала независимо
# от перенаправлений stdout.
tui_logo_fits() {
    [[ -f "$MYFOX_ROOT/assets/logo.txt" ]] || return 1
    # whiptail не поддерживает --no-collapse: пробелы разъедет в любом
    # случае, поэтому лого показываем только под dialog.
    [[ "$(tui_backend)" == "dialog" ]] || return 1
    local rows cols
    read -r rows cols < <(stty size </dev/tty 2>/dev/null) || return 1
    [[ -n "$rows" && -n "$cols" ]] || return 1
    local need_rows=$(( MYFOX_LOGO_HEIGHT + 17 ))
    local need_cols=$(( MYFOX_LOGO_WIDTH + 6 ))
    (( rows >= need_rows && cols >= need_cols ))
}

# Печатает assets/logo.txt, отцентрированным по ширине БОКСА, который ему
# реально достанется (_tui_box_width — та же величина, что уйдёт в dialog),
# а НЕ по ширине всего терминала: раньше центрирование считалось для
# полноэкранного текста, а сам текст потом клался в более узкий бокс — вот
# и получался гигантский лишний отступ. Ширина лого — известная константа
# (MYFOX_LOGO_WIDTH), не перемеряется. Вызывать после tui_logo_fits.
tui_print_logo() {
    local f="$MYFOX_ROOT/assets/logo.txt"
    [[ -f "$f" ]] || return 0
    local box_w pad
    box_w=$(_tui_box_width)
    pad=$(( (box_w - 2 - MYFOX_LOGO_WIDTH) / 2 ))
    (( pad < 0 )) && pad=0
    awk -v p="$pad" 'BEGIN{ for(i=0;i<p;i++) s=s" " } { print s $0 }' "$f"
}
