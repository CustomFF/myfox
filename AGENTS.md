# AGENTS.md — правила для агентов (ИИ-ассистентов)

Этот файл задаёт правила и контекст для любой автоматизации/ИИ-агента, работающего с репозиторием **myfox**.

## Обзор проекта

MyFox — набор твиков для Firefox и инсталлер. Основная идея:

1. **install.sh** скачивает последний стабильный Firefox напрямую с `download.mozilla.org` (тарбол) в каталог по умолчанию `~/.local/share/firefox` (или `--prefix <path>`) и применяет на него твики myfox.
2. **Твики** — три части:
   - **`autoconfig/`** — включение Autoconfig (`autoconfig.js` в `defaults/pref/`) и сам твик-скрипт `firefox.cfg` (privileged JS: регистрирует `agent_overrides.css` как `AGENT_SHEET`, патчит sidebar/downloads, ставит нужные префы).
   - **`chrome/`** — CSS: `userChrome.css` (user-sheet) и `agent_overrides.css` (agent-sheet, регистрируется firefox.cfg).
   - **Префы** — выставляются самим `firefox.cfg` (block «corePreferencesInitialized»).
3. **Букмарклеты** — НЕ часть этого репозитория. Это отдельный репозиторий **ddbml**, подключаемый как **git submodule** в `bookmarklets/`. Инсталлер лишь опционально дёргает его (`blm build` + `blm patchff`) для твиков букмарклетов.

Навеска на уже установленный (системный) Firefox НЕ реализована в скриптах — только инструкция в README (секция «Applying to an existing Firefox»). Не добавляй логику навески в install.sh без явной просьбы (YAGNI).

## Структура

```
myfox/
├── autoconfig/       # autoconfig.js + firefox.cfg (твики)
├── chrome/           # userChrome.css + agent_overrides.css
├── lib/              # bash-библиотеки
│   ├── common.sh     # логирование, маркер (state), helpers
│   ├── firefox.sh    # тарбол: arch/lang, скачивание, версия, desktop entry
│   ├── profile.sh    # детекция/создание профилей
│   └── apply.sh      # применение autoconfig/chrome + blm
├── install.sh        # главный инсталлер
├── uninstall.sh      # деинсталлер
├── scratch/          # dev-инструменты (RDP hot-reload и пр.)
├── bookmarklets/     # submodule → ddbml (не коммитится напрямую)
├── docs/             # логика, скриншоты
├── tests/            # тест-план
└── AGENTS.md, README.md, README.ru.md
```

## Как работает инсталлер

### Маркер установки (state)
Инсталлер хранит записи в `$XDG_STATE_HOME/myfox/install.json` (по умолчанию `~/.local/state/myfox/install.json`):
`install_dir`, `firefox_version`, `profile_dir`, `backup_dir`, `installed_at`. Запись/чтение маркера требуют `jq` или `python3` (без них `state_set` падает).

- Внутри инсталляционного каталога лежит файл-флаг `install_dir/.myfox-installed` — отличает «нашу» инсталляцию от чужой (поставленной вручную по тому же пути).
- Повторный запуск `install.sh`:
  - если `install_dir` существует И содержит `.myfox-installed` → не качает браузер, только обновляет твики;
  - если `install_dir` существует, но `.myfox-installed` нет → предупреждение, **бэкап всей директории**, установка начисто, путь бэкапа пишется в `backup_dir`;
  - профиль берётся из `profile_dir` в маркере (если существует), при первом запуске — детекция/создание (см. profile.sh).

### Профиль
- `lib/profile.sh` ищет `profiles.ini` в `~/.mozilla/firefox`, flatpak, snap.
- Первый запуск: если найден профиль, который подтянется инсталляцией — спросить «использовать существующий или создать новый?» (рекомендуется новый); если нет — создать новый (`Name=myfox`, путь `myfox-N`).
- `--profile <path>` переопределяет всё.

### blm (букмарклеты)
- Твики букмарклетов применяются опционально. По умолчанию инсталлер спрашивает; флаг `--noblm` отключает.
- Для работы нужен submodule: `git submodule update --init --recursive`.
- `apply_bookmarklets()` вызывает `blm build` и `blm patchff` — blm **сам** управляет профилем (пишет `~/.config/blm/config.json`).

## Правила для агентов

1. **Язык**: по умолчанию код, комментарии и этот AGENTS.md — **русский** (комментарии можно и по-русски, и по-английски, но предпочтителен русский). README основной — английский, плюс `README.ru.md`.
2. **Не дублировать**: НЕ копируй тупо `mozinst.sh` или `blm`. Их идеи уже адаптированы:
   - mozinst → `lib/firefox.sh` (только Firefox, без Thunderbird, интегрировано с маркером).
   - blm → живёт в ddbml и вызывается как внешний инструмент.
3. **Изменения твиков**: `autoconfig/firefox.cfg` и CSS правь аккуратно — они исполняются в privileged-контексте Firefox. Префы для включения твиков ставятся блоками-одноразовиками в `firefox.cfg` (`myfox.corePreferencesInitialized`, `sidebar.main.tools.downloadsInitialized`, `sidebar.launcherAboveSidebar.initialized`) — не добавляй их в `user.js` и не дублируй. Guards срабатывают только раз: изменил преф внутри блока — на существующем профиле он НЕ переприменится, пока не сбросишь guard преф (about:config или удалить преф).
4. **`set -eo pipefail`** в скриптах активен (без `-u`). При работе с командными подстановками от функций (возврат значения через stdout) всегда обертывай вызовы `|| true` там, где функции могут вернуть ненулевой код, а логирование (log/success/warn/error) уже уходит в **stderr** — не перехватывай его в переменные.
5. **Не коммить**: `Office.conf`, любые бэкапы, маркеры, содержимое `bookmarklets/` (это submodule), сгенерированные `docs/` из ddbml.
6. **Тесты**: автоматической тест-инфраструктуры нет — только ручные чек-листы в `tests/README.md`. Минимум перед сдачей:
   - `bash -n install.sh uninstall.sh lib/*.sh`
   - `shellcheck -S error install.sh uninstall.sh lib/*.sh`
   - `python3 -m py_compile scratch/*.py` (если трогали dev-скрипты)
7. **Не трогай чужие файлы**: `clone`-версии (вроде `~/dev/myfox`) — не изменяй; правь только копию проекта, над которой работаешь.
8. **Осторожно с реальной установкой**: `install.sh` может качать большие тарболы и изменять профиль пользователя. При тестах используй `--prefix /tmp/...` и неинтерактивные `-y`.

## Справочник команд

```
./install.sh                    # тарбол + твики (+ вопрос про blm)
./install.sh --prefix /tmp/ff   # кастомный путь
./install.sh --reinstall        # перекачать браузер
./install.sh --profile <path>   # явный профиль
./install.sh --noblm            # без букмарклет-твиков
./install.sh -y                 # без подтверждений
./uninstall.sh [-y]             # удаление твиков (+восстановление бэкапа при наличии)
```