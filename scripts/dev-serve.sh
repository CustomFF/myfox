#!/usr/bin/env bash
# dev-serve.sh [port] — dev-инструмент, НЕ часть продукта: собирает
# myfox-dist.tar.gz и раздаёт его локальным HTTP-сервером, чтобы обкатать
# curl|bash полностью офлайн-эквивалентно, без публикации в GitHub.
# python3 тут — только приёмный http.server моей стороны разработки.
set -eo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${1:-8787}"
OUT_DIR="$ROOT/dist"

# MYFOX_DIST_URL — build-dist.sh патчит ОБЕ копии get.sh (раздаваемую и ту,
# что внутри тарбола станет ~/.local/bin/myfox) одним и тем же локальным
# адресом, так что `myfox update`/`myfox uninstall` после первой установки
# тоже бьют сюда, а не в заглушку example.invalid.
export MYFOX_DIST_URL="http://127.0.0.1:${PORT}/myfox-dist.tar.gz"
"$ROOT/scripts/build-dist.sh" "$OUT_DIR"

echo "" >&2
echo "dev-serve: serving $OUT_DIR on http://127.0.0.1:${PORT}/ (Ctrl-C to stop)" >&2
echo "" >&2
echo "Real curl|bash test — exactly what a real user would type, no env vars" >&2
echo "(run in a sandboxed HOME, see scratch/sandbox.sh):" >&2
echo "  curl -fsSL http://127.0.0.1:${PORT}/get.sh | bash" >&2
echo "  curl -fsSL http://127.0.0.1:${PORT}/get.sh | bash -s -- uninstall" >&2
echo "  curl -fsSL http://127.0.0.1:${PORT}/get.sh | bash -s -- -y --lang ru --nobl --noaddons" >&2
echo "" >&2

cd "$OUT_DIR"
exec python3 -m http.server "$PORT"
