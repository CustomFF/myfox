# Makefile — для тех, кто работает с клоном репозитория (не curl|bash).
# TUI — dialog/whiptail (обычно уже в системе) с примитивным bash-фолбэком,
# ничего скачивать/готовить заранее не требуется.

SHELL := /usr/bin/env bash
ROOT  := $(CURDIR)
ARGS  ?=

.PHONY: install update uninstall

install:
	"$(ROOT)/bin/myfox-core" install $(ARGS)

update:
	"$(ROOT)/bin/myfox-core" update $(ARGS)

uninstall:
	"$(ROOT)/bin/myfox-core" uninstall $(ARGS)
