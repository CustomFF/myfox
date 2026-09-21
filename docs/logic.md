# MyFox — описание логики и назначение

## Назначение

MyFox — набор твиков для браузера **Firefox** (интерфейс, сайдбар, вкладки, панель закладок) плюс инсталлер, который:

1. устанавливает последний стабильный Firefox прямо из официального тарбола Mozilla;
2. применяет на него твики;
3. опционально подключает твики для букмарклетов.

Букмарклеты — отдельный проект **ddbml** (отдельный каталог, **НЕ submodule** myfox). Инсталлер только копирует готовые твики (CSS + иконки) из него — локально при тестировании (`MYFOX_DDBLM_LOCAL`) или с raw.githubusercontent.com.

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
   └─ [bl?]     (опц.) букмарклет-твики: blm_panel.css + все иконки ddblm в профиль
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
Файл `~/.local/state/myfox/install.json` хранит `install_dir`, `profile_dir`, версию и дату. Назначение:
- повторный `install.sh` понимает, что установка наша — не качает заново, не переспрашивает профиль;
- `uninstall.sh` знает, что удалять;
- флаг `<install>/.myfox-installed` (а также `<install>/.myfox-version`) отличает нашу инсталляцию от вручную поставленной.

### Чужая занятая директория
Если по целевому пути уже что-то стоит, а маркера myfox нет — инсталлятор предупреждает и устанавливает начисто (бэкапы не делаются: в install-каталоге только скачиваемые бинарники, а профиль пользователя лежит отдельно и не трогается).

### Почему три `lib/*.sh`
- `common.sh` — инфраструктура (логирование в stderr, работа с state, подтверждения) — переиспользуется и install, и uninstall.
- `firefox.sh` — тарбол-установка (адаптация идей старого `mozinst.sh`: arch/lang, URL, версия, desktop entry; убран Thunderbird).
- `profile.sh` — работа с profiles.ini (detect/create), отдельно для тестируемости.
- `apply.sh` — перенос артефактов и букмарклет-твиков, отдельно для тестируемости.

### Роль ddblm (отдельный проект)
- Репозиторий ddblm — самостоятельный проект букмарклетов (исходники в `src/`, иконки, генерация галереи в `docs/index.html`).
- Галерея публикуется на GitHub Pages (drag&drop закладок).
- Installer копирует из ddblm готовые твики: `docs/blm_panel.css` → `chrome/blm_panel.css` и ВСЕ `icons/*.svg` → `chrome/panel-icons/`. Источник: локальная копия (`MYFOX_DDBLM_LOCAL`) при тестировании, иначе raw.githubusercontent.com. Сам ddblm myfox не устанавливает и не собирает.

## Поток установки по шагам (install.sh)

1. Парсинг флагов (`--prefix`, `--reinstall`, `--profile`, `--nobl`, `--noaddons`, `--plasma-integration`, `--noplasma`, `-y/--yes`, `-h/--help`).
2. Загрузка `lib/*.sh`, `check_deps` (curl, tar, grep, awk).
3. `INSTALL_DIR` = `--prefix` ? так : (из state ? так : `~/.local/share/firefox`).
4. Браузерная часть (`lib/firefox.sh`):
   - наш маркер → обновляем только твики (если не `--reinstall`);
   - чужая занятая директория → предупреждение, очистка, установка начисто;
   - иначе → `firefox_install_tarball` (скачивание, распаковка, запись версии).
5. Профиль (`lib/profile.sh`):
   - из `--profile` → использовать;
   - из state → использовать (проверить существование);
   - первый запуск → existing/default → спросить; нет → создать `myfox-N`.
6. `apply_autoconfig`, `apply_chrome` (копирование файлов).
7. `firefox_create_desktop_entry` (имя «Firefox (myfox)»).
8. Запись state (`install_dir`, `installed_at`, `firefox_version`).
9. Букмарклеты — если не `--nobl` и пользователь согласен → `apply_bookmarklets` (копирует blm_panel.css + все иконки из локального ddblm или raw github).
10. Дополнения: uBlock, тема Chrome Dark, plasma-integration (см. `--plasma-integration`/`--noplasma`).
11. Сводка.

## Поток удаления (uninstall.sh)

1. Нет state → предупреждение и выход (твики ставились вручную → см. README).
2. Подтверждение.
3. Удаление autoconfig (`defaults/pref/autoconfig.js`, `firefox.cfg`, `.myfox-installed`), chrome CSS, файлов букмарклет-твиков (blm_panel.css, panel-icons/).
4. Удаление desktop entry.
5. Браузер (сам install_dir) — спросить, оставляем или удаляем.
6. Очистка state.

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
| `lib/apply.sh` | применение твиков + букмарклет-твики (ddblm) |
| `install.sh` / `uninstall.sh` | точки входа |

## Известные ограничения

- Linux only (bash 4+).
- Только двигатель Release (стабильный) Firefox.
- Нельзя ставить твики автоматически на системный/уже установленный браузер (только ручная инструкция в README).
- При изменении пути `--prefix` вниз маркер используется от первого указанного (переопределить можно `--prefix` явно).