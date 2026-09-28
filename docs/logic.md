# MyFox — описание логики и назначение

## Назначение

MyFox — набор твиков для браузера **Firefox** (интерфейс, сайдбар, вкладки, панель закладок) плюс инсталлер, который:

1. устанавливает Firefox (stable или beta) прямо из официального тарбола Mozilla;
2. применяет на него твики;
3. ставит обе темы (тёмную/светлую) и включает выбранную; по сессии/флагу — интеграцию с KDE Plasma;
4. подключает твики для букмарклетов (входят в «твики: да»).

Букмарклеты — отдельный проект **ddblm** (отдельный каталог, **НЕ submodule** myfox). Инсталлер только копирует готовые твики (CSS + иконки) из него — локально при тестировании (`MYFOX_DDBLM_LOCAL`) или с raw.githubusercontent.com.

## Точки входа

```
get.sh                публичный вход, две роли:
                        1) bootstrap: curl … | bash — качает дистрибутив-тарбол во временный каталог
                           и запускает из него bin/myfox-core
                        2) установленный лаунчер ~/.local/bin/myfox → ~/.local/share/myfox/bin/myfox
bin/myfox-core        диспетчер: install | update | uninstall | help (внутренний интерфейс)
```

Команды лаунчера: `myfox` (статус + справка, браузер не запускает), `myfox browser|ff [args]`
(exec `<install>/firefox-myfox` — тот же wrapper, что в `.desktop`), `myfox update`, `myfox uninstall`,
`myfox help [команда]`. `update` качает тарбол заново; `uninstall`/`help` работают офлайн из
`~/.local/share/myfox/`.

`bin/myfox-core` устроен как `main()` первой функцией и `main "$@"` последней строкой. Флаги разбираются
по таблицам на подкоманду (`INSTALL_OPTS`/`UPDATE_OPTS`/`UNINSTALL_OPTS` + общие `GLOBAL_OPTS`; принимаются
`--flag value` и `--flag=value`); чужой для подкоманды флаг — ошибка, а не молчаливое игнорирование.
Ошибки разбора флагов печатаются по-английски: язык интерфейса (он сам зависит от `--lang`) ещё не известен.

## Модель установки

```
myfox-core install
   ├─ [браузер]  скачать download.mozilla.org → распаковать в install_dir
   │              install_dir = --prefix | из state | ~/.local/share/firefox
   │              чужой непустой каталог без нашего маркера — НЕ трогаем (ошибка)
   ├─ [профиль]  --profile | мастер / автосоздание нового myfox-N
   │              каталог профилей — по правилу самого Firefox (см. ниже)
   ├─ [твики]    autoconfig.js → <install>/defaults/pref/ ; myfox.cfg + myfox/*.js → <install>/
   │              userChrome.css + user/ + agent/ → <profile>/chrome/ ; маркер <profile>/.myfox
   │              префы ставит сам myfox.cfg при старте
   ├─ [темы]     обе XPI → <profile>/extensions/ ; выбор → <profile>/user.js (myfox.theme)
   ├─ [plasma?]  (по сессии/флагу) plasma-browser-integration → <profile>/extensions/
   ├─ [bl]       blm_panel.css + все иконки ddblm → <profile>/chrome/ (если не --nobl)
   ├─ [desktop]  «Firefox (myfox)» → ~/.local/share/applications/firefox-myfox.desktop
   └─ [launcher] ~/.local/share/myfox/{bin,lib,i18n,assets} + симлинк ~/.local/bin/myfox
```

**Навеска на существующий браузер** НЕ реализована в скриптах. Она описана в README (секция «Applying to an existing Firefox») как ручные шаги.

### Мастер (первая интерактивная установка)

На tty шаги идут в одном alt-экране (`dialog`, либо `whiptail`, либо обычные вопросы):
приветствие → каталог установки → канал (stable/beta) → язык Firefox → профиль (только свои `myfox-*`;
если их нет — шаг пропускается) → твики (да/нет) → оформление (только при «твики: да») → сводка.
На каждом шаге, кроме первого, есть «Назад». Шаги-«проходники» помнят направление (`GOING_BACK`), чтобы
«Назад» не отскакивал вперёд. «Твики: нет» — чистый профиль: браузер и ярлык, без стилей/тем/пиннинга.
Без tty или с `-y` мастера нет: язык/канал берутся из флагов, сохранённого состояния или умолчаний.

Долгие шаги идут под `tui_spin` (спиннер `[⠋] Название` → `[✔]`/`[✗]`; вне tty — просто строка).
Всё сетевое (список языков) качается ДО входа в alt-экран — иначе экраны мигают.

## Ключевые решения (и почему)

### Почему тарбол и почему ~/.local/share/firefox
- Тарбол с официального CDN — единый путь для всех дистрибутивов, не зависит от apt/snap/flatpak.
- Установка в `~/.local` не требует root. Autoconfig-файлы можно класть без sudo.
- Имя «Firefox (myfox)» не конфликтует с системным ярлыком браузера.

### Почему префы ставятся через myfox.cfg, а не user.js
- `myfox.cfg` (Autoconfig) выполняется при каждом старте с привилегиями и уже используется твиками — это надёжная точка для префов.
- Всё, что пользователь может поменять штатно, ставится ОДИН раз на профиль под собственным guard-префом
  (`myfox.corePreferencesInitialized`, `myfox.firstRunPreferencesInitialized`, `myfox.themeApplied`,
  `myfox.galleryBookmarkAdded`, `sidebar.launcherAboveSidebar.initialized`) и не перезаписывается позже.
- Единственное, что идёт через `user.js`: `myfox.theme` — сигнал от инсталлера свежему, ещё не стартовавшему
  профилю (у него нет `prefs.js`, куда писать). Сам `myfox.theme` — не настройка Firefox, ничто кроме `myfox.cfg` её не читает.

### Профиль-локальность
`myfox.cfg` первым делом проверяет маркер `<profile>/.myfox` и иначе бросает исключение — ниже ничего не
исполняется. Политик (`distribution/policies.json`) нет; аддоны — в `<profile>/extensions/`. Чужой/новый профиль
в той же инсталляции — обычный Firefox.

### Стили: два механизма
- `userChrome.css` — user-лист, читается один раз при старте; сам только `@import`-ит `user/*.css`
  (относительные `url()` внутри импортируемых файлов считаются от них самих).
- `agent/*.css` — **agent-листы**: регистрируются `myfox.cfg` через `nsIStyleSheetService.AGENT_SHEET`, по имени файла
  (числовые префиксы = порядок каскада). Только агентский origin достаёт внутрь shadow DOM
  (`moz-button`, `panel-list`, …) и перекрывает стили самих документов; user-лист так не умеет. Правила с общими
  именами классов обёрнуты в `@-moz-document url-prefix("about:"), url-prefix("chrome://")` (в agent-листе честны только
  голые схемы), чтобы не задеть сайты.

### Каталог профилей
Профили лежат в `~/.mozilla/firefox`, если каталог `~/.mozilla/firefox` уже существует, иначе (Firefox 147+ на
свежей системе) — в `$XDG_CONFIG_HOME/mozilla/firefox`; плюс flatpak/snap. Правило повторяет то, что делает сам Firefox
(`profile_native_dir()`). Store общий с обычным Firefox: правим ТОЛЬКО свои секции (`[Install<HASH>]`, `[ProfileN] Name=myfox`).

### State
Плоский `key=value` файл `~/.local/state/myfox/state` (без jq/python): `install_dir`, `profile_dir`, `firefox_version`,
`install_hash`, `installed_at` и сохранённые выборы `opt_*` (`browser_only`, `lang`, `channel`, `bl`, `theme`, `plasma`),
которые переиспользует `update`. Флаг `<install>/.myfox-installed` отличает нашу инсталляцию от чужой по тому же пути.

### Единый каталог `~/.local/share/myfox`
`bin/myfox` (лаунчер), `bin/myfox-core`, `lib/`, `i18n/`, `assets/` — всё, что нужно `myfox-core` офлайн.
`~/.local/bin/myfox` — симлинк на `bin/myfox`. `install_launcher` сносит каталог целиком и наполняет заново; `uninstall`
удаляет симлинк только если он резолвится в наш каталог, и затем сам каталог (самоудаление безопасно — bash уже прочитал скрипт).

### i18n
`i18n/en.sh` — база, `i18n/ru.sh` — переопределения поверх; отсутствующий ключ остаётся английским. Язык интерфейса:
`--lang` → сохранённый `opt_lang` → `$LANG` → en. Строки через `t key [args…]` (printf-формат; позиционные `%1$s`
bash-printf не поддерживает — повторяющийся аргумент передаётся дважды).

### Вывод
`cprintf "[bold]…[/bold]"` (`lib/common.sh`) — разметка тегами вместо сырых ANSI; цвет отключается вне tty, при `NO_COLOR`
и `TERM=dumb`. `log`/`success` молчат без `-v`, `warn`/`error` — всегда; всё в stderr.

### Роль ddblm (отдельный проект)
- ddblm — самостоятельный проект букмарклетов (исходники в `src/`, иконки, генерация галереи в `docs/index.html`).
- Галерея на GitHub Pages (drag&drop закладок).
- Инсталлер копирует готовые твики: `docs/blm_panel.css` → `chrome/blm_panel.css` и ВСЕ `icons/*.svg` → `chrome/panel-icons/`.
  Источник: локальная копия (`MYFOX_DDBLM_LOCAL`) при тестировании, иначе raw.githubusercontent.com (404 — предупреждение и пропуск).

## Модули

| Файл | Роль |
|---|---|
| `get.sh` | bootstrap + установленный лаунчер (без `lib/*`, только bash/curl/tar/awk) |
| `bin/myfox-core` | диспетчер, мастер, install/update/uninstall |
| `lib/common.sh` | пути, `cprintf`/логи, state (`state_*`, `opts_*`), проверка зависимостей |
| `lib/i18n.sh`, `i18n/*.sh` | каталог сообщений и `t()` |
| `lib/tui.sh` | обёртки над dialog/whiptail + bash-фолбэк, `tui_spin`, alt-экран |
| `lib/firefox.sh` | тарбол, язык, версия, desktop entry, wrapper `firefox-myfox` |
| `lib/profile.sh` | `profiles.ini`/`installs.ini`, пиннинг `[Install<HASH>]`, создание профилей |
| `lib/apply.sh` | autoconfig, `chrome/`, тема (`user.js`), букмарклеты (ddblm) |
| `lib/addons.sh` | XPI с AMO (`addon_guid`/`addon_fetch`), детект Plasma и системного пакета |
| `autoconfig/myfox.cfg`, `autoconfig/myfox/*.js`, `autoconfig/autoconfig.js` | privileged JS твики / включение Autoconfig |
| `chrome/userChrome.css`, `chrome/user/*.css`, `chrome/agent/*.css` | стили |
| `scripts/build-dist.sh`, `scripts/dev-serve.sh` | сборка дистрибутива / локальная раздача |
| `scratch/sandbox.sh` | безопасный прогон в изолированном `$HOME` |

## Поток install

1. `parse_args` (по таблице подкоманды) → `common.sh`/`i18n` → `check_deps` (curl, tar, awk).
2. `INSTALL_DIR` = `--prefix` | из state | `~/.local/share/firefox`.
3. Уже установлено и нет `--force`: интерактивно — вопрос «переустановить?», с `-y` — ошибка.
4. Мастер (tty и не `-y`) либо `resolve_lang`/`resolve_channel`.
5. Браузер: `install_browser_tarball` (наш каталог — переиспользуем; чужой — ошибка; `--reinstall` — чистая перекачка).
6. Профиль: `--profile` | выбор мастера | `profile_resolve` (в `-y` чужой профиль не берём никогда — создаём `myfox-N`).
7. Чистый профиль → только ярлык + лаунчер. Иначе `resolve_theme`, `resolve_plasma`, `resolve_bookmarklets`, и под одним спиннером
   `_setup_profile`: пиннинг `[Install<HASH>]` (headless-прогон Firefox, потом уборка мусорного first-run профиля),
   autoconfig, chrome, `user.js` темы, XPI, букмарклеты.
8. Ярлык, `install_launcher`, сводка (+ заметка про системный пакет Plasma, если его нет).

## Поток update / uninstall

- `update`: из state берёт `install_dir`/`profile_dir`/`opt_*`; без `--reinstall` браузер не трогает; переприменяет
  autoconfig, chrome, букмарклеты; обновляет `~/.local/share/myfox`. Тему НЕ трогает (guard `myfox.themeApplied`).
- `uninstall` (мастер: удалить приложение? → удалить профиль? → сводка; `-y` — всё): останавливает наш запущенный Firefox,
  снимает пиннинг, удаляет autoconfig и ярлык; созданный установщиком профиль — целиком (или оставляет, убрав только запись
  `[ProfileN]`); чужой (`--profile`) — только `chrome/agent`, `chrome/user`, `userChrome.css` (с возвратом бэкапа), маркер и
  наши XPI по фиксированным ID; затем симлинк и `~/.local/share/myfox`.

## Известные ограничения

- Linux only (bash 4+), x86_64/aarch64.
- Нельзя ставить твики автоматически на системный/уже установленный браузер (только ручная инструкция в README).
- Публичного адреса дистрибутива пока нет (`DIST_URL` в `get.sh` — заглушка; `MYFOX_DIST_URL` переопределяет).
