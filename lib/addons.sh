# shellcheck shell=bash
# addons.sh — загрузка и установка дополнений (XPI) из AMO.
#
# Механика (enterprise-путь Firefox, без плашки подтверждения sideload):
#   XPI скачивается со стабильного URL
#     https://addons.mozilla.org/firefox/downloads/latest/<slug>/addon-latest.xpi
#   и кладётся в <install_dir>/distribution/extensions/<addon-id>.xpi.
#   При старте Firefox (installDistributionAddons) копирует его в профиль и
#   ставит extensions.installedDistroAddon.<id>=true; новые версии обновляются,
#   повторно не переустанавливаются при той же версии.
#
# ID для имени файла берём из AMO API (guid): у тем без gecko.id в манифесте
# это единственный надёжный источник (GUID из сертификата подписи).
#
# Список дополнений по умолчанию:
#   ublock-origin          — adblock
#   google-chrome-dark     — тема Chrome Dark
#   plasma-integration     — интеграция с KDE Plasma (ставится только по запросу,
#                            причём только если сессия Plasma и стоит системный
#                            пакет plasma-browser-integration)
#
# Требуются common.sh, curl, python3.

# ─── Список дополнений по умолчанию ─────────────────────────────────────────

# uBlock Origin — ставится по умолчанию.
MYFOX_ADDON_UBLOCK="ublock-origin"

# Тема "Google Chrome Dark".
MYFOX_ADDON_THEME="google-chrome-dark"

# Интеграция с KDE Plasma (Native Messaging + Plasma Browser Integration).
MYFOX_ADDON_PLASMA="plasma-integration"

# ─── Детект KDE Plasma ───────────────────────────────────────────────────────

# Проверяет, работаем ли мы в сессии KDE Plasma.
# Возвращает 0 если да, 1 если нет.
addons_is_plasma() {
    if [[ "${XDG_CURRENT_DESKTOP:-}" =~ (^|:)KDE(;|:)|Plasma ]]; then
        return 0
    fi
    if [[ "${KDE_FULL_SESSION:-}" =~ true|1 ]]; then
        return 0
    fi
    return 1
}

# ─── Скачивание XPI ──────────────────────────────────────────────────────────

# addon_fetch <slug> <out-file> — скачивает latest XPI с AMO. Возвращает 0 при успехе.
addon_fetch() {
    local slug="$1" out="$2"
    local url="https://addons.mozilla.org/firefox/downloads/latest/${slug}/addon-latest.xpi"
    log "Fetching add-on: ${slug}"
    curl -L --fail --silent --show-error -o "$out" "$url" || return 1
    # XPI — это zip: заголовок должен начинаться с PK.
    if [[ $(head -c 2 "$out") != "PK" ]]; then
        warn "Downloaded file for '${slug}' is not a valid XPI — skipping."
        rm -f "$out"
        return 1
    fi
    return 0
}

# addon_guid <slug> — печатает guid (ID аддона) из AMO API. Пусто при ошибке.
addon_guid() {
    local slug="$1"
    curl -L --fail --silent --show-error \
        "https://addons.mozilla.org/api/v5/addons/addon/${slug}/" \
        | python3 -c 'import json,sys; print(json.load(sys.stdin).get("guid") or "")' 2>/dev/null || true
}

# ─── Системный пакет plasma-browser-integration ──────────────────────────────

# addons_pkg_installed — проверяет, установлен ли системный пакет
# plasma-browser-integration (native-messaging host). Возвращает 0 если есть.
addons_pkg_installed() {
    # Пакет ставит host-манифест в общий каталог.
    for host in \
        /usr/lib/mozilla/native-messaging-hosts/org.kde.plasma.browser_integration.json \
        /usr/lib64/mozilla/native-messaging-hosts/org.kde.plasma.browser_integration.json \
        /usr/local/lib/mozilla/native-messaging-hosts/org.kde.plasma.browser_integration.json; do
        if [[ -f "$host" ]]; then
            return 0
        fi
    done
    return 1
}

# addons_pkg_install — ставит системный пакет через sudo. Возвращает 0 при успехе.
addons_pkg_install() {
    warn "Installing system package 'plasma-browser-integration' (requires sudo)..."
    if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get install -y plasma-browser-integration
    elif command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y plasma-browser-integration
    elif command -v pacman >/dev/null 2>&1; then
        sudo pacman -S --noconfirm plasma-browser-integration
    elif command -v zypper >/dev/null 2>&1; then
        sudo zypper install -y plasma-browser-integration
    else
        warn "No supported package manager found. Install 'plasma-browser-integration' manually."
        return 1
    fi
}

# ─── Применение дополнений ───────────────────────────────────────────────────

# addons_apply <install_dir> <slug>... — скачивает XPI с AMO и кладёт
# в distribution/extensions/ браузера (тихая установка при следующем старте).
addons_apply() {
    local install_dir="$1"; shift
    local distro_dir="$install_dir/distribution/extensions"
    mkdir -p "$distro_dir"

    local slug out id
    for slug in "$@"; do
        id=$(addon_guid "$slug")
        if [[ -z "$id" ]]; then
            warn "Could not resolve add-on ID for '${slug}' — skipping."
            continue
        fi
        out=$(mktemp --suffix=.xpi)
        if ! addon_fetch "$slug" "$out"; then
            rm -f "$out"
            continue
        fi
        install -m 0644 "$out" "$distro_dir/$id.xpi"
        rm -f "$out"
        success "Installed ${slug} → distribution/extensions/${id}.xpi"
    done

    if [[ -z "$(ls -A "$distro_dir" 2>/dev/null)" ]]; then
        rmdir "$distro_dir" 2>/dev/null || true
        rmdir "$install_dir/distribution" 2>/dev/null || true
    fi
    return 0
}