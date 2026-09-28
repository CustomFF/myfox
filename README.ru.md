# MyFox — твики для Firefox + инсталлер

> **[English version](README.md)**

MyFox — набор твиков интерфейса Firefox (плавающая «карточка» вкладок, скруглённые углы,
выровненный сайдбар, загрузки и расширения как виды боковой панели, компактные поля поиска) в комплекте с
**инсталлером**, который скачивает Firefox (stable или beta) с официального тарбола Mozilla
и применяет на него твики.

В этом репозитории — **твики и инсталлер**. Букмарклеты живут в отдельном проекте
**[ddblm](https://github.com/DayDve/ddblm)** (DayDve BookmarkLet Manager). MyFox скачивает
готовые твик-файлы (CSS + иконки) из ddblm через raw.githubusercontent.com — клонировать
или собирать ddblm самостоятельно не нужно.

## Что умеет

- **Мастер или одна команда** — в терминале пошаговый мастер (каталог установки, stable/beta,
  язык Firefox, профиль, твики, тёмное/светлое оформление); с `-y` работает без вопросов.
- **Всё в профиле** — твики применяются только к профилю, который пометил инсталлер
  (`<profile>/.myfox`). Любой другой профиль в той же инсталляции — обычный Firefox; удалил
  профиль — от MyFox в нём ничего не осталось. Никаких политик, ничего «на всю установку».
- **Обе темы, выбираешь ты** — тёмная и светлая темы Google Chrome ставятся в профиль;
  выбранная включается при первом запуске (один раз — твой последующий выбор не перезаписывается).
- **Интеграция с KDE Plasma** — дополнение ставится в сессии Plasma (или с `--plasma-integration`).
- **Настоящая команда после установки** — `myfox browser`, `myfox update`, `myfox uninstall`.
- **Без root** — Firefox ставится в `~/.local/share/firefox`, ярлык называется
  **«Firefox (myfox)»** и не конфликтует с системным.

## Требования

- Linux (x86_64 или aarch64), bash 4+
- `curl`, `tar`, `awk`
- `dialog` или `whiptail` — по желанию (без них мастер работает на обычных вопросах)

## Быстрый старт

Из клона:

```bash
git clone https://github.com/DayDve/myfox.git
cd myfox
./bin/myfox-core install          # или: make install ARGS="-y"
```

Инсталлер рассчитан на раздачу дистрибутивным тарболом плюс `get.sh`
(`curl -fsSL <url>/get.sh | bash`); публичного адреса пока нет — как поднять его локально,
см. [Разработка](#разработка).

## Команда `myfox`

Инсталлер кладёт команду `myfox` в `~/.local/bin` (проверь, что каталог в `PATH`):

```text
myfox                       Строка статуса и справка (браузер не запускает)
myfox browser [args…]       Запустить установленный браузер; все аргументы уходят в Firefox
myfox ff [args…]            Синоним `myfox browser`
myfox update [--reinstall]  Переприменить твики (с --reinstall — ещё и перекачать Firefox)
myfox uninstall [-y]        Удалить MyFox
myfox help [команда]        Справка по одной команде
```

## Параметры установки

```text
  --prefix <path>        Поставить Firefox в другой путь (по умолчанию ~/.local/share/firefox).
  --profile <path>       Использовать конкретный каталог профиля (минуя определение).
  --lang <code>          Язык Firefox (проверяется по каталогу Mozilla; см. --list-languages).
                         Заодно выбирает язык интерфейса самого инсталлера (ru/en).
  --list-languages       Показать доступные языки Firefox и выйти.
  --reinstall            Принудительно перекачать Firefox, даже если он уже установлен.
  --browser-only         Только тарбол и ярлык: без профиля и твиков.
  --nobl                 Не применять твики букмарклетов.
  --theme <dark|light>   Оформление нового профиля (по умолчанию: dark).
  --plasma-integration   Поставить дополнение KDE Plasma integration (без вопроса),
                         даже вне сессии Plasma.
  --noplasma             Не ставить интеграцию с Plasma даже под Plasma.
  --force                Установить, даже если уже установлено.
  -y, --yes              Работать без подтверждений.
  -v, --verbose          Подробный вывод.
  -h, --help             Показать справку.
```

Работают и `--флаг значение`, и `--флаг=значение`. `update` принимает `--reinstall`, `-y`, `-v`;
`uninstall` — `-y`, `-v`; остальные флаги для этих команд отклоняются, а не молча игнорируются.
Канал stable/beta выбирается в мастере (без мастера — stable).

## Обновление

```bash
myfox update               # обновляет твики; Firefox НЕ перекачивает
myfox update --reinstall   # ещё и скачивает свежую сборку Firefox
```

Стили (`userChrome.css`) и `myfox.cfg` читаются при старте браузера — после обновления
перезапусти Firefox.

## Удаление

```bash
myfox uninstall [-y]
```

Удаляет приложение (файлы autoconfig, ярлык, команду `myfox`) и спрашивает, удалять ли профиль
MyFox. У профиля, указанного через `--profile`, снимаются только твики MyFox (твой собственный
`userChrome.css` возвращается из бэкапа).

## Что устанавливается

| Где | Что |
|---|---|
| `~/.local/share/firefox` (`--prefix`) | сам Firefox, плюс `defaults/pref/autoconfig.js`, `myfox.cfg` и `myfox/*.js` (privileged JS: регистрирует agent-листы, патчит сайдбар/загрузки, ставит профильные префы) |
| `~/.local/share/myfox/` | сам инсталлер: `bin/myfox`, `bin/myfox-core`, `lib/`, `i18n/`, `assets/` — чтобы `update`/`uninstall`/`help` работали офлайн |
| `~/.local/bin/myfox` | символическая ссылка на `~/.local/share/myfox/bin/myfox` |
| `<profile>/chrome/userChrome.css` + `user/*.css` | user-sheet стили (вкладки, панели, карточки, …) |
| `<profile>/chrome/agent/*.css` | agent-sheet стили (регистрирует `myfox.cfg`; достают внутрь shadow DOM) |
| `<profile>/extensions/` | обе темы, по желанию интеграция с Plasma |
| `<profile>/user.js` | одна строка `myfox.theme`, `myfox.cfg` читает её один раз |
| `<profile>/.myfox` | маркер профиля — твики получает только помеченный профиль |
| `~/.local/share/applications/firefox-myfox.desktop` | ярлык «Firefox (myfox)» |
| `~/.local/state/myfox/state` | состояние инсталлера (плоский `key=value`, см. [docs/logic.md](docs/logic.md)) |

Профили лежат в `~/.mozilla/firefox`, если этот каталог есть, иначе (Firefox 147+ на свежей
системе) — в `$XDG_CONFIG_HOME/mozilla/firefox`; распознаются и расположения flatpak/snap.

Нужные префы (`toolkit.legacyUserProfileCustomizations.stylesheets`, `sidebar.revamp`) ставит
`myfox.cfg` при первом старте — **но только для помеченного профиля**. Любой другой профиль
остаётся чистым Firefox: `myfox.cfg` отказывается что-либо к нему применять (ни префов, ни
стилей, ни правок окна).

На помеченном профиле `myfox.cfg` ещё, один раз: добавляет на панель закладок две закладки —
**«Расширенные настройки»** (about:config) и **«Добавить букмарклеты»** (галерея ddblm —
двуязычная, для русскоязычного Firefox открывается как `?lang=ru`) — включает выбранную тему и
выставляет стартовые настройки свежего профиля (компактный интерфейс, ИИ/телеметрия/спонсоры выключены).

## Дополнения

- **Темы Google Chrome Dark / Light** — ставятся обе; шаг мастера (или `--theme`) решает, какая
  включена, и заодно выставляет «внешний вид веб-сайтов» Firefox в соответствие.
- **Интеграция с KDE Plasma** — ставится молча в сессии Plasma (или с `--plasma-integration`).

Дополнению Plasma дополнительно нужен системный пакет `plasma-browser-integration` (native-messaging
host). Инсталлер проверяет его наличие: если пакета нет, в конце установки печатается заметка с
командой установки — никаких `sudo`-промптов посреди диалогов. `--noplasma` не ставит дополнение
даже под Plasma.

## Букмарклеты (ddblm)

Букмарклеты — [отдельный проект](https://github.com/DayDve/ddblm). Твики (кастомные иконки и
скрытые подписи на панели закладок — из ddblm) идут вместе с «твики: да»; `--nobl` их пропускает.
Инсталлер копирует `docs/blm_panel.css` и **все** `icons/*.svg` из ddblm (raw.githubusercontent.com
для опубликованного ddblm; локальная копия через `MYFOX_DDBLM_LOCAL=/path` при разработке) в
`<profile>/chrome/`, так что клонировать и собирать ddblm самому не нужно. Сама галерея живёт на
GitHub Pages ([https://daydve.github.io/ddblm/](https://daydve.github.io/ddblm/)).

После установки открой галерею (клик по **«Добавить букмарклеты»** на панели закладок), включи
панель (`Ctrl+Shift+B`) и перетащи карточки на неё.

## Навеска на существующий Firefox (вручную)

> Инсталлер создаёт только свежую установку из тарбола. Чтобы навесить твики на уже
> установленный Firefox, выполни шаги вручную:

1. **Найди каталог установки**, например `/usr/lib/firefox` (или `~/.local/share/firefox`).
2. Скопируй `autoconfig/autoconfig.js` в `<install>/defaults/pref/`.
3. Скопируй `autoconfig/myfox.cfg` и каталог `autoconfig/myfox/` в `<install>/` (рядом с
   бинарником `firefox`).
4. Скопируй `chrome/userChrome.css`, `chrome/user/` и `chrome/agent/` в каталог `chrome/`
   своего профиля (путь показан в `about:support` → *Папка профиля*).
5. Создай файл-маркер `<profile>/.myfox` — без него `myfox.cfg` профиль не трогает.
6. Перезапусти Firefox. Нужные префы выставятся сами через autoconfig.

> **Важно:** правка `/usr/lib/firefox` требует sudo. Если писать в каталог установки нельзя,
> этот способ не сработает — используй установку из тарбола.

## Как выглядят твики

- Страницы рисуются плавающей карточкой со скруглёнными углами и ровными отступами; сайдбар — тоже.
- Один радиус скругления (`--myfox-radius`) везде вместо разнокалиберных «пилюль» Nova.
- Плотные строки в панелях сайдбара (история, синхронизированные вкладки, загрузки, пароли), один
  базовый шрифт 12px на внутренних страницах, круглые кнопки закрытия, синий акцент вместо
  фиолетового Nova.
- Кнопка сайдбара подсвечивается при открытой панели и переключается одним кликом.
- Компактные букмарклеты с кастомными иконками и скрытыми подписями (если не `--nobl`).

## Разработка

Сборки и автотестов нет; ручные чек-листы — в [tests/README.md](tests/README.md). Перед сдачей:

```bash
bash -n get.sh bin/myfox-core lib/*.sh scripts/*.sh
shellcheck -S error get.sh bin/myfox-core lib/*.sh scripts/*.sh
python3 -m py_compile scratch/*.py        # если трогали scratch/*.py
```

Никогда не запускай инсталлер на реальном `$HOME` при разработке — есть песочница, которая
перенаправляет `$HOME` и все `$XDG_*`:

```bash
scratch/sandbox.sh /tmp/mf --fresh -- ./bin/myfox-core install -y --nobl
scratch/sandbox.sh /tmp/mf -- ./bin/myfox-core update -y
scratch/sandbox.sh /tmp/mf -- ./bin/myfox-core uninstall -y
```

Чтобы проверить настоящий путь `curl | bash` локально: `scripts/dev-serve.sh` собирает
`dist/myfox-dist.tar.gz` и раздаёт его (вместе с `get.sh`, который смотрит на себя же) на
`http://127.0.0.1:8787`.

Горячая перезагрузка стилей без рестарта браузера возможна через RDP-прокси
(`firefox_rdp_proxy.py`, живёт в проекте ddblm):

```bash
python3 firefox_rdp_proxy.py 34423     # из клона ddblm
python3 scratch/reload_userchrome.py
```

Архитектура: [docs/logic.md](docs/logic.md). Правила для агентов: [AGENTS.md](AGENTS.md).

Лицензия: [MIT](LICENSE) © DayDve.
