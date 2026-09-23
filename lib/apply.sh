# shellcheck shell=bash
# apply.sh — применение твиков myfox: autoconfig, chrome CSS, букмарклеты (ddblm).
# Требует common.sh, i18n.sh.

# ─── Autoconfig ──────────────────────────────────────────────────────────────

apply_autoconfig() {
    local install_dir="$1"
    mkdir -p "$install_dir/defaults/pref"
    log "$(t applying_autoconfig)"
    install -m 0644 "$MYFOX_AUTOCONFIG_DIR/autoconfig.js" "$install_dir/defaults/pref/autoconfig.js"
    install -m 0644 "$MYFOX_AUTOCONFIG_DIR/firefox.cfg" "$install_dir/firefox.cfg"
    success "$(t autoconfig_installed)"
    # Никаких глобальных политик (distribution/policies.json) — всё профиль-локально.
}

# ─── Chrome CSS ──────────────────────────────────────────────────────────────

apply_chrome() {
    local profile_dir="$1"
    mkdir -p "$profile_dir/chrome"

    local c_dir="$profile_dir/chrome" f
    for f in userChrome.css agent_overrides.css; do
        if [[ -f "$c_dir/$f" && ! -f "$c_dir/$f.myfox-backup" ]]; then
            cp "$c_dir/$f" "$c_dir/$f.myfox-backup"
            warn "$(t warn_backed_up_style "$f")"
        fi
    done

    log "$(t applying_chrome)"
    install -m 0644 "$MYFOX_CHROME_DIR/userChrome.css" "$profile_dir/chrome/userChrome.css"
    install -m 0644 "$MYFOX_CHROME_DIR/agent_overrides.css" "$profile_dir/chrome/agent_overrides.css"

    # Маркер профиля: firefox.cfg проверяет его в начале и применяет твики ТОЛЬКО
    # к профилю с этим файлом. Профили без маркера остаются чистым Firefox.
    touch "$profile_dir/.myfox"

    success "$(t chrome_installed)"
}

# ─── Букмарклеты (ddblm) ──────────────────────────────────────────────────────
#
# docs/blm_panel.css → chrome/blm_panel.css, ВСЕ icons/*.svg → chrome/panel-icons/.
# Источник: локальная копия (MYFOX_DDBLM_LOCAL) при отладке, иначе raw github.

ddblm_file() {  # <rel> <out>
    local rel="$1" out="$2"
    if [[ -n "$MYFOX_DDBLM_LOCAL" && -f "$MYFOX_DDBLM_LOCAL/$rel" ]]; then
        install -m 0644 "$MYFOX_DDBLM_LOCAL/$rel" "$out"
        return 0
    fi
    local url="${MYFOX_DDBLM_RAW}/${rel}"
    log "$(t fetching_url "$url")"
    curl -L --fail --silent --show-error -o "$out" "$url"
}

apply_bookmarklets() {
    local profile_dir="$1"
    local c_dir="$profile_dir/chrome"
    mkdir -p "$c_dir"

    local src_dir=""
    if [[ -n "$MYFOX_DDBLM_LOCAL" && -d "$MYFOX_DDBLM_LOCAL/icons" ]]; then
        src_dir="$MYFOX_DDBLM_LOCAL"
        log "$(t using_local_ddblm "$src_dir")"
    fi

    if ! ddblm_file "docs/blm_panel.css" "$c_dir/blm_panel.css"; then
        warn "$(t warn_ddblm_unreachable)"
        return 1
    fi

    mkdir -p "$c_dir/panel-icons"
    if [[ -n "$src_dir" ]]; then
        local f
        for f in "$src_dir"/icons/*.svg; do
            [[ -f "$f" ]] || continue
            install -m 0644 "$f" "$c_dir/panel-icons/$(basename "$f")"
        done
    else
        local names rel
        names=$(awk '
            { while (match($0, /url\("panel-icons\/[^"]*"\)/)) {
                  s = substr($0, RSTART, RLENGTH)
                  gsub(/url\("panel-icons\//, "", s); gsub(/\.svg"\)/, "", s)
                  print s
                  $0 = substr($0, RSTART + RLENGTH)
              } }
        ' "$c_dir/blm_panel.css" "$c_dir/userChrome.css" | sort -u)
        names+=" import-bookmarklets"
        for rel in $names; do
            ddblm_file "icons/${rel}.svg" "$c_dir/panel-icons/${rel}.svg" \
                || warn "$(t warn_icon_missing "$rel")"
        done
    fi

    success "$(t bookmarklets_applied)"
    echo "$MYFOX_DDBLM_GALLERY"
}
