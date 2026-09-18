# Тесты MyFox

Этот каталог содержит описание/план тестов. Автоматические тестовые скрипты пока не заведены —
сюда складываем чек-листы и команды для проверки инсталлера и твиков.

## 0. Статические проверки

```bash
cd ~/development/myfox
bash -n install.sh uninstall.sh lib/*.sh          # синтаксис
shellcheck -S error install.sh uninstall.sh lib/*.sh   # static analysis (есть в системе)
python3 -m py_compile scratch/*.py   # если трогали dev-скрипты (необязательно)
```

## 1. Юнит-проверка lib по отдельности (без сети)

Все работы — в каталоге `/tmp`, с временным `HOME` и `XDG_STATE_HOME`:

### 1.1 Маркер и opts (common.sh)
```bash
export MYFOX_STATE_DIR=/tmp/mf-state
source lib/common.sh
state_set install_dir /tmp/ff && state_get install_dir   # → /tmp/ff
state_clear && state_get install_dir                      # → пусто
opts_get bl     # → true (дефолт)
opts_get lang   # → пусто
opts_set bl false && opts_get bl   # → false
```

### 1.2 Парсинг profiles.ini (profile.sh)
Фикстура с `IsRelative=1/0` и `Default=1` и существующими каталогами — проверка
`profile_parse_ini`, `profile_list_existing`, `profile_find_default`,
`_profile_entry_path_for`, `_ini_remove_section`, `_ini_write_install_section`
(на КОПИИ profiles.ini, не на боевом).

### 1.3 Создание профиля
```bash
export HOME=/tmp/mf-home  XDG_STATE_HOME=/tmp/mf-home/.local/state
mkdir -p /tmp/mf-home/.mozilla/firefox
source lib/common.sh lib/profile.sh
MYFOX_NONINTERACTIVE=1 profile_resolve
# ожидаем создание /tmp/mf-home/.mozilla/firefox/myfox-1 и [Profile0] Name=myfox
```

### 1.4 Языки (firefox.sh, нужна сеть)
```bash
source lib/common.sh lib/firefox.sh
firefox_list_languages                  # печатает коды + English-названия
firefox_validate_lang de && echo ok     # → ok
firefox_validate_lang zz || echo bad    # → bad
echo $LANG; firefox_detect_lang         # соответствует LANG
```

## 2. Интеграционные тесты инсталлера (можно с реальной установкой)

> Используем `-y` и `--prefix /tmp/...` — не трогаем реальный профиль.
> Для чистоты профилей/state — временный `HOME` и `XDG_STATE_HOME`:
> ```bash
> export HOME=/tmp/mf-home  XDG_STATE_HOME=/tmp/mf-home/.local/state
> ```

### 2.0 Мастер установки (интерактивно, tty + dialog/whiptail)
```bash
./install.sh --prefix /tmp/myfox-wiz        # БЕЗ -y, на реальном tty
```
- [ ] от старта до конца — один пошаговый визард, экран НЕ мигает между шагами
      (welcome → lang → профиль tweaked/clean → bl → stable/beta)
- [ ] кнопки: Continue/No/Cancel, «Back» есть на всех шагах кроме первого,
      на последнем шаге — кнопка «Install»
- [ ] шаг языка: пункт «Search / filter…» открывает поле фильтра; Enter по коду
      или названию (напр. `german`) сужает список, Enter сразу выбирает первый
      результат; Esc в фильтре возвращает к списку с сохранённым фильтром;
      пустой фильтр показывает все языки
- [ ] после «Install» установка идёт **внутри того же alt-экрана**: виден gauge
      с этапами «Downloading Firefox…» → «Extracting…» → «Pinning profile…» →
      «Applying tweaks…» → «Installing add-ons…»
- [ ] в самом конце alt-экран снимается, а итоговая сводка `=== MyFox ===`
      остаётся на обычном экране
- [ ] ошибка во время установки (напр. нет сети → «Download failed.») не оставляет
      терминал «висящим» в alt-экране (срабатывает EXIT-trap `_wizard_trap_cleanup`)
- [ ] `-y` и неинтерактив идут прежним последовательным потоком БЕЗ gauge

### 2.1 Первая установка (полная)
```bash
./install.sh -y --prefix /tmp/myfox-test --profile /tmp/mf-home/.mozilla/firefox/myfox-1
```
Проверки:
- [ ] тарбол скачан и распакован (есть `firefox`, `application.ini`)
- [ ] `<prefix>/defaults/pref/autoconfig.js`, `<prefix>/firefox.cfg`, `<prefix>/.myfox-installed`
- [ ] в профиле появился маркер `<profile>/.myfox`
- [ ] **пиннинг**: в `profiles.ini` появилась `[Install<HASH>]` с `Default=<myfox-...>` и `Locked=1`;
      та же секция в `installs.ini`; в `install.json` записан `install_hash`
- [ ] после headless-прогона Firefox НЕ назначил Default на чужой/новый профиль (мы переписали на myfox)
- [ ] после headless-пиннинга в `~/.mozilla/firefox` НЕТ мусорного `default-*` профиля (cat + `[ProfileN]` вычищены)
- [ ] `~/.local/share/applications/firefox-myfox.desktop` создан («Firefox (myfox)»), Exec без `--profile`
- [ ] `install.json` содержит `opts: {browser_only:false, lang:…, bl, addons, plasma}`

### 2.2 Повторный запуск без флагов → меню
```bash
./install.sh --prefix /tmp/myfox-test
```
- [ ] интерактивное меню: «1) Update tweaks (default) 2) Reinstall … 3) Quit»;
      Enter → обновление твиков (браузер НЕ перекачан)
- [ ] `./install.sh -y --prefix /tmp/myfox-test` → без вопрпосов, твики обновлены

### 2.3 --update
```bash
./install.sh --update -y
```
- [ ] autoconfig/chrome обновлены, браузер не качается, аддоны не трогаются
- [ ] букмарклеты применяются, если `opts.bl=true`, и пропускаются при `false` (или `--nobl`)
- [ ] `--update --lang de` и `--update --profile X` → ошибка (несовместимо)
- [ ] без state (`install.json` отсутствует) → понятная ошибка

### 2.4 --reinstall (+ язык)
```bash
./install.sh --reinstall -y --lang de
```
- [ ] браузер перекачан заново, `[Install<HASH>]` Default снова указывает на myfox-профиль
- [ ] `--reinstall -y` БЕЗ `--lang` → язык берётся из сохранённого `opts.lang`
- [ ] первой установке `--reinstall` не задаёт интерактивный вопрос о языке

### 2.5 --browser-only
```bash
./install.sh --browser-only -y --prefix /tmp/myfox-bo
```
- [ ] тарбол + desktop entry, НО `profiles.ini` не создаётся/не меняется (нет пиннинга, нет профиля)
- [ ] state: `opts.browser_only=true`, профиль-пути отсутствуют
- [ ] никаких твиков/аддонов в любые профили
- [ ] при запуске `/tmp/myfox-bo/firefox` Firefox сам создаст дедикейтед-профиль, твики не применятся

### 2.6 --list-languages и --lang
```bash
./install.sh --list-languages          # коды + English-названия в stderr, exit 0
./install.sh --lang zz -y              # → error «Unknown language code»
./install.sh --lang de -y --prefix /tmp/myfox-test6
```
- [ ] после `--lang de` в `application.ini` видно `lang=de` / каталог `browser/de`
- [ ] `--list-languages` выходит, игнорируя остальные флаги

### 2.7 Добавление --noaddons / plasma
```bash
./install.sh -y --prefix /tmp/myfox-test7 --noaddons --nobl --noplasma
./install.sh -y --prefix /tmp/myfox-test8 --nobl --plasma-integration  # если пакет есть
```
- [ ] `--noaddons` → в `<profile>/extensions/` пусто, добавлены `opts.addons=false`
- [ ] `--plasma-integration` → аддон `plasma-browser-integration@kde.org.xpi` появился в `<profile>/extensions/`; `opts.plasma=true`
- [ ] `--noplasma` → `opts.plasma=false`
- [ ] `distribution/` в инсталляции НЕ создаётся (никаких глобальных политик — всё профиль-локально)

### 2.8 Занятая директория (чужой Firefox)
1. Положить в `/tmp/myfox-occ` произвольный файл (эмулируем вручную поставленный ff) без `.myfox-installed`.
2. `./install.sh -y --prefix /tmp/myfox-occ`
- [ ] появилось предупреждение «Something is already present»
- [ ] бэкап создан (в `install.json` есть `backup_dir`, файл существует)
- [ ] установка прошла начисто

### 2.9 uninstall: unpin + секция профиля
После установки 2.1 (профиль создан myfox, есть `.myfox-created`):
```bash
./uninstall.sh -y
```
- [ ] `[Install<HASH>]` удалён из profiles.ini и installs.ini
- [ ] запись `[ProfileN]` Name=myfox удалена из profiles.ini
- [ ] **профиль удалён** целиком (каталог + запись) — `-y` подтверждает удаление
- [ ] autoconfig-файлы удалены, chrome CSS удалены, desktop entry удалён, `install.json` удалён
- [ ] вопрос «Remove MyFox tweaks?» для профиля, созданного инсталлером, НЕ показывается — вместо него сразу «Delete the myfox profile completely?»

Интерактивно для профиля с `.myfox-created`:
```bash
./uninstall.sh
```
- [ ] первый вопрос — «Delete the myfox profile completely?»; ответ «n»: данные профиля и запись в profiles.ini сохранены, твики всё равно сняты

Интерактивно для СУЩЕСТВУЮЩЕГО профиля (`--profile` без `.myfox-created`):
```bash
./uninstall.sh
```
- [ ] вопрос «Remove MyFox tweaks?» показывается; ответ «n» — отмена всего
- [ ] ответ «y»: твики сняты, профиль НЕ удалён и НЕ предлагается к удалению

### 2.10 Деградация пиннинга (headless не смог)
1. После установки тарбола «сломать» его (убрать shared-libs, напр. переименовать `libxul.so`).
2. `./install.sh --reinstall -y` → headless-запуск падает.
- [ ] warning «Headless Firefox run failed…», установка продолжается и завершается успешно
- [ ] `install_hash` в state пуст/отсутствует; uninstall не падает без него

### 2.11 uninstall с восстановлением бэкапа
После 2.8:
```bash
./uninstall.sh -y
```
- [ ] autoconfig-файлы удалены
- [ ] chrome CSS удалены из профиля
- [ ] бэкап восстановлен (содержимое `/tmp/myfox-occ` == исходное)
- [ ] desktop entry удалён
- [ ] `install.json` удалён

## 3. Ручные сценарии (нужен тестовый профиль)

### 3.1 Запуск и визуальная проверка твиков
```bash
/tmp/myfox-test/firefox --profile /tmp/myfox-test-prof
# или — после пиннинга — просто:
/tmp/myfox-test/firefox
```
- [ ] после пиннинга запуск **без** `--profile` открывает именно myfox-профиль (проверить через `about:profiles`: Default стоит на myfox-…), а не созданный Firefox-ом `default-release`
- [ ] карточный стиль (закруглённые углы вкладки-вкладки, отступы)
- [ ] сайдбар работает (`sidebar.revamp=true`); вертикальные вкладки НЕ включены по умолчанию (`sidebar.verticalTabs` не установлен)
- [ ] поле поиска в sidebar/скачивания — пилюля
- [ ] кнопка переключения сайдбара подсвечивается при открытой панели
- [ ] downloads как вид сайдбара
- [ ] `toolkit.legacyUserProfileCustomizations.stylesheets=true` (поставлен через autoconfig — проверить в about:config)

### 3.2 Свежий профиль: закладки галереи + первый запуск (важно!)
После **первого** старта на чистом профиле (не перезапуске):
- [ ] на панели закладок две закладки: **«Расширенные настройки»** (about:config) и **«Добавить букмарклеты»** (https://daydve.github.io/ddblm/)
- [ ] закладки не пропали после перезапуска (блок идемпотентен)
- [ ] кнопки «Импорт закладок» НЕТ (виджет `import-button` убирается профиль-локально в firefox.cfg)
- [ ] приветственный визард about:welcome («Импорт из другого браузера») НЕ показывается
- [ ] в Настройки → Внешний вид: тема оформления для сайтов = **Тёмная** (`layout.css.prefers-color-scheme.content-override=0` в about:config)
- [ ] панель закладок видна **на любой вкладке**, не только на новой (`browser.toolbars.bookmarks.visibility="always"`)
- [ ] кнопки профиля (`fxa-toolbar-menu-button`) на панели НЕТ
- [ ] guard-преф `myfox.galleryBookmarkAdded=true` в about:config (диагностический, не блокирует)

### 3.3 Чужие/новые профили — чистый Firefox (маркер `.myfox`)
1. Создать новый профиль в той же инсталляции без инсталлера (или `--profile /tmp/void-new`)
   и запустить в нём `/tmp/myfox-test/firefox`.
2. Глобальных политик в `distribution/` нет — инсталляция профиль-агностична; снятие твиков =
   удаление профиля обходит весь код firefox.cfg через guard.
Проверки:
- [ ] `install_dir/.myfox-installed` в профиле НЕ создан (это файл инсталла, не профиля)
- [ ] в `<new>/chrome/` НЕТ файлов (myfox не создаёт chrome в чужом профиле)
- [ ] префы `toolkit.legacyUserProfileCustomizations.stylesheets`, `sidebar.revamp`,
      `browser.aboutwelcome.enabled`, `layout.css.prefers-color-scheme.content-override` НЕ выставлены
- [ ] закладок «Расширенные настройки»/«Добавить букмарклеты» НЕТ
- [ ] интерфейс выглядит как обычный немодифицированный Firefox

### 3.4 Букмарклеты (ddblm, при включённых твиках)

Включить твики из опубликованного ddblm (raw.githubusercontent.com) или с локальной копии:
```bash
./install.sh -y --prefix /tmp/myfox-test6 --profile <profile>
# либо для проверки локальных правок твиков:
MYFOX_DDBLM_LOCAL=/home/daydve/development/ddblm \
  ./install.sh -y --prefix /tmp/myfox-test6 --profile <profile>
```
Проверки:
- [ ] в `<profile>/chrome/` появились `blm_panel.css` и **ВСЕ** `panel-icons/*.svg` из `icons/` ddblm (13 шт., включая `import-bookmarklets.svg`)
- [ ] кнопка «Добавить букмарклеты» на панели закладок с иконкой (не пустой/сломанной)
- [ ] в русскоязычном Firefox закладка «Добавить букмарклеты» открывает `https://daydve.github.io/ddblm/?lang=ru`, в англоязычном — базу без параметра
- [ ] перетаскивание карточек из галереи на панель закладок работает (drag&drop)
- [ ] иконки и скрытие подписей (через `blm_panel.css` + `userChrome.css`) применились
- [ ] при `MYFOX_DDBLM_LOCAL` пустом — твики тянутся с raw.githubusercontent.com (при 404 иконок/`blm_panel.css` — ясное предупреждение и пропуск)

### 3.5 Применение к существующему браузеру (README-инструкция)
Выполнить шаги секции «Applying to an existing Firefox» на временной инсталляции:
- [ ] копирование `autoconfig.js` → `defaults/pref/`, `firefox.cfg` → корень
- [ ] копирование CSS → `chrome/` профиля
- [ ] префы единоразово выставились (не спрашивали вручную)
- [ ] твики работают

## 4. Регрессия твиков (после изменения firefox.cfg / CSS)
- [ ] `bash -n`/shellcheck пройден
- [ ] hot-reload dev-скриптами (scratch) не развалился: `userChrome.css` + `agent_overrides.css` копируются, `@import` вырезается
- [ ] нет сообщений об ошибках JS в браузерной консоли (about:config → devtools)
- [ ] при перезапуске Firefox твики по-прежнему применяются

## 5. Где смотреть результаты
- state: `~/.local/state/myfox/install.json`
- бэкапы: `~/.local/state/myfox/backups/`
- desktop: `~/.local/share/applications/firefox-myfox.desktop`
- профили/пиннинг: `~/.mozilla/firefox/profiles.ini`, `~/.mozilla/firefox/installs.ini`
- локальный ddblm: `/home/daydve/development/ddblm` (источник твиков для `MYFOX_DDBLM_LOCAL` при отладке локальных правок твиков; опубликованная версия — `DayDve/ddblm` на GitHub Pages)