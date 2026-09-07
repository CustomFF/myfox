# MyFox — описание логики и назначение

## Назначение

MyFox — набор твиков для браузера **Firefox** (интерфейс, сайдбар, вкладки, панель закладок) плюс инсталлер, который:

1. устанавливает последний стабильный Firefox прямо из официального тарбола Mozilla;
2. применяет на него твики;
3. опционально подключает твики для букмарклетов.

Букмарклеты — отдельный проект **ddbml**, подключаемый git submodule'ом в `bookmarklets/`.

## Модель установки

```
install.sh --default
   ├─ [браузер]  скачать download.mozilla.org → распаковать в install_dir
   │              install_dir = --prefix | из маркера | ~/.local/share/firefox
   ├─ [профиль]  первый раз: детекция existing / создание нового
   │              далее: из маркера (profile_dir)
   ├─ [твики]    autoconfig.js → <install>/defaults/pref/
   │              firefox.cfg  → <install>/
   │              userChrome.css, agent_overrides.css → <profile>/chrome/
   │              префы ставятся самим firefox.cfg при старте
   ├─ [desktop]  «Firefox (myfox)» → ~/.local/share/applications/firefox-myfox.desktop
   └─ [blm?]     (опц.) blm build + blm patchff → твики букмарклетов в профиль
```

**Навеска на существующий браузер** НЕ реализована в скриптах. Она описана в README (секция «Applying to an existing Firefox») как ручные шаги.

## Ключевые решения (и почему)

### Почему тарбол и почему ~/.local/share/firefox
- Тарбол с официального CDN — единый путь для всех дистрибутивов, не зависит от apt/snap/flatpak.
- Установка в `~/.local` не требует root. Autoconfig-файлы можно класть без sudo.
- Имя «Firefox (myfox)» не конфликтует с системным ярлыком браузера.

### Почему префы ставятся через firefox.cfg, а не user.js
- `firefox.cfg` (Autoconfig) выполняется при каждом старте с привилегиями и уже используется твиками — это надёжная точка для префов.
- `toolkit.legacyUserProfileCustomizations.stylesheets`, `sidebar.revamp`, `sidebar.verticalTabs` выставляются один раз (маркер `myfox.corePreferencesInitialized`).
- Это избавляет пользователя от ручного шага в about:config.

### Маркер (state)
Файл `~/.local/state/myfox/install.json` хранит `install_dir`, `profile_dir`, `backup_dir`, версию и дату. Назначение:
- повторный `install.sh` понимает, что установка наша — не качает заново, не переспрашивает профиль;
- `uninstall.sh` знает, что удалять и что восстанавливать;
- флаг `<install>/.myfox-installed` отличает нашу инсталляцию от вручную поставленной (тогда перед установкой — бэкап всей директории).

### Бэкап
Бэкап делается **только** когда по целевому пути уже что-то стоит без нашего маркера (например, браузер поставлен вручную). Вся занятая директория пакуется в `tar.gz` в `~/.local/state/myfox/backups/`, путь пишется в state. При удалении `uninstall.sh` предлагает восстановить из бэкапа.

### Почему три `lib/*.sh`
- `common.sh` — инфраструктура (логирование в stderr, работа с state, подтверждения) — переиспользуется и install, и uninstall.
- `firefox.sh` — тарбол-установка (адаптация идей старого `mozinst.sh`: arch/lang, URL, версия, desktop entry; убран Thunderbird).
- `profile.sh` — работа с profiles.ini (detect/create), отдельно для тестируемости.
- `apply.sh` — перенос артефактов и запуск blm, отдельно для тестируемости.

### Роль ddbml (submodule)
- Репозиторий ddbml — самостоятельный проект букмарклетов (Python CLI `blm`, исходники в `src/`, иконки, генерация галереи в `docs/index.html`).
- Галерея публикуется на GitHub Pages (drag&drop закладок).
- Installer вызывает blm как внешний инструмент; blm сам управляет своим конфигом `~/.config/blm/config.json`.

## Поток установки по шагам (install.sh)

1. Парсинг флагов (`--prefix`, `--reinstall`, `--profile`, `--noblm`, `-y/--yes`, `-h/--help`).
2. Загрузка `lib/*.sh`, `check_deps` (curl, tar, grep, awk).
3. `INSTALL_DIR` = `--prefix` ? так : (из state ? так : `~/.local/share/firefox`).
4. Браузерная часть (`lib/firefox.sh`):
   - наш маркер → обновляем только твики (если не `--reinstall`);
   - чужая занятая директория → бэкап `tar.gz`, очистка, установка начисто;
   - иначе → `firefox_install_tarball` (скачивание, распаковка, запись версии).
5. Профиль (`lib/profile.sh`):
   - из `--profile` → использовать;
   - из state → использовать (проверить существование);
   - первый запуск → existing/default → спросить; нет → создать `myfox-N`.
6. `apply_autoconfig`, `apply_chrome` (копирование файлов).
7. `firefox_create_desktop_entry` (имя «Firefox (myfox)»).
8. Запись state (`install_dir`, `installed_at`, `firefox_version`).
9. B lm — если не `--noblm` и пользователь согласен → `apply_bookmarklets`.
10. Сводка.

## Поток удаления (uninstall.sh)

1. Нет state → предупреждение и выход (твики ставились вручную → см. README).
2. Подтверждение.
3. Удаление autoconfig (`defaults/pref/autoconfig.js`, `firefox.cfg`, `.myfox-installed`), chrome CSS, файлов blm.
4. Если есть `backup_dir` → предложить восстановить (восстановление в `install_dir`).
5. Удаление desktop entry.
6. Браузер (сам install_dir) — спросить, оставляем или удаляем.
7. Очистка state.

## Ключевые файлы

| Файл | Роль |
|---|---|
| `autoconfig/firefox.cfg` | privileged JS твики: agent sheet, sidebar/downloads, префы |
| `autoconfig/autoconfig.js` | включение Autoconfig (defaults/pref/) |
| `chrome/userChrome.css` | user-sheet стили |
| `chrome/agent_overrides.css` | agent-sheet стили (регистрируется firefox.cfg) |
| `lib/common.sh` | логика, state, helpers |
| `lib/firefox.sh` | тарбол-установка (адаптация mozinst) |
| `lib/profile.sh` | профили |
| `lib/apply.sh` | применение твиков + blm |
| `install.sh` / `uninstall.sh` | точки входа |
| `bookmarklets/` | submodule → ddbml |

## Известные ограничения

- Linux only (bash 4+).
- Только двигатель Release (стабильный) Firefox.
- Нельзя ставить твики автоматически на системный/уже установленный браузер (только ручная инструкция в README).
- При изменении пути `--prefix` вниз маркер используется от первого указанного (переопределить можно `--prefix` явно).