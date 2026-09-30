# Makefile — для тех, кто работает с клоном репозитория (не curl|bash).
# Идёт переход на Python (docs/python-rewrite-plan.md) — цели ниже дёргают
# новый python3 -m myfox прямо из рабочей копии, без сборки архивов (та
# нужна только для настоящего релиза). `install` пока недоступна: мастер
# первой установки живёт в bootstrap.py (проход 5), которого ещё нет —
# см. план.

ROOT := $(CURDIR)
ARGS ?=

.PHONY: refresh reinstall uninstall

refresh:
	cd "$(ROOT)" && python3 -m myfox refresh $(ARGS)

reinstall:
	cd "$(ROOT)" && python3 -m myfox reinstall $(ARGS)

uninstall:
	cd "$(ROOT)" && python3 -m myfox uninstall $(ARGS)
