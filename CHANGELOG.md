# Changelog

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
