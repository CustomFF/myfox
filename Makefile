# MyFox from a git clone.
#
#   make install [gui]                    install from this working copy (gui: in a window)
#   MYFOX_INSTALL=AUTO make install       no questions, the defaults
#   make refresh|reinstall|uninstall [gui]   the installed `myfox` command
#
# Once installed, `myfox` is the one place to update or remove MyFox; the
# targets below only call it.

GUI := $(if $(filter gui,$(MAKECMDGOALS)),--gui)
AUTO := $(if $(filter AUTO auto,$(MYFOX_INSTALL)),-y)

.PHONY: install refresh reinstall uninstall gui

install:
	@MYFOX_CORE_DIR="$(CURDIR)" python3 "$(CURDIR)/bootstrap.py" $(GUI) $(AUTO)

refresh reinstall uninstall:
	@m="$$HOME/.local/bin/myfox"; [ -x "$$m" ] || m=$$(command -v myfox); \
	if [ -n "$$m" ] && [ -x "$$m" ]; then exec "$$m" $@ $(GUI); fi; \
	case "$${LC_ALL:-$${LC_MESSAGES:-$$LANG}}" in \
	    ru*) echo "MyFox не установлен: make install" >&2 ;; \
	    *) echo "MyFox is not installed: make install" >&2 ;; \
	esac; \
	exit 1

# A modifier for the targets above, not a target of its own.
gui:
	@:
