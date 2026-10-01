# AGENTS.md — правила для агентов (ИИ-ассистентов)

Этот файл задаёт правила и контекст для любой автоматизации/ИИ-агента, работающего с репозиторием **myfox**.
Английская сводка команд и архитектуры — в `CLAUDE.md`; подробности потоков — в `docs/logic.md`.

## Обзор проекта

MyFox — набор твиков для Firefox и инсталлер. Основная идея:

1. **Инсталлер** скачивает Firefox (stable или beta) с `download.mozilla.org` (тарбол) в `~/.local/share/firefox` (или `--prefix <path>`) и применяет на него твики myfox. Публичный вход — `get.sh` (bootstrap `curl … | bash` и установленный лаунчер `myfox`); вся логика — в `bin/myfox-core`.
2. **Твики** — в двух местах:
   - **`autoconfig/`** — `autoconfig.js` в `defaults/pref/` (включает Autoconfig: `general.config.filename=myfox.cfg`) и `myfox.cfg` в корне установки — загрузчик: проверяет профиль и подгружает модули `<install>/myfox/*.js` (из `autoconfig/myfox/`, порядок по имени файла, через `resource://myfox/`). Это **privileged JS, исполняется Firefox** при каждом старте; модули: регистрирует все `chrome/agent/*.css` как `AGENT_SHEET`, патчит sidebar (панели «Загрузки» и «Расширения»), ставит префы, закладки, включает выбранную тему.
   - **`chrome/`** — CSS: `userChrome.css` (user-sheet, только `@import user/*.css`), `user/*.css` и `agent/*.css` (agent-sheets, порядок каскада — по имени файла, отсюда числовые префиксы).
3. **Кросс-инсталляция и изоляция профилей (важная идея)**: твики и аддоны применяются ТОЛЬКО к профилю с маркером `<profile>/.myfox` внутри инсталляции с флагом `install_dir/.myfox-installed` (legacy-условия «есть `agent_overrides.css`» больше нет). Чужой/новый профиль в той же инсталляции — немодифицированный Firefox (myfox.cfg бросает исключение до любых твиков). Аддоны ставятся пер-профильно в `<profile>/extensions/`, а не в `distribution/` — иначе попали бы во все профили.
   **Инвариант «профиль-локальность»**: НИКАКИХ глобальных настроек инсталляции (`distribution/policies.json` не ставится, политики не используются) — весь код и все префы живут в профиле (prefs.js, `chrome/`, `extensions/`, `user.js`). Удалил профиль → кристально чистый ванильный Firefox. Всё профиль-специфичное пишет только `myfox.cfg` под guard-ом.
4. **Букмарклеты** — не часть этого репозитория и НЕ сабмодуль. Это отдельный проект **ddblm** (`/home/daydve/development/ddblm`); myfox только копирует его готовые твики: `docs/blm_panel.css` → `<profile>/chrome/blm_panel.css` и ВСЕ `icons/*.svg` → `<profile>/chrome/panel-icons/`.

## Структура

```
myfox/
├── get.sh            # bootstrap (curl|bash) и установленный лаунчер (~/.local/bin/myfox → …/share/myfox/bin/myfox)
├── bin/myfox-core    # диспетчер install/update/uninstall/help: main() первой, main "$@" последней
├── lib/              # bash-библиотеки (подключаются из bin/myfox-core)
│   ├── common.sh     # пути, cprintf/логи (stderr), state (плоский key=value) и opts_*, check_deps
│   ├── i18n.sh       # t() и загрузка каталога; каталоги — i18n/en.sh (база), i18n/ru.sh (поверх)
│   ├── tui.sh        # dialog/whiptail-обёртки + bash-фолбэк, tui_spin, alt-экран
│   ├── firefox.sh    # тарбол: arch/lang, скачивание (curl), версия, desktop entry + wrapper firefox-myfox
│   ├── profile.sh    # profiles.ini/installs.ini, пиннинг [Install<HASH>], создание профилей
│   ├── apply.sh      # autoconfig/chrome, тема (user.js), букмарклеты (ddblm)
│   └── addons.sh     # XPI с AMO в <profile>/extensions/ (две темы, plasma), детект Plasma
├── autoconfig/       # autoconfig.js + myfox.cfg (загрузчик) + myfox/*.js (модули privileged JS с логикой твиков)
├── chrome/           # userChrome.css (импорты) + user/*.css + agent/*.css
├── i18n/             # каталоги сообщений интерфейса инсталлера
├── assets/           # logo.txt для приветствия мастера
├── scripts/          # build-dist.sh (сборка дистрибутива), dev-serve.sh (локальная раздача)
├── scratch/          # dev-инструменты: sandbox.sh (безопасный тест), reload_userchrome.py, test-welcome.sh
├── Makefile          # make install/update/uninstall ARGS="…" для работы из клона
├── docs/             # logic.md (архитектура), refactor-plan.md (план и статус рефакторинга)
├── tests/README.md   # ручные чек-листы (автотестов нет)
└── AGENTS.md, CLAUDE.md, README.md, README.ru.md
```

## Как работает инсталлер

### Команды и флаги
- Подкоманды `bin/myfox-core`: `install` (по умолчанию), `update`, `uninstall`, `help [cmd]`. Публично: `myfox` (статус+справка), `myfox browser|ff [args]` (запуск через `<install>/firefox-myfox`), `myfox update|uninstall|help`.
- Флаги разбираются по таблицам `INSTALL_OPTS`/`UPDATE_OPTS`/`UNINSTALL_OPTS` + `GLOBAL_OPTS` в начале `bin/myfox-core`; принимаются `--flag value` и `--flag=value`. Чужой для подкоманды флаг — ошибка. Новый флаг = строка в таблице + ключ `usage_*` в `i18n/*.sh` + строка в `usage()`.
- `--reinstall`/`--browser-only` взаимоисключающие. `--browser-only` — только тарбол + ярлык (без профиля/твиков). Канал stable/beta выбирается только в мастере (иначе stable).

### State и opts
- `$XDG_STATE_HOME/myfox/state` (по умолч. `~/.local/state/myfox/state`) — плоский `key=value`: `install_dir`, `profile_dir`, `firefox_version`, `install_hash`, `installed_at` и `opt_*` (`browser_only`, `lang`, `channel`, `bl`, `theme`, `plasma`). `state_get`/`state_set`/`opts_get`/`opts_set` в `lib/common.sh`; без jq/python. Дефолты — `opts_default`.
- Флаг `install_dir/.myfox-installed` отличает «нашу» инсталляцию от чужой по тому же пути. Чужой непустой каталог инсталлер не трогает (ошибка).

### Единый каталог и лаунчер
- Всё, что нужно `myfox-core` офлайн (`bin/myfox`, `bin/myfox-core`, `lib/`, `i18n/`, `assets/`), лежит в `$MYFOX_SHARE_DIR` (`~/.local/share/myfox`); `~/.local/bin/myfox` — симлинк. `install_launcher` сносит и наполняет каталог заново; `uninstall` удаляет симлинк только если он резолвится в наш каталог. Пути — переменные в `lib/common.sh`.

### Профиль
- `lib/profile.sh` ищет `profiles.ini` в `~/.mozilla/firefox` (легаси) или, если этого каталога нет, в `$XDG_CONFIG_HOME/mozilla/firefox` (Firefox 147+ на свежей системе), плюс flatpak/snap — см. `profile_native_dir()` (повторяет правило самого Firefox). Store — **общий** с обычным Firefox: правим ТОЛЬКО секции под нашу установку.
- **Не-деструктивность (критично)**: инсталлер добавляет/переключает исключительно `[Install<HASH>] Default=<наш профиль>` и `[ProfileN] Name=myfox`. Чужие `[Install<HASH>]`, `[ProfileN]`, `Default=1` и каталоги не трогать. Новый `[ProfileN]` нумеруется `max+1`, а не `grep -c`.
- **`-y`/неинтерактив: чужой профиль НЕ трогать никогда** — только создать новый `myfox-N`. Использовать чужой профиль можно лишь явным `--profile <path>`. Мастер показывает только свои `myfox-*` профили (включая «сиротские» каталоги с `.myfox-created`).
- Пиннинг `[Install<HASH>]` (FF 67+): HASH самому не считать — один раз гоняем инсталляцию headless (`--screenshot about:blank`, таймаут 180с), Firefox сам пишет секцию; после прогона **автоматически вычищается мусорный профиль** (каталог + `[ProfileN]`) first-run (`_profile_purge_headless_strays`); fallback — hash на чистом HOME или единственная существующая `[Install…]`. Пишется и в `profiles.ini`, и в `installs.ini`.

### Мастер установки
- Первая полная установка на интерактивном tty: приветствие → каталог → канал → язык → профиль (пропускается, если своих профилей нет) → твики (да/нет) → оформление (только при «да») → сводка. «Назад» везде, кроме первого шага (`GOING_BACK` — чтобы шаги-проходники не отскакивали вперёд). Результат: `LANG_CODE`, `CHANNEL`, `TWEAKED_PROFILE`, `WIZ_PROFILE(_NEW)`, `WIZ_THEME`. Без tty/с `-y` — без мастера.
- Букмарклеты отдельно НЕ спрашиваются (входят в «твики: да») — поэтому и в сводке отдельной строки нет.
- Инварианты TUI (не ломать): каталог языков качается ДО входа в alt-экран (`firefox_prepare_lang_list`/`MYFOX_LANG_LIST`) — между диалогами мастера **ни одной сетевой операции**, иначе экраны мигают; `dialog` сам рвёт alt-экран на каждый вызов, это гасят копией terminfo без smcup/rmcup (`_tui_terminfo_noalt`, кэш `~/.cache/myfox/terminfo`) и единой парой `tui_enter`/`tui_leave` на всю сессию (`tui_session_begin`/`_end`, `MYFOX_TUI_FENCED`). Долгие шаги — `tui_spin` (не gauge).
- Выбор языка (`firefox_detect_lang`) маппит `LANG` → коды Mozilla; список — из сети (`product-details.mozilla.org/1.0/languages.json`), фильтр по подстроке. `--lang` заодно выбирает язык интерфейса инсталлера.

### Темы и аддоны
- `lib/addons.sh`: по AMO-слагу `addon_guid` тянет guid через API, `addon_fetch` кладёт XPI в `<profile>/extensions/<guid>.xpi` (Firefox ставит при первом старте; нужен `extensions.autoDisableScopes=0` defaultPref в `myfox.cfg`). Зависимости — curl + awk. Сейчас так ставится только Plasma-интеграция.
- Обе темы — наш собственный форк (`themes/`, цвета скопированы у прежних AMO-тем Stylefox `google-chrome-dark`/`-light`, подписаны через AMO unlisted-канал, см. `themes/README.md`, `scripts/{build,sign}-themes.sh`). Готовые подписанные XPI лежат в `assets/themes/*.xpi` (в git, не пересобираются на лету) и ставятся `addons_install_themes` (`lib/addons.sh`) — обычным копированием, без сети и без `addon_guid`. Ставятся ВСЕГДА; выбор (мастер/`--theme`, дефолт dark) пишется `apply_theme_pref` в `<profile>/user.js` как `myfox.theme` и один раз (guard `myfox.themeApplied`) включается `myfox.cfg`, он же выставляет `layout.css.prefers-color-scheme.content-override`. ID тем — `MYFOX_THEME_DARK_ID`/`MYFOX_THEME_LIGHT_ID` (`lib/addons.sh`), дублируются в `myfox.cfg` (`THEME_IDS`) и в списке удаляемых XPI в `run_uninstall` (тот список хранит ещё и старые brace-GUID от Stylefox — для чистки профилей, установленных до форка) — менять вместе. Правишь палитру — обнови `themes/<name>/manifest.json`, подними `version`, перезапусти `scripts/sign-themes.sh`, скопируй результат в `assets/themes/`.
- KDE Plasma integration: молча в сессии Plasma или с `--plasma-integration` (`--noplasma` гасит). Нужен системный пакет `plasma-browser-integration` (native host): инсталлер проверяет (`addons_pkg_installed`, каталоги переопределяются `MYFOX_NMH_DIRS` — для тестов) и печатает заметку с командой в конце, без sudo-промптов.

### Букмарклеты (bl)
- Входят в «твики: да»; `--nobl` отключает, `opts.bl` запоминается. `apply_bookmarklets()` копирует `docs/blm_panel.css` → `<profile>/chrome/blm_panel.css` и иконки → `panel-icons/`. Источник: `MYFOX_DDBLM_LOCAL=<dir>` либо raw.githubusercontent.com (`CustomFF/ddblm`, master); 404 — предупреждение и пропуск.
- Галерея двуязычная (EN по умолчанию, RU по `?lang=ru`, клиентским JS). Закладка «Добавить букмарклеты» для русскоязычного Firefox — на `…/ddblm/?lang=ru`; при миграции с base-URL закладка переносится, а не дублируется.
- Иконка этой закладки подключена `url("../panel-icons/…")` из `chrome/user/10-menus-bookmarks.css`: **относительные `url()` в импортируемом файле считаются от него самого**, не от `userChrome.css`.
- Термин «blm» в myfox не используется — только «bl»/букмарклеты (имя файла `blm_panel.css` сохранено как в ddblm).

### Твики и префы (autoconfig/myfox.cfg и autoconfig/myfox/*.js)
- **Guard профиля** в самом начале `myfox.cfg`, до загрузки модулей: нет `<profile>/.myfox` → `throw`; дальше ничего не исполняется. Не обходить и не выносить логику за него.
- Всё, что пользователь может менять штатно (префы, тема, закладки), применяется **не более одного раза** на профиль под guard-префом (`oncePerProfile(guardPref, fn)`): `myfox.corePreferencesInitialized`, `myfox.firstRunPreferencesInitialized`, `sidebar.launcherAboveSidebar.initialized`, `myfox.themeApplied`, `myfox.galleryBookmarkAdded` — и никогда не перезаписывает выбор пользователя. **Guards срабатывают один раз**: изменил преф внутри блока — на существующем профиле НЕ переприменится, пока не сбросишь guard (about:config). Не дублируй эти префы в `user.js`. Свои панели («Загрузки», «Расширения», «Переводы») добавляются в `sidebar.main.tools` тем же способом — один раз, `myfox.sidebarToolsInitialized` (`30-sidebar.js`); это не `oncePerProfile`, а свой guard с повтором, потому что при загрузке `myfox.cfg` дефолт этого префа ещё пуст — важно не перезаписывать её на каждое изменение префа: это тот самый список включённых панелей, который пишет чекбокс «Настройки боковой панели», и раньше код восстанавливал имя при каждом изменении, из-за чего выключить свою панель через чекбокс было невозможно.
- Стартовые настройки свежего профиля (компактный интерфейс, отключение ИИ/Pocket/спонсоров/телеметрии) — таблица `freshProfilePrefs` (`autoconfig/myfox/20-prefs.js`) в блоке `myfox.firstRunPreferencesInitialized`.
- `distribution/policies.json` **не ставится**; кнопка «Импорт закладок» убирается профиль-локально (виджет `import-button`).
- Хелперы — `autoconfig/myfox/00-common.js`: `oncePerProfile`, `whenDelayedStartupDone`, `whenPlacesReady`, `t(key, ...args)` (строки), `createOwnPanel`/`wrapSearchWithClear` (панели на пустой странице). **Строки интерфейса не хардкодятся**: они лежат в каталогах `autoconfig/myfox/i18n/<язык>.js` (`en.js` — база и запасной вариант, `ru.js`, …); подбирается каталог по языку браузера (`pt-br` → `pt` → `en`), новый язык = новый файл.
- Закладки «Advanced settings» (about:config) и «Add bookmarklets» (галерея ddblm) распознаются по **GUID закладки**, а не по заголовку/URL: `70-bookmarks.js` пишет GUID в `myfox.bookmark.advanced|gallery` (для старых профилей находит один раз по URL; прежние адреса галереи — в `GALLERY_LEGACY_URLS`), `72-bookmark-roles.js` вешает на кнопки атрибут `myfox-role`, CSS (`user/10-menus-bookmarks.css`) смотрит на него. Сменил адрес ddblm — поменяй `GALLERY_URL` и добавь старый в `GALLERY_LEGACY_URLS`.
- Свои панели сайдбара (таблица `EXTRA_SIDEBARS` в `30-sidebar.js`): «Загрузки» — стандартная `about:downloads` с добавленными шапкой/поиском/подвалом; «Расширения» — своя страница на `about:blank?myfox-addons`; «Переводы Firefox» — пустая страница, в которой живёт настоящий remote-`<browser>` с `about:translations` (в нативном браузере сайдбара страница пуста, у неё не подключается актор). Стили: `agent/22-own-panels.css` (общее), `25-addons-sidebar.css`, `26-translations-sidebar.css`.

### Стили (chrome/)
- `agent/*.css` регистрирует `myfox.cfg` в порядке имён файлов — новый файл = новый номер, каталог/манифест не нужны. Agent-origin нужен, чтобы достать внутрь shadow DOM и перекрыть стили документов; user-лист так не умеет. Правила с общими именами классов оборачивай в `@-moz-document url-prefix("about:"), url-prefix("chrome://")` (в agent-листе работают только голые схемы, длинные префиксы не срабатывают).
- `userChrome.css` читается один раз при старте (правки user-листов — рестарт браузера); agent-листы можно перерегистрировать на лету, но **content-процессы (about:newtab, about:preferences…) динамическую подмену не подхватывают** — проверять после перезапуска.
- Один радиус `--myfox-radius`; Nova-токены переопределяются как custom properties, а не через pref.

## Python-код (myfox/) — идёт замена bash, см. docs/python-rewrite-plan.md

Обязательные правила, не пожелания. Перед тем как показать диф — перечитать
именно на эти пункты, не полагаться на память.

1. **Каскад `if`/`elif` по одному признаку — это таблица, не код.** Логика
   вида «вход X → выход Y» по списку соответствий — словарь (или множество
   для да/нет), не цепочка `if low.startswith(...)`.
   ```python
   # НЕ ТАК:
   if low.startswith("pt_br"): return "pt-BR"
   if low.startswith("pt"): return "pt-PT"
   if low.startswith(("zh_cn", "zh_sg")): return "zh-CN"
   ...
   # А ТАК:
   _LANG_WITH_REGION = {"pt_br": "pt-BR", "pt": "pt-PT", "zh_cn": "zh-CN", ...}
   ```
2. **DRY: два похожих блока — один блок с параметром.** Если два места
   отличаются только регуляркой/полем/одним словом — общая часть в функцию
   с этим отличием параметром, а не копия тела целиком.
3. **Одна каноническая форма значения.** Если код то оборачивает `f"[{x}]"`,
   то режет `x[1:-1]`, то добавляет `"Install"`, то отрезает — значение
   должно жить в ОДНОЙ форме через всю функцию; обёртка/снятие только на
   границе (запись/чтение файла), не посередине логики.
4. **Комментарий — факт, не поток сознания.** Одна-две строки: что и
   почему, если не очевидно из кода. Не хроника рассуждений, не пересказ
   кода словами, не ссылки на историю правок (она в git).
5. **Без боилерплейта.** Не заводить обёртки/классы/слои абстракции, которые
   не решают конкретную задачу здесь и сейчас.
6. **Лаконичность** — в сообщениях пользователю, докстрингах, комментариях:
   без повторов одной мысли разными словами.

## Правила для агентов

1. **Язык**: код и комментарии — английские, коротко и только «почему» (без ссылок на историю правок — она в git); этот файл — русский. README основной — английский + `README.ru.md`. Пользовательские строки инсталлера — через `i18n/` (ru+en), не хардкодом; исключение — ошибки разбора флагов (язык ещё не известен).
2. **Не дублировать**: тарбол-логика — в `lib/firefox.sh`; менеджер букмарклетов живёт в ddblm — myfox только копирует готовые твики. Логику навески на системный Firefox в инсталлер не добавляй без явной просьбы (есть только README-инструкция).
3. **`set -eo pipefail`** активен (без `-u`). Функции возвращают значения через stdout, а `log/success/warn/error` уходят в **stderr** — из `$(...)` stderr не захватывать; вызовы в `$(...)`, которые могут вернуть ненулевой код, оборачивать `|| true`.
4. **Изменения твиков**: `myfox.cfg` и CSS исполняются в privileged-контексте Firefox — правь аккуратно, соблюдай guards. После правки `myfox.cfg`/`user/*.css` нужен `myfox update` + перезапуск браузера.
5. **Не коммить**: `Office.conf`, бэкапы, state-маркеры, файлы ddblm (правим/копируем их при тесте твиков), сгенерированные артефакты (`dist/`, `scratch/refactor-baseline/`).
6. **Тесты**: автотестов нет — чек-листы в `tests/README.md`. Минимум перед сдачей:
   - `bash -n get.sh bin/myfox-core lib/*.sh scripts/*.sh`
   - `shellcheck -S error get.sh bin/myfox-core lib/*.sh scripts/*.sh`
7. **Не трогай чужие файлы**: другие клоны репозитория (вроде `~/dev/myfox`) не изменяй — правь только копию, над которой работаешь.
8. **Осторожно с реальной установкой**: инсталлер качает большие тарболы и меняет `~/.mozilla`/профили/desktop entry. Только песочница: `scratch/sandbox.sh <dir> [--fresh] -- ./bin/myfox-core <cmd> …` (изолирует HOME и все XDG; `--prefix` подставляет сам, только для `install`). Реальный профиль пользователя не трогай.
9. **Проверка стилей вживую**: через RDP-прокси (см. README, «Development»); `--headless --screenshot` для проверки JS `myfox.cfg` не годится — процесс завершается раньше асинхронной логики; нужен настоящий запуск.

## Справочник команд

```
./bin/myfox-core install [флаги]     # то же, что curl … | bash; в клоне: make install ARGS="…"
./bin/myfox-core update [--reinstall]
./bin/myfox-core uninstall [-y]
./bin/myfox-core help [команда]

install: --prefix <p> --profile <p> --lang <c> --list-languages --reinstall --browser-only
         --nobl --theme dark|light --plasma-integration --noplasma --force  -y  -v  -h

MYFOX_DDBLM_LOCAL=/path/to/ddblm ./bin/myfox-core install …   # твики букмарклетов из локальной копии ddblm
MYFOX_NMH_DIRS=/empty/dir …                                   # имитировать отсутствие пакета plasma-browser-integration
MYFOX_SANDBOX_KEEP_DESKTOP=1 scratch/sandbox.sh …             # оставить XDG_CURRENT_DESKTOP (по умолчанию песочница его сбрасывает)
scripts/dev-serve.sh                                          # собрать dist и раздать на 127.0.0.1:8787 (настоящий curl|bash)
```
