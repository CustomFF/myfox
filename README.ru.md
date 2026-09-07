# MyFox — твики для Firefox + инсталлер

> **[English version](README.md)**

MyFox — набор твиков интерфейса Firefox (плавающая «карточка» вкладок, скруглённые углы,
выровненный сайдбар, загрузки как вид боковой панели, поля поиска-«пилюли») в комплекте с
**инсталлером в одну команду**, который скачивает последний стабильный Firefox
с официального тарбола Mozilla и применяет на него твики.

В этом репозитории — **твики и инсталлер**. Букмарклеты живут в отдельном проекте
**[ddbml](https://github.com/.../ddbml)** и подключаются git submodule'ом в `bookmarklets/`.

## Что умеет

- **Установка одной командой** — `./install.sh` скачивает Firefox с `download.mozilla.org`
  и применяет всё: autoconfig, стили, нужные префы `about:config`.
- **Повторные запуски умные (идемпотентны)** — браузер не качается заново, выбранный
  профиль переиспользуется, твики обновляются.
- **`uninstall.sh`** — удаляет твики и может восстановить бэкап, если по целевому
  каталогу раньше стоял вручную установленный Firefox.
- **Опциональные твики букмарклетов** (`blm`) — кастомные иконки, скрытые подписи,
  ссылка на страницу галереи букмарклетов.
- **Без root** — Firefox ставится в `~/.local/share/firefox`, ярлык называется
  **«Firefox (myfox)»** и не конфликтует с системным.

## Требования

- Linux, bash 4+
- `curl`, `tar`, `grep`, `awk` (для твиков букмарклетов дополнительно `python3`)

## Быстрый старт

```bash
git clone --recurse-submodules https://github.com/ваш/dbrepo-myfox.git myfox
cd myfox
./install.sh
```

В конце спросят про твики букмарклетов (можно ответить *n*).

## Параметры

```text
  --prefix <path>    Поставить Firefox в другой путь (по умолчанию ~/.local/share/firefox).
                     Путь запоминается для следующих запусков.
  --reinstall        Принудительно перекачать Firefox, даже если он уже установлен.
  --profile <path>   Использовать конкретный каталог профиля (минуя определение).
  --noblm            Не применять твики букмарклетов.
  -y, --yes          Работать без подтверждений.
  -h, --help         Показать справку.
```

## Обновление

```bash
./install.sh               # обновляет твики; Firefox НЕ перекачивает
./install.sh --reinstall   # заодно забирает свежий Firefox
```

## Удаление

```bash
./uninstall.sh [-y]
```

Удаляет твики (autoconfig-файлы, стили chrome), убирает desktop-ярлык и спрашивает,
оставить ли саму установку Firefox. Если каталог инсталляции раньше был занят вручную
поставленным Firefox — есть бэкап, и `uninstall.sh` предложит его восстановить.

## Что ставится

| Куда | Что |
|---|---|
| `<install>/defaults/pref/autoconfig.js` | включает систему Autoconfig |
| `<install>/firefox.cfg` | privileged JS: регистрирует agent sheet, правит сайдбар/загрузки, ставит префы |
| `<profile>/chrome/userChrome.css` | стили user-sheet |
| `<profile>/chrome/agent_overrides.css` | стили agent-sheet |
| `~/.local/share/applications/firefox-myfox.desktop` | ярлык «Firefox (myfox)» |
| `~/.local/state/myfox/install.json` | состояние инсталлера (см. [docs/logic.md](docs/logic.md)) |

Необходимые префы (`toolkit.legacyUserProfileCustomizations.stylesheets`, `sidebar.revamp`,
`sidebar.verticalTabs`) выставляются автоматически `firefox.cfg` при первом старте.

## Букмарклеты (ddbml)

Букмарклеты — это [отдельный проект](https://github.com/.../ddbml). При установке можно
подключить твики `blm` (кастомные иконки + скрытые подписи на панели закладок) и ссылку
на галерею, размещённую на GitHub Pages. Управлять вручную:

```bash
cd bookmarklets
git submodule update --init --recursive   # если клонировали без --recurse-submodules
./blm config set ff_profile /path/to/profile
./blm build
./blm patchff
```

Затем откройте `bookmarklets/docs/index.html`, включите панель закладок (`Ctrl+Shift+B`)
и перетащите карточки на неё.

## Натянуть на уже установленный Firefox (вручную)

> Инсталлер ставит только с нуля (тарбол). Чтобы навесить твики на существующий
> браузер — проделайте шаги вручную:

1. **Найдите каталог установки**, например `/usr/lib/firefox` (или `~/.local/share/firefox`).
2. Скопируйте `autoconfig/autoconfig.js` в `<install>/defaults/pref/`.
3. Скопируйте `autoconfig/firefox.cfg` в `<install>/` (рядом с бинарником `firefox`).
   *Если там уже есть свой `firefox.cfg` — сначала сделайте бэкап.*
4. Скопируйте `chrome/userChrome.css` и `chrome/agent_overrides.css` в каталог `chrome/`
   вашего профиля (путь показан на `about:support` → *Папка профиля*).
5. Перезапустите Firefox. Нужные префы применятся автоматически через autoconfig.

> **Важно:** правка `/usr/lib/firefox` требует sudo. Если писать в каталог установки
> нельзя — используйте установку через тарбол.

## Что дают твики

- Веб-страница выглядит как плавающая карточка со скруглёнными углами и ровными отступами.
- Низ сайдбара выровнен с низом карточки.
- Кнопка переключения сайдбара подсвечивается, когда панель открыта, и переключает один клик.
- Поля поиска в истории/закладках становятся компактными «пилюлями» и при фокусе
  подсвечиваются как адресная строка.
- Компактные букмарклеты с кастомными иконками и скрытым текстом (при включённых твиках `blm`).

## Разработка

Горячая перезагрузка стилей без перезапуска браузера — через RDP-прокси:

```bash
(cd bookmarklets && python3 firefox_rdp_proxy.py 34423)
python3 scratch/reload_userchrome.py
```

Архитектура: [docs/logic.md](docs/logic.md). Правила для агентов: [AGENTS.md](AGENTS.md).
План тестов: [tests/README.md](tests/README.md).