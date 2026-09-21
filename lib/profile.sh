# shellcheck shell=bash
# profile.sh — детекция и управление профилями Firefox.
#
# Профильный store — ОБЩИЙ с обычным Firefox: ~/.mozilla/firefox (или плотар/snap).
# Так устроено у Mozilla: все установки делят один profiles.ini/installs.ini, у
# каждой — своя секция [Install<HASH>]. Мы правим ТОЛЬКО секции под нашу
# установку ([Install<HASH>] и [ProfileN] Name=myfox), чужие не трогаем.
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

# Список ТОЛЬКО наших myfox-профилей: <path>|<name>. Профили других браузеров /
# установок (каталог без префикса myfox-) игнорируем целиком — myfox их не
# предлагает и не трогает.
# Кроме записей profiles.ini ищет «сиротские» каталоги myfox-* с маркером
# .myfox-created: так повторная установка находит профиль, который пользователь
# сохранил при деинсталляции (запись [ProfileN] могла быть удалена, а данные —
# оставлены). Сироты не дублируются, если профиль уже есть в profiles.ini.
profile_list_myfox() {
    local ini ini_dir isrel path name rest abs
    local -A seen
    while IFS= read -r ini; do
        [[ -z "$ini" ]] && continue
        ini_dir=$(dirname "$ini")
        while IFS= read -r line; do
            [[ -z "$line" ]] && continue
            path="${line%%|*}"
            rest="${line#*|}"
            name="${rest%%|*}"
            isrel="${rest##*|}"
            abs=$(profile_resolve_dir "$ini_dir" "$isrel" "$path")
            if [[ "$(basename "$abs")" == myfox-* && -d "$abs" ]]; then
                seen["$abs"]=1
                echo "$abs|$name"
            fi
        done < <(profile_parse_ini "$ini")
    done < <(profile_find_ini)
    # Сироты: каталог myfox-* с маркером .myfox-created, без записи в profiles.ini
    local base_dir d
    while IFS= read -r base_dir; do
        [[ -z "$base_dir" ]] && continue
        [[ -d "$base_dir" ]] || continue
        while IFS= read -r -d '' d; do
            d="${d%/}"
            [[ -v "seen[$d]" ]] && continue
            [[ -f "$d/.myfox-created" ]] || continue
            seen["$d"]=1
            echo "$d|"
        done < <(find "$base_dir" -maxdepth 1 -type d -name 'myfox-*' -print0 2>/dev/null)
    done < <(profile_search_dirs)
}

# ─── Дата создания/изменения каталога профиля (YYYY-MM-DD) ──────────────────
# Дата создания (birth time, stat %w) есть не на всех ФС — тогда «—». mtime — дата
# изменения. Обе даты печатаются в диалоге выбора профиля «таблицей».
profile_dir_created() {  # <dir> → YYYY-MM-DD | —
    local c
    c=$(stat -c %w "$1" 2>/dev/null || echo "—")
    [[ "$c" == "-" || -z "$c" ]] && c="—"
    printf '%s' "${c:0:10}"
}

profile_dir_modified() {  # <dir> → YYYY-MM-DD | —
    local m
    m=$(stat -c %y "$1" 2>/dev/null || echo "—")
    [[ -z "$m" ]] && m="—"
    printf '%s' "${m:0:10}"
}

# Одна строка таблицы для диалога выбора профиля:
#   <name>  <path>  <created>  <modified>
profile_table_row() {  # <path> [<name>]
    local p="$1" n="${2:-$(basename "$1")}"
    printf '%-14s %-38s %-18s %s' \
        "$n" "$p" "$(profile_dir_created "$p")" "$(profile_dir_modified "$p")"
}

# Шапка колонок таблицы — рисуется ПУНКТОМ меню (первым), а не текстом над
# списком: dialog рисует колонку тегов (даже скрытую --no-tags) шириной в самый
# длинный тег и сдвигает item-текст — text-шапку не выровнять. Пункт-заголовок
# имеет короткий тег-сигнатуру (не влияет на колонку) и при выборе
# игнорируется (повтор запроса).
PROFILE_HEADER_TAG="::"

profile_table_heading_row() {
    printf '%-14s %-38s %-18s %s' "Profile" "Path" "Created" "Modified"
}

# Пояснение над списком (управление), self-documented.
profile_pick_heading() {
    printf '%s\n%s\n' \
        "MyFox profiles from previous installations were found" \
        "you can use an existing one or create a new one"
}

# ─── Создание нового профиля ────────────────────────────────────────────────
#
# Создаёт профиль с именем myfox и уникальным путём (myfox-XXXX) в общем
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
        # Следующий свободный номер [ProfileN] = max существующего + 1.
        # (grep -c подвёл бы при пропущенных номерах → коллизия с чужим профилем.)
        local section
        section=$(awk -F'[][]' '/^\[Profile[0-9]+\]$/ { n=substr($2,8)+0; if (n>m) m=n } END { print m+1 }' "$ini")
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

# ─── Пиннинг профиля на инсталляцию (профиль на инсталляцию, FF 67+) ─────────
#
# Firefox 67+ хранит в profiles.ini секции [Install<HASH>], где <HASH> =
# CityHash64 от каталога установки; браузер при запуске открывает профиль из
# Default= своей секции. HASH мы САМИ не считаем: один раз запускаем нашу
# инсталляцию headless — Firefox сам выполнит first-run, посчитает hash и
# напишет свою секцию [Install<HASH>] в profiles.ini (+installs.ini). Остаётся
# прочитать появившуюся секцию и выставить в ней Default= на наш профиль.

# Список имен секций инсталляций в ini (пусто, если нет). Hash — hex, 1..16
# символов: CityHash64 даёт 16, но ведущий ноль Firefox отбрасывает (реально 15).
_profile_install_sections() {
    grep -o '^\[Install[0-9A-F]\{1,16\}\]' "$1" 2>/dev/null || true
}

# Удалить секцию "[<name>]" (и все строки до следующей секции) из ini, записав
# результат в out. Атомарность — на стороне вызывающего (tmp + mv).
_ini_remove_section() {
    local ini="$1" name="$2" out="$3"
    if [[ ! -f "$ini" ]]; then
        : > "$out"
        return 0
    fi
    awk -v s="[$name]" '
        /^\[/ { if ($0 == s) { skip=1; next } skip=0 }
        !skip { print }
    ' "$ini" > "$out"
}

# Путь профиля (значение Path= как в profiles.ini) для каталога target_dir.
# Возвращает 0 и печатает Path если профиль найден в ini.
_profile_entry_path_for() {
    local ini="$1" target_dir="$2"
    local ini_dir line path isrel abs
    ini_dir=$(dirname "$ini")
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        path="${line%%|*}"
        rest="${line#*|}"
        rest="${rest#*|}"
        rest="${rest#*|}"
        isrel="${rest##*|}"
        abs=$(profile_resolve_dir "$ini_dir" "$isrel" "$path")
        if [[ "$abs" == "$target_dir" ]]; then
            echo "$path"
            return 0
        fi
    done < <(profile_parse_ini "$ini")
    return 1
}

# Список каталогов-профилей в store (только реально существующие, с prefs.js).
# Используется для вычистки мусорных профилей, созданных самим Firefox.
_profile_store_profile_dirs() {
    local store_dir="$1"
    find "$store_dir" -mindepth 1 -maxdepth 1 -type d \
        -exec test -f '{}/prefs.js' \; -printf '%f\n' 2>/dev/null | sort -u
}

# Регистрация записи [ProfileN] для существующего каталога профиля, у которого
# её нет (сирота после деинсталляции «не удалять профиль» + «удалить запись»).
# Каталог и данные НЕ трогаем, только добавляем секцию (нумерация max+1,
# как в profile_create_new). Печатает Path (значение для Default= в Install-секции).
profile_register_entry() {
    local ini="$1" profile_abs="$2"
    local ini_dir rel isrel
    ini_dir=$(dirname "$ini")
    if [[ "$profile_abs" == "$ini_dir/"* ]]; then
        rel="${profile_abs#"$ini_dir/"}"
        isrel=1
    else
        rel="$profile_abs"
        isrel=0
    fi
    local section
    section=$(awk -F'[][]' '/^\[Profile[0-9]+\]$/ { n=substr($2,8)+0; if (n>m) m=n } END { print m+1 }' "$ini")
    printf '\n[Profile%s]\nName=myfox\nIsRelative=%s\nPath=%s\n' \
        "$section" "$isrel" "$rel" >> "$ini"
    log "Registered [Profile${section}] for kept profile (Path=$rel)."
    echo "$rel"
}

# Имя секции [ProfileN], чей каталог == target_dir (для удаления секции).
_profile_section_for_dir() {
    local ini="$1" target="$2" idir
    idir=$(dirname "$ini")
    awk -v target="$target" -v idir="$idir" '
        function abs(p,rel) { return (rel=="1") ? (idir "/" p) : p }
        /^\[/ { sec=$0; path=""; isrel=""; next }
        sec ~ /^\[Profile[0-9]+\]$/ && /^Path=/ { path=substr($0,6) }
        sec ~ /^\[Profile[0-9]+\]$/ && /^IsRelative=/ { isrel=substr($0,12) }
        sec ~ /^\[Profile[0-9]+\]$/ && path!="" && isrel!="" && abs(path,isrel)==target {
            print substr(sec,2,length(sec)-2); exit
        }
    ' "$ini"
}

# Вычистка «мусорных» профилей, которые Firefox создаёт сам при first-run
# (headless-прогон для пиннинга): новый каталог профиля + его [ProfileN] секция.
# Наш профиль (сторона инсталлера) и каталоги, существовавшие ДО прогона, не трогаем.
# $1=store_dir  $2=profiles.ini  $3=наш профиль(abs, не трогаем)  $4=каталоги до (по одному в строке)
_profile_purge_headless_strays() {
    local store_dir="$1" ini="$2" our="$3" before="$4"
    [[ -n "$store_dir" && -d "$store_dir" ]] || return 0
    local d abs sec
    while IFS= read -r d; do
        [[ -z "$d" ]] && continue
        abs="$store_dir/$d"
        [[ "$abs" == "$our" ]] && continue
        grep -qxF "$d" <<<"$before" && continue
        [[ -d "$abs" ]] || continue
        # Секция [ProfileN] для этого каталога (если Firefox её создал) — убрать.
        if [[ -n "$ini" && -f "$ini" ]]; then
            sec=$(_profile_section_for_dir "$ini" "$abs")
            if [[ -n "$sec" ]]; then
                _ini_remove_section "$ini" "$sec" "${ini}.myfox.tmp" && mv "${ini}.myfox.tmp" "$ini"
            fi
        fi
        rm -rf -- "$abs"
    done <<< "$(_profile_store_profile_dirs "$store_dir")"
}

# Однократный запуск нашей инсталляции в headless-режиме, чтобы Firefox
# выполнил first-run и записал [Install<HASH>] (profiles.ini) / [<HASH>]
# (installs.ini) в ОБЩИЙ store. Секционную регистрацию ловим в обоих файлах:
# на части версий FF hash пишется только в installs.ini. Первый запуск бывает
# медленным — ищем щедрым таймаутом и повторяем попытку один раз.
# Побочный эффект first-run — Firefox создаёт собственный временный профиль
# (default-*) в store; его каталог и [ProfileN] секцию вычищаем после.
# Печатает имя секции вида "Install<HASH>", если появилась новая; иначе пусто.
profile_headless_once() {
    local install_dir="$1" our_profile="$2"
    local bin="$install_dir/firefox"
    [[ -x "$bin" ]] || return 1

    local ini inst_ini shot ini_before inst_before store_dir before_dirs
    ini=$(profile_find_ini) || true
    ini_before=""
    [[ -n "$ini" ]] && ini_before=$(_profile_install_sections "$ini")
    inst_ini=""
    [[ -n "$ini" ]] && inst_ini="$(dirname "$ini")/installs.ini"
    inst_before=""
    [[ -f "$inst_ini" ]] && inst_before=$(grep -o '^\[[0-9A-F]\{1,16\}\]' "$inst_ini" || true)

    # Снимок профилей ДО прогона: те, что создаст Firefox для first-run,
    # после удалим (мусор, см. _profile_purge_headless_strays).
    store_dir=""
    before_dirs=""
    if [[ -n "$ini" ]]; then
        store_dir=$(dirname "$ini")
    else
        # profiles.ini ещё нет — headless-Firefox создаст его в первом каталоге
        # поиска ($HOME/.mozilla/firefox); туда же смотреть для вычистки.
        store_dir=$(profile_search_dirs | head -1)
    fi
    [[ -n "$store_dir" ]] && before_dirs=$(_profile_store_profile_dirs "$store_dir")

    local attempt=0 rc new found=""
    while (( attempt < 2 )); do
        attempt=$((attempt + 1))
        shot=$(mktemp --suffix=.myfox-shot.png)
        # first-run в headless; выход после скриншота; таймаут от зависания.
        timeout 180 "$bin" --headless --screenshot "$shot" about:blank >/dev/null 2>&1
        rc=$?
        rm -f "$shot"
        [[ $rc -ne 0 ]] && break

        # Новая секция появилась — first-run отработал именно на нашу установку.
        # comm требует сортированные входы; grep -o даёт их в порядке файла.
        local ini_after inst_after
        [[ -n "$ini" ]] && ini_after=$(_profile_install_sections "$ini")
        inst_after=""
        [[ -f "$inst_ini" ]] && inst_after=$(grep -o '^\[[0-9A-F]\{1,16\}\]' "$inst_ini" || true)
        new=$(comm -13 <(printf '%s\n' "$ini_before" | sort -u) \
            <(printf '%s\n' "$ini_after" | sort -u) \
            | grep '^\[Install[0-9A-F]\{1,16\}\]$' || true)
        if [[ -n "$new" ]]; then
            found="${new%%$'\n'*}"
            break
        fi
        new=$(comm -13 <(printf '%s\n' "$inst_before" | sort -u) \
            <(printf '%s\n' "$inst_after" | sort -u) \
            | grep '^\[[0-9A-F]\{1,16\}\]$' || true)
        if [[ -n "$new" ]]; then
            found="${new%%$'\n'*}"
            break
        fi
    done

    # Убираем профиль, который Firefox создал для first-run (если создал).
    _profile_purge_headless_strays "$store_dir" "$ini" "$our_profile" "$before_dirs"

    if [[ -n "$found" ]]; then
        echo "${found:1:-1}"
        return 0
    fi
    return 1
}

# Детерминированный hash своей установки: запуск в изолированном (чистом) HOME.
# Firefox при первом запуске АБСОЛЮТНО ВСЕГДА регистрирует установку на свежем
# profiles.ini (в отличие от основного HOME, где [Install<HASH>] уже может быть
# от прошлой установки на тот же путь). Печатает HASH (без "Install"), иначе пусто.
profile_install_hash_fresh() {
    local install_dir="$1"
    local bin="$install_dir/firefox"
    [[ -x "$bin" ]] || return 1

    local tmp_home shot rc hash fresh_ini
    tmp_home=$(mktemp -d) || return 1
    shot="$tmp_home/.myfox-shot.png"

    # Изолируем профиль-каталог: HOME и XDG во временной папке. При первом
    # запуске Firefox создаёт там свой profiles.ini (на Linux — в ~/.mozilla или
    # $XDG_CONFIG_HOME/mozilla) и [Install<HASH>] для нашей установки.
    HOME="$tmp_home" XDG_CONFIG_HOME="$tmp_home/.config" XDG_DATA_HOME="$tmp_home/.local/share" \
        timeout 180 "$bin" --headless --screenshot "$shot" about:blank >/dev/null 2>&1
    rc=$?
    hash=""
    if [[ $rc -eq 0 ]]; then
        for fresh_ini in "$tmp_home/.mozilla/firefox/profiles.ini" \
                         "$tmp_home/.config/mozilla/firefox/profiles.ini"; do
            [[ -f "$fresh_ini" ]] || continue
            hash=$(grep -o '^\[Install[0-9A-F]\{1,16\}\]' "$fresh_ini" \
                | sed -e 's/^\[Install//; s/\]$//' | head -1)
            [[ -n "$hash" ]] && break
        done
    fi
    rm -rf -- "${tmp_home}"
    [[ -n "$hash" ]] && { printf '%s' "$hash"; return 0; }
    return 1
}

# Пиннинг: найти/получить [Install<HASH>] нашей инсталляции и поставить
# Default= на наш профиль. Хэш переиспользуется из state при --update/--reinstall.
# Печатает HASH (без "Install") при успехе, иначе warning + 1.
profile_pin_install() {
    local install_dir="$1" profile_abs="$2"
    local ini hash section profile_path

    ini=$(profile_find_ini) || { warn "profiles.ini not found — cannot pin profile."; return 1; }

    # Используем уже известный hash, если секция для него есть.
    hash=$(state_get install_hash) || true
    section=""
    if [[ -n "$hash" && -n "$(grep "^\[Install${hash}\]$" "$ini" 2>/dev/null || true)" ]]; then
        section="Install${hash}"
    fi

    if [[ -z "$section" ]]; then
        # 1) Обычный путь: headless first-run регистрирует новую секцию
        #    (наш профиль передаём, чтобы мусорку-профилей его не задело).
        section=$(profile_headless_once "$install_dir" "$profile_abs") || true

        if [[ -z "$section" ]]; then
            # 2) Новой секции нет — Firefox уже знает эту установку (повторный
            #    запуск/переустановка, [Install<HASH>] осталась от прошлого раза).
            #    Узнаём наш hash детерминированно: на изолированном чистом HOME
            #    Firefox регистрирует установку всегда (hash = CityHash64 от пути).
            local fresh_hash
            fresh_hash=$(profile_install_hash_fresh "$install_dir") || true
            if [[ -n "$fresh_hash" ]]; then
                section="Install${fresh_hash}"
                warn "Adopting the existing [${section}] section (pre-registered by an earlier install)."
            elif [[ "$(printf '%s\n' "$(_profile_install_sections "$ini")" | grep -c '^\[Install' || true)" -eq 1 ]]; then
                # Последний резерв: секция ровно одна и хеша мы не знаем — она от нас.
                section="$(_profile_install_sections "$ini")"
                section="${section:1:-1}"
                warn "Adopting the single existing [Install...] section."
            else
                warn "Headless Firefox run failed — cannot pin the profile to this install."
                warn "The desktop entry will open Firefox's own default profile (tweaks will NOT apply in it)."
                return 1
            fi
        fi
        hash="${section#Install}"
    fi

    # Проверяем, что наш профиль есть в profiles.ini и берём его Path (для Default=).
    profile_path=$(_profile_entry_path_for "$ini" "$profile_abs") || {
        # Профиль-сирота (выбран сохранённый при деинсталляции): каталог есть,
        # а записи [ProfileN] нет — регистрируем её и используем как Path.
        profile_path=$(profile_register_entry "$ini" "$profile_abs") || {
            warn "Our profile ($profile_abs) not found in profiles.ini — cannot pin it."
            return 1
        }
    }

    # In profiles.ini секция называется [Install<HASH>], в installs.ini — просто
    # [<HASH>] (так делает сам Firefox; дублируем его формат).
    _ini_write_install_section "$ini" "$section" "$profile_path"
    local installs_ini
    installs_ini="$(dirname "$ini")/installs.ini"
    _ini_write_install_section "$installs_ini" "${section#Install}" "$profile_path"

    success "Profile pinned: [${section}] Default=${profile_path}"
    echo "$hash"
}

# Запись [<section>] Default=<path> Locked=1 в ini (и удаление старой такой же
# секции, чтобы она не осталась дублем в другом месте файла).
_ini_write_install_section() {
    local ini="$1" section="$2" profile_path="$3"
    local tmp="${ini}.myfox.tmp"
    _ini_remove_section "$ini" "$section" "$tmp"
    printf '\n[%s]\nDefault=%s\nLocked=1\n' "$section" "$profile_path" >> "$tmp"
    mv "$tmp" "$ini"
}

# Снятие пиннинга: удалить [Install<HASH>] из profiles.ini и installs.ini.
profile_unpin_install() {
    local hash="$1"
    [[ -z "$hash" ]] && return 0
    local ini i_dir
    ini=$(profile_find_ini) || true
    if [[ -n "$ini" ]]; then
        i_dir=$(dirname "$ini")
        _ini_remove_section "$ini" "Install${hash}" "${ini}.myfox.tmp" && mv "${ini}.myfox.tmp" "$ini"
        success "Unpinned [Install${hash}] from ${ini}"
        local installs_ini="$i_dir/installs.ini"
        if [[ -f "$installs_ini" ]]; then
            _ini_remove_section "$installs_ini" "$hash" "${installs_ini}.myfox.tmp" \
                && mv "${installs_ini}.myfox.tmp" "$installs_ini"
            success "Unpinned [${hash}] from ${installs_ini}"
        fi
    fi
}

# Удалить из profiles.ini секцию [ProfileN] с Name=myfox (запись остаётся —
# данные профиля не трогаем). Возвращает 0 если удалили/не было.
profile_remove_myfox_section() {
    local ini target
    ini=$(profile_find_ini) || return 0
    target=$(awk '
        function flush(cur) { if (cur != "" && name == "myfox") print cur }
        /^\[Profile[0-9]+\]/ { flush(cur); cur=$0; name=""; next }
        cur != "" && /^Name=/ { name=substr($0, 6) }
        END { flush(cur) }
    ' "$ini") || true
    [[ -z "$target" ]] && { log "No myfox profile entry in profiles.ini."; return 0; }
    local name
    name="${target:1:-1}"
    _ini_remove_section "$ini" "$name" "${ini}.myfox.tmp" && mv "${ini}.myfox.tmp" "$ini"
    success "Removed profile section [${name}] from ${ini}"
}

# ─── Точка входа: определить/выбрать/создать профиль ────────────────────────
#
# profile_resolve [--explicit <path>]
#   1. передан --explicit и путь существует → использовать.
#   2. MYFOX_PROFILE_FORCE_NEW=1 (мастер выбрал «создать новый») → создать.
#   3. в маркере есть profile_dir и он существует → использовать.
#   4. иначе (первый запуск): рассматриваются ТОЛЬКО наши myfox-профили
#      (profile_list_myfox). Если их нет → создать новый; есть и интерактив и
#      dialog/whiptail → меню со списком (по умолчанию «создать новый»); во всех
#      остальных случаях (неинтерактив, под gauge/alt-экраном, без GUI) —
#      создать новый. Никогда никаких echo-списков и read над диалогом.
profile_resolve() {
    local explicit=""
    if [[ "$1" == "--explicit" ]]; then explicit="$2"; fi

    # 1. Явный (--profile или выбор существующего профиля из мастера)
    if [[ -n "$explicit" ]]; then
        [[ -d "$explicit" ]] || error "Profile directory not found: $explicit"
        echo "$explicit"
        return 0
    fi

    # 2. Мастер выбрал «создать новый» — вопрос уже задан на шаге profile,
    #    сразу создаём (никаких read: идём из-под gauge/alt-экрана).
    if [[ "$MYFOX_PROFILE_FORCE_NEW" == "1" ]]; then
        log "Creating a new profile (wizard choice)."
        profile_create_new
        return 0
    fi

    # 3. Из маркера
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

    # 4. Первый запуск: только наши myfox-профили.
    local myfox_list
    myfox_list=$(profile_list_myfox) || true
    if [[ -z "$myfox_list" ]]; then
        log "No MyFox profiles found — creating a new one."
        profile_create_new
        return 0
    fi

    # Неинтерактив (-y): спросить не можем → создаём свежий myfox-N.
    if [[ -n "$MYFOX_NONINTERACTIVE" ]]; then
        log "MyFox profiles exist but running non-interactively — creating a new one."
        profile_create_new
        return 0
    fi

    # Защита от future-regressions: если мы под dialog/gauge/alt-экраном,
    # интерактивный выбор здесь невозможен (его делает мастер на шаге profile).
    # Блокирующий echo+read здесь недопустим — просто создаём новый.
    if [[ -n "$MYFOX_GAUGE_FD" || "$MYFOX_TUI_FENCED" == "1" ]]; then
        log "MyFox profiles exist but a TUI is active — creating a new one."
        profile_create_new
        return 0
    fi

    # Интерактив вне мастера: только dialog/whiptail-меню (список + «создать
    # новый», дефолт на «создать новый»). Им владеет своя пара tui_enter/reset.
    if command -v dialog >/dev/null 2>&1 || command -v whiptail >/dev/null 2>&1; then
        local chosen
        chosen=$(profile_pick_myfox "$myfox_list") || { error "Profile selection cancelled."; return 1; }
        if [[ -n "$chosen" ]]; then
            echo "$chosen"
            return 0
        fi
        log "Creating a new profile..."
        profile_create_new
        return 0
    fi

    # Нет GUI вовсе: список/echo/read не печатаем — молча создаём новый.
    log "No dialog/whiptail available — creating a new MyFox profile."
    profile_create_new
}

# Диалог выбора профиля: существующие myfox-профили + «создать новый» (дефолт).
# Всё рисуется в текущий экран (в мастере — внутрь alt-экрана), alt-экран НЕ
# переключается (terminfo без smcup/rmcup, как в языковом меню). stdout: путь
# выбранного профиля, или пусто = «создать новый»; rc 1 — отмена пользователем.
profile_pick_myfox() {  # <list path|name …>
    local list="$1"
    local p n i=0
    local -a paths=()
    local items=(
        "$PROFILE_HEADER_TAG" "$(profile_table_heading_row)"
        "new" "$(printf '%-14s' 'New profile')"
    )
    while IFS='|' read -r p n; do
        [[ -z "$p" ]] && continue
        i=$((i + 1))
        paths[$i]="$p"
        items+=("$i" "$(profile_table_row "$p" "$(basename "$p")")")
    done <<< "$list"
    local _fenced="${MYFOX_TUI_FENCED:-0}"
    if [[ "$_fenced" != "1" ]]; then
        use_ui_terminfo_noalt || true
        tui_enter
    fi
    local tag rc=0
    while :; do
        if command -v dialog >/dev/null 2>&1; then
            tag=$(dialog --stdout --clear --no-tags --no-collapse --ok-label "Continue" --cancel-label "Cancel" --default-item "new" \
                --menu "$(profile_pick_heading)" 0 0 0 "${items[@]}") || rc=$?
        else
            tag=$(whiptail --clear --ok-button "Continue" --cancel-button "Cancel" --default-item "new" \
                --menu "$(profile_pick_heading)" 0 0 0 "${items[@]}" 3>&1 1>&2 2>&3) || rc=$?
        fi
        [[ "$rc" -ne 0 ]] && break
        [[ "$tag" == "$PROFILE_HEADER_TAG" ]] && continue
        break
    done
    if [[ "$_fenced" != "1" ]]; then
        tui_reset
        reset_ui_terminfo_noalt
    fi
    [[ "$rc" -ne 0 ]] && return 1
    [[ "$tag" == "new" ]] && return 0
    if [[ -n "${paths[$tag]:-}" ]]; then echo "${paths[$tag]}"; fi
}