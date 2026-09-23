# shellcheck shell=bash
# i18n.sh — каталог сообщений интерфейса инсталлятора (не путать с --lang,
# который выбирает язык самого Firefox-тарбола — используется как источник
# и для этого выбора тоже, см. i18n_detect).
#
# Требует MYFOX_ROOT (common.sh уже подключён).

declare -gA MYFOX_MSG

# ru_RU.UTF-8 → ru, pt-BR → pt, en → en — двухбуквенный префикс в нижнем регистре.
_i18n_normalize() {
    local raw="${1:-}"
    raw="${raw%%[-_.@]*}"
    printf '%s' "${raw,,}"
}

# Код языка интерфейса: явный аргумент (обычно --lang) → LANG из окружения →
# en. Если под этот код нет каталога в i18n/ — падаем на en.
i18n_detect() {
    local candidate="${1:-}"
    [[ -z "$candidate" ]] && candidate="${LANG:-en}"
    candidate=$(_i18n_normalize "$candidate")
    if [[ -n "$candidate" && -f "$MYFOX_ROOT/i18n/${candidate}.sh" ]]; then
        printf '%s' "$candidate"
    else
        printf 'en'
    fi
}

# i18n_load [preferred-code] — грузит en.sh как базу, затем (если код не en)
# накладывает переопределения из <code>.sh. Отсутствующий в накладке ключ
# автоматически остаётся английским.
i18n_load() {
    MYFOX_MSG=()
    # shellcheck source=/dev/null
    . "$MYFOX_ROOT/i18n/en.sh"
    MYFOX_UI_LANG=$(i18n_detect "${1:-}")
    if [[ "$MYFOX_UI_LANG" != "en" ]]; then
        # shellcheck source=/dev/null
        . "$MYFOX_ROOT/i18n/${MYFOX_UI_LANG}.sh"
    fi
}

# t <key> [printf-args...] — переведённая строка; неизвестный ключ печатает
# сам себя (никогда не падает на отсутствующей строке).
t() {
    local key="$1"; shift || true
    local fmt="${MYFOX_MSG[$key]:-$key}"
    # shellcheck disable=SC2059
    printf "$fmt" "$@"
}
