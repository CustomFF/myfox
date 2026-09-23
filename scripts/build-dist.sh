#!/usr/bin/env bash
# build-dist.sh [out-dir] — собирает myfox-dist.tar.gz: bin/myfox-core,
# bin/myfox-launcher (копия get.sh), lib/, i18n/, autoconfig/, chrome/, assets/.
# Плюс кладёт РЯДОМ с тарболом отдельный get.sh (то, что реально раздаётся
# по публичному URL) — ЭТА ЖЕ функция патчит DIST_URL в ОБЕИХ копиях get.sh
# (публичной и той, что внутри тарбола становится ~/.local/bin/myfox) одним
# и тем же значением MYFOX_DIST_URL, если оно задано в окружении — раньше
# патчилась только раздаваемая копия (в dev-serve.sh), а установленный
# лауничер внутри тарбола оставался с заглушкой example.invalid, из-за чего
# `myfox update`/`myfox uninstall` после первой установки не могли
# докачаться до локального dev-сервера.
#
# Используется локально (dev-serve.sh) и (в будущем) сборкой в CI. Тарбол
# имеет один верхнеуровневый каталог — get.sh распаковывает его с
# --strip-components=1, как GitHub-архивы. Никаких внешних бинарников не
# качаем — TUI на dialog/whiptail (обычно уже есть в системе) с примитивным
# bash-фолбэком, см. lib/tui.sh.
set -eo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-$ROOT/dist}"
STAGE_NAME="myfox-dist"
STAGE="$OUT_DIR/$STAGE_NAME"

rm -rf "$STAGE"
mkdir -p "$STAGE/bin"

# get.sh — одна функция копирования для обеих копий (публичной и внутри
# тарбола), гарантированно с одинаковым DIST_URL.
_install_get_sh() {  # <dest>
    if [[ -n "${MYFOX_DIST_URL:-}" ]]; then
        sed "s#https://example.invalid/myfox-dist.tar.gz#${MYFOX_DIST_URL}#" \
            "$ROOT/get.sh" > "$1"
        chmod +x "$1"
    else
        install -m 0755 "$ROOT/get.sh" "$1"
    fi
}

install -m 0755 "$ROOT/bin/myfox-core" "$STAGE/bin/myfox-core"
_install_get_sh "$STAGE/bin/myfox-launcher"
_install_get_sh "$OUT_DIR/get.sh"
cp -a "$ROOT/lib" "$STAGE/lib"
cp -a "$ROOT/i18n" "$STAGE/i18n"
cp -a "$ROOT/autoconfig" "$STAGE/autoconfig"
cp -a "$ROOT/chrome" "$STAGE/chrome"
cp -a "$ROOT/assets" "$STAGE/assets"

tar -C "$OUT_DIR" -czf "$OUT_DIR/myfox-dist.tar.gz" "$STAGE_NAME"
rm -rf "$STAGE"
echo "build-dist: $OUT_DIR/myfox-dist.tar.gz" >&2
