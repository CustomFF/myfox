# Changelog

## 1.1.3 — 2026-10-07

- The reinstall window shows a beta Firefox version whole (158.0b4, not 4)

## 1.1.2 — 2026-10-07

- Installing on aarch64 works: it asked Mozilla for a download that doesn't exist
- Uninstalling no longer leaves an empty state file behind

## 1.1.1 — 2026-10-07

- Uninstalling with "also delete the profile" now also deletes a profile installed without the tweaks
- The `-v` option is gone: it did nothing

## 1.1.0 — 2026-10-07

- `myfox reinstall` and `myfox uninstall` open the same window as the update, in the terminal or with `--gui`: what will happen, then progress
- Uninstalling can delete the profile too (bookmarks, history, passwords): a checkbox, off by default, or `--remove-profile`; otherwise the profile stays on disk
- Reinstalling replaces Firefox only once the new copy is fully downloaded; a failed download leaves the current one working
- Both refuse to run while Firefox from this install is open
- Without a terminal nothing is asked any more: MyFox shows what it would do and the command to run with `-y`
- In the terminal interface, keys pressed quickly (a held arrow key) are no longer lost

## 1.0.2 — 2026-10-07

- The graphical window no longer hangs where OpenGL can't use the graphics card: it falls back to software rendering, or the install carries on in the terminal
- The interface language follows LANGUAGE / LC_ALL / LC_MESSAGES / LANG even when the system lacks that locale
- Tying the MyFox profile to Firefox no longer depends on the graphical session
- Versions in the update progress no longer show the "core-" tag prefix

## 1.0.1 — 2026-10-07

- After the install, a note in the terminal when the MyFox profile couldn't be tied to Firefox (Firefox didn't start); `myfox reinstall` now ties it
- No more Python warning about unpacking archives on Python 3.13

## 1.0.0 — 2026-10-07

- The installer and updater are rewritten in Python and need nothing beyond python3 and curl
- One install window, in the terminal or graphical (--gui), with a language search, theme and profile choice
- Firefox goes into ~/.local/share/myfox/firefox, next to MyFox itself
- The tweaks are downloaded from their own releases and updated on their own
- `myfox refresh` checks for updates first and shows what's new before updating
- "Update MyFox" in the Firefox shortcut's context menu
- In a KDE Plasma session the Plasma Integration add-on is installed, with a hint when the system package is missing
