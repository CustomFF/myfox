"""First-install wizard: loads the install form and shows it the way the
session allows. The form's logic is one (install_form.InstallForm); --gui
only picks how it looks:

  --gui           dearpygui window
  tty             picotui dialog
  no tty          plain questions on stdin/stdout
  -y              no questions, defaults

Runs from bootstrap.py's "not installed yet" branch — there's no `install`
subcommand (see docs/python-rewrite-plan.md). For development:

    python3 -m myfox.wizard [--gui] [-y] [--dry-run]
"""

from __future__ import annotations

import argparse
import sys

from . import gui_deps, i18n
from .install_form import Answers, InstallForm, Installer, simulate_install
from .installer import install as real_install
from .ui import _has_tty


def run(gui: bool = False, noninteractive: bool = False, install: Installer = real_install) -> Answers | None:
    form = InstallForm.load()
    if noninteractive:
        from .ui import form_plain

        return form_plain.run(form, install, noninteractive=True)
    if gui:
        try:
            gui_deps.prepare()
            from .ui import form_gui
        except (ImportError, OSError, RuntimeError) as exc:
            print(i18n.t("err_gui_unavailable", exc), file=sys.stderr)
            return None
        return form_gui.run(form, install)
    if _has_tty():
        from .ui import form_tui

        return form_tui.run(form, install)
    from .ui import form_plain

    return form_plain.run(form, install)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="myfox-wizard")
    parser.add_argument("--gui", action="store_true", help="graphical window instead of the terminal")
    parser.add_argument("-y", "--yes", action="store_true", dest="noninteractive", help="no questions, defaults")
    parser.add_argument("--dry-run", action="store_true", help="show the install's stages without installing")
    args = parser.parse_args(argv)
    i18n.load()
    install = simulate_install if args.dry_run else real_install
    answers = run(gui=args.gui, noninteractive=args.noninteractive, install=install)
    if answers and answers.notes:
        if "myfox.ui.picotui_backend" in sys.modules:
            sys.modules["myfox.ui.picotui_backend"].end_screen()
        for note in answers.notes:
            print(note)
    return 0 if answers is not None else 1


if __name__ == "__main__":
    sys.exit(main())
