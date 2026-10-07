# MyFox — Firefox с твиками одной командой

> **[English version](README.md)**

MyFox ставит Firefox (стабильный или бету) из официального тарбола Mozilla в домашний каталог и
применяет к нему [твики MyFox](https://github.com/CustomFF/tweaks): вкладки-«карточки», скруглённые
углы, переделанная боковая панель с «Загрузками» и «Расширениями», тёмная и светлая темы. Без root,
без пакетов, без pip.

```bash
curl -fsSL https://raw.githubusercontent.com/CustomFF/myfox/master/get.sh | sh
```

В терминале откроется форма установки; `-s -- --gui` — окно вместо неё, `-s -- -y` — установка с
настройками по умолчанию без вопросов:

```bash
curl -fsSL https://raw.githubusercontent.com/CustomFF/myfox/master/get.sh | sh -s -- --gui
```

Из клона — то же через `make`:

```bash
git clone https://github.com/CustomFF/myfox.git && cd myfox
make install                    # форма в терминале; `make install gui` — в окне
MYFOX_INSTALL=AUTO make install # по умолчанию, без вопросов
```

`make refresh`, `make reinstall` и `make uninstall` (каждый с необязательным `gui`) просто
вызывают установленную команду `myfox`, описанную ниже.

## Что нужно

- Linux, x86_64 или aarch64
- Python 3.8 или новее, `curl`
- Для окна (`--gui`) — графическая сессия; библиотеку интерфейса MyFox скачает сам

## Что получится

- **Firefox** в `~/.local/share/myfox/firefox` (или в выбранном каталоге), со своим профилем и
  ярлыком **«Firefox (myfox)»** — с системным Firefox не конфликтует.
- **Твики** только в этом профиле. Любой другой профиль — обычный Firefox; удалите профиль MyFox —
  и от MyFox в нём ничего не останется. Ничего не пишется на всю установку (никаких политик).
- **Обе темы**, тёмная и светлая; выбранная включается при первом запуске, один раз — ваш
  последующий выбор в Firefox не перезаписывается.
- **Интеграция с KDE Plasma** в сессии Plasma.
- **Оформление букмарклетов** из [ddblm](https://github.com/CustomFF/ddblm); закладка «Добавить
  букмарклеты» на панели закладок открывает галерею.
- **Команда `myfox`** в `~/.local/bin` (каталог должен быть в `PATH`).

## Команда `myfox`

```text
myfox browser [аргументы…]                  Запустить установленный Firefox; аргументы — в Firefox
myfox refresh [--force] [--gui]             Обновить твики и сам MyFox
myfox reinstall [--gui]                     Скачать Firefox заново и применить твики
myfox uninstall [--remove-profile] [--gui]  Удалить MyFox
myfox help                                  Этот список
myfox --version
```

Каждая команда сначала показывает, что сделает, и спрашивает — в терминале или в окне с `--gui`;
`-y` — без вопроса. Без терминала (cron, скрипт) ничего не спрашивается: MyFox показывает, что
сделал бы, и команду с `-y`.

- **Обновление.** Firefox обновляется сам. `myfox refresh` обновляет твики и MyFox и показывает,
  что нового; в контекстном меню ярлыка есть «Обновить MyFox». После обновления перезапустите Firefox.
- **Переустановка.** `myfox reinstall` подменяет Firefox только после полной загрузки новой копии;
  профиль остаётся как есть.
- **Удаление.** `myfox uninstall` удаляет Firefox, ярлык, команду `myfox` и `~/.local/share/myfox`.
  Профиль (закладки, история, пароли) остаётся на диске, если не поставить галочку «удалить и
  профиль» или не передать `--remove-profile`.

Пока открыт Firefox из этой установки, ни одна из них не запустится.

## Твики вручную

Твики работают и без MyFox, в том числе на уже установленном Firefox — см.
[CustomFF/tweaks](https://github.com/CustomFF/tweaks#apply-by-hand).

## Разработка

```bash
python3 -m unittest discover -t . -s myfox/tests -p "test_*.py" < /dev/null   # тесты
python3 -m myfox.wizard --dry-run [--gui]                                     # форма установки, ничего не ставит
```

Настоящую установку — только в песочнице: она подменяет `$HOME` и все `$XDG_*`:

```bash
R=$PWD
scratch/sandbox.sh /tmp/mf --fresh -- bash -c "cd /tmp && cat $R/get.sh | \
    MYFOX_BOOTSTRAP_URL=file://$R/bootstrap.py MYFOX_CORE_DIR=$R sh -s -- -y"
```

Ручной чек-лист: [tests/README.md](tests/README.md). Как устроено: [docs/logic.md](docs/logic.md).

**Релиз MyFox:** поднять `__version__` в `myfox/__init__.py`, добавить в `CHANGELOG.md` раздел
`## <версия> — <дата>`, закоммитить, запушить, затем запушить тег `core-<версия>`. Workflow `core.yml`
проверяет, что все три совпадают, и публикует `myfox-core.tar.gz` и `changelog.json`; установленные
копии получат его через `myfox refresh`.

Лицензия: [MIT](LICENSE) © DayDve.
