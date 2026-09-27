# shellcheck shell=bash
# addons.sh — загрузка и установка дополнений (XPI) из AMO, пер-профильно
# (<profile_dir>/extensions/<addon-id>.xpi — Firefox ставит их тихо при первом
# старте профиля). Требует common.sh, i18n.sh. Только curl+awk, без python3.

MYFOX_ADDON_THEME_DARK="google-chrome-dark"
MYFOX_ADDON_THEME_LIGHT="google-chrome-light"
MYFOX_ADDON_PLASMA="plasma-integration"

# ─── Детект KDE Plasma ────────────────────────────────────────────────────────

addons_is_plasma() {
    [[ "${XDG_CURRENT_DESKTOP:-}" =~ (^|:)KDE(\;|:|$)|(^|:)Plasma(\;|:|$) ]] && return 0
    [[ "${KDE_FULL_SESSION:-}" =~ true|1 ]] && return 0
    return 1
}

# ─── AMO ─────────────────────────────────────────────────────────────────────

# addon_fetch <slug> <out-file> — тянет latest XPI. XPI — это zip: проверяем "PK".
addon_fetch() {
    local slug="$1" out="$2"
    local url="https://addons.mozilla.org/firefox/downloads/latest/${slug}/addon-latest.xpi"
    # No log() here on purpose — addons_apply's caller wraps the whole
    # batch in one tui_spin; a log() line per addon would each print with
    # a newline mid-animation, breaking the spinner's one-line redraw.
    curl -L --fail --silent --show-error -o "$out" "$url" || return 1
    if [[ "$(head -c 2 "$out")" != "PK" ]]; then
        warn "$(t warn_addon_invalid "$slug")"
        rm -f "$out"
        return 1
    fi
    return 0
}

# addon_guid <slug> → guid (ID аддона) из AMO API v5. Плоский JSON — один awk.
addon_guid() {
    local slug="$1"
    curl -L --fail --silent --show-error \
        "https://addons.mozilla.org/api/v5/addons/addon/${slug}/" 2>/dev/null \
        | awk '
            match($0, /"guid"[[:space:]]*:[[:space:]]*"[^"]*"/) {
                s = substr($0, RSTART, RLENGTH)
                sub(/^"guid"[[:space:]]*:[[:space:]]*"/, "", s)
                sub(/"$/, "", s)
                print s
                exit
            }
        '
}

# ─── Системный пакет plasma-browser-integration (native-messaging host) ─────

# Dirs searched for the native-messaging-host manifest. Overridable via
# MYFOX_NMH_DIRS (colon-separated) so this can be tested with the package
# "missing" without actually uninstalling it — production runs never set
# that var, so the real fixed list below is what always applies.
addons_pkg_installed() {
    local dirs="${MYFOX_NMH_DIRS:-/usr/lib/mozilla/native-messaging-hosts:/usr/lib64/mozilla/native-messaging-hosts:/usr/local/lib/mozilla/native-messaging-hosts}"
    local dir
    local IFS=:
    for dir in $dirs; do
        [[ -f "$dir/org.kde.plasma.browser_integration.json" ]] && return 0
    done
    return 1
}

addons_pkg_suggest() {
    if command -v apt-get >/dev/null 2>&1; then
        echo "sudo apt install plasma-browser-integration"
    elif command -v dnf >/dev/null 2>&1; then
        echo "sudo dnf install plasma-browser-integration"
    elif command -v pacman >/dev/null 2>&1; then
        echo "sudo pacman -S plasma-browser-integration"
    elif command -v zypper >/dev/null 2>&1; then
        echo "sudo zypper install plasma-browser-integration"
    fi
}

# ─── Применение ───────────────────────────────────────────────────────────────

addons_apply() {  # <profile_dir> <slug>...
    local profile_dir="$1"; shift
    local addon_dir="$profile_dir/extensions"
    mkdir -p "$addon_dir"

    local slug out id
    for slug in "$@"; do
        id=$(addon_guid "$slug")
        if [[ -z "$id" ]]; then
            warn "$(t warn_addon_guid_unresolved "$slug")"
            continue
        fi
        out=$(mktemp --suffix=.xpi)
        if ! addon_fetch "$slug" "$out"; then
            rm -f "$out"
            continue
        fi
        install -m 0644 "$out" "$addon_dir/$id.xpi"
        rm -f "$out"
    done

    [[ -z "$(ls -A "$addon_dir" 2>/dev/null)" ]] && rmdir "$addon_dir" 2>/dev/null
    return 0
}
