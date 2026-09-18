# MyFox — Firefox tweaks + installer

> **[Русская версия](README.ru.md)**

MyFox is a set of Firefox user-interface tweaks (floating "card" tabs, rounded corners,
aligned sidebar, Downloads-as-a-sidebar-view, pill-shaped search fields) bundled with a
**one-command installer** that grabs the latest stable Firefox straight from Mozilla's
official tarball and applies the tweaks to it.

This repository only contains the **tweaks and the installer**. Bookmarklets live in a
separate project — **[ddblm](https://github.com/DayDve/ddblm)** (DayDve BookmarkLet Manager). MyFox
downloads the ready-made tweak files (CSS + icons) from ddblm over raw.githubusercontent.com;
you do not need to build or clone ddblm yourself.

## Highlights

- **One command install** — `./install.sh` downloads Firefox from `download.mozilla.org`
  and applies everything: autoconfig, styles, required `about:config` prefs.
- **Re-runs are smart (idempotent)** — the browser is not re-downloaded, your chosen
  profile is reused, tweaks are refreshed.
- **`uninstall.sh`** removes tweaks and can restore a backup of a previously occupied
  install directory.
- **Optional bookmarklet tweaks** — icons, hidden labels, and a link to the
  bookmarklet gallery page (taken from the separate **ddblm** project).
- **Optional add-ons** — uBlock Origin and a dark theme are installed by default into
  `<profile>/extensions` (per-profile, so other profiles stay pristine); KDE Plasma integration is available on request.
- **No root required** — Firefox lands in `~/.local/share/firefox` and the desktop shortcut
  is named **«Firefox (myfox)»** so it never conflicts with a system-installed Firefox.

## Requirements

- Linux, bash 4+
- `curl`, `tar`, `grep`, `awk` (and `python3` only for bookmarklet tweaks)

## Quick start

```bash
git clone https://github.com/DayDve/myfox.git
cd myfox
./install.sh
```

You will be prompted about bookmarklet tweaks at the end (say *n* to skip).

## Options

```text
  --prefix <path>        Install Firefox to a custom path (default ~/.local/share/firefox).
                         The path is remembered for future runs.
  --reinstall            Force re-download of Firefox even if already installed.
  --profile <path>       Use a specific Firefox profile directory (skips detection).
  --nobl                 Skip bookmarklet tweaks.
  --noaddons             Skip add-ons (uBlock, theme, Plasma integration).
  --plasma-integration   Force-install the KDE Plasma integration add-on (no prompt),
                         even outside a Plasma session.
  --noplasma             Skip KDE Plasma integration even under Plasma.
  -y, --yes              Non-interactive (no prompts).
  -h, --help             Show help.
```

## Updating

```bash
./install.sh          # refreshes tweaks; does NOT re-download Firefox
./install.sh --reinstall   # also pulls the latest Firefox build
```

## Uninstalling

```bash
./uninstall.sh [-y]
```

It removes the tweaks (autoconfig files, chrome styles), deletes the desktop entry and
asks whether to keep or delete the Firefox installation itself. If the install directory
was previously occupied by a hand-installed Firefox, a backup was created — `uninstall.sh`
offers to restore it.

## What gets installed

| Where | What |
|---|---|
| `<install>/defaults/pref/autoconfig.js` | enables the Autoconfig system |
| `<install>/firefox.cfg` | privileged JS: registers agent sheet, patches sidebar/downloads, sets profile-local prefs |
| `<profile>/chrome/userChrome.css` | user-sheet styles |
| `<profile>/chrome/agent_overrides.css` | agent-sheet styles |
| `<profile>/.myfox` | profile marker — only marked profiles get tweaks |
| `~/.local/share/applications/firefox-myfox.desktop` | launcher «Firefox (myfox)» |
| `~/.local/state/myfox/install.json` | installer state (see [docs/logic.md](docs/logic.md)) |

Required prefs (`toolkit.legacyUserProfileCustomizations.stylesheets`, `sidebar.revamp`)
are set automatically by `firefox.cfg` on first start — **but only for the profile marked by
myfox** (`<profile>/.myfox`, or fallback: a legacy profile that already has
`chrome/agent_overrides.css`). Any other profile stays a pristine, unmodified Firefox:
`firefox.cfg` refuses to apply anything to it (no prefs, no styles, no window tweaks).

On the marked profile, `firefox.cfg` also adds two bookmarks to the Bookmarks Toolbar:
**«Расширенные настройки»** (about:config) and **«Добавить букмарклеты»** (the ddblm
gallery — bilingual, opens in Russian as `?lang=ru` for a Russian-locale Firefox), and
activates the installed Chrome Dark theme (when present).

## Add-ons

By default the installer puts three things into the Firefox install:

- **uBlock Origin** — adblock (installed by default).
- **Chrome Dark theme** — a dark UI theme (installed by default).
- **KDE Plasma integration** — installed silently under a Plasma session (or with `--plasma-integration`).

The Plasma integration add-on additionally requires the system package
`plasma-browser-integration` (the native-messaging host). The installer checks it:
if the package is missing, a note with the install command is printed at the end of
the setup — no `sudo` prompts interrupting the dialogs. Use `--noplasma` to skip it
even under Plasma, and `--noaddons` to skip all add-ons.

## Bookmarklets (ddblm)

Bookmarklets are a [separate project](https://github.com/DayDve/ddblm). At install time you
may opt in to the tweaks (custom icons + hidden labels on the Bookmarks Toolbar taken from
ddblm) and a link to the bookmarklet gallery hosted on GitHub Pages
([https://daydve.github.io/ddblm/](https://daydve.github.io/ddblm/)). The installer copies
`docs/blm_panel.css` and **all** `icons/*.svg` from ddblm (raw.githubusercontent.com for
published ddblm; a local checkout via `MYFOX_DDBLM_LOCAL=/path` while developing)
into `<profile>/chrome/`, so you do not need to clone or build ddblm yourself.

After install, open the gallery (click **«Добавить букмарклеты»** on the Bookmarks Toolbar),
enable the toolbar (`Ctrl+Shift+B`) and drag the cards onto it.

## Applying to an existing Firefox (manual)

> The installer only creates a fresh tarball install. To attach the tweaks to an already
> installed Firefox, do these steps by hand:

1. **Locate the install directory**, e.g. `/usr/lib/firefox` (or `~/.local/share/firefox`).
2. Copy `autoconfig/autoconfig.js` into `<install>/defaults/pref/`.
3. Copy `autoconfig/firefox.cfg` into `<install>/` (next to the `firefox` binary).
   *If a `firefox.cfg` already exists there, back it up first.*
4. Copy `chrome/userChrome.css` and `chrome/agent_overrides.css` into your profile's
   `chrome/` directory (path is shown at `about:support` → *Profile Folder*).
5. Restart Firefox. The required prefs are applied automatically via autoconfig.

> **Note:** editing `/usr/lib/firefox` requires sudo. On systems where you cannot write to
> the install directory, this approach won't work — use the tarball install instead.

## What the tweaks look like

- Web pages render as a floating card with rounded corners and even margins.
- Sidebar bottom aligns with the card bottom.
- The sidebar toggle button highlights when the panel is open and toggles on a single click.
- History/Bookmarks search fields become compact pills that match the address bar on focus.
- Compact bookmarklets with custom icons and hidden text labels (when ddblm tweaks enabled).

## Development

Hot-reload of styles without restarting the browser is possible via the RDP proxy
(`firefox_rdp_proxy.py`, lives in the ddblm project):

```bash
python3 firefox_rdp_proxy.py 34423     # from a ddblm checkout
python3 scratch/reload_userchrome.py
```

Architecture details: [docs/logic.md](docs/logic.md).
Test plan: [tests/README.md](tests/README.md).

License: [MIT](LICENSE) © DayDve.