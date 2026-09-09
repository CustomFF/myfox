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
    mkdir -p "$install_dir/distribution"

    # Если у инсталляции уже есть autoconfig, но это НЕ наша копия (нет наших твиков) —
    # просто перезаписываем (безопасно: инсталляция всё равно целиком наша после установки).
    log "Installing autoconfig files..."
    install -m 0644 "$MYFOX_AUTOCONFIG_DIR/autoconfig.js" "$install_dir/defaults/pref/autoconfig.js"
    install -m 0644 "$MYFOX_AUTOCONFIG_DIR/firefox.cfg" "$install_dir/firefox.cfg"
    success "Autoconfig installed."

    # Политика DisableProfileImport: запрещает штатный механизм Firefox
    # «добавить кнопку Импорт закладок в панель» (maybeAddImportButton на
    # browser-idle-startup добавляет её при <3 закладках в панели, и firefox.cfg
    # её не переигрывает). Политикой браузер сам её убирает.
    if [[ ! -f "$install_dir/distribution/policies.json" ]] || \
       ! grep -q 'DisableProfileImport' "$install_dir/distribution/policies.json"; then
        log "Installing distribution/policies.json (DisableProfileImport)..."
        printf '%s\n' \
            '{' \
            '  "policies": {' \
            '    "DisableProfileImport": true' \
            '  }' \
            '}' > "$install_dir/distribution/policies.json"
        success "DisableProfileImport policy installed."
    fi
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

# ─── Букмарклеты (твики из отдельного проекта ddblm по прямой ссылке) ───────
#
# Применяет твики букмарклетов из отдельного проекта DayDve/ddblm: готовый
# bookmarks_panel.css и svg-иконки скачиваются напрямую из raw.githubusercontent.com
# в chrome/ профиля. Локальная установка ddbml (blm) НЕ требуется — only raw-файлы.
# Ссылка на галерею букмарклетов на панель закладок добавляется отдельно (firefox.cfg).
# ВНИМАНИЕ: пока твики проверяются РУЧНЫМ копированием из локального ddblm,
# автоматизация (эта функция) может не сработать, пока ddblm не запушен.

# Скачивает один raw-файл из репо ddblm. <rel> — путь без ведущего слэша, напр.
# "docs/bookmarks_panel.css" или "icons/foo.svg".
ddblm_fetch() {
    local rel="$1" out="$2"
    local url="${MYFOX_DDBLM_RAW}/${rel}"
    log "Fetching ${url}"
    curl -L --fail --silent --show-error -o "$out" "$url"
}

apply_bookmarklets() {
    local profile_dir="$1"
    local c_dir="$profile_dir/chrome"

    [[ -d "$c_dir" ]] || mkdir -p "$c_dir"

    # 1) Готовый blm_panel.css (иконки + скрытие текста букмарклетов).
    local css="$c_dir/blm_panel.css"
    if ! ddblm_fetch "docs/blm_panel.css" "$css"; then
        warn "Could not fetch blm_panel.css from ddblm — skipping bookmarklet tweaks."
        return 1
    fi

    # 2) Иконки, на которые ссылается css (panel-icons/<name>.svg).
    local names
    names=$(grep -o 'url("panel-icons/[^"]*")' "$css" "$c_dir/userChrome.css" \
        | sed 's/.*url("panel-icons\///;s/")//' | sort -u || true)
    if [[ -n "$names" ]]; then
        mkdir -p "$c_dir/panel-icons"
        local n
        for n in $names; do
            ddblm_fetch "icons/$n" "$c_dir/panel-icons/$n" \
                || warn "Icon not available in ddblm repo: $n"
        done
    fi

    success "Bookmarklet tweaks applied (from ddblm)."
    echo "$MYFOX_DDBLM_GALLERY"
}
