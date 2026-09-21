# shellcheck shell=bash
# firefox.sh — адаптация идей mozinst.sh, only Firefox (Release).
# Скачивание тарбола Firefox с download.mozilla.org, определение версии,
# desktop entry. Интегрирован с маркером myfox (не «сырой» порт).
#
# Требуется common.sh (переменные/функции).

# ─── Локализация и архитектура ──────────────────────────────────────────────

# Полная локаль (LANG) → код языка Firefox (download.mozilla.org &lang=<code>).
# Неизвестная/не-локализованная → en-US.
firefox_detect_lang() {
    local lang base
    lang="${LANG:-en_US.UTF-8}"
    # Отбрасываем кодировку/модификатор: "pt_BR.UTF-8" → "pt_BR", "en_US@euro" → "en_US"
    base="${lang%%@*}"
    base="${base%%.*}"
    case "$base" in
        ru_*|ru)          echo "ru" ;;
        de_*|de)          echo "de" ;;
        fr_*|fr)          echo "fr" ;;
        it_*|it)          echo "it" ;;
        es_*|es)          echo "es-ES" ;;
        pt_BR*|pt_BR)     echo "pt-BR" ;;
        pt_*|pt)          echo "pt-PT" ;;
        uk_*|uk)          echo "uk" ;;
        ja_*|ja)          echo "ja" ;;
        zh_CN*|zh_SG*|zh_CN|zh_SG|zh) echo "zh-CN" ;;
        zh_TW*|zh_HK*|zh_TW|zh_HK) echo "zh-TW" ;;
        pl_*|pl)          echo "pl" ;;
        nl_*|nl)          echo "nl" ;;
        cs_*|cs)          echo "cs" ;;
        sk_*|sk)          echo "sk" ;;
        hu_*|hu)          echo "hu" ;;
        tr_*|tr)          echo "tr" ;;
        sv_*|sv)          echo "sv-SE" ;;
        nb_*|no_*|nb|no) echo "nb-NO" ;;
        nn_*|nn)          echo "nn-NO" ;;
        he_*|he)          echo "he" ;;
        ar_*|ar)          echo "ar" ;;
        fi_*|fi)          echo "fi" ;;
        da_*|da)          echo "da" ;;
        el_*|el)          echo "el" ;;
        bg_*|bg)          echo "bg" ;;
        hr_*|hr)          echo "hr" ;;
        ro_*|ro)          echo "ro" ;;
        sl_*|sl)          echo "sl" ;;
        sr_*|sr)          echo "sr" ;;
        vi_*|vi)          echo "vi" ;;
        th_*|th)          echo "th" ;;
        ko_*|ko)          echo "ko" ;;
        hi_IN*|hi_*|hi)   echo "hi-IN" ;;
        id_*|id)          echo "id" ;;
        en_GB*|en_GB)     echo "en-GB" ;;
        en_*|en)          echo "en-US" ;;
        *)                echo "en-US" ;;
    esac
}

firefox_detect_arch() {
    case "$(uname -m)" in
        x86_64)   echo "linux64" ;;
        i?86)     echo "linux" ;;
        aarch64)  echo "linux-aarch64" ;;
        *)        echo "linux64" ;; # fallback
    esac
}

# ─── Определение версии установленного Firefox ─────────────────────────────

firefox_local_version() {
    local inst_path="$1"
    local ver=""

    if [[ -f "$inst_path/application.ini" ]]; then
        ver=$(grep '^Version=' "$inst_path/application.ini" 2>/dev/null | cut -d= -f2) || true
    fi

    local bin="$inst_path/firefox-bin"
    if [[ -f "$bin" ]]; then
        local bin_ver
        bin_ver=$("$bin" --version 2>/dev/null | grep -oP '[0-9]+\.[0-9]+[a-z]*[0-9]*' | head -1) || true
        [[ -n "$bin_ver" ]] && ver="$bin_ver"
    fi

    if [[ -n "$ver" ]]; then
        echo "$ver"
    fi
    return 0
}

# ─── Языки (каталог Mozilla) ────────────────────────────────────────────────
#
# Источник: https://product-details.mozilla.org/1.0/languages.json
# Формат: { "<code>": { "English": "…", "native": "…" }, … }
# Кеш — на время одного запуска (mktemp), чтобы несколько вызовов не качали
# повторно; файл остаётся в /tmp (ОС подчистит).

MYFOX_LANG_JSON="${MYFOX_LANG_JSON:-}"

firefox_fetch_lang_json() {
    if [[ -z "$MYFOX_LANG_JSON" ]]; then
        MYFOX_LANG_JSON=$(mktemp --suffix=.myfox-languages.json)
        if ! curl -L --fail --silent --show-error --connect-timeout 10 --max-time 30 \
            -o "$MYFOX_LANG_JSON" \
            "https://product-details.mozilla.org/1.0/languages.json"; then
            rm -f "$MYFOX_LANG_JSON"
            MYFOX_LANG_JSON=""
            return 1
        fi
    fi
    echo "$MYFOX_LANG_JSON"
}

# Печать всех языков: код  English-название (в stderr — твики-capture не трогаем).
firefox_list_languages() {
    local cache
    cache=$(firefox_fetch_lang_json) || { error "Failed to fetch Mozilla language list."; return 1; }
    python3 - "$cache" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
for code in sorted(d):
    print(f"{code}  {d[code]['English']}", file=sys.stderr)
EOF
}

# Валидация кода по списку Mozilla. Возвращает 0 если валиден.
firefox_validate_lang() {
    local code="$1" cache
    cache=$(firefox_fetch_lang_json) || return 1
    python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print("yes" if sys.argv[2] in d else "no")' \
        "$cache" "$code" | grep -qx yes
}

# Отрисовка окна scrollable-меню (win строк, начиная с 3-й строки) с подсветкой
# текущей позиции. ВЕСЬ вывод в stderr — функция вызывается из $(...), и stdout
# уходит в капчу (иначе меню не видно).
_lang_render() {  # _lang_render <list> <total> <top> <win> <sel>
    local list="$1" total="$2" top="$3" win="$4" sel="$5"
    printf '\e[3;1H' >&2
    awk -F'\t' -v win="$win" -v top="$top" -v sel="$sel" '
        {
            if (NR > top && NR <= top + win) {
                s = (NR-1 == sel) ? "\033[7m" : ""
                e = (NR-1 == sel) ? "\033[0m" : ""
                printf "%s  %3d. %-9s %s%s\033[K\n", s, $1, $2, $3, e
                filled = NR
            }
        }
        END {
            for (i = filled+1; i <= top+win; i++) printf " \033[K\n"
        }' "$list" >&2
    # статус-строка (row 3+win): текущий язык
    printf '\r  ▶ %s\e[K' "$(awk -F'\t' -v s="$sel" 'NR-1==s {print $2" — "$3}' "$list")" >&2
}

# Без tty (труба/CI): простой промпт — Enter = default, либо код языка.
_lang_prompt_fallback() {  # stdout: выбранный код
    local default_lang="$1" a
    read -rp "Language [$default_lang]: " a
    a="${a:-$default_lang}"
    if [[ "$a" != "$default_lang" ]] && ! firefox_validate_lang "$a"; then
        warn "Unknown code '$a', using $default_lang."
        a="$default_lang"
    fi
    echo "$a"
}

# dialog (KDE/apt, как у dpkg-reconfigure) или whiptail (newt/Debian):
# нормальный box со встроенной прокруткой и клавиатурой. stdout — выбранный TAG
# (номер пункта); выбранный язык маппится в caller'е. <def> — tag дефолта
# (автодетект), чтобы Enter сразу выбирал родной язык.
_lang_menu_dialog() {  # <list> <def> → stdout: tag (номер)
    local list="$1" def="$2" items=()
    while IFS=$'\t' read -r i c n; do items+=("$i" "$c  $n"); done < "$list"
    local msg="Firefox UI language — it also picks the tarball to download."
    # dialog по умолчанию сам включает/выключает alt-экран (ncurses+terminfo
    # smcup/rmcup) и между вызовами на миг показывает главный экран. Чтобы не
    # мигало, wizard_full/sequential подсовывают dialog'у terminfo без
    # smcup/rmcup (use_ui_terminfo_noalt) — тогда он рисует в текущий экран.
    # Если wizard_full уже занял альтернативный экран (MYFOX_TUI_FENCED=1),
    # dialog просто рисует в него. Иначе — это standalone-вызов, нужна своя пара.
    local _fenced="${MYFOX_TUI_FENCED:-0}"
    if [[ "$_fenced" != "1" ]]; then
        use_ui_terminfo_noalt || true
        tui_enter
    fi
    if command -v dialog >/dev/null 2>&1; then
        dialog --stdout --clear --ok-label "Continue" --default-item "$def" \
            --menu "$msg" 0 0 0 "${items[@]}"
    elif command -v whiptail >/dev/null 2>&1; then
        # Обмен fds: GUI на терминал (stdout), результат — в капче (эмпирически проверено).
        whiptail --clear --ok-button "Continue" --default-item "$def" \
            --menu "$msg" 0 0 0 "${items[@]}" 3>&1 1>&2 2>&3
    fi
    if [[ "$_fenced" != "1" ]]; then
        tui_reset
        reset_ui_terminfo_noalt
    fi
}

# Scrollable-меню на чистом bash (запасной путь, если нет ни dialog, ни whiptail).
# Всю отрисовку — в stderr; в stdout — только выбранный код.
_lang_picker_menu() {  # <list> <default_lang> → stdout
    local list="$1" default_lang="$2"
    local total top sel win key k2 k3 k4
    total=$(wc -l < "$list")
    win=10
    sel=$(awk -F'\t' -v c="$default_lang" '$2==c {print NR-1}' "$list")  # 0-based
    [[ "$sel" =~ ^[0-9]+$ ]] || sel=0
    (( sel >= total )) && sel=$((total - 1))
    local sel_default=$sel
    top=0
    (( sel >= win )) && top=$(( sel - win + 1 ))

    printf '\e[?25l' >&2
    while true; do
        _lang_render "$list" "$total" "$top" "$win" "$sel"
        read -rsn1 key || key=''
        if [[ "$key" == $'\e' ]]; then
            read -rsn1 k2 || k2=''
            if [[ "$k2" == '[' ]]; then
                read -rsn1 k3 || k3=''
                case "$k3" in
                    A) (( sel > 0 )) && sel=$((sel - 1)) ;;
                    B) (( sel < total - 1 )) && sel=$((sel + 1)) ;;
                    H) sel=0 ;;
                    F) sel=$((total - 1)) ;;
                    5) read -rsn1 k4 || k4=''; (( sel >= win )) && sel=$((sel - win)) || sel=0 ;;
                    6) read -rsn1 k4 || k4=''; (( s = sel + win, s < total )) && sel=$s || sel=$((total - 1)) ;;
                esac
            fi
        elif [[ "$key" == '' || "$key" == $'\n' || "$key" == $'\r' ]]; then
            break
        elif [[ "$key" == 'q' || "$key" == 'Q' ]]; then
            sel=$sel_default
            break
        fi
        # Не даём окну "уезжать" от курсора.
        (( sel < top )) && top=$sel
        (( sel >= top + win )) && top=$(( sel - win + 1 ))
    done

    printf '\e[?25h\n' >&2
    awk -F'\t' -v s="$sel" 'NR-1==s {print $2}' "$list"
}

# Синхронно качает каталог языков и строит список <tag>\t<code>\t<English> —
# тот же формат, что использует _lang_menu_dialog. Путь — в MYFOX_LANG_LIST,
# переиспользуется firefox_interactive_lang. Вызывается ДО входа в мастер:
# всю тяжёлую работу (curl+python3) делаем на обычном экране, чтобы между
# диалогами мастера не было ни одной операции (иначе на переходах мигает —
# dialog успевает разобрать ncurses и показать голый буфер).
firefox_prepare_lang_list() {
    if [[ -s "${MYFOX_LANG_LIST:-}" ]]; then
        return 0
    fi
    local cache
    cache=$(firefox_fetch_lang_json) || return 1
    MYFOX_LANG_LIST=$(mktemp --suffix=.myfox-langlist)
    if ! python3 - "$cache" "$MYFOX_LANG_LIST" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
with open(sys.argv[2], "w") as f:
    for i, code in enumerate(sorted(d), 1):
        f.write(f"{i}\t{code}\t{d[code]['English']}\n")
EOF
    then
        rm -f "$MYFOX_LANG_LIST"
        MYFOX_LANG_LIST=""
        return 1
    fi
}

MYFOX_LANG_LIST="${MYFOX_LANG_LIST:-}"

# Интерактивный выбор языка (первая установка).
#
# Приоритет: dialog (как в dpkg-reconfigure) → whiptail → scrollable bash-меню →
# простой промпт (нет tty). Выбранный код — в stdout (меню рисуется в stderr,
# чтобы не утекать в капчу $(...)).
firefox_interactive_lang() {
    local default_lang list code tag
    default_lang=$(firefox_detect_lang)

    # Без tty интерактив не имеет смысла — простой промпт.
    if [[ ! -t 0 ]]; then
        _lang_prompt_fallback "$default_lang"
        return 0
    fi

    # Список почти всегда уже построен wizard_full (MYFOX_LANG_LIST); если нет —
    # строим сами синхронно (sequential-путь).
    if [[ -s "${MYFOX_LANG_LIST:-}" ]]; then
        list="$MYFOX_LANG_LIST"
    elif firefox_prepare_lang_list; then
        list="$MYFOX_LANG_LIST"
    else
        error "Failed to fetch Mozilla language list."
        return 1
    fi

    code=""
    if command -v dialog >/dev/null 2>&1 || command -v whiptail >/dev/null 2>&1; then
        myfox_debug "lang: before menu dialog"
        # dialog не должен дёргать alt-экран (иначе мигает) — урезанный terminfo.
        use_ui_terminfo_noalt || true
        local def
        def=$(awk -F'\t' -v c="$default_lang" '$2==c {print $1}' "$list")
        [[ "$def" =~ ^[0-9]+$ ]] || def=1
        tag=$(_lang_menu_dialog "$list" "$def") || tag=""
        if [[ -z "$tag" ]]; then
            return 1   # пользователь закрыл диалог (Cancel/Esc) — вызывающий решает
        fi
        code=$(awk -F'\t' -v n="$tag" '$1==n {print $2}' "$list")
    fi

    if [[ -z "$code" ]]; then
        code=$(_lang_picker_menu "$list" "$default_lang")
    fi

    # Временный список (built самотстоятельно) удаляем; shared MYFOX_LANG_LIST — нет.
    [[ "$list" != "$MYFOX_LANG_LIST" ]] && rm -f "$list"
    [[ -n "$code" ]] || code="$default_lang"
    echo "$code"
}

# ─── Скачивание ─────────────────────────────────────────────────────────────
#
# Качаем только curl'ом (без внешних ускорителей вроде aria2c). В обычном
# режиме curl сам рисует прогрессбар (--progress-bar). В мастере (активен
# gauge) вывод curl глушим, а прогресс показывает gauge-спиннер — иначе строка
# curl затёрла бы dialog.

firefox_download_archive() {
    local url="$1" out="$2"
    if [[ -n "$MYFOX_GAUGE_FD" ]]; then
        gauge_spin 5 60 \
            curl -L --fail --silent --show-error --retry 1 -o "$out" "$url"
    else
        curl -L --fail --progress-bar --retry 1 -o "$out" "$url"
    fi
}

# ─── Установка из тарбола ───────────────────────────────────────────────────
#
# firefox_install_tarball <install_dir> [lang_override]
#   - резолвит download.mozilla.org URL (arch+lang)
#   - скачивает, распаковывает начисто в install_dir
#   - пишет .myfox-installed-version метаданные
#   - при прерывании (INT) — останавливается (tar-транзакция не атомарна, но
#     повторные запуски перекачивают/дораспаковывают; корректность гарантирует --reinstall)
firefox_install_tarball() {
    local install_dir="$1"
    local lang_override="${2:-}"
    local channel="${3:-stable}"
    local lang arch url dl_archive effective_url remote_ver

    if [[ -n "$lang_override" ]]; then
        lang="$lang_override"
    else
        lang=$(firefox_detect_lang)
    fi
    arch=$(firefox_detect_arch)

    # Канал: stable (firefox-latest-ssl) или beta (firefox-beta-latest-ssl).
    # aarch64: Mozilla отдаёт linux-x86_64 для linux64; на aarch64 нужен linux-aarch64.
    local product="firefox-latest-ssl"
    local channel_tag=""
    if [[ "$channel" == "beta" ]]; then
        product="firefox-beta-latest-ssl"
        channel_tag="  (beta)"
    fi
    url="https://download.mozilla.org/?product=${product}&os=${arch}&lang=${lang}"

    log "Checking for the latest Firefox... (${channel})"

    effective_url=$(curl -sIL --connect-timeout 10 --max-time 30 -o /dev/null -w "%{url_effective}" "$url")
    if [[ -z "$effective_url" ]]; then
        error "Failed to resolve download URL."
    fi

    if [[ "$arch" == "linux-aarch64" ]]; then
        log "Adjusting URL for aarch64..."
        effective_url="${effective_url/linux-x86_64/linux-aarch64}"
    fi

    remote_ver=$(echo "$effective_url" | grep -oP "(?<=firefox-)[^/]+(?=\.tar)" | head -1)
    [[ -z "$remote_ver" ]] && remote_ver="unknown"

    # Баннер печатаем в stderr: install.sh захватывает stdout функции в переменную
    # (firefox_version), поэтому в stdout должен оставаться только результат.
    # При активном gauge текстовый вывод не нужен (он затёр бы dialog).
    if [[ -z "$MYFOX_GAUGE_FD" ]]; then
        echo -e "${BOLD}Firefox ${GREEN}${remote_ver}${NC}${BOLD}${channel_tag}  ·  ${lang}  →  ${install_dir}${NC}" >&2
    fi

    # Подтверждение «Proceed?» — для путей БЕЗ мастера (browser-only, fallback без
    # dialog). Мастер заканчивается кнопкой Install и ставит MYFOX_SKIP_CONFIRM=1.
    if [[ -z $MYFOX_NONINTERACTIVE && -z $MYFOX_SKIP_CONFIRM ]] && ! confirm "Proceed with installation?"; then
        echo "Cancelled." >&2
        # rc 2 = «отменено»; рекомендуется НЕ exit (нельзя: функция вызывается из
        # $(...), exit выйдет только из подшелла, и инсталлер продолжится как ни в
        # чём не бывало). Отмену обрабатывает install.sh.
        return 2
    fi

    mkdir -p "$install_dir"

    if [[ -z "$MYFOX_GAUGE_FD" ]]; then
        echo "  Downloading…" >&2
    else
        gauge_set 5 "Downloading Firefox…"
    fi
    dl_archive=$(mktemp "/tmp/moz_dl_XXXXXX.tar.xz")
    trap 'rm -f "$dl_archive"' INT

    if ! firefox_download_archive "$effective_url" "$dl_archive"; then
        rm -f "$dl_archive"
        trap - INT
        echo "" >&2
        error "Download failed."
    fi
    if [[ -z "$MYFOX_GAUGE_FD" ]]; then
        echo "" >&2
        echo "  Extracting…" >&2
    else
        gauge_set 62 "Extracting Firefox…"
    fi
    if ! tar -xJf "$dl_archive" -C "$install_dir" --strip-components=1; then
        rm -f "$dl_archive"
        trap - INT
        error "Extraction failed."
    fi

    rm -f "$dl_archive"
    trap - INT

    # Записываем версию (маркер версии — копия, не заменяет факт-маркер установки)
    echo "$remote_ver" > "$install_dir/.myfox-version"

    success "Firefox ${remote_ver} successfully installed!"
    echo "$remote_ver"
}

# ─── Desktop entry ──────────────────────────────────────────────────────────

firefox_create_desktop_entry() {
    local inst_path="$1" title="$2" name="$3"
    mkdir -p "$HOME/.local/share/applications"
    local desktop_file="$HOME/.local/share/applications/$name"
    local real_icon="firefox"
    local icon_search_paths=(
        "$inst_path/browser/chrome/icons/default/default128.png"
        "$inst_path/chrome/icons/default/default128.png"
    )
    for p in "${icon_search_paths[@]}"; do
        if [[ -f "$p" ]]; then
            real_icon="$p"
            break
        fi
    done

    local wayland_opt=""
    [[ "$XDG_SESSION_TYPE" == "wayland" ]] && wayland_opt="MOZ_ENABLE_WAYLAND=1 "

    # Ярлык НЕ должен содержать --profile: Firefox сам откроет профиль из
    # installs.ini (Default= секции [Install<HASH>]), который инсталлер пиннит
    # на нашу установку. Жёсткий путь сломал бы профиль, пересозданный
    # пользователем через about:profiles / troubleshooting.
    local exec_base="env GTK_USE_PORTAL=1 ${wayland_opt}${inst_path}/firefox"

    local ru_new_window="Новое окно"
    local ru_new_tab="Новая вкладка"
    local ru_new_private="Новое приватное окно"
    local ru_prefs="Настройки"
    local ru_profiles="Менеджер профилей"

    cat <<EOF > "$desktop_file"
[Desktop Entry]
Actions=new-window;new-tab;new-private-window;preferences;profile-manager;
Categories=Network;WebBrowser;Browser
Comment=${title} Web Browser
Encoding=UTF-8
Exec=${exec_base} %u
GenericName=${title} Web Browser
Icon=${real_icon}
Name=${title}
Name[ru_RU]=${title}
NoDisplay=false
StartupNotify=true
StartupWMClass=firefox-myfox
Terminal=false
Type=Application
Version=1.0

[Desktop Action new-window]
Exec=${exec_base} --new-window
Icon=window-new-symbolic
Name=New Window
Name[ru_RU]=${ru_new_window}

[Desktop Action new-tab]
Exec=${exec_base} --new-tab about:newtab
Icon=tab-new-symbolic
Name=New Tab
Name[ru_RU]=${ru_new_tab}

[Desktop Action new-private-window]
Exec=${exec_base} --private-window
Icon=view-private-symbolic
Name=New Private Window
Name[ru_RU]=${ru_new_private}

[Desktop Action preferences]
Exec=${exec_base} --preferences
Icon=settings-configure-symbolic
Name=Preferences
Name[ru_RU]=${ru_prefs}

[Desktop Action profile-manager]
Exec=${exec_base} --ProfileManager
Icon=user-group-properties-symbolic
Name=Profile Manager
Name[ru_RU]=${ru_profiles}
EOF
    chmod +x "$desktop_file"

    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$HOME/.local/share/applications"
    elif command -v kbuildsycoca6 >/dev/null 2>&1; then
        kbuildsycoca6 >/dev/null 2>&1
    elif command -v kbuildsycoca5 >/dev/null 2>&1; then
        kbuildsycoca5 >/dev/null 2>&1
    fi

    success "Desktop entry created: ${desktop_file}"
}

firefox_remove_desktop_entry() {
    local desktop_file="$HOME/.local/share/applications/$MYFOX_DESKTOP_NAME"
    if [[ -f "$desktop_file" ]]; then
        rm -f "$desktop_file"
        success "Desktop entry removed: ${desktop_file}"
    fi
}