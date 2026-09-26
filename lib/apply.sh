# shellcheck shell=bash
# apply.sh — применение твиков myfox: autoconfig, chrome CSS, букмарклеты (ddblm).
# Требует common.sh, i18n.sh.

# ─── Autoconfig ──────────────────────────────────────────────────────────────

apply_autoconfig() {
    local install_dir="$1"
    mkdir -p "$install_dir/defaults/pref"
    install -m 0644 "$MYFOX_AUTOCONFIG_DIR/autoconfig.js" "$install_dir/defaults/pref/autoconfig.js"
    install -m 0644 "$MYFOX_AUTOCONFIG_DIR/firefox.cfg" "$install_dir/firefox.cfg"
    # Никаких глобальных политик (distribution/policies.json) — всё профиль-локально.
    # No log()/success() here on purpose — both call sites wrap this in the
    # single "Настройка профиля" tui_spin; a line here would break its
    # one-line redraw.
}

# ─── Chrome CSS ──────────────────────────────────────────────────────────────

apply_chrome() {
    local profile_dir="$1"
    mkdir -p "$profile_dir/chrome"

    local c_dir="$profile_dir/chrome" f
    for f in userChrome.css agent_overrides.css; do
        if [[ -f "$c_dir/$f" && ! -f "$c_dir/$f.myfox-backup" ]]; then
            cp "$c_dir/$f" "$c_dir/$f.myfox-backup"
            warn "$(t warn_backed_up_style "$f" "$f")"
        fi
    done

    install -m 0644 "$MYFOX_CHROME_DIR/userChrome.css" "$profile_dir/chrome/userChrome.css"
    install -m 0644 "$MYFOX_CHROME_DIR/agent_overrides.css" "$profile_dir/chrome/agent_overrides.css"

    # Маркер профиля: firefox.cfg проверяет его в начале и применяет твики ТОЛЬКО
    # к профилю с этим файлом. Профили без маркера остаются чистым Firefox.
    touch "$profile_dir/.myfox"
    # No log()/success() here — see apply_autoconfig comment above.
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
    # No per-file log line here on purpose: this fetches a dozen-odd small
    # SVGs one at a time, and the caller (apply_bookmarklets) is wrapped in
    # a single tui_spin — per-file log() lines would each print with a
    # newline mid-animation, breaking the spinner's one-line redraw into a
    # scroll of half-finished frames instead of a clean "stage [✔]".
    local url="${MYFOX_DDBLM_RAW}/${rel}"
    curl -L --fail --silent --show-error -o "$out" "$url"
}

apply_bookmarklets() {
    local profile_dir="$1"
    local c_dir="$profile_dir/chrome"
    mkdir -p "$c_dir"

    local src_dir=""
    if [[ -n "$MYFOX_DDBLM_LOCAL" && -d "$MYFOX_DDBLM_LOCAL/icons" ]]; then
        src_dir="$MYFOX_DDBLM_LOCAL"
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

    echo "$MYFOX_DDBLM_GALLERY"
}
