[![Русский](https://img.shields.io/badge/%D0%A0%D1%83%D1%81%D1%81%D0%BA%D0%B8%D0%B9-blue?style=flat&logo=readme&logoColor=white)](README.ru.md)

# MyFox

MyFox is a toolkit for installing and maintaining the official Firefox with
[MyFox tweaks](https://github.com/CustomFF/myfox-tweaks).

## Requirements

- Linux, x86_64 or aarch64: Python 3.8 or newer, curl
- Windows 10 or 11, x64 or ARM64: nothing (MyFox brings its own Python)

## Installing

Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/CustomFF/myfox/master/get.sh | sh
```

Windows, in PowerShell (not as administrator):

```powershell
irm https://raw.githubusercontent.com/CustomFF/myfox/master/get.ps1 | iex
```

Install modes:

- interactive, TUI dialog (the default);
- interactive, GUI dialog – `sh -s -- --gui`;
- non-interactive, default settings – `sh -s -- -y`.

The install is controlled by flags passed after `sh -s --`; on Windows,
`& ([scriptblock]::Create((irm https://raw.githubusercontent.com/CustomFF/myfox/master/get.ps1))) --gui`.
All flags are described in the [documentation](https://github.com/CustomFF/myfox/wiki).

Firefox is installed into your home directory (by default ~/.local/share/myfox/firefox) with its own
profile: a new one, or a copy of another Firefox's profile (also snap and flatpak), with the Firefox
account left in the original, signed in in both, or moved to the copy. No root is needed; a
system-wide Firefox is not affected, its profiles are only read.

After the install, the application menu has a Firefox shortcut and ~/.local/bin has the `myfox`
command (the directory must be in PATH).

On Windows everything goes into %LOCALAPPDATA%\myfox, for your user only, without administrator
rights: Firefox (from Mozilla's own installer), python.org's embeddable Python that MyFox runs on, and
MyFox itself. The Start menu gets a MyFox folder (Firefox, Firefox Private Browsing, Update MyFox), Settings >
Apps lists MyFox (uninstalling goes there), and the `myfox` command works in a new terminal. The GUI dialogs need x64; on ARM64
the dialogs open in the console.

## Updating

Firefox updates itself through Mozilla's built-in updater, not through the distribution's
package manager. The tweaks, the themes and MyFox are updated with `myfox refresh` or the
"Update MyFox" item in the shortcut's context menu (on Windows, in the Start menu's MyFox folder).

Updated tweaks take effect after Firefox restarts. `myfox refresh` offers a restart, and the
shortcut's menu (Linux) and the tweaks' `about:myfox` page have a "Restart" item; windows and tabs
are restored.

The tweaks are made for the current Firefox beta and checked on the stable release before it.
If your Firefox is older and the newest tweaks misbehave on it, go back to the ones made for it:

```text
myfox tweaks                     the installed tweaks version and the Firefox version
myfox tweaks versions            the tweaks versions, one per Firefox version
myfox tweaks use 159             install the tweaks for Firefox 159 and keep them
myfox tweaks use latest          back to the newest; refresh updates them again
```

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
myfox command on    make the firefox command start this Firefox (on Windows also Win+R)
myfox completion    the shell completion script (bash and fish get it on install)
myfox help          the list of all commands
```

## Uninstalling

```bash
myfox uninstall
```

Or, on Windows, Settings > Apps > MyFox > Uninstall.

Removes Firefox, the shortcut, the `myfox` command and MyFox's directory. The profile
(bookmarks, history, passwords) is kept; to delete it too, tick "Also delete the profile" in the
dialog (only profiles MyFox created are deleted). If the install moved the Firefox account into the
copy, it goes back to the original profile.

## about:myfox and security

The tweaks' `about:myfox` page runs the `myfox` command for its buttons (updates, profiles, the
firefox command). It is a page of the browser itself: websites can't open it, embed it or reach it,
and its buttons act only on a click. It runs only what MyFox wrote into the install's `myfox.json`,
with the arguments handed to the program as they are, never through a shell (on Windows `pythonw`,
not a batch file, whose `cmd.exe` would read a quote and an `&` in a profile name as commands).
Replacing those files takes write access to your own home directory, which already allows anything
done as you; that is not something MyFox can or claims to guard against.

## Code signing policy

Free code signing provided by [SignPath.io](https://about.signpath.io), certificate by
[SignPath Foundation](https://signpath.org).

Only `MyFox-Setup.exe` is signed. It is built from this repository by GitHub Actions, and every
release is approved by hand before signing.

Committers, reviewers and approvers: [DayDve](https://github.com/DayDve).

Privacy: MyFox sends no telemetry. It connects only to GitHub, python.org and Mozilla, to download
what it installs and to check for updates.

License: [MPL-2.0](LICENSE).
