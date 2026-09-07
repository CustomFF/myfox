# shellcheck shell=bash
# profile.sh — детекция и управление профилями Firefox.
#
# Ищет profiles.ini в стандартных местах (~/.mozilla, flatpak, snap),
# парсит профили, позволяет эксплицитно указать профиль, создаёт новый.
# Требуется common.sh.

# ─── Поиск profiles.ini ─────────────────────────────────────────────────────

profile_search_dirs() {
    # Каталоги, где может лежать profiles.ini (в порядке приоритета).
    echo "$HOME/.mozilla/firefox"
    [[ -d "$HOME/.var/app/org.mozilla.firefox" ]] && echo "$HOME/.var/app/org.mozilla.firefox/.mozilla/firefox"
    [[ -d "$HOME/snap/firefox" ]] && echo "$HOME/snap/firefox/common/.mozilla/firefox"
}

# Возвращает первый найденный путь profiles.ini (или пустоту)
profile_find_ini() {
    local d
    while IFS= read -r d; do
        [[ -z "$d" ]] && continue
        [[ -f "$d/profiles.ini" ]] && { echo "$d/profiles.ini"; return 0; }
    done < <(profile_search_dirs)
    return 1
}

# ─── Парсинг profiles.ini ───────────────────────────────────────────────────
#
# Формат (упрощённо):
#   [Profile0]
#   Name=default-release
#   IsRelative=1
#   Path=g1w8ozah.default-release
#   Default=1
# profile_parse_ini выводит строки:  <Path>|<Name>|<Default>|<IsRelative>
profile_parse_ini() {
    local ini="$1"
    [[ -f "$ini" ]] || return 1
    awk '
        function flush() {
            if (path != "")
                print path "|" name "|" (def ? "1" : "0") "|" isrel
            path=""; name=""; def=0; isrel=0
        }
        /^\[/ {
            flush()
            insection = ($0 ~ /^\[Profile[0-9]+\]/) ? 1 : 0
            next
        }
        insection && /^Name=/       { name=substr($0, 6) }
        insection && /^Path=/       { path=substr($0, 6) }
        insection && /^IsRelative=/ { isrel=substr($0, 12) }
        insection && /^Default=1/   { def=1 }
        END { flush() }
    ' "$ini"
}

# Резолв пути профиля (IsRelative + Path → абсолютный путь)
profile_resolve_dir() {
    local ini_dir="$1" isrel="$2" path="$3"
    if [[ "$isrel" == "1" ]]; then
        echo "$ini_dir/$path"
    else
        [[ "${path:0:1}" == "/" ]] && echo "$path" || echo "$ini_dir/$path"
    fi
}

# Список абсолютных путей существующих профилей: <path>|<name>|<default>
profile_list_existing() {
    local ini ini_dir isrel path name def abs
    while IFS= read -r ini; do
        [[ -z "$ini" ]] && continue
        ini_dir=$(dirname "$ini")
        while IFS= read -r line; do
            [[ -z "$line" ]] && continue
            path="${line%%|*}"
            rest="${line#*|}"
            name="${rest%%|*}"
            rest="${rest#*|}"
            def="${rest%%|*}"
            isrel="${rest##*|}"
            abs=$(profile_resolve_dir "$ini_dir" "$isrel" "$path")
            if [[ -d "$abs" ]]; then
                echo "$abs|$name|$def"
            fi
        done < <(profile_parse_ini "$ini")
    done < <(profile_find_ini)
}

# Поиск «дефолтного» профиля который подтянется при запуске нашей инсталляции.
# На деле Firefox выбирает Profile0 если нет Default=1; учитываем оба.
profile_find_default() {
    local line abs
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        def="${line##*|}"
        [[ "$def" == "1" ]] && { echo "${line%%|*}"; return 0; }
    done < <(profile_list_existing)
    # Нет Default=1 — берём первый (Profile0)
    line=$(profile_list_existing | head -1)
    [[ -z "$line" ]] && return 1
    echo "${line%%|*}"
}

# Все существующие профили одной строкой (paths); если несколько — их выводим в список.
profile_list_all() {
    profile_list_existing
}

# ─── Создание нового профиля ────────────────────────────────────────────────
#
# Создаёт профиль с именем myfox и уникальным путём (myfox-XXXX) в стандартном
# profiles-каталоге. Возвращает абсолютный путь профиля.
profile_create_new() {
    local ini ini_dir ppath
    ini=$(profile_find_ini) || true
    if [[ -z "$ini" ]]; then
        ini_dir="$HOME/.mozilla/firefox"
        mkdir -p "$ini_dir"
        ini="$ini_dir/profiles.ini"
    else
        ini_dir=$(dirname "$ini")
    fi

    # Уникальный путь профиля myfox-<n>
    local idx=0
    while true; do
        idx=$((idx + 1))
        ppath="myfox-$idx"
        [[ ! -e "$ini_dir/$ppath" ]] && break
    done

    mkdir -p "$ini_dir/$ppath"
    touch "$ini_dir/$ppath/.myfox-created"

    if [[ -f "$ini" ]]; then
        local section
        section=$(grep -c '^\[Profile' "$ini")
        cat >> "$ini" <<EOF

[Profile${section}]
Name=myfox
IsRelative=1
Path=$ppath
EOF
    else
        cat > "$ini" <<EOF
[Profile0]
Name=myfox
IsRelative=1
Path=$ppath
EOF
    fi

    echo "$ini_dir/$ppath"
}

# ─── Точка входа: определить/выбрать/создать профиль ────────────────────────
#
# profile_resolve [--explicit <path>]
#   1. если передан --explicit и путь существует → использовать.
#   2. если в маркере есть profile_dir и он существует → использовать.
#   3. иначе (первый запуск):
#      - если найден «по умолчанию» подтягивающийся профиль → спросить (использовать/создать новый)
#      - если не найдено → создать новый.
profile_resolve() {
    local explicit=""
    if [[ "$1" == "--explicit" ]]; then explicit="$2"; fi

    # 1. Явный
    if [[ -n "$explicit" ]]; then
        [[ -d "$explicit" ]] || error "Profile directory not found: $explicit"
        echo "$explicit"
        return 0
    fi

    # 2. Из маркера
    local marked
    marked=$(state_get profile_dir)
    if [[ -n "$marked" && -d "$marked" ]]; then
        log "Using saved profile: $marked"
        echo "$marked"
        return 0
    fi
    if [[ -n "$marked" ]]; then
        warn "Saved profile no longer exists: $marked"
    fi

    # 3. Первый запуск
    local existing
    existing=$(profile_list_existing) || true   # строки path|name|default
    if [[ -z "$existing" ]]; then
        log "No existing profiles found — creating a new one."
        profile_create_new
        return 0
    fi

    local default_abs
    default_abs=$(profile_find_default) || true
    if [[ -n "$default_abs" ]]; then
        warn "An existing Firefox profile might be picked up automatically:"
        log "    $default_abs"
        if confirm "Use this existing profile instead of creating a new one? (recommended: create new)" "n"; then
            echo "$default_abs"
            return 0
        fi
        log "Creating a new profile..."
        profile_create_new
        return 0
    fi

    log "Creating a new profile..."
    profile_create_new
}