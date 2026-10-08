# Тесты MyFox

Автотесты — `unittest` из stdlib в `myfox/tests/` (без pytest и pip):

```bash
python3 -m unittest discover -t . -s myfox/tests -p "test_*.py" < /dev/null
python3 -m unittest myfox.tests.test_task          # один модуль
```

Всё, что ниже, — ручные проверки: GUI автотестов не имеет, а настоящую установку, профиль и
Firefox тесты не трогают. Чек-лист самих твиков (CSS/JS в `autoconfig/`/`chrome/`) — в
[CustomFF/tweaks](https://github.com/CustomFF/tweaks/blob/master/TESTING.md).

Все прогоны — только в песочнице (`scratch/sandbox.sh` подставляет свой `$HOME` и все `$XDG_*`).
Реальный профиль и `$HOME` не трогать.

## 1. Установка: настоящий путь `curl | sh`, из рабочей копии

```bash
R=$PWD
scratch/sandbox.sh /tmp/mf --fresh -- bash -c "cd /tmp && cat $R/get.sh | \
    MYFOX_BOOTSTRAP_URL=file://$R/bootstrap.py MYFOX_CORE_DIR=$R sh -s -- -y"
```
`-y` — без вопросов, по умолчанию; без него — форма (TUI в терминале, `--gui` — окно).
Ядро из архива вместо рабочей копии: `MYFOX_CORE_URL=<путь или URL myfox-core.tar.gz>`
(собрать — `scripts/build-core-dist.sh`).

- [ ] `<data>/myfox/`: `myfox/` (пакет), `tweaks/`, `dearpygui/` (с `.myfox-wheel`), `firefox/`, `bin/myfox`; `~/.local/bin/myfox` — симлинк на `bin/myfox`
- [ ] в `firefox/`: `defaults/pref/autoconfig.js`, `myfox.cfg`, `myfox/*.js`, `.myfox-installed`, обёртка `firefox-myfox`
- [ ] профиль `<config>/mozilla/firefox/myfox-1` (при существующем `~/.mozilla/firefox` — там): `.myfox`, `chrome/`, `user.js` с `myfox.theme`, в `extensions/` две темы
- [ ] пиннинг: `[Install<HASH>]` с `Default=myfox-1` в `profiles.ini` и `installs.ini`; `install_hash` в state; мусорного `default-*` профиля нет
- [ ] `<data>/applications/firefox-myfox.desktop` («Firefox (myfox)»), в меню действий «Перезапустить» и «Обновить MyFox», пункта «Удалить» нет; «Перезапустить» при запущенном Firefox перезапускает его с вкладками, без лишнего окна, при незапущенном — просто запускает
- [ ] `state/myfox/state.json`: `install_dir`, `profile_dir`, `firefox_version`, `install_hash`, `lang`, `channel`, `theme`, `tweaks`, `core_version`, `tweaks_version`
- [ ] без терминала и без `-y` (`… < /dev/null`): сводка и «Установку нужно подтвердить. Запустите: … -y», ничего не установлено
- [ ] повторный запуск `get.sh` при установленном: «MyFox уже установлен», с аргументами — уходит в установленный `myfox`

### Чистый контейнер, другие дистрибутивы и aarch64

```bash
scratch/docker-test.sh debian:13 ubuntu:26.04 fedora:latest     # из рабочей копии
scratch/docker-test.sh --arch arm64 debian:13                   # под qemu
scratch/docker-test.sh --release debian:13                      # опубликованный MyFox с GitHub
```
Ставит `-y`, проверяет state (в том числе `install_hash`), `myfox browser --version`, импорт
dearpygui и чистое удаление. Для `--arch arm64` на x86_64 нужна эмуляция:
`sudo apt install qemu-user-static`.

## 2. Форма установки

```bash
python3 -m myfox.wizard --dry-run [--gui]     # ничего не ставит, только этапы
```
- [ ] успешная установка: форма закрывается сама (TUI и GUI), в терминале сводка; ошибка — форма остаётся с «Закрыть»
- [ ] TUI: Tab/Shift+Tab по полям, поиск языка, «Обзор…» открывает выбор каталога; зажатая стрелка не теряет нажатий
- [ ] GUI: та же форма; выбор каталога через портал; клавиши поиск → список → кнопки
- [ ] нет сети до Mozilla → ошибка в форме, «Установить» не работает
- [ ] «Твики: нет» → строки «Оформление» нет

## 3. `myfox refresh`

- [ ] нового нет → одна строка (с `--gui` — уведомление), диалога нет
- [ ] есть новое → диалог: строки «старая → новая», «Что нового» из changelog; `-y` — без диалога
- [ ] `--force` → все треки заново
- [ ] новые твики и запущен Firefox этой установки → галочка «Перезапустить Firefox»; после обновления Firefox перезапускается, вкладки восстановлены, лишнего окна нет; галочка снята → не перезапускается
- [ ] самообновление: поставить старое ядро (`MYFOX_CORE_URL=…/core-1.0.2/myfox-core.tar.gz`), затем `myfox refresh -y` → `myfox --version` новый, `core_version` в state обновлён

## 4. `myfox reinstall`

- [ ] TUI и `--gui`: строки Firefox/канал/каталог, «Переустановить» → прогресс → «Закрыть»
- [ ] после: Firefox новый, обёртка, ярлык, пиннинг и твики на месте; временных `.firefox-new-*`/`-old-*` нет
- [ ] обрыв загрузки (нет сети) → старый Firefox цел

## 5. `myfox uninstall`

- [ ] фокус сразу на «Отмена», Enter ничего не удаляет; Escape закрывает
- [ ] без галочки: Firefox, ярлык, `myfox`, `<data>/myfox` удалены; профиль на диске, его `[ProfileN]` и `[Install<HASH>]` убраны; state пуст
- [ ] с галочкой / `--remove-profile`: и каталог профиля удалён — только созданный MyFox (`.myfox-created`), в том числе с «Твики: нет»
- [ ] без терминала и без `-y`: сводка и обе подсказки (`myfox uninstall -y`, `… --remove-profile`), ничего не удалено
- [ ] GUI удаляет и себя (`<data>/myfox/dearpygui`) — окно не падает до «Закрыть»

## 6. Общее для reinstall/uninstall/refresh в GUI

- [ ] во время работы «Отмена» и крестик окна не срабатывают; после — «Закрыть», крестик закрывает
- [ ] запущен Firefox из этой установки → «Сначала закройте Firefox: он запущен.», действие недоступно (и с `-y`)
- [ ] длинные пути переносятся, окно по высоте содержимого

## 7. KDE Plasma (`MYFOX_SANDBOX_KEEP_DESKTOP=1`, `MYFOX_NMH_DIRS=<пустой каталог>` — «пакета нет»)

- [ ] сессия Plasma → аддон ставится; без пакета `plasma-browser-integration` — заметка с командой установки в конце
- [ ] не Plasma → аддон не ставится

## 8. Где смотреть результаты

- state: `~/.local/state/myfox/state.json`
- MyFox и Firefox: `~/.local/share/myfox/`, `~/.local/bin/myfox`
- ярлык: `~/.local/share/applications/firefox-myfox.desktop`
- профили/пиннинг: `~/.mozilla/firefox/` или `~/.config/mozilla/firefox/` (`profiles.ini`, `installs.ini`)
- твики из локальной копии: `MYFOX_TWEAKS_LOCAL=<CustomFF/tweaks>`; букмарклеты: `MYFOX_DDBLM_LOCAL=<ddblm>`
