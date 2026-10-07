# Makefile — the installed commands run straight from a working copy
# (python3 -m myfox <cmd>); they act on the real MyFox install, so use the
# sandbox (scratch/sandbox.sh) while developing.

ROOT := $(CURDIR)
ARGS ?=

.PHONY: refresh reinstall uninstall

refresh:
	cd "$(ROOT)" && python3 -m myfox refresh $(ARGS)

reinstall:
	cd "$(ROOT)" && python3 -m myfox reinstall $(ARGS)

uninstall:
	cd "$(ROOT)" && python3 -m myfox uninstall $(ARGS)

