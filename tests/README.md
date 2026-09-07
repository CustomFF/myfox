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

### 1.1 Маркер (common.sh)
```bash
export MYFOX_STATE_DIR=/tmp/mf-state
source lib/common.sh
state_set install_dir /tmp/ff && state_get install_dir   # → /tmp/ff
state_clear && state_get install_dir                      # → пусто
```

### 1.2 Парсинг profiles.ini (profile.sh)
Фикстура с `IsRelative=1/0` и `Default=1` и существующими каталогами — проверка
`profile_parse_ini`, `profile_list_existing`, `profile_find_default`.

### 1.3 Создание профиля
```bash
export HOME=/tmp/mf-home  XDG_STATE_HOME=/tmp/mf-home/.local/state
mkdir -p /tmp/mf-home/.mozilla/firefox
source lib/common.sh lib/profile.sh
MYFOX_NONINTERACTIVE=1 profile_resolve
# ожидаем создание /tmp/mf-home/.mozilla/firefox/myfox-1 и [Profile0] Name=myfox
```

## 2. Интеграционные тесты инсталлера (можно с реальной установкой)

> Используем `-y` и `--prefix /tmp/...` — не трогаем реальный профиль.

### 2.1 Первая установка
```bash
./install.sh -y --prefix /tmp/myfox-test
```
Проверки:
- [ ] тарбол скачан и распакован (есть `firefox`, `application.ini`)
- [ ] `<prefix>/defaults/pref/autoconfig.js` существует
- [ ] `<prefix>/firefox.cfg` существует
- [ ] `<prefix>/.myfox-installed` существует
- [ ] профиль создан/выбран; в `~/tmp-state` появился `install.json` с `install_dir` и `profile_dir`
- [ ] `~/.local/share/applications/firefox-myfox.desktop` создан («Firefox (myfox)»)

### 2.2 Повторный запуск (idempotent)
```bash
./install.sh -y --prefix /tmp/myfox-test
```
- [ ] браузер НЕ перекачан (нет нового скачивания)
- [ ] профиль взят из маркера (в output используется тот же profile_dir)
- [ ] твики обновлены

### 2.3 Отдельная инсталляция и --noblm
```bash
./install.sh -y --prefix /tmp/myfox-test2 --noblm
```
- [ ] установка прошла
- [ ] в логике не вызывался blm / не создан `bookmarks_panel.css` в профиле

### 2.4 Занятая директория (чужой Firefox)
1. Положить в `/tmp/myfox-occ` произвольный файл (эмулируем вручную поставленный ff) без `.myfox-installed`.
2. `./install.sh -y --prefix /tmp/myfox-occ`
- [ ] появилось предупреждение «Something is already present»
- [ ] бэкап создан (в `install.json` есть `backup_dir`, файл существует)
- [ ] установка прошла начисто

### 2.5 uninstall с восстановлением бэкапа
После 2.4:
```bash
./uninstall.sh -y
```
- [ ] autoconfig-файлы удалены
- [ ] chrome CSS удалены из профиля
- [ ] бэкап восстановлен (содержимое `/tmp/myfox-occ` == исходное)
- [ ] desktop entry удалён
- [ ] `install.json` удалён

### 2.6 uninstall без бэкапа
После простой установки (2.1): `./uninstall.sh -y` — без бэкапа, браузер удаляется (спрашиваем/`-y`), твики удалены, state очищен.

## 3. Ручные сценарии (нужен тестовый профиль)

### 3.1 Запуск и визуальная проверка твиков
```bash
/tmp/myfox-test/firefox --profile /tmp/myfox-test-prof
```
- [ ] карточный стиль (закруглённые углы вкладки-вкладки, отступы)
- [ ] сайдбар с вертикальными вкладками (`sidebar.verticalTabs=true` в about:config)
- [ ] поле поиска в sidebar/скачивания — пилюля
- [ ] кнопка переключения сайдбара подсвечивается при открытой панели
- [ ] downloads как вид сайдбара
- [ ] `toolkit.legacyUserProfileCustomizations.stylesheets=true` (поставлен через autoconfig — проверить в about:config)

### 3.2 Букмарклеты (при включённом blm)
- [ ] `bookmarklets/docs/index.html` сгенерирован
- [ ] в `~/.config/blm/config.json` указан тестовый профиль
- [ ] перетаскивание карточек на панель закладок работает (drag&drop)
- [ ] иконки и скрытие подписей (через `bookmarks_panel.css`) применились
- [ ] (если публиковано) галерея доступна на GitHub Pages

### 3.3 Применение к существующему браузеру (README-инструкция)
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
- blm config: `~/.config/blm/config.json`