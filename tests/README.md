# Тесты MyFox

Автотестов нет — здесь чек-листы и команды для проверки инсталлера и твиков.

Все прогоны инсталлера — только в песочнице (`scratch/sandbox.sh` подставляет свой `$HOME` и все `$XDG_*`,
для `install` сам добавляет `--prefix <sandbox>/install`). Реальный профиль и `$HOME` не трогать.

```bash
scratch/sandbox.sh /tmp/mf --fresh -- ./bin/myfox-core install -y --nobl   # с нуля
scratch/sandbox.sh /tmp/mf -- ./bin/myfox-core update -y
scratch/sandbox.sh /tmp/mf -- ./bin/myfox-core uninstall -y
```

## 0. Статические проверки

```bash
bash -n get.sh bin/myfox-core lib/*.sh scripts/*.sh
shellcheck -S error get.sh bin/myfox-core lib/*.sh scripts/*.sh
python3 -m py_compile scratch/*.py        # если трогали dev-скрипты
for f in autoconfig/myfox.cfg autoconfig/myfox/*.js; do cp $f /tmp/fc.js && node --check /tmp/fc.js; done   # синтаксис privileged JS
```

## 1. Справка и разбор флагов (без сети)

```bash
./bin/myfox-core --help ; ./bin/myfox-core help install ; ./bin/myfox-core update --help
```
- [ ] справка по каждой подкоманде, по-русски при `LANG=ru_RU.UTF-8`, по-английски иначе
- [ ] `./bin/myfox-core uninstall --lang ru` → `Unknown option for 'uninstall': --lang`, код 1 (то же для `update --theme light`, `update --prefix x`)
- [ ] `--prefix` без значения → `Option '--prefix' requires a value.`; `--reinstall --browser-only` → «взаимоисключающие»
- [ ] `--lang=ru` и `--lang ru` эквивалентны; `--theme purple` → переведённая ошибка «Неизвестное оформление»
- [ ] `--list-languages` печатает коды и выходит (нужна сеть)

## 2. Установка (песочница, нужна сеть)

### 2.1 Полная установка, `-y`
```bash
scratch/sandbox.sh /tmp/mf --fresh -- ./bin/myfox-core install -y --nobl
```
- [ ] тарбол распакован; `<prefix>/defaults/pref/autoconfig.js`, `<prefix>/myfox.cfg`, `<prefix>/myfox/*.js`, `<prefix>/.myfox-installed`, wrapper `<prefix>/firefox-myfox`
- [ ] профиль создан в `<config>/mozilla/firefox/myfox-1` (свежий `$HOME` без `~/.mozilla/firefox` → каталог XDG; при существующем `~/.mozilla/firefox` — он)
- [ ] в профиле: `.myfox`, `.myfox-created`, `chrome/userChrome.css`, `chrome/user/*.css`, `chrome/agent/*.css`, `user.js` с `myfox.theme`
- [ ] в `extensions/` ровно две XPI тем (`{9631ec37-…}`, `{1fd1213e-…}`); Plasma — нет (не сессия Plasma)
- [ ] **пиннинг**: в `profiles.ini` и `installs.ini` секция `[Install<HASH>]` с `Default=myfox-1`, `Locked=1`; `install_hash` в state; мусорного `default-*` профиля нет
- [ ] `~/.local/share/applications/firefox-myfox.desktop` («Firefox (myfox)»)
- [ ] `~/.local/share/myfox/{bin/myfox,bin/myfox-core,lib,i18n,assets}` и симлинк `~/.local/bin/myfox` → `…/share/myfox/bin/myfox`
- [ ] state (`~/.local/state/myfox/state`): `install_dir`, `profile_dir`, `firefox_version`, `opt_lang`, `opt_channel`, `opt_theme`, `opt_bl`, `opt_plasma`

### 2.2 Повторный запуск
- [ ] `install -y` при уже установленном → ошибка «pass --force»; с `--force` — переустановка
- [ ] интерактивно без `-y` — вопрос «переустановить?» (по умолчанию «нет»)
- [ ] из лаунчера `myfox install` без `--force` → строка статуса + справка (как у `myfox`), без скачивания; из bootstrap (`get.sh` вне лаунчера) → сообщение «уже установлен…»

### 2.3 Тема
```bash
… install -y --nobl --theme light      # и --theme dark, и без флага
```
- [ ] `user.js` содержит `user_pref("myfox.theme", "light")` (без дублей при повторной установке)
- [ ] обе XPI на месте при любом выборе
- [ ] настоящий запуск Firefox (не `--headless --screenshot`: он завершается раньше асинхронной активации) → в `prefs.js`: `extensions.activeThemeID` = ID выбранной темы, `myfox.themeApplied=true`, `layout.css.prefers-color-scheme.content-override` = 1 (light) / 0 (dark)
- [ ] `update` тему не трогает

### 2.4 KDE Plasma (`MYFOX_SANDBOX_KEEP_DESKTOP=1`, `MYFOX_NMH_DIRS=<пустой каталог>` — имитация «пакета нет»)
- [ ] Plasma-сессия + пакет есть → XPI ставится, тихо
- [ ] Plasma-сессия + пакета нет → XPI ставится, предупреждение и подсказка `sudo <pm> install plasma-browser-integration` в логе И в итоговой сводке; код 0
- [ ] не-Plasma + `--plasma-integration` → то же, принудительно; `--noplasma` под Plasma → не ставится
- [ ] не-Plasma без флага → плазма не трогается, предупреждений нет

### 2.5 `--browser-only`, язык, канал
- [ ] `--browser-only` → тарбол + ярлык + лаунчер; `profiles.ini` не создаётся, профиля и твиков нет; `opt_browser_only=true`
- [ ] `--lang de` → язык в `application.ini`/`browser/de`; неизвестный код → ошибка
- [ ] канал beta — только через мастер (2.7)

### 2.6 Занятая директория
- [ ] в `--prefix` лежит чужой непустой каталог без `.myfox-installed` → ошибка, каталог НЕ тронут

### 2.7 Мастер (интерактивно, реальный tty, `dialog`/`whiptail`)
```bash
scratch/sandbox.sh /tmp/mf-wiz --fresh -- ./bin/myfox-core install
```
- [ ] шаги: приветствие → каталог → канал → язык → профиль (пропускается без своих профилей) → твики → оформление → сводка; экран не мигает между шагами
- [ ] «Назад» на каждом шаге, кроме первого; из сводки — на «оформление» при «твики: да» и на «твики» при «нет»
- [ ] «твики: нет» → шага оформления нет, в сводке «Твики: нет», профиль чистый (без `.myfox`, стилей, тем)
- [ ] в сводке нет строки про букмарклеты; подпись шага — «Оформление» (не «веб-сайтов»)
- [ ] шаг языка: фильтр по подстроке (`german`), Enter выбирает первый результат
- [ ] после «Установить» — спиннеры этапов `[✔]`, итоговая сводка на обычном экране; ошибка (нет сети) не оставляет терминал в alt-экране
- [ ] без `dialog`/`whiptail` — обычные вопросы

## 3. Лаунчер

```bash
L=<sandbox>/home/.local/bin/myfox     # с теми же XDG-переменными, что у песочницы
$L ; $L help ; $L browser --version ; $L ff --version ; $L update -y ; $L uninstall -y
```
- [ ] `myfox` без аргументов: строка «MyFox установлен: <путь> (Firefox <версия>)» + справка, браузер НЕ стартует
- [ ] `myfox browser`/`ff` печатают версию и передают код; аргументы уходят в Firefox
- [ ] до установки `myfox browser` → «MyFox is not installed.», код 1
- [ ] `update` не дублирует файлы в `~/.local/share/myfox`, симлинк цел
- [ ] `uninstall` работает офлайн и полностью убирает симлинк и `~/.local/share/myfox` (в т.ч. самого себя)
- [ ] чужой файл/симлинк на месте `~/.local/bin/myfox` при `uninstall` остаётся нетронутым

## 4. Удаление

- [ ] `uninstall -y` для созданного профиля: `[Install<HASH>]` убран из `profiles.ini`/`installs.ini`, `[ProfileN] Name=myfox` убран, каталог профиля удалён; autoconfig, ярлык, state, симлинк, `~/.local/share/myfox` удалены
- [ ] интерактивно: два экрана («удалить приложение?» → «удалить профиль?» / для чужого профиля «снять твики?»), затем сводка; «Назад» работает
- [ ] «оставить профиль»: каталог `myfox-N` и `.myfox-created` остаются, запись `[ProfileN]` удалена; повторная установка видит его в мастере (без дублей) и корректно пиннит
- [ ] чужой профиль (`--profile <dir>` с собственным `userChrome.css`): при установке бэкап `userChrome.css.myfox-backup` (один раз; `update` его не пересоздаёт); при удалении `userChrome.css` возвращён из бэкапа, `chrome/agent`, `chrome/user`, `.myfox` убраны, профиль цел
- [ ] запущенный наш Firefox: `uninstall` просит закрыть (SIGTERM, через 10 с SIGKILL)
- [ ] деградация пиннинга: сломать тарбол (`libxul.so`) и `--reinstall -y` → предупреждение «headless failed», установка завершается, `install_hash` пуст, uninstall не падает

## 5. Твики в браузере (ручная проверка после `myfox update` + рестарта)

### 5.1 Свежий профиль, первый старт
- [ ] на панели закладок две закладки: «Расширенные настройки» (about:config) и «Добавить букмарклеты» (ddblm; для русского Firefox — `?lang=ru`); **обе видны с иконками** и не пропадают после второго запуска
- [ ] кнопки «Импорт закладок» и кнопки профиля нет; about:welcome не показывается
- [ ] панель закладок видна на любой вкладке (`browser.toolbars.bookmarks.visibility=always`)
- [ ] компактный интерфейс; ИИ/Pocket/спонсоры/телеметрия выключены (см. `freshProfilePrefs`)
- [ ] префы: `toolkit.legacyUserProfileCustomizations.stylesheets`, `sidebar.revamp`, guard-префы `myfox.*`
- [ ] активна выбранная тема; «внешний вид веб-сайтов» ей соответствует

### 5.2 Стили
- [ ] вкладки-карточки с «ушками», страница и сайдбар — карточки; один радиус везде; нет фиолетового (новая вкладка, about:preferences, кнопки)
- [ ] сайдбар: закладки, история, синхронизированные вкладки (ряды сдвинуты под заголовок, без «пилюль», плотные), загрузки (свой заголовок, поиск, «Очистить»), пароли (фон как у других панелей)
- [ ] ✕ круглые и на вкладках при наведении, в том числе когда вкладок много; кнопка закрытия сайдбара
- [ ] about:preferences/logins/addons/processes — 12px, без «пилюль»
- [ ] светлая тема: выбранная вкладка отделена тенью; проверить и на stable, и на beta
- [ ] `userChrome.css` подхватывается вместе с `@import user/*.css` (все семь файлов) и agent-листы регистрируются из `chrome/agent/` (проверять ПОСЛЕ перезапуска: content-процессы — about:newtab, about:preferences — динамическую подмену не подхватывают)

### 5.3 Чужие профили — чистый Firefox
- создать новый профиль в той же инсталляции (без инсталлера) и запустить `<prefix>/firefox -P <имя>`:
- [ ] в `<profile>/chrome/` нет файлов, нет `.myfox`, префы `myfox.*` не выставлены, закладок нет, интерфейс — обычный Firefox

### 5.4 Букмарклеты (ddblm)
```bash
… install -y --profile <p>                      # с сетью
MYFOX_DDBLM_LOCAL=/home/daydve/development/ddblm … install -y --profile <p>   # локальные правки
```
- [ ] в `<profile>/chrome/` `blm_panel.css` и все `panel-icons/*.svg` (включая `import-bookmarklets.svg`)
- [ ] иконки и скрытие подписей применились; drag&drop карточек из галереи работает
- [ ] недоступный источник (404) — предупреждение и пропуск, не падение

### 5.5 Навеска вручную (README, «Applying to an existing Firefox»)
- [ ] шаги 1–6 (включая `touch <profile>/.myfox`) на временной инсталляции: твики работают; без `.myfox` — не работают

## 6. Регрессия после правок

- [ ] `myfox.cfg`: `node --check`; настоящий запуск в песочнице дважды подряд — те же `myfox.*` префы, закладки на месте; ошибок в Browser Console нет
- [ ] CSS: относительные `url()` в `chrome/user/*.css` — только с `../` (`grep -rn 'url(' chrome/user chrome/agent | grep -v 'chrome://\|data:'`)
- [ ] после разбиения/переноса стилей — сравнить computed-style до/после на живом Firefox (главное окно + сайдбары), одинаково для старого и нового набора
- [ ] `scratch/reload_userchrome.py` (горячая перезагрузка) не развалился: склеивает `user/*.css` и `agent/*.css`
- [ ] `scripts/dev-serve.sh` + реальный `curl | bash` в изолированном `$HOME`: install → `myfox` → `myfox browser --version` → `update` → `uninstall`

## 7. Где смотреть результаты

- state: `~/.local/state/myfox/state`
- инсталлер: `~/.local/share/myfox/`, `~/.local/bin/myfox`
- ярлык: `~/.local/share/applications/firefox-myfox.desktop`
- профили/пиннинг: `~/.mozilla/firefox/` или `~/.config/mozilla/firefox/` (`profiles.ini`, `installs.ini`)
- локальный ddblm: `/home/daydve/development/ddblm` (источник для `MYFOX_DDBLM_LOCAL`)
