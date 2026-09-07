# shellcheck shell=bash
# apply.sh — применение твиков myfox:
#   - autoconfig (autoconfig.js → defaults/pref/, firefox.cfg → install root)
#   - chrome CSS (userChrome.css, agent_overrides.css → profile chrome/)
#   - префы (уже вшиты в firefox.cfg — применяются самим Firefox при старте)
#   - бэкап занятой директории (если по целевому пути стоит чужой Firefox)
# Требуются common.sh.

# ─── Бэкап занятой директории ───────────────────────────────────────────────
#
# backup_dir_nonempty <target_dir> → создаёт tar.gz бэкап рядом, возвращает путь бэкапа.
# Если каталог пуст/не существует — бэкап не нужен (вернуть пустоту).
backup_dir_nonempty() {
    local target="$1"
    if [[ ! -d "$target" || -z "$(ls -A "$target" 2>/dev/null)" ]]; then
        return 0
    fi
    mkdir -p "$MYFOX_STATE_DIR/backups"
    local stamp
    stamp=$(date +%Y%m%d-%H%M%S)
    local backup="$MYFOX_STATE_DIR/backups/install-${stamp}.tar.gz"
    log "Backing up existing directory: $target"
    if ! tar -czf "$backup" -C "$target" .; then
        warn "Backup failed, proceeding without backup."
        return 0
    fi
    echo "$backup"
}

# ─── Применение autoconfig ──────────────────────────────────────────────────

apply_autoconfig() {
    local install_dir="$1" backup_dir_var="$2"
    mkdir -p "$install_dir/defaults/pref"

    # Если у инсталляции уже есть autoconfig, но это НЕ наша копия (нет наших твиков) —
    # просто перезаписываем (безопасно: инсталляция всё равно целиком наша после установки).
    log "Installing autoconfig files..."
    install -m 0644 "$MYFOX_AUTOCONFIG_DIR/autoconfig.js" "$install_dir/defaults/pref/autoconfig.js"
    install -m 0644 "$MYFOX_AUTOCONFIG_DIR/firefox.cfg" "$install_dir/firefox.cfg"
    success "Autoconfig installed."
}

# ─── Применение chrome CSS ──────────────────────────────────────────────────

apply_chrome() {
    local profile_dir="$1"
    mkdir -p "$profile_dir/chrome"

    # Защитное сохранение чужих стилей профиля (если выбран существующий профиль,
    # в котором уже были свои userChrome/agent_overrides до нас).
    local c_dir="$profile_dir/chrome"
    local stamp
    stamp=$(date +%Y%m%d-%H%M%S)
    for f in userChrome.css agent_overrides.css; do
        if [[ -f "$c_dir/$f" && ! -f "$c_dir/$f.myfox-backup" ]]; then
            cp "$c_dir/$f" "$c_dir/$f.myfox-backup"
            warn "Saved your existing $f as $f.myfox-backup"
        fi
    done

    log "Installing chrome styles..."
    install -m 0644 "$MYFOX_CHROME_DIR/userChrome.css" "$profile_dir/chrome/userChrome.css"
    install -m 0644 "$MYFOX_CHROME_DIR/agent_overrides.css" "$profile_dir/chrome/agent_overrides.css"
    success "Chrome styles installed."
}

# ─── Букмарклеты (blm, опционально) ─────────────────────────────────────────
#
# Применяет твики букмарклетов из submodule ddbml: build + patchff.
# blm — автономная утилита ddbml; здесь мы лишь дёргаем её.
# Также вносит ссылку на галерею (GitHub Pages) в панель закладок.
apply_bookmarklets() {
    local profile_dir="$1"
    local blm_dir="$MYFOX_BOOKMARKLETS_DIR"

    if [[ ! -x "$blm_dir/blm" ]]; then
        warn "Bookmarklet submodule (ddbml) not checked out — skipping bookmarklet tweaks."
        warn "  Run: git submodule update --init --recursive"
        return 1
    fi

    log "Configuring blm for profile: $profile_dir"
    "$blm_dir/blm" config set ff_profile "$profile_dir"
    log "Building bookmarklet gallery..."
    "$blm_dir/blm" build
    log "Patching Firefox profile for bookmarklet styles..."
    "$blm_dir/blm" patchff

    success "Bookmarklet tweaks applied."
    echo "$blm_dir/docs/index.html"
}