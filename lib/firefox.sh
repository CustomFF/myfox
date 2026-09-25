# shellcheck shell=bash
# firefox.sh — тарбол Firefox с download.mozilla.org, версия, языки, desktop entry.
# Требует common.sh, i18n.sh, tui.sh. Только curl/tar/awk — без python3/jq.

# ─── Локализация Firefox и архитектура ──────────────────────────────────────

# Полная локаль (LANG) → код языка Firefox (download.mozilla.org &lang=<code>).
firefox_detect_lang() {
    local lang base
    lang="${LANG:-en_US.UTF-8}"
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

# amd64→linux64, arm64→linux-aarch64. 32-бит не поддерживается (myfox_arch падает).
firefox_detect_arch() {
    case "$(myfox_arch)" in
        amd64) echo "linux64" ;;
        arm64) echo "linux-aarch64" ;;
    esac
}

# ─── Версия установленного Firefox ──────────────────────────────────────────

firefox_local_version() {
    local inst_path="$1" ver=""
    if [[ -f "$inst_path/application.ini" ]]; then
        ver=$(awk -F= '/^Version=/{print $2; exit}' "$inst_path/application.ini")
    fi
    [[ -n "$ver" ]] && echo "$ver"
    return 0
}

# Состояние целевого каталога установки: ours|foreign|empty.
# install_dir_validate <path> → rc 0: stdout = нормализованный абсолютный путь;
# rc 1: stdout = текст ошибки для пользователя. Ничего не создаёт.
install_dir_validate() {
    local p="$1"
    p="${p#"${p%%[![:space:]]*}"}"
    p="${p%"${p##*[![:space:]]}"}"
    if [[ -z "$p" ]]; then t err_installdir_empty; return 1; fi
    [[ "$p" == "~" || "$p" == "~/"* ]] && p="$HOME${p#\~}"
    if [[ "$p" != /* ]]; then t err_installdir_relative "$p"; return 1; fi
    while [[ "$p" == */ && "$p" != "/" ]]; do p="${p%/}"; done
    if [[ "$p" == "/" ]]; then t err_installdir_root; return 1; fi
    if [[ -e "$p" ]]; then
        if [[ ! -d "$p" ]]; then t err_installdir_not_dir "$p"; return 1; fi
        if [[ ! -w "$p" || ! -x "$p" ]]; then t err_installdir_not_writable "$p"; return 1; fi
        if [[ -n "$(ls -A "$p" 2>/dev/null)" ]] && ! is_myfox_dir "$p"; then
            t err_installdir_foreign "$p"; return 1
        fi
    else
        local parent="$p"
        while [[ ! -e "$parent" ]]; do
            parent="${parent%/*}"
            [[ -z "$parent" ]] && parent="/"
        done
        if [[ ! -d "$parent" || ! -w "$parent" || ! -x "$parent" ]]; then
            t err_installdir_cannot_create "$parent"
            return 1
        fi
    fi
    printf '%s' "$p"
}

firefox_dir_claim_state() {
    local dir="$1"
    if [[ -f "$dir/application.ini" ]] && is_myfox_dir "$dir"; then
        echo ours
    elif [[ -d "$dir" && -n "$(ls -A "$dir" 2>/dev/null)" ]]; then
        is_myfox_dir "$dir" && echo ours || echo foreign
    else
        echo empty
    fi
}

# ─── Каталог языков Mozilla (product-details.mozilla.org) ───────────────────

MYFOX_LANG_JSON="${MYFOX_LANG_JSON:-}"

firefox_fetch_lang_json() {
    if [[ -z "$MYFOX_LANG_JSON" ]]; then
        MYFOX_LANG_JSON=$(mktemp --suffix=.myfox-languages.json)
        if ! curl -L --fail --silent --show-error --connect-timeout 10 --max-time 30 \
            -o "$MYFOX_LANG_JSON" "https://product-details.mozilla.org/1.0/languages.json"; then
            rm -f "$MYFOX_LANG_JSON"
            MYFOX_LANG_JSON=""
            return 1
        fi
    fi
    echo "$MYFOX_LANG_JSON"
}

# <json-file> → stdout: "code\tEnglish name" по одному на строку. Формат ответа:
# {"code":{"English":"Name","native":"..."}, ...} — плоский, парсим одним awk без jq/python3.
firefox_lang_catalog_awk() {
    awk '
        BEGIN { RS="\034" }
        {
            s = $0
            while (match(s, /"[A-Za-z_-]+"[[:space:]]*:[[:space:]]*\{[[:space:]]*"English"[[:space:]]*:[[:space:]]*"[^"]*"/)) {
                entry = substr(s, RSTART, RLENGTH)
                s = substr(s, RSTART + RLENGTH)
                n = split(entry, p, "\"")
                print p[2] "\t" p[6]
            }
        }
    ' "$1"
}

firefox_list_languages() {
    local cache
    cache=$(firefox_fetch_lang_json) || { error "$(t err_lang_fetch)"; return 1; }
    firefox_lang_catalog_awk "$cache" | LC_ALL=C sort | awk -F'\t' '{ printf "%s  %s\n", $1, $2 }' >&2
}

firefox_validate_lang() {
    local code="$1" cache
    cache=$(firefox_fetch_lang_json) || return 1
    # Без exit в теле правила: под set -o pipefail ранний exit оборвал бы
    # верхнюю часть пайпа (SIGPIPE) и уронил бы вызывающий скрипт.
    firefox_lang_catalog_awk "$cache" | awk -F'\t' -v c="$code" '$1==c{f=1} END{exit !f}'
}

# Синхронно строит список языков в MYFOX_LANG_LIST (переиспользуется между вызовами).
firefox_prepare_lang_list() {
    [[ -s "${MYFOX_LANG_LIST:-}" ]] && return 0
    local cache
    cache=$(firefox_fetch_lang_json) || return 1
    MYFOX_LANG_LIST=$(mktemp --suffix=.myfox-langlist)
    # LC_ALL=C: a locale-aware collation (e.g. the user's own ru_RU.UTF-8)
    # reorders plain-ASCII English names in ways that look scrambled to
    # someone expecting plain alphabetical order — force byte-order sort
    # regardless of the installer's own runtime locale. -t explicit: names
    # can contain spaces ("Chinese (Simplified)"), only the tab is a field
    # boundary.
    firefox_lang_catalog_awk "$cache" | LC_ALL=C sort -t $'\t' -k2 > "$MYFOX_LANG_LIST"
    if [[ ! -s "$MYFOX_LANG_LIST" ]]; then
        rm -f "$MYFOX_LANG_LIST"
        MYFOX_LANG_LIST=""
        return 1
    fi
}

MYFOX_LANG_LIST="${MYFOX_LANG_LIST:-}"

# Интерактивный выбор языка Firefox (первая установка). stdout: код. rc 1 = отмена.
firefox_interactive_lang() {  # [back:0|1]
    local back="${1:-0}"
    local default_lang list code
    default_lang=$(firefox_detect_lang)

    if [[ ! -t 0 ]]; then
        echo "$default_lang"
        return 0
    fi

    if [[ -s "${MYFOX_LANG_LIST:-}" ]]; then
        list="$MYFOX_LANG_LIST"
    elif firefox_prepare_lang_list; then
        list="$MYFOX_LANG_LIST"
    else
        error "$(t err_lang_fetch)"
        return 1
    fi

    # dialog/whiptail's single-keypress jump-to-item matches against what's
    # actually visible — with --no-tags that's the label text, which used
    # to start with the ISO code ("rw       Kinyarwanda"). Sorted by
    # English name, pressing 'r' would jump to any *code* starting with
    # 'r', landing somewhere with a totally different first letter than
    # what's on screen (reported: 'r' jumped to "rw" Kinyarwanda, sorted
    # among the K's, nowhere near "Russian"). Put the name first in the
    # label so the visible text and the jump target agree. The tag (the
    # actual return value, never shown) is the name too, so it also comes
    # back in a form we can use directly — except for the handful of codes
    # that share an English name (several Serbian script variants etc.),
    # disambiguated with a NUL-separated code suffix so tags stay unique
    # without changing what's typed to jump to them.
    local -a kv=()
    local -A name_count=()
    local c n
    while IFS=$'\t' read -r c n; do
        [[ -z "$c" ]] && continue
        name_count["$n"]=$(( ${name_count["$n"]:-0} + 1 ))
    done < "$list"

    local default_tag=""
    while IFS=$'\t' read -r c n; do
        [[ -z "$c" ]] && continue
        local tag="$n"
        [[ "${name_count[$n]}" -gt 1 ]] && tag="$n"$'\x01'"$c"
        [[ "$c" == "$default_lang" ]] && default_tag="$tag"
        kv+=("$tag" "$(printf '%-30s %s' "$n" "$c")")
    done < "$list"

    local rc=0 selected
    selected=$(tui_filter_kv "$(t lang_pick_header)" "$default_tag" "$back" "${kv[@]}") || rc=$?
    if [[ "$rc" -eq 0 ]]; then
        if [[ "$selected" == *$'\x01'* ]]; then
            code="${selected##*$'\x01'}"
        else
            code=$(awk -F'\t' -v n="$selected" '$2 == n { print $1; exit }' "$list")
        fi
    fi
    [[ "$list" != "$MYFOX_LANG_LIST" ]] && rm -f "$list"
    [[ "$rc" -eq 0 ]] && { echo "$code"; return 0; }
    return "$rc"
}

# Без -v (на тарболе Firefox — тысячи имён файлов, шум, не прогресс).
# Никакого процентного прогресса тут больше не нужно — вызывающий код
# оборачивает это в tui_spin, который сам показывает, что работа идёт.
_extract_tarball() {  # <archive> <install_dir>
    local archive="$1" install_dir="$2"
    # Mozilla's .tar.xz is a multi-block xz stream, so `xz -T0` (xz >= 5.4)
    # decompresses the blocks on all cores — ~3x faster than tar -J's single
    # thread (18s -> 6s on 8 cores). Older xz just ignores the parallelism.
    if command -v xz >/dev/null 2>&1; then
        xz -dc -T0 "$archive" | tar -x -C "$install_dir" --strip-components=1
    else
        tar -xJf "$archive" -C "$install_dir" --strip-components=1
    fi
}

# ─── Установка из тарбола ───────────────────────────────────────────────────

firefox_install_tarball() {
    local install_dir="$1" lang_override="${2:-}" channel="${3:-stable}"
    local lang arch url dl_archive effective_url remote_ver

    lang="${lang_override:-$(firefox_detect_lang)}"
    arch=$(firefox_detect_arch) || error "$(t err_unsupported_arch)"

    local product="firefox-latest-ssl" channel_tag=""
    if [[ "$channel" == "beta" ]]; then
        product="firefox-beta-latest-ssl"
        channel_tag=" ($(t channel_beta))"
    fi
    url="https://download.mozilla.org/?product=${product}&os=${arch}&lang=${lang}"

    log "$(t checking_latest)"
    effective_url=$(curl -sIL --connect-timeout 10 --max-time 30 -o /dev/null -w '%{url_effective}' "$url")
    [[ -n "$effective_url" ]] || error "$(t err_resolve_url)"

    if [[ "$arch" == "linux-aarch64" ]]; then
        effective_url="${effective_url/linux-x86_64/linux-aarch64}"
    fi

    remote_ver=$(printf '%s' "$effective_url" \
        | awk 'match($0, /firefox-[^\/]+\.tar/){print substr($0, RSTART+8, RLENGTH-12)}')
    [[ -n "$remote_ver" ]] || remote_ver="unknown"

    tui_style "$(t firefox_banner "$remote_ver" "$channel_tag" "$lang" "$install_dir")"

    if [[ -z "${MYFOX_NONINTERACTIVE:-}" && -z "${MYFOX_SKIP_CONFIRM:-}" ]] \
        && ! tui_confirm "$(t confirm_proceed)"; then
        echo "$(t cancelled)" >&2
        return 2
    fi

    mkdir -p "$install_dir"
    dl_archive=$(mktemp "${TMPDIR:-/tmp}/moz_dl_XXXXXX.tar.xz")
    trap 'rm -f "$dl_archive"' INT

    # --silent: curl's own progress bar would fight tui_spin's spinner for
    # the same terminal line — one indicator per step, always the spinner.
    if ! tui_spin "$(t downloading_firefox)" -- \
        curl -L --fail --silent --show-error --retry 1 -o "$dl_archive" "$effective_url"; then
        rm -f "$dl_archive"; trap - INT
        error "$(t err_download_failed)"
    fi

    if ! tui_spin "$(t extracting_firefox)" -- \
        _extract_tarball "$dl_archive" "$install_dir"; then
        rm -f "$dl_archive"; trap - INT
        error "$(t err_extract_failed)"
    fi

    rm -f "$dl_archive"
    trap - INT

    echo "$remote_ver" > "$install_dir/.myfox-version"
    success "$(t firefox_installed "$remote_ver")"
    echo "$remote_ver"
}

# ─── Desktop entry ──────────────────────────────────────────────────────────

firefox_create_desktop_entry() {
    local inst_path="$1" title="$2" name="$3"
    mkdir -p "$HOME/.local/share/applications"
    local desktop_file="$HOME/.local/share/applications/$name"
    local real_icon="firefox"
    local p
    for p in "$inst_path/browser/chrome/icons/default/default128.png" \
             "$inst_path/chrome/icons/default/default128.png"; do
        [[ -f "$p" ]] && { real_icon="$p"; break; }
    done

    # Без --profile: Firefox сам откроет профиль из Default= секции [Install<HASH>]
    # (пиннинг делает profile_pin_install) — жёсткий путь сломал бы пересозданный профиль.
    # GTK_USE_PORTAL=1 намеренно НЕ ставим: xdg-desktop-portal не умеет
    # нормально проверять/устанавливать default-браузер (mozilla bug 1516290,
    # "keeps asking for being set as default browser when GTK_USE_PORTAL=1 is
    # set") — Firefox 99+ сам отключает mime-портал для не-sandboxed сборок,
    # а этот флаг в Exec= принудительно включает обратно сломанное поведение.
    # MOZ_ENABLE_WAYLAND тоже не форсим: с Firefox 121 Wayland-бэкенд включается
    # автоопределением сессии сам, без переменной.
    #
    # Exec= указывает на wrapper-скрипт, а не на бинарник firefox напрямую и не
    # на `env VAR=... firefox` — чтобы одновременно:
    # 1) не сломать определение "браузер по умолчанию": Firefox ищет свой .desktop
    #    по первому токену Exec=, резолвит его через g_find_program_in_path и
    #    сравнивает с собственным путём (browser/components/shell/nsGNOMEShellService.cpp,
    #    KeyMatchesAppName) — «env» первым токеном ломает это сравнение;
    #    MOZ_APP_LAUNCHER=<путь до самого wrapper'а> заставляет Firefox считать
    #    «собой» путь wrapper'а, который совпадает с первым токеном Exec=;
    # 2) отличать WM_CLASS/app_id нашей сборки от системного Firefox (иначе они
    #    группируются в панели задач и берут одну иконку/значок) —
    #    MOZ_APP_REMOTINGNAME меняет GTK prgname, от которого зависит WM_CLASS/
    #    app_id окна; должно совпадать со StartupWMClass= ниже.
    local wrapper_path="${inst_path}/firefox-myfox"
    cat <<WRAPEOF > "$wrapper_path"
#!/bin/sh
export MOZ_APP_LAUNCHER="$wrapper_path"
export MOZ_APP_REMOTINGNAME="firefox-myfox"
exec "${inst_path}/firefox" "\$@"
WRAPEOF
    chmod +x "$wrapper_path"
    local exec_base="$wrapper_path"

    cat <<EOF > "$desktop_file"
[Desktop Entry]
Actions=new-window;new-tab;new-private-window;preferences;profile-manager;
Categories=Network;WebBrowser;Browser
Comment=${title} Web Browser
Encoding=UTF-8
Exec=${exec_base} %u
GenericName=${title} Web Browser
Icon=${real_icon}
MimeType=video/webm;text/html;image/png;image/jpeg;image/gif;application/xml;application/xhtml+xml;application/x-xpinstall;application/rss+xml;application/rdf+xml;application/pdf;application/xhtml_xml;image/webp;text/xml;x-scheme-handler/http;x-scheme-handler/https;
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
Name[ru_RU]=Новое окно

[Desktop Action new-tab]
Exec=${exec_base} --new-tab about:newtab
Icon=tab-new-symbolic
Name=New Tab
Name[ru_RU]=Новая вкладка

[Desktop Action new-private-window]
Exec=${exec_base} --private-window
Icon=view-private-symbolic
Name=New Private Window
Name[ru_RU]=Новое приватное окно

[Desktop Action preferences]
Exec=${exec_base} --preferences
Icon=settings-configure-symbolic
Name=Preferences
Name[ru_RU]=Настройки

[Desktop Action profile-manager]
Exec=${exec_base} --ProfileManager
Icon=user-group-properties-symbolic
Name=Profile Manager
Name[ru_RU]=Менеджер профилей
EOF
    chmod +x "$desktop_file"

    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$HOME/.local/share/applications"
    elif command -v kbuildsycoca6 >/dev/null 2>&1; then
        kbuildsycoca6 >/dev/null 2>&1
    elif command -v kbuildsycoca5 >/dev/null 2>&1; then
        kbuildsycoca5 >/dev/null 2>&1
    fi

    success "$(t desktop_entry_created "$desktop_file")"
}

firefox_remove_desktop_entry() {
    local desktop_file="$HOME/.local/share/applications/$MYFOX_DESKTOP_NAME"
    if [[ -f "$desktop_file" ]]; then
        rm -f "$desktop_file"
        success "$(t desktop_entry_removed "$desktop_file")"
    fi
}
