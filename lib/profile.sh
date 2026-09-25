# shellcheck shell=bash
# profile.sh — детекция и управление профилями Firefox.
#
# Профильный store — ОБЩИЙ с обычным Firefox: ~/.mozilla/firefox (легаси-путь) или,
# начиная с Firefox 147, $XDG_CONFIG_HOME/mozilla/firefox (обычно ~/.config/mozilla/
# firefox) — Firefox сам выбирает между ними по правилу profile_native_dir() ниже.
# Плюс flatpak/snap — свои изолированные копии этого же дерева.
# Правим ТОЛЬКО секции под нашу установку ([Install<HASH>] и [ProfileN] Name=myfox),
# чужие не трогаем. Требует common.sh, i18n.sh, tui.sh.

# ─── Поиск profiles.ini ─────────────────────────────────────────────────────

# Нативный (не flatpak/snap) каталог профилей — то же правило, что использует
# сам Firefox: легаси-путь, если каталог `~/.mozilla/firefox` уже существует
# (проверено live: наличие именно .../firefox, не просто ~/.mozilla), иначе —
# XDG-путь.
profile_native_dir() {
    if [[ -d "$HOME/.mozilla/firefox" ]]; then
        echo "$HOME/.mozilla/firefox"
    else
        echo "${XDG_CONFIG_HOME:-$HOME/.config}/mozilla/firefox"
    fi
}

profile_search_dirs() {
    profile_native_dir
    [[ -d "$HOME/.var/app/org.mozilla.firefox" ]] && echo "$HOME/.var/app/org.mozilla.firefox/.mozilla/firefox"
    [[ -d "$HOME/snap/firefox" ]] && echo "$HOME/snap/firefox/common/.mozilla/firefox"
}

profile_find_ini() {
    local d
    while IFS= read -r d; do
        [[ -z "$d" ]] && continue
        [[ -f "$d/profiles.ini" ]] && { echo "$d/profiles.ini"; return 0; }
    done < <(profile_search_dirs)
    return 1
}

# ─── Парсинг profiles.ini ───────────────────────────────────────────────────
# Выводит строки:  <Path>|<Name>|<Default>|<IsRelative>

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

profile_resolve_dir() {
    local ini_dir="$1" isrel="$2" path="$3"
    if [[ "$isrel" == "1" ]]; then
        echo "$ini_dir/$path"
    else
        [[ "${path:0:1}" == "/" ]] && echo "$path" || echo "$ini_dir/$path"
    fi
}

# Список ТОЛЬКО наших myfox-профилей: <path>|<name>. Плюс «сиротские» каталоги
# myfox-* с маркером .myfox-created без записи в profiles.ini (сохранены при
# uninstall) — так повторная установка их находит.
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
            [[ -v "seen[$abs]" ]] && continue
            if [[ "$(basename "$abs")" == myfox-* && -d "$abs" ]]; then
                seen["$abs"]=1
                echo "$abs|$name"
            fi
        done < <(profile_parse_ini "$ini")
    done < <(profile_find_ini)
    local base_dir d
    while IFS= read -r base_dir; do
        [[ -z "$base_dir" || ! -d "$base_dir" ]] && continue
        while IFS= read -r -d '' d; do
            d="${d%/}"
            [[ -v "seen[$d]" ]] && continue
            [[ -f "$d/.myfox-created" ]] || continue
            seen["$d"]=1
            echo "$d|"
        done < <(find "$base_dir" -maxdepth 1 -type d -name 'myfox-*' -print0 2>/dev/null)
    done < <(profile_search_dirs)
}

# ─── Таблица профилей для tui_choose_kv ──────────────────────────────────────

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

profile_table_row() {  # <path> [<name>]
    local p="$1" n="${2:-$(basename "$1")}"
    printf '%s %s %s %s' \
        "$(myfox_pad "$n" 14)" "$(myfox_pad "$(myfox_shorten_home "$p")" 38)" \
        "$(myfox_pad "$(profile_dir_created "$p")" 12)" "$(profile_dir_modified "$p")"
}

# ─── Создание нового профиля ────────────────────────────────────────────────

profile_create_new() {
    local ini ini_dir ppath
    ini=$(profile_find_ini) || true
    if [[ -z "$ini" ]]; then
        ini_dir=$(profile_native_dir)
        mkdir -p "$ini_dir"
        ini="$ini_dir/profiles.ini"
    else
        ini_dir=$(dirname "$ini")
    fi

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

# ─── Пиннинг профиля на инсталляцию (FF 67+, [Install<HASH>]) ───────────────
#
# HASH мы сами не считаем: один раз гоняем headless-прогон, Firefox сам его
# посчитает и запишет свою секцию — остаётся прочитать её и выставить Default=.

_profile_install_sections() {
    grep -o '^\[Install[0-9A-F]\{1,16\}\]' "$1" 2>/dev/null || true
}

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

_profile_entry_path_for() {
    local ini="$1" target_dir="${2%/}"
    local ini_dir line path isrel abs rest
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

_profile_store_profile_dirs() {
    local store_dir="$1"
    find "$store_dir" -mindepth 1 -maxdepth 1 -type d \
        -exec test -f '{}/prefs.js' \; -printf '%f\n' 2>/dev/null | sort -u
}

profile_register_entry() {
    local ini="$1" profile_abs="$2"
    profile_abs="${profile_abs%/}"
    local ini_dir rel isrel
    ini_dir=$(dirname "$ini")

    # Idempotent: reinstalling repeatedly against the same profile directory
    # must reuse its existing [ProfileN] entry, not pile up a duplicate one
    # every time (observed: 6+ duplicate [ProfileN] Name=myfox Path=myfox-1
    # sections after repeated --reinstall runs during a single test session).
    local existing
    existing=$(_profile_entry_path_for "$ini" "$profile_abs") && {
        echo "$existing"
        return 0
    }

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
    log "$(t profile_entry_registered "$section" "$rel")"
    echo "$rel"
}

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
        if [[ -n "$ini" && -f "$ini" ]]; then
            sec=$(_profile_section_for_dir "$ini" "$abs")
            if [[ -n "$sec" ]]; then
                _ini_remove_section "$ini" "$sec" "${ini}.myfox.tmp" && mv "${ini}.myfox.tmp" "$ini"
            fi
        fi
        rm -rf -- "$abs"
    done <<< "$(_profile_store_profile_dirs "$store_dir")"
}

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

    store_dir=""
    before_dirs=""
    if [[ -n "$ini" ]]; then
        store_dir=$(dirname "$ini")
    else
        store_dir=$(profile_search_dirs | head -1)
    fi
    [[ -n "$store_dir" ]] && before_dirs=$(_profile_store_profile_dirs "$store_dir")

    local attempt=0 rc new found=""
    while (( attempt < 2 )); do
        attempt=$((attempt + 1))
        shot=$(mktemp --suffix=.myfox-shot.png)
        timeout 180 "$bin" --headless --screenshot "$shot" about:blank >/dev/null 2>&1
        rc=$?
        rm -f "$shot"
        [[ $rc -ne 0 ]] && break

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

    _profile_purge_headless_strays "$store_dir" "$ini" "$our_profile" "$before_dirs"

    if [[ -n "$found" ]]; then
        echo "${found:1:-1}"
        return 0
    fi
    return 1
}

profile_install_hash_fresh() {
    local install_dir="$1"
    local bin="$install_dir/firefox"
    [[ -x "$bin" ]] || return 1

    local tmp_home shot rc hash fresh_ini
    tmp_home=$(mktemp -d) || return 1
    shot="$tmp_home/.myfox-shot.png"

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

profile_pin_install() {
    local install_dir="$1" profile_abs="${2%/}"
    local ini hash section profile_path

    ini=$(profile_find_ini) || { warn "$(t warn_no_profiles_ini)"; return 1; }

    hash=$(state_get install_hash) || true
    section=""
    if [[ -n "$hash" && -n "$(grep "^\[Install${hash}\]$" "$ini" 2>/dev/null || true)" ]]; then
        section="Install${hash}"
    fi

    if [[ -z "$section" ]]; then
        section=$(profile_headless_once "$install_dir" "$profile_abs") || true

        if [[ -z "$section" ]]; then
            local fresh_hash
            fresh_hash=$(profile_install_hash_fresh "$install_dir") || true
            if [[ -n "$fresh_hash" ]]; then
                section="Install${fresh_hash}"
                warn "$(t warn_adopt_existing_section "$section")"
            elif [[ "$(printf '%s\n' "$(_profile_install_sections "$ini")" | grep -c '^\[Install' || true)" -eq 1 ]]; then
                section="$(_profile_install_sections "$ini")"
                section="${section:1:-1}"
                warn "$(t warn_adopt_single_section)"
            else
                warn "$(t warn_headless_pin_failed)"
                warn "$(t warn_pin_own_default)"
                return 1
            fi
        fi
        hash="${section#Install}"
    fi

    profile_path=$(_profile_entry_path_for "$ini" "$profile_abs") || {
        profile_path=$(profile_register_entry "$ini" "$profile_abs") || {
            warn "$(t warn_profile_not_in_ini "$profile_abs")"
            return 1
        }
    }

    _ini_write_install_section "$ini" "$section" "$profile_path"
    local installs_ini
    installs_ini="$(dirname "$ini")/installs.ini"
    _ini_write_install_section "$installs_ini" "${section#Install}" "$profile_path"

    success "$(t profile_pinned "$section" "$profile_path")"
    echo "$hash"
}

_ini_write_install_section() {
    local ini="$1" section="$2" profile_path="$3"
    local tmp="${ini}.myfox.tmp"
    _ini_remove_section "$ini" "$section" "$tmp"
    printf '\n[%s]\nDefault=%s\nLocked=1\n' "$section" "$profile_path" >> "$tmp"
    mv "$tmp" "$ini"
}

profile_unpin_install() {
    local hash="$1"
    [[ -z "$hash" ]] && return 0
    local ini i_dir
    ini=$(profile_find_ini) || true
    if [[ -n "$ini" ]]; then
        i_dir=$(dirname "$ini")
        _ini_remove_section "$ini" "Install${hash}" "${ini}.myfox.tmp" && mv "${ini}.myfox.tmp" "$ini"
        success "$(t profile_unpinned "[Install${hash}]" "$ini")"
        local installs_ini="$i_dir/installs.ini"
        if [[ -f "$installs_ini" ]]; then
            _ini_remove_section "$installs_ini" "$hash" "${installs_ini}.myfox.tmp" \
                && mv "${installs_ini}.myfox.tmp" "$installs_ini"
            success "$(t profile_unpinned "[${hash}]" "$installs_ini")"
        fi
    fi
}

profile_remove_myfox_section() {  # <profile_dir>
    # Scoped to the exact profile directory being uninstalled — NOT "remove
    # any [ProfileN] with Name=myfox", which would also rip out entries for
    # other, unrelated myfox installs/profiles still on the machine. (The
    # previous implementation additionally mis-handled multiple matches: it
    # collected every matching section into one multi-line awk result and
    # then blindly stripped one leading/trailing char off the whole blob,
    # producing a garbled section name whenever more than one existed.)
    local profile_dir="${1%/}"
    local ini
    ini=$(profile_find_ini) || return 0
    local name
    name=$(_profile_section_for_dir "$ini" "$profile_dir") || true
    [[ -z "$name" ]] && { log "$(t profile_no_myfox_section)"; return 0; }
    _ini_remove_section "$ini" "$name" "${ini}.myfox.tmp" && mv "${ini}.myfox.tmp" "$ini"
    success "$(t profile_section_removed "[${name}]" "$ini")"
}

# ─── Точка входа: определить/выбрать/создать профиль ────────────────────────
#
# profile_resolve [--explicit <path>]
#   1. --explicit и путь существует → использовать.
#   2. MYFOX_PROFILE_FORCE_NEW=1 → создать новый.
#   3. в state есть profile_dir и он существует → использовать.
#   4. первый запуск: только наши myfox-профили; если их нет или неинтерактив —
#      создать новый; иначе — tui-выбор (profile_pick_myfox).
profile_resolve() {
    local explicit=""
    [[ "$1" == "--explicit" ]] && explicit="$2"

    if [[ -n "$explicit" ]]; then
        [[ -d "$explicit" ]] || error "$(t err_profile_not_found "$explicit")"
        echo "$explicit"
        return 0
    fi

    if [[ "$MYFOX_PROFILE_FORCE_NEW" == "1" ]]; then
        log "$(t profile_creating_new_wizard)"
        profile_create_new
        return 0
    fi

    local marked
    marked=$(state_get profile_dir)
    if [[ -n "$marked" && -d "$marked" ]]; then
        log "$(t profile_using_saved "$marked")"
        echo "$marked"
        return 0
    fi
    [[ -n "$marked" ]] && warn "$(t warn_saved_profile_gone "$marked")"

    local myfox_list
    myfox_list=$(profile_list_myfox) || true
    if [[ -z "$myfox_list" ]]; then
        log "$(t profile_creating_new_none_found)"
        profile_create_new
        return 0
    fi

    if [[ -n "$MYFOX_NONINTERACTIVE" ]]; then
        log "$(t profile_creating_new_noninteractive)"
        profile_create_new
        return 0
    fi

    local chosen
    chosen=$(profile_pick_myfox "$myfox_list" 0) || error "$(t err_profile_selection_cancelled)"
    if [[ -n "$chosen" ]]; then
        echo "$chosen"
        return 0
    fi
    log "$(t profile_creating_new_chosen)"
    profile_create_new
}

# Диалог выбора профиля (существующие myfox-профили + «создать новый», дефолт).
# stdout: путь выбранного профиля, пусто = «создать новый». rc 1 = отмена,
# rc 3 = выбрано «Назад» (только если back=1).
# notags=1 (см. tui_choose_kv): колонка тегов скрыта, шапка колонок —
# отдельный псевдо-пункт (MYFOX_HEADER_TAG), а не текст диалога — иначе
# dialog выравнивает текст диалога и пункты списка по-разному и всё едет.
profile_pick_myfox() {  # <list path|name …> <back:0|1>
    local list="$1" back="${2:-0}"
    local p n
    local -a kv=(
        "$MYFOX_HEADER_TAG" "$(printf '%s %s %s %s' \
            "$(myfox_pad "$(t col_profile)" 14)" "$(myfox_pad "$(t col_path)" 38)" \
            "$(myfox_pad "$(t col_created)" 12)" "$(t col_modified)")"
        "new" "$(t profile_new_option)"
    )
    while IFS='|' read -r p n; do
        [[ -z "$p" ]] && continue
        kv+=("$p" "$(profile_table_row "$p" "$(basename "$p")")")
    done <<< "$list"
    local tag rc=0
    tag=$(tui_choose_kv "$(t profile_pick_heading)" "new" "$back" 1 "${kv[@]}") || rc=$?
    [[ "$rc" -eq 3 ]] && return 3
    [[ "$rc" -ne 0 ]] && return 1
    [[ "$tag" == "new" ]] && return 0
    echo "$tag"
}
