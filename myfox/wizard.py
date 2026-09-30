"""First-install wizard: welcome -> dir -> channel -> lang -> profile ->
tweaks -> theme -> summary, with Back.

TODO(pass 3): an explicit stack of screens (append on forward, pop on Back)
over the ui.Backend interface — replaces bin/myfox-core's install_wizard,
a step-string state machine driven by tui_choose_kv/tui_confirm return codes
0/1/3 meaning next/cancel/back. Not invoked as a `myfox` subcommand at all
(see docs/python-rewrite-plan.md: there's no `install` command) — only from
bootstrap.py's own "not installed yet" branch.
"""

from __future__ import annotations
