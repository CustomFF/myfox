# shellcheck shell=bash
# firefox.sh — адаптация идей mozinst.sh, only Firefox (Release).
# Скачивание тарбола Firefox с download.mozilla.org, определение версии,
# desktop entry. Интегрирован с маркером myfox (не «сырой» порт).
#
# Требуется common.sh (переменные/функции).

# ─── Локализация и архитектура ──────────────────────────────────────────────

firefox_detect_lang() {
    case "${LANG:-en_US.UTF-8}" in
        ru_*) echo "ru" ;;
        *)    echo "en-US" ;;
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

# ─── Скачивание ─────────────────────────────────────────────────────────────

firefox_download_archive() {
    local url="$1" out="$2"
    if command -v aria2c >/dev/null 2>&1; then
        # aria2c трактует -o как имя относительно CWD (в отличие от curl -o),
        # поэтому передаём каталог и имя отдельно. mktemp уже создал пустой
        # target-файл, а aria2c по умолчанию не перезаписывает существующий файл
        # (пишет в *.1) — поэтому нужен allow-overwrite=true.
        aria2c -x16 -j16 --allow-overwrite=true --console-log-level=notice --summary-interval=0 \
            --dir "$(dirname "$out")" -o "$(basename "$out")" "$url" 1>&2
    else
        curl -L --progress-bar -o "$out" "$url"
    fi
}

# ─── Установка из тарбола ───────────────────────────────────────────────────
#
# firefox_install_tarball <install_dir>
#   - резолвит download.mozilla.org URL (arch+lang)
#   - скачивает, распаковывает начисто в install_dir
#   - пишет .myfox-installed-version метаданные
#   - при прерывании (INT) — останавливается (tar-транзакция не атомарна, но
#     повторные запуски перекачивают/дораспаковывают; корректность гарантирует --reinstall)
firefox_install_tarball() {
    local install_dir="$1"
    local lang arch url dl_archive effective_url remote_ver

    lang=$(firefox_detect_lang)
    arch=$(firefox_detect_arch)

    # aarch64: Mozilla отдаёт linux-x86_64 для linux64; на aarch64 нужен linux-aarch64.
    # resolve URL и подмена.
    url="https://download.mozilla.org/?product=firefox-latest-ssl&os=${arch}&lang=${lang}"

    log "Checking for the latest Firefox..."

    effective_url=$(curl -sIL -o /dev/null -w "%{url_effective}" "$url")
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
    echo -e "${BOLD}Firefox${NC}" >&2
    echo "  Version:  ${GREEN}${remote_ver}${NC}" >&2
    echo "  Language: ${lang}" >&2
    echo "  Target:   ${install_dir}" >&2
    echo "" >&2

    if [[ -z $MYFOX_NONINTERACTIVE ]] && ! confirm "Proceed with installation?"; then
        echo "Cancelled." >&2
        exit 0
    fi

    mkdir -p "$install_dir"

    log "Downloading..."
    dl_archive=$(mktemp "/tmp/moz_dl_XXXXXX.tar.xz")
    trap 'rm -f "$dl_archive"' INT

    if ! firefox_download_archive "$effective_url" "$dl_archive"; then
        rm -f "$dl_archive"
        trap - INT
        error "Download failed."
    fi

    log "Extracting..."
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
    [[ -f "$desktop_file" ]] && rm -f "$desktop_file" && success "Desktop entry removed: ${desktop_file}"
}