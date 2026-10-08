# MyFox — как устроено

MyFox ставит Firefox (stable или beta) из официального тарбола Mozilla в каталог пользователя и
применяет к нему твики из [CustomFF/tweaks](https://github.com/CustomFF/tweaks). Root не нужен.
Код — пакет `myfox/` на Python 3.8+, только stdlib; сторонний чистый Python — исходниками в
`myfox/_vendor/` (picotui, jeepney), бинарный dearpygui — из собственного релиза.

Твики (что именно меняется в браузере и как) описаны в самом репозитории tweaks; здесь — только
как установщик их доставляет. Букмарклеты — отдельный проект ddblm, установщик копирует его
готовые CSS и иконки.

## Три источника, три трека релизов

| Что | Откуда | Тег | Обновляет |
|---|---|---|---|
| Ядро (пакет `myfox/`) | релизы этого репозитория: `myfox-core.tar.gz`, `changelog.json` | `core-<semver>` | `myfox refresh` |
| Твики (`autoconfig/`, `chrome/`) | релизы CustomFF/tweaks: `myfox-tweaks.tar.gz`, `changelog.json` | `<beta major>.<patch>` (`158.0`) | `myfox refresh` |
| Темы | релизы CustomFF/tweaks | `themes-*` | при установке, reinstall и обновлении твиков |
| dearpygui (для GUI) | релиз этого репозитория, колёса cp38–cp314 × x86_64/aarch64 | `dearpygui-2.3.1` | при установке; заново — после смены версии Python |
| Firefox | `download.mozilla.org` | — | обновляется сам; заново — `myfox reinstall` |

Версии сравниваются как числа (`changelog.py`); `core-` в интерфейсе не показывается.
`changelog.json` — накопительный, новые версии первыми; «Что нового» — строки новее установленной.

## Точки входа

```
get.sh          curl -fsSL …/get.sh | sh [-s -- аргументы]
                нужен python3; скачивает bootstrap.py и запускает его, отдав ему терминал (/dev/tty)
bootstrap.py    MyFox уже стоит → аргументы уходят в установленный `myfox`; без аргументов —
                «уже установлен» и вопрос «проверить обновления?» (без терминала — команда)
                не стоит → ядро последнего core-* во временный каталог (+ dearpygui для --gui)
                и `python3 -m myfox.wizard` оттуда
myfox           ~/.local/bin/myfox → ~/.local/share/myfox/bin/myfox (sh: python3 -m myfox)
```

Подкоманды `myfox` (`__main__.py`): `browser [аргументы Firefox]` (exec обёртки
`<install>/firefox-myfox`), `refresh [--force]`, `reinstall`, `uninstall [--remove-profile]`, `help`,
`--version`. Общие флаги: `-y` (без вопросов), `--gui` (окно). Подкоманды `install` нет:
первая установка — только из `bootstrap.py`.

## Как показывается интерфейс

Логика одна, видов три; `--gui` меняет только вид.

- **Форма первой установки** — `install_form.InstallForm` (ответы, выбор, проверка каталога, языки
  Firefox с поиском) и виды `ui/form_gui.py` (dearpygui), `ui/form_tui.py` (picotui),
  `ui/form_plain.py`.
- **Диалог команды** (refresh, reinstall, uninstall) — `task.Task`: строки, необязательный список,
  галочки, одна кнопка действия, прогресс, «Закрыть». Виды `ui/task_{gui,tui,plain}.py`, выбор —
  `task.show()`. Разрушительное действие начинает с фокуса на «Отмена»; если действие сейчас
  невозможно (запущен Firefox из этой установки), причина показана, кнопка недоступна.

Выбор вида: `-y` → текстовый, без вопросов; `--gui` → окно (не открылось — терминал, а без терминала —
уведомление); терминал → TUI; иначе текстовый. **Текстовый вид никогда не спрашивает** — вопрос в
трубе никто не увидит: без `-y` он печатает сводку и команду с `-y` и выходит с кодом 1.

GUI: перед первым окном `gui_deps.prepare()` открывает пробное окно в дочернем процессе (таймаут),
при неудаче повторяет с `LIBGL_ALWAYS_SOFTWARE=1`. Колесо dearpygui проверяется по метке
`.myfox-wheel`: сменилась версия Python — колесо перекачивается до импорта.

## Первая установка (`installer.install`)

Поля формы: каталог (по умолчанию `~/.local/share/myfox/firefox`), канал, профиль (только свои
`myfox-*` или новый), твики да/нет, оформление (только при твиках), язык Firefox (по умолчанию из
`$LANG`; список — с Mozilla до показа формы, без сети форма показывает ошибку и не ставит).

1. Firefox: тарбол в каталог (наш уже стоящий — переиспользуется), метка `.myfox-installed`.
2. Профиль: выбранный или новый `myfox-N` (метка `.myfox-created`).
3. При твиках: релиз твиков в `~/.local/share/myfox/tweaks`; пиннинг профиля; `autoconfig/` в
   установку, `chrome/` и метка `.myfox` в профиль; `myfox.theme` в `user.js`; обе темы в
   `<profile>/extensions/`; букмарклеты из ddblm (недоступен — предупреждение, не ошибка).
4. Сессия KDE Plasma и твики: аддон интеграции с AMO; нет системного пакета
   `plasma-browser-integration` — заметка с командой установки в конце.
5. Себя — в `~/.local/share/myfox/myfox`, лаунчер `bin/myfox`, симлинк `~/.local/bin/myfox`;
   dearpygui рядом; ярлык.
6. State.

После успешной установки форма (TUI и GUI) закрывается сама, а в терминал печатается сводка
(`install_form.summary`: версия Firefox, каталог, профиль, канал, твики, оформление, язык, как
запустить). При ошибке форма остаётся с ошибкой и кнопкой «Закрыть». То, что нужно сказать после
закрытия формы (пиннинг не удался, нет пакета Plasma, GUI не поставился), копится в
`answers.notes` и печатается после сводки.

## Обновление (`refresh.py`)

Сначала проверка обоих треков. Нового нет (и нет `--force`) → одна строка или уведомление, без
диалога. Есть → диалог: «старая → новая» по трекам и «Что нового». `--force` берёт все треки, у
которых есть релиз. Порядок: твики (скачать, применить к установке и профилю, записать версию),
потом ядро (заменить `share/myfox/myfox`; новый код работает со следующего запуска).

## Переустановка (`reinstall.py`)

Firefox качается в соседний временный каталог и подменяет текущий только после полной загрузки —
обрыв оставляет рабочий Firefox. Затем метка, обёртка и ярлык; при профиле с твиками — пиннинг и
`apply.reapply_tweaks()` с сохранёнными выборами. Профиль не трогается.

## Удаление (`uninstall.py`)

Секция профиля и `[Install<HASH>]` убираются из `profiles.ini`/`installs.ini`; удаляются Firefox,
ярлык, симлинк `myfox` (только если он ведёт в нашу копию) и `~/.local/share/myfox`; state
очищается. Профиль остаётся на диске (его потом найдёт новая установка), если не выбрано «удалить и
профиль» / `--remove-profile` — и тогда удаляется только созданный MyFox (`.myfox-created`).
Пункта «удалить» в меню ярлыка нет намеренно: его легко нажать случайно.

## Профили (`profiles.py`)

- Каталог профилей — общий с обычным Firefox: `~/.mozilla/firefox`, если он есть, иначе
  `$XDG_CONFIG_HOME/mozilla/firefox` (так решает сам Firefox 147+).
- Трогаются только свои секции: `[ProfileN]` нашего каталога и `[Install<HASH>]` нашей установки.
  Чужие `[ProfileN]`, `[Install…]`, `Default=1` и каталоги — никогда. Новый `[ProfileN]` — `max+1`.
- **Пиннинг**: хэш установки считает только сам Firefox, поэтому установка один раз запускается
  headless (`--screenshot about:blank`, без `DISPLAY`/`WAYLAND_DISPLAY`), Firefox пишет свою секцию,
  её `Default=` переключается на наш профиль (в `profiles.ini` и `installs.ini`), а профиль, который
  Firefox создал при этом прогоне, удаляется.

## Где что лежит

| Где | Что |
|---|---|
| `~/.local/share/myfox/` | `myfox/` (пакет), `tweaks/`, `dearpygui/`, `bin/myfox`, по умолчанию `firefox/` |
| `<install>/` | Firefox, `defaults/pref/autoconfig.js`, `myfox.cfg`, `myfox/*.js`, `.myfox-installed`, обёртка `firefox-myfox` |
| `<profile>/` | `.myfox` (твики), `.myfox-created`, `chrome/`, `user.js`, `extensions/` |
| `~/.local/bin/myfox` | симлинк на `~/.local/share/myfox/bin/myfox` |
| `~/.local/share/applications/firefox-myfox.desktop` | «Firefox (myfox)» с действием «Обновить MyFox» |
| `~/.local/state/myfox/state.json` | `install_dir`, `profile_dir`, `firefox_version`, `install_hash`, `lang`, `channel`, `theme`, `tweaks`, `core_version`, `tweaks_version`, … |

## Профиль-локальность

Твики работают только в профиле с меткой `.myfox` внутри установки с `.myfox-installed`:
`myfox.cfg` проверяет метку первым делом. Глобального ничего не пишется (`policies.json` нет), темы
и аддоны — в `<profile>/extensions/`. Другой профиль той же установки — обычный Firefox; удалённый
профиль не оставляет следов MyFox.

## Переменные окружения для разработки

| Переменная | Что делает |
|---|---|
| `MYFOX_BOOTSTRAP_URL` | откуда `get.sh` берёт `bootstrap.py` (`file://…` — из рабочей копии) |
| `MYFOX_CORE_DIR` | `bootstrap.py` берёт ядро из этого каталога, не качая |
| `MYFOX_CORE_URL` | архив ядра (путь или URL) вместо релиза — для bootstrap и `refresh` |
| `MYFOX_TWEAKS_LOCAL` | твики и темы из локальной копии CustomFF/tweaks |
| `MYFOX_DDBLM_LOCAL` | букмарклеты из локальной копии ddblm |
| `MYFOX_DEARPYGUI_DIR` | каталог с колёсами dearpygui вместо релиза |
| `MYFOX_NMH_DIRS` | где искать native host Plasma (пустой каталог — «пакета нет») |
| `MYFOX_BIN_DIR` | куда класть симлинк `myfox` вместо `~/.local/bin` |
| `MYFOX_SANDBOX_KEEP_DESKTOP` | `scratch/sandbox.sh` не сбрасывает переменные сессии (тест Plasma) |
