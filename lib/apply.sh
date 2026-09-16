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

    # Никаких глобальных политик: distribution/policies.json не ставим.
    # Всё твики — строго профиль-локальные (firefox.cfg + chrome/ профиля).
    # Удалил профиль → кристально чистый ванильный Firefox.
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

    # Маркер «нашего» профиля: firefox.cfg проверяет его в начале и применяет твики
    # ТОЛЬКО к профилю с этим файлом. Новые чистые профили без маркера остаются
    # немодифицированным Firefox (никаких твиков/префов/CSS).
    touch "$profile_dir/.myfox"

    success "Chrome styles installed."
}

# ─── Букмарклеты (твики из отдельного проекта ddblm) ────────────────────────
#
# Применяет твики букмарклетов из отдельного проекта DayDve/ddblm:
#   - docs/blm_panel.css  → chrome/blm_panel.css
#   - ВСЕ icons/*.svg     → chrome/panel-icons/  (не только те, что упомянуты
#     в css: иконки могут понадобиться galler-букмарклетам, добавленным позже).
#
# Источник файлов:
#   - если доступна локальная копия ddblm (MYFOX_DDBLM_LOCAL) — копируем её
#     (используется при тестировании твиков);
#   - иначе тянем из raw.githubusercontent.com (опубликованный репозиторий).
# Ссылка на галерею на панель закладок добавляется отдельно (firefox.cfg).

# Копирует/скачивает один файл ddblm. <rel> — путь без ведущего слэша
# (напр. "docs/blm_panel.css" или "icons/foo.svg"). Источник выбирается
# автоматически: локальный каталог → raw github.
# Второй аргумент — целевой путь в chrome/ профиля.
ddblm_file() {
    local rel="$1" out="$2"
    if [[ -n "$MYFOX_DDBLM_LOCAL" && -f "$MYFOX_DDBLM_LOCAL/$rel" ]]; then
        install -m 0644 "$MYFOX_DDBLM_LOCAL/$rel" "$out"
        return 0
    fi
    local url="${MYFOX_DDBLM_RAW}/${rel}"
    log "Fetching ${url}"
    curl -L --fail --silent --show-error -o "$out" "$url"
}

apply_bookmarklets() {
    local profile_dir="$1"
    local c_dir="$profile_dir/chrome"

    [[ -d "$c_dir" ]] || mkdir -p "$c_dir"

    local src_dir rel f

    # Источник: локальная копия ddblm (для теста твиков) или raw github.
    src_dir=""
    if [[ -n "$MYFOX_DDBLM_LOCAL" && -d "$MYFOX_DDBLM_LOCAL/icons" ]]; then
        src_dir="$MYFOX_DDBLM_LOCAL"
        log "Using local ddblm copy: $src_dir"
    fi

    # 1) Готовый blm_panel.css (иконки + скрытие текста букмарклетов).
    if ! ddblm_file "docs/blm_panel.css" "$c_dir/blm_panel.css"; then
        warn "Could not fetch blm_panel.css from ddblm — skipping bookmarklet tweaks."
        return 1
    fi

    # 2) ВСЕ иконки (panel-icons/<имя>.svg). Локально — копируем папку целиком.
    mkdir -p "$c_dir/panel-icons"
    if [[ -n "$src_dir" ]]; then
        for f in "$src_dir"/icons/*.svg; do
            [[ -f "$f" ]] || continue
            install -m 0644 "$f" "$c_dir/panel-icons/$(basename "$f")"
        done
    else
        # На удалённом источнике список имён берём из css (panel-icons/<base>.svg).
        # Глобально не знаем полного каталога raw-репо; тут он совпадает с icons/.
        local names
        names=$(grep -o 'url("panel-icons/[^"]*")' "$c_dir/blm_panel.css" "$c_dir/userChrome.css" \
            | sed 's/.*url("panel-icons\///;s/")//;s/\.svg$//' | sort -u || true)
        # Кнопка «Добавить букмарклеты» в userChrome.css опирается на неё.
        names+=" import-bookmarklets"
        for rel in $names; do
            ddblm_file "icons/${rel}.svg" "$c_dir/panel-icons/${rel}.svg" \
                || warn "Icon not available in ddblm repo: $rel"
        done
        # Иконки, которые могут понадобиться позже (если всё же известны в css).
        # IMG
    fi

    success "Bookmarklet tweaks applied (from ddblm)."
    echo "$MYFOX_DDBLM_GALLERY"
}
