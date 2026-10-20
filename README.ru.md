[![English](https://img.shields.io/badge/English-blue?style=flat&logo=readme&logoColor=white)](README.md)

# MyFox

MyFox — инструментарий для установки и сопровождения официального Firefox с
[MyFox tweaks](https://github.com/CustomFF/myfox-tweaks).

## Требования

- Linux, x86_64 или aarch64
- Python 3.8 или новее
- curl

## Установка

```bash
curl -fsSL https://raw.githubusercontent.com/CustomFF/myfox/master/get.sh | sh
```

Режимы установки:

- в терминале (по умолчанию) — форма в текстовом интерфейсе;
- в окне — `sh -s -- --gui`;
- автоматический — `sh -s -- -y`: параметры по умолчанию, без вопросов.

Установка управляется флагами, они передаются после `sh -s --`. Все флаги описаны в
[документации](https://github.com/CustomFF/myfox/wiki).

Firefox устанавливается в домашний каталог (по умолчанию ~/.local/share/myfox/firefox) с отдельным
профилем. Права root не нужны, установленный в системе Firefox не затрагивается.

После установки в меню приложений появляется ярлык Firefox, в ~/.local/bin — команда `myfox`
(каталог должен быть в PATH).

## Обновление

Firefox обновляется сам, встроенным механизмом Mozilla, а не через пакетный менеджер
дистрибутива. Твики, темы и MyFox обновляются командой `myfox refresh` или пунктом
«Обновить MyFox» в контекстном меню ярлыка.

Обновлённые твики применяются после перезапуска Firefox. `myfox refresh` предлагает перезапуск,
в меню ярлыка есть пункт «Перезапустить»; окна и вкладки при перезапуске восстанавливаются.

## Другие команды

```text
myfox reinstall     повторно скачать Firefox; профиль не меняется
myfox command on    запускать этот Firefox командой firefox
myfox help          список всех команд
```

## Удаление

```bash
myfox uninstall
```

Удаляются Firefox, ярлык, команда `myfox` и ~/.local/share/myfox. Профиль (закладки, история,
пароли) сохраняется; чтобы удалить и его, отметьте «Удалить и профиль» в диалоге.

Лицензия: [MIT](LICENSE).
