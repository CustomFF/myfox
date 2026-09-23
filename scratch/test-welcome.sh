#!/usr/bin/env bash
# scratch/test-welcome.sh [height] — показывает ТОЛЬКО экран приветствия
# (лого + текст, dialog/whiptail), без установки/сети/тарбола/песочницы.
# Для быстрого визуального подбора высоты диалога.
#
# Usage:
#   scratch/test-welcome.sh          # высота по умолчанию (32)
#   scratch/test-welcome.sh 28       # конкретное значение
set -eo pipefail

MYFOX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export MYFOX_ROOT

# shellcheck source=lib/common.sh
. "$MYFOX_ROOT/lib/common.sh"
# shellcheck source=lib/i18n.sh
. "$MYFOX_ROOT/lib/i18n.sh"
i18n_load
# shellcheck source=lib/tui.sh
. "$MYFOX_ROOT/lib/tui.sh"

h="${1:-${MYFOX_WELCOME_HEIGHT:-32}}"

welcome_prompt="$(t wizard_welcome_text)"
if tui_logo_fits; then
    welcome_prompt="$(tui_print_logo)"$'\n\n'"$welcome_prompt"
else
    echo "(лого не влезает в текущий терминал — показан только текст)" >&2
fi

tui_confirm "$welcome_prompt" yes 0 \
    "$(t wizard_continue_label)" "$(t opt_cancel)" "$h"
echo "rc=$? (height=$h)"
