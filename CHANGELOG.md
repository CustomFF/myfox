# Changelog

## 1.1.10 — 2026-10-09

- `myfox refresh` updates the themes too, when a new themes release comes out, and offers to restart Firefox afterwards
- Themes that haven't changed are no longer downloaded again with every tweaks update or reinstall

## 1.1.9 — 2026-10-08

- `myfox refresh` keeps the shortcut up to date: new context-menu items, such as «Restart», arrive with the update, no reinstall needed

## 1.1.8 — 2026-10-08

- The shortcut's context menu has «Restart»: Firefox restarts with its windows and tabs back (needs tweaks 158.1 or newer; an existing install gets it after `myfox reinstall`)

## 1.1.7 — 2026-10-08

- After the tweaks are updated, `myfox refresh` offers to restart a running Firefox so they apply right away, with all windows and tabs restored (needs tweaks 158.1 or newer already running)

## 1.1.6 — 2026-10-08

- No more pause after downloading Firefox: it is unpacked in a single pass, and the progress bar moves right away
- On KDE Plasma a new or removed shortcut is picked up at once

## 1.1.5 — 2026-10-08

- In the terminal interface the focused field, checkbox or list row is highlighted like a focused button, so it's clear where the keyboard is
- Downloading Firefox no longer shows megabytes: the progress bar is enough
- Running the install command from a folder that has a `myfox` folder in it no longer runs that code instead of the downloaded MyFox

## 1.1.4 — 2026-10-08

- After a successful install the window closes by itself, and the terminal shows a summary: what was installed, where, and how to launch it

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
