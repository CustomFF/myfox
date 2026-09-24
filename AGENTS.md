# AGENTS.md — правила для агентов (ИИ-ассистентов)

Этот файл задаёт правила и контекст для любой автоматизации/ИИ-агента, работающего с репозиторием **myfox**.

## Обзор проекта

MyFox — набор твиков для Firefox и инсталлер. Основная идея:

1. **install.sh** скачивает Firefox (stable или beta) с `download.mozilla.org` (тарбол) в каталог по умолчанию `~/.local/share/firefox` (или `--prefix <path>`) и применяет на него твики myfox.
2. **Твики** — в двух местах:
   - **`autoconfig/`** — `autoconfig.js` в `defaults/pref/` (включает Autoconfig: `general.config.filename=firefox.cfg`) и сам `firefox.cfg` в корне установки. Это **privileged JS, исполняется Firefox** при каждом старте: регистрирует `agent_overrides.css` как `AGENT_SHEET`, патчит sidebar/downloads, ставит префы и закладки.
   - **`chrome/`** — CSS: `userChrome.css` (user-sheet) и `agent_overrides.css` (agent-sheet).
3. **Кросс-инсталляция и изоляция профилей (важная идея)**: твики и аддоны применяются ТОЛЬКО к профилю с маркером `<profile>/.myfox` (или fallback `chrome/agent_overrides.css`) внутри инсталляции с флагом `install_dir/.myfox-installed`. Чужой/новый профиль в той же инсталляции — это немодифицированный Firefox (firefox.cfg бросает исключение до любых твиков). Аддоны ставятся пер-профильно в `<profile>/extensions/`, а не в `distribution/` — иначе попали бы во все профили.
   **Инвариант «профиль-локальность»**: НИКАКИХ глобальных настроек инсталляции (`distribution/policies.json` не ставится, политики не используются) — весь код и все префы живут в профиле (prefs.js, `chrome/`, `extensions/`). Удалил профиль → кристально чистый ванильный Firefox. Всё профиль-специфичное пишет только `firefox.cfg` под guard-ом.
4. **Букмарклеты** — не часть этого репозитория и НЕ сабмодуль (ранее был, удалён). Это отдельный проект **ddblm** (`/home/daydve/development/ddblm`); myfox только копирует его готовые твики: `docs/blm_panel.css` → `<profile>/chrome/blm_panel.css` и ВСЕ `icons/*.svg` → `<profile>/chrome/panel-icons/`.

## Структура

```
myfox/
├── autoconfig/       # autoconfig.js + firefox.cfg (privileged JS со всей логикой твиков)
├── chrome/           # userChrome.css + agent_overrides.css
├── lib/              # bash-библиотеки (подключаются через . "$MYFOX_ROOT/lib/*.sh")
│   ├── common.sh     # логирование (stderr), state/opts (install.json), confirm, TUI-хелперы
│   ├── firefox.sh    # тарбол: arch/lang, скачивание (curl), версия, desktop entry, выбор языка
│   ├── profile.sh    # profiles.ini/installs.ini, пиннинг [Install<HASH>], создание профилей
│   ├── apply.sh      # autoconfig/chrome, букмарклеты (ddblm)
│   └── addons.sh     # XPI с AMO в <profile>/extensions/ (uBlock, тема, plasma)
├── install.sh        # главный инсталлер (моды: install / --update / --reinstall / --browser-only)
├── uninstall.sh      # деинсталлятор
├── scratch/          # dev-инструменты: sandbox.sh (безопасный тест), hot-reload python-скрипты
├── docs/logic.md     # архитектура
├── tests/README.md   # ручные чек-листы (автотестов нет)
└── AGENTS.md, README.md, README.ru.md
```

## Как работает инсталлер

### Режимы (взаимоисключающие)
- Без режима при сохранённом state → интерактивное меню «1) Update tweaks · 2) Reinstall · 3) Quit»; с `-y` → автоматически `update`.
- `--update` — только твики из сохранённого state (браузер/профиль не трогаются); `--lang`/`--profile` с ним НЕсовместимы (ошибка).
- `--browser-only` — только тарбол + desktop entry, без профиля/твиков/аддонов (Firefox потом сам заведёт dedicated-профиль).
- `--reinstall` — перекачать браузер и переприменить всё (занятая чужая директория заменяется начисто, без бэкапа).

### Маркер (state) и opts
- State: `$XDG_STATE_HOME/myfox/install.json` (по умолч. `~/.local/state/myfox/install.json`): `install_dir`, `firefox_version`, `profile_dir`, `install_hash`, `installed_at` + объект **`opts`** `{browser_only, lang, bl, addons, plasma}` (сохранённые выборы, переиспользуются при --update/повторных запусках; старые маркеры без opts подставляют дефолты).
- `state_set`/`opts_set` при существующем файле требуют **jq или python3**; `state_get` простых строк имеет grep-fallback без них. `--update`/`profiles` и т.п. полагаются на `opts`.
- Флаг `install_dir/.myfox-installed` отличает «нашу» инсталляцию от чужой по тому же пути.

### Профиль
- `lib/profile.sh` ищет `profiles.ini` в `~/.mozilla/firefox`, flatpak, snap. Store — **общий** с обычным Firefox: правим ТОЛЬКО секции под нашу установку.
- **Не-деструктивность (критично)**: инсталлер добавляет/переключает исключительно `[Install<HASH>] Default=<наш профиль>` и `[ProfileN] Name=myfox`. Чужие `[Install<HASH>]`, `[ProfileN]`, `Default=1` и каталоги не трогать. Новый `[ProfileN]` нумеруется `max+1`, а не `grep -c`.
- **`-y`/неинтерактив: чужой профиль НЕ трогать никогда** — только создать новый `myfox-N` (`Name=myfox`, путь `myfox-<N>`). Использовать чужой профиль можно лишь явным `--profile <path>` (переопределяет всё). В интерактивном режиме можно спросить «использовать существующий?».
- Пиннинг `[Install<HASH>]` (FF 67+): HASH самому не считать — один раз гоняем инсталляцию headless (`--screenshot about:blank`, таймаут 180с), Firefox сам пишет секцию; после прогона **автоматически вычищается мусорный профиль** (каталог + `[ProfileN]`), который Firefox создаёт для своего first-run (см. `_profile_purge_headless_strays`); fallback — детерминированный hash на чистом HOME или единственная существующая `[Install...]`. Пишется и в `profiles.ini`, и в `installs.ini`.

### Мастер (wizard) установки
- Первая полная установка на интерактивном tty при наличии `dialog`/`whiptail` запускает мастер: welcome → lang → профиль (tweaked **или clean** — чистый профиль без твиков и маркера) → букмарклеты → stable/beta. Результаты: `TWEAKED_PROFILE`, `BL_ON`, `CHANNEL`, `MYFOX_SKIP_CONFIRM`. Без tty/без `-y` — последовательный поток.
- **Установка — финальный шаг мастера, а не отдельный поток.** Шаг `version` (кнопка Install) НЕ выходит из alt-экрана: ставит `MYFOX_WIZARD_INSTALL=1` и возвращает управление. `run_full` открывает `dialog --gauge` (`lib/common.sh`: `gauge_open`/`gauge_set`/`gauge_close`/`gauge_spin`), гонит по этапам проценты (download → extract → profile → pin → tweaks → bl → addons) и в конце `_wizard_finish` закрывает gauge, делает `tui_reset` и печатает `print_summary` УЖЕ на обычном экране (сводка остаётся видимой). EXIT-trap `_wizard_trap_cleanup` снимает alt-экран при ошибке.
  - Протокол GNU dialog `--gauge`: `XXX\n<pct>\n<текст>\nXXX` (не пустая строка!); whiptail понимает только голое число. dialog/whiptail рисуют в **stdout**, поэтому `gauge_open` направляет их вывод на `/dev/tty`, а FIFO открывает в режиме read-write (`<>`) — не блокируется и не даёт EOF после кадра.
- Инварианты TUI (не ломать):
  - каталог языков качается синхронно ДО входа в alt-экран (`firefox_prepare_lang_list`/`MYFOX_LANG_LIST`) — между диалогами мастера не должно быть **ни одной сетевой операции**, иначе экраны мигают;
  - `dialog` сам рвёт alt-экран на каждый вызов; это гасят флагом `use_ui_terminfo_noalt` (копия terminfo без smcup/rmcup через infocmp+tic, кэш в `~/.cache/myfox/terminfo`) и единой парой `tui_enter`/`tui_reset` на весь мастер (флаг `MYFOX_TUI_FENCED`, снимается только в `_wizard_finish`/`_wizard_trap_cleanup`). Всё пишется в `/dev/tty`.
- Выбор языка (`firefox_detect_lang`) маппит `LANG` → коды Mozilla; интерактив через dialog/whiptail/scrollable bash-меню/промпт-fallback. У dialog/whiptail нет встроенного поиска — пункт «Search / filter…» в меню открывает `--inputbox`, по подстроке (код/English-название, регистронезависимо) список сужается; при активном фильтре Enter выбирает первый результат; в bash-меню поиск — клавиша `/`. Источник языков — сеть: `product-details.mozilla.org/1.0/languages.json`.

### Твики и префы (autoconfig/firefox.cfg)
- **Guard профиля** в самом начале firefox.cfg: нет `<profile>/.myfox` и нет `chrome/agent_overrides.css` → `throw`; дальше по блоку ничего не исполняется. Не обходить и не выносить логику за него.
- Префы включаются блоками-одноразовиками с guard-префами: `myfox.corePreferencesInitialized`, `sidebar.launcherAboveSidebar.initialized`. **Guards срабатывают один раз**: изменил преф внутри блока — на существующем профиле НЕ переприменится, пока не сбросишь guard (about:config). Не добавляй эти префы в `user.js` и не дублируй.
- Всё, что пользователь может менять штатно (тема, закладки и т.п.), применяется **не более одного раза** на профиль под собственным guard-префом (`myfox.themeApplied`, `myfox.galleryBookmarkAdded`) и никогда не перезаписывает уже сделанный выбор пользователя при последующих запусках. Тема Google Chrome Dark ставится только если активна тема по умолчанию. Исключение — пункт «Загрузки» в `sidebar.main.tools`: он возвращается всегда (на нём держится наша панель загрузок).
- `distribution/policies.json` **не ставится** — политики глобальны для инсталляции и нарушают инвариант профиль-локальности. Кнопка «Импорт закладок» (ранее гасилась политикой `DisableProfileImport`) убирается в `firefox.cfg` профиль-локально (виджет `import-button`).

### Аддоны (lib/addons.sh)
- Пер-профильно: по AMO-слагу `addon_guid` тянет guid через API (`addons.mozilla.org/api/v5`), XPI кладётся в `<profile>/extensions/<guid>.xpi` — при первом старте профиля ставится тихо (важно: `extensions.autoDisableScopes=0` defaultPref в firefox.cfg). Требует curl + python3.
- uBlock + Google Chrome Dark — по умолчанию; KDE Plasma integration — ставится молча вместе с твиками в сессии Plasma или при `--plasma-integration` (`--noplasma` гасит). Аддон требует системный пакет `plasma-browser-integration` (native host): инсталлер проверяет его наличие и, если пакета нет, печатает заметку с командой установки в конце (никаких sudo-промптов в разрыв диалогов).
- Плазменный аддон в `profile/extensions` регистрируется по `plasma-browser-integration@kde.org`.

### Букмарклеты (bl)
- Опционально; по умолчанию вопрос, `--nobl` отключает, `opts.bl` запоминается.
- `apply_bookmarklets()` копирует `docs/blm_panel.css` → `<profile>/chrome/blm_panel.css` и иконки → `panel-icons/`. Источник: `MYFOX_DDBLM_LOCAL=<dir>` (локально, для отладки твиков) либо raw.githubusercontent.com (`DayDve/ddblm`, ветка master). Если raw 404 — предупреждение и пропуск (не падать).
- Галерея ddblm двуязычная (EN по умолчанию, RU по `?lang=ru`, язык — клиентским JS). В `firefox.cfg` закладка «Добавить букмарклеты» для русскоязычного Firefox ставится на `https://daydve.github.io/ddblm/?lang=ru`, иначе на базовый URL; при миграции с base-URL закладка не дублируется, а переносится (`pu.bookmarks.update`).
- Термин «blm» в myfox не используется — только «bl»/букмарклеты (имя файла `blm_panel.css` сохранено как в ddblm).

## Правила для агентов

1. **Язык**: код, комментарии и этот файл — русский (по умолчанию). README основной — английский + `README.ru.md`.
2. **Не дублировать**: mozinst.sh уже адаптирован в `lib/firefox.sh`; менеджер букмарклетов живёт в ddblm — myfox только копирует готовые твики. Новую логику навески на системный Firefox в install.sh не добавляй без явной просьбы (есть только README-инструкция).
3. **`set -eo pipefail`** активен (без `-u`). Функции возвращают значения через stdout, а логирование (log/success/warn/error) уходит в **stderr** — из командных подстановок stderr не захватывать; вызовы функций в `$(...)`, которые могут вернуть ненулевой код, оборачивать `|| true`.
4. **Изменения твиков**: `firefox.cfg` и CSS исполняются в privileged-контексте Firefox — правь аккуратно, соблюдай guards (см. выше). Изменённый преф внутри guard-блока на существующем профиле не переприменится без сброса guard.
5. **Не коммить**: `Office.conf`, бэкапы, state-маркеры, файлы ddblm (правим/копируем их при тесте твиков), сгенерированные артефакты. ddblm не сабмодуль.
6. **Тесты**: автотестов нет — ручные чек-листы в `tests/README.md`. Минимум перед сдачей:
   - `bash -n install.sh uninstall.sh lib/*.sh`
   - `shellcheck -S error install.sh uninstall.sh lib/*.sh`
   - `python3 -m py_compile scratch/*.py` (если трогали dev-скрипты)
7. **Не трогай чужие файлы**: `clone`-версии (вроде `~/dev/myfox`) не изменяй — правь только копию проекта, над которой работаешь.
8. **Осторожно с реальной установкой**: install.sh качает большие тарболы и может менять `~/.mozilla`/профили/desktop entry. Лучший способ теста — песочница: `scratch/sandbox.sh <dir> [--fresh] -- ./install.sh -y ...` (изолирует HOME и все XDG, см. шапку скрипта). Без неё — `--prefix /tmp/...` + `-y`. Реальный профиль пользователя не трогай.

## Справочник команд

```
./install.sh                         # полная установка; если уже есть state — меню (update/reinstall/quit)
./install.sh --update                # только твики из saved state
./install.sh --reinstall             # перекачать браузер + применить всё
./install.sh --browser-only          # только тарбол + desktop entry
./install.sh --prefix /tmp/ff        # кастомный путь установки
./install.sh --profile <path>        # явный профиль (переопределяет всё)
./install.sh --lang de               # язык Firefox (см. --list-languages)
./install.sh --list-languages        # коды языков Mozilla (в stderr), exit 0
./install.sh --nobl                  # без букмарклет-твиков
./install.sh --noaddons              # без дополнений (uBlock, тема)
./install.sh --plasma-integration    # принудительно поставить plasma-integration
./install.sh --noplasma              # не ставить plasma-integration даже под Plasma
./install.sh -y                      # неинтерактивно
./install.sh -v                      # подробный вывод
./uninstall.sh [-y]                  # снять твики; для созданного профиля — вопрос об удалении целиком

MYFOX_DDBLM_LOCAL=/path/to/ddblm ./install.sh ...   # тест букмарклет-твиков из локальной копии ddblm
scratch/sandbox.sh /tmp/mf -- ./install.sh -y ...   # полностью изолированный тест инсталлера
MYFOX_DEBUG=1 ./install.sh ...                      # тайминги мастера в ~/.local/state/myfox/debug.log
```