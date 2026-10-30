[![Русский](https://img.shields.io/badge/%D0%A0%D1%83%D1%81%D1%81%D0%BA%D0%B8%D0%B9-blue?style=flat&logo=readme&logoColor=white)](README.ru.md)

# MyFox

MyFox is a toolkit for installing and maintaining the official Firefox with
[MyFox tweaks](https://github.com/CustomFF/myfox-tweaks).

## Requirements

- Linux, x86_64 or aarch64
- Python 3.8 or newer
- curl

## Installing

```bash
curl -fsSL https://raw.githubusercontent.com/CustomFF/myfox/master/get.sh | sh
```

Install modes:

- interactive, TUI dialog (the default);
- interactive, GUI dialog — `sh -s -- --gui`;
- non-interactive, default settings — `sh -s -- -y`.

The install is controlled by flags passed after `sh -s --`. All flags are described in the
[documentation](https://github.com/CustomFF/myfox/wiki).

Firefox is installed into your home directory (by default ~/.local/share/myfox/firefox) with its own
profile: a new one, or a copy of another Firefox's profile (also snap and flatpak), with the Firefox
account left in the original, signed in in both, or moved to the copy. No root is needed; a
system-wide Firefox is not affected, its profiles are only read.

After the install, the application menu has a Firefox shortcut and ~/.local/bin has the `myfox`
command (the directory must be in PATH).

## Updating

Firefox updates itself through Mozilla's built-in updater, not through the distribution's
package manager. The tweaks, the themes and MyFox are updated with `myfox refresh` or the
"Update MyFox" item in the shortcut's context menu.

Updated tweaks take effect after Firefox restarts. `myfox refresh` offers a restart, and the
shortcut's menu has a "Restart" item; windows and tabs are restored.

## Profiles

```text
myfox profile list               MyFox's profiles and the ones it can take
myfox profile new                a new profile with the tweaks
myfox profile import <ID>        copy (or --move) another Firefox's profile into a new one
myfox profile use <ID>           the profile this Firefox opens
myfox profile rename <ID> <NAME>
myfox profile remove <ID>
```

Making, importing, renaming and deleting profiles work with Firefox open; several MyFox profiles can
be open at once, each in its own window. Only switching the default profile needs Firefox closed,
MyFox closes and reopens it with the session kept. The same is on the tweaks' `about:myfox` page.
More in the [documentation](https://github.com/CustomFF/myfox/wiki/Profiles).

## Other commands

```text
myfox reinstall     download Firefox again; the profile is kept
myfox command on    make the firefox shell command start this Firefox
myfox completion    the shell completion script (bash and fish get it on install)
myfox help          the list of all commands
```

## Uninstalling

```bash
myfox uninstall
```

Removes Firefox, the shortcut, the `myfox` command and ~/.local/share/myfox. The profile
(bookmarks, history, passwords) is kept; to delete it too, tick "Also delete the profile" in the
dialog (only profiles MyFox created are deleted). If the install moved the Firefox account into the
copy, it goes back to the original profile.

License: [MPL-2.0](LICENSE).
