# AGENTS.md — правила для агентов (ИИ-ассистентов)

Этот файл задаёт правила и контекст для любой автоматизации/ИИ-агента, работающего с репозиторием **myfox**.

## Обзор проекта

MyFox — набор твиков для Firefox и инсталлер. Основная идея:

1. **install.sh** скачивает последний стабильный Firefox напрямую с `download.mozilla.org` (тарбол) в каталог по умолчанию `~/.local/share/firefox` (или `--prefix <path>`) и применяет на него твики myfox.
2. **Твики** — три части:
   - **`autoconfig/`** — включение Autoconfig (`autoconfig.js` в `defaults/pref/`) и сам твик-скрипт `firefox.cfg` (privileged JS: регистрирует `agent_overrides.css` как `AGENT_SHEET`, патчит sidebar/downloads, ставит нужные префы).
   - **`chrome/`** — CSS: `userChrome.css` (user-sheet) и `agent_overrides.css` (agent-sheet, регистрируется firefox.cfg).
   - **Префы** — выставляются самим `firefox.cfg` (block «corePreferencesInitialized»).
3. **Букмарклеты** — НЕ часть этого репозитория и НЕ сабмодуль. Это отдельный проект **ddblm**, живущий в отдельном каталоге `/home/daydve/development/ddblm`. Пользователю myfox НЕ нужно самостоятельно генерировать букмарклеты — он только **добавляет готовые** из галереи и подтягивает для них соответствующие твики (CSS) и значки. Твики берутся из `docs/blm_panel.css` и ВСЕХ `icons/*.svg` проекта ddblm.
   **Источник твиков**: обычно raw.githubusercontent.com (из запушенного ddblm); для тестирования задаём локальный каталог через `MYFOX_DDBLM_LOCAL=/home/daydve/development/ddblm ./install.sh ...` — тогда файлы копируются из него напрямую. Пока сообщаем `--nobl`/вопрос вручную; автоматизация в install.sh разрешена и работает через обе ветки (локально/raw).

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
│   └── apply.sh      # применение autoconfig/chrome + букмарклеты
├── install.sh        # главный инсталлер
├── uninstall.sh      # деинсталлер
├── scratch/          # dev-инструменты (RDP hot-reload и пр.)
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
- Профильный store — **общий** с обычным Firefox (как задумано у Mozilla: все установки делят один `profiles.ini`/`installs.ini`, у каждой — своя секция `[Install<HASH>]`). «Свои ini» для myfox НЕ реализуемы без env-костылей: перенос store через `XDG_CONFIG_HOME` ломает окружение (GTK/dconf/fontconfig) и к тому же игнорируется, если `~/.mozilla/firefox` уже существует. Поэтому правим **только** секции под нашу установку.
- **Не-деструктивность (критично)**: инсталлер добавляет/переключает исключительно `[Install<HASH>] Default=<наш профиль>` и `[ProfileN] Name=myfox`. Чужие `[Install<HASH>]`, `[ProfileN]`, `Default=1` и каталоги профилей не трогать, не переименовывать, не удалять. Новый `[ProfileN]` нумеруется как `max+1`, а не `grep -c`.
- Первый запуск (интерактивный): если найден профиль, который подтянется инсталляцией — спросить «использовать существующий или создать новый?» (рекомендуется новый); если нет — создать новый (`Name=myfox`, путь `myfox-N`).
- **`-y`/неинтерактивный: чужой профиль НЕ трогать никогда** — только создать новый `myfox-N`. Спросить нельзя, поэтому автоматического захвата чужого `default-release` быть не должно. Использовать чужой профиль можно лишь явным `--profile <path>`.
- `--profile <path>` переопределяет всё.

### Букмарклеты (bl)
- Твики букмарклетов применяются опционально. По умолчанию инсталлер спрашивает; флаг `--nobl` отключает.
- ddblm — отдельный проект (`/home/daydve/development/ddblm`), **НЕ сабмодуль**.
- `apply_bookmarklets()` копирует из ddblm `docs/blm_panel.css` → `chrome/blm_panel.css` и ВСЕ `icons/*.svg` → `chrome/panel-icons/`. Источник: локальный каталог (`MYFOX_DDBLM_LOCAL`) при наличии, иначе raw github. Термин «blm» в myfox НЕ используется (blm = «bookmarklet manager», а у нас не менеджер) — только «bl»/букмарклеты; имя файла `blm_panel.css` сохранено как в ddblm.

## Правила для агентов

1. **Язык**: по умолчанию код, комментарии и этот AGENTS.md — **русский** (комментарии можно и по-русски, и по-английски, но предпочтителен русский). README основной — английский, плюс `README.ru.md`.
2. **Не дублировать**: НЕ копируй тупо `mozinst.sh` или менеджер букмарклетов ddblm. Их идеи уже адаптированы:
   - mozinst → `lib/firefox.sh` (только Firefox, без Thunderbird, интегрировано с маркером).
   - blm (менеджер букмарклетов) → живёт в ddblm как отдельный проект; myfox только копирует его готовые твики.
3. **Изменения твиков**: `autoconfig/firefox.cfg` и CSS правь аккуратно — они исполняются в privileged-контексте Firefox. Префы для включения твиков ставятся блоками-одноразовиками в `firefox.cfg` (`myfox.corePreferencesInitialized`, `sidebar.main.tools.downloadsInitialized`, `sidebar.launcherAboveSidebar.initialized`) — не добавляй их в `user.js` и не дублируй. Guards срабатывают только раз: изменил преф внутри блока — на существующем профиле он НЕ переприменится, пока не сбросишь guard преф (about:config или удалить преф).
4. **Твики привязаны к профилю**: firefox.cfg в самом начале проверяет, что профиль «наш» — маркер `<profile>/.myfox` (ставит `apply_chrome`) или fallback `chrome/agent_overrides.css` (старые установки без маркера). Если ни того, ни другого нет — firefox.cfg выбрасывает исключение и **ничего** не применяет (ни префы, ни CSS, ни твики окна). Это сделано, чтобы новый чистый профиль выглядел как немодифицированный Firefox. При добавлении новых твиков не обходи этот guard и не выноси логику применения за него.
4. **`set -eo pipefail`** в скриптах активен (без `-u`). При работе с командными подстановками от функций (возврат значения через stdout) всегда обертывай вызовы `|| true` там, где функции могут вернуть ненулевой код, а логирование (log/success/warn/error) уже уходит в **stderr** — не перехватывай его в переменные.
5. **Не коммить**: `Office.conf`, любые бэкапы, маркеры, файлы ddblm (правим/копируем их при тесте твиков), сгенерированные `docs/` из ddblm.
6. **Тесты**: автоматической тест-инфраструктуры нет — только ручные чек-листы в `tests/README.md`. Минимум перед сдачей:
   - `bash -n install.sh uninstall.sh lib/*.sh`
   - `shellcheck -S error install.sh uninstall.sh lib/*.sh`
   - `python3 -m py_compile scratch/*.py` (если трогали dev-скрипты)
7. **Не трогай чужие файлы**: `clone`-версии (вроде `~/dev/myfox`) — не изменяй; правь только копию проекта, над которой работаешь.
8. **Осторожно с реальной установкой**: `install.sh` может качать большие тарболы и изменять профиль пользователя. При тестах используй `--prefix /tmp/...` и неинтерактивные `-y`.

## Справочник команд

```
./install.sh                    # тарбол + твики (+ вопрос про букмарклеты)
./install.sh --prefix /tmp/ff   # кастомный путь
./install.sh --reinstall        # перекачать браузер
./install.sh --profile <path>   # явный профиль
./install.sh --nobl             # без букмарклет-твиков
./install.sh --noaddons         # без дополнений (uBlock, тема)
./install.sh --plasma-integration  # принудительно ставить plasma-integration (и без вопроса)
./install.sh --noplasma         # не ставить plasma-integration даже под Plasma
./install.sh -y                 # без подтверждений
./uninstall.sh [-y]             # удаление твиков (+восстановление бэкапа при наличии)
```