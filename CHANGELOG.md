# Changelog

## 1.2.0 — 2026-10-26

- Import a profile from another Firefox (the system one, snap, flatpak, or any folder): the install form's «Profile» field or `--import`; a copy becomes the MyFox profile, the original stays. The Firefox account can stay behind, be copied or move into the copy (`--sync`); a profile from a newer Firefox needs a confirmation (`--allow-downgrade`)
- `myfox profile list|new|import|apply|use|remove`: several MyFox profiles, the tweaks applied to a profile made with `firefox -p`, switching which profile MyFox's Firefox opens; without an ID the command asks which one
- `myfox refresh` and `myfox reinstall` update the tweaks in every MyFox profile; `myfox uninstall` handles all of them and moves a Firefox account an import took back into its original profile (`--no-restore-sync` to leave it)
- The install form offers the profiles made with `firefox -p` in MyFox's Firefox and never-opened ones to use as they are
- Reinstall and uninstall notice at once when Firefox is closed while their dialog waits
- Fixed: removing a MyFox profile from Firefox's profile list (for example on uninstall) could hide the profiles listed after it, also another Firefox's

## 1.1.25 — 2026-10-23

- The install form has a «DNS over HTTPS» checkbox (on by default, with the tweaks); unticked, or with `--no-doh`, the tweaks leave DNS over HTTPS off in the new profile

## 1.1.24 — 2026-10-23

- The install no longer leaves the cache of Firefox's throwaway first-run profile and an empty downloads folder behind

## 1.1.23 — 2026-10-23

- The install can be cancelled while it runs: Cancel, Esc, Ctrl+C, closing the window or the terminal; what it has created is removed
- A failed install removes what it has created, so it can be started again right away
- `myfox reinstall` can be cancelled until the new Firefox is swapped in
- While the network doesn't answer, the progress line counts the seconds; after 20 seconds the download stops with an error
- In the install form the shell command's checkbox is «Shell command»

## 1.1.22 — 2026-10-20

- The `firefox` command is called the firefox shell command; in the install form its checkbox is «Shell integration»

## 1.1.21 — 2026-10-20

- «Preferences» in the shortcut's menu opens in the running Firefox instead of a new window
- Links open in the running Firefox even from a terminal whose folder has been deleted

## 1.1.20 — 2026-10-19

- After `myfox refresh` installs a new MyFox, its new parts (such as what about:myfox needs) are in place at once, not only after the next refresh
- Turning the `firefox` command off can leave the `firefox` it replaced aside instead of putting it back
- `myfox` without arguments says what it is and how to restart the browser

## 1.1.19 — 2026-10-19

- Fixes for the `firefox` command switch on the about:myfox page: it always gets an answer it understands, and its notes read cleanly

## 1.1.18 — 2026-10-19

- Groundwork for MyFox settings in the browser: the about:myfox page of the tweaks can find MyFox and turn the `firefox` command on or off

## 1.1.17 — 2026-10-19

- `firefox` on the command line can run this Firefox: a checkbox in the install form, `--firefox-command` for `curl … | sh -s -- -y --firefox-command`, or later `myfox command on` / `off`. A `firefox` already in `~/.local/bin` is kept and put back when it's turned off; MyFox warns when another `firefox` would still be found first

## 1.1.16 — 2026-10-19

- The applications menu shows plain «Firefox», described as «Firefox with the MyFox tweaks»

## 1.1.15 — 2026-10-19

- Tweaks updated while a Firefox update waits for a restart are no longer rolled back by that update

## 1.1.14 — 2026-10-16

- The update window closes itself after the update when «Restart Firefox» is ticked

## 1.1.13 — 2026-10-16

- In the update window, «…and N more» under «What's new» opens the full changelog in Firefox (needs tweaks 159.3 or newer)
- The tweaks and themes come from the renamed repository, CustomFF/myfox-tweaks

## 1.1.12 — 2026-10-16

- `myfox refresh` updates the bookmarklet styling too, when it changes in ddblm, and offers to restart Firefox afterwards
- «Profile Manager» is gone from the shortcut's context menu

## 1.1.11 — 2026-10-14

- Ready for new style folders in the tweaks (such as author style sheets for web pages): they reach the profile with the tweaks update

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
