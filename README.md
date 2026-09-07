# MyFox — Firefox tweaks + installer

> **[Русская версия](README.ru.md)**

MyFox is a set of Firefox user-interface tweaks (floating "card" tabs, rounded corners,
aligned sidebar, Downloads-as-a-sidebar-view, pill-shaped search fields) bundled with a
**one-command installer** that grabs the latest stable Firefox straight from Mozilla's
official tarball and applies the tweaks to it.

This repository only contains the **tweaks and the installer**. Bookmarklets live in a
separate project — **[ddblm](https://github.com/DayDve/ddblm)** (DayDve BookmarkLet Manager) — attached as a git submodule
under `bookmarklets/`.

## Highlights

- **One command install** — `./install.sh` downloads Firefox from `download.mozilla.org`
  and applies everything: autoconfig, styles, required `about:config` prefs.
- **Re-runs are smart (idempotent)** — the browser is not re-downloaded, your chosen
  profile is reused, tweaks are refreshed.
- **`uninstall.sh`** removes tweaks and can restore a backup of a previously occupied
  install directory.
- **Optional bookmarklet tweaks** (`blm`) — icons, hidden labels, and a link to the
  bookmarklet gallery page.
- **No root required** — Firefox lands in `~/.local/share/firefox` and the desktop shortcut
  is named **«Firefox (myfox)»** so it never conflicts with a system-installed Firefox.

## Requirements

- Linux, bash 4+
- `curl`, `tar`, `grep`, `awk` (and `python3` only for bookmarklet tweaks)

## Quick start

```bash
git clone --recurse-submodules https://github.com/DayDve/myfox.git myfox
cd myfox
./install.sh
```

You will be prompted about bookmarklet tweaks at the end (say *n* to skip).

## Options

```text
  --prefix <path>    Install Firefox to a custom path (default ~/.local/share/firefox).
                     The path is remembered for future runs.
  --reinstall        Force re-download of Firefox even if already installed.
  --profile <path>   Use a specific Firefox profile directory (skips detection).
  --noblm            Skip bookmarklet tweaks.
  -y, --yes          Non-interactive (no prompts).
  -h, --help         Show help.
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
| `<install>/firefox.cfg` | privileged JS: registers agent sheet, patches sidebar/downloads, sets prefs |
| `<profile>/chrome/userChrome.css` | user-sheet styles |
| `<profile>/chrome/agent_overrides.css` | agent-sheet styles |
| `~/.local/share/applications/firefox-myfox.desktop` | launcher «Firefox (myfox)» |
| `~/.local/state/myfox/install.json` | installer state (see [docs/logic.md](docs/logic.md)) |

Required prefs (`toolkit.legacyUserProfileCustomizations.stylesheets`, `sidebar.revamp`,
`sidebar.verticalTabs`) are set automatically by `firefox.cfg` on first start.

## Bookmarklets (ddblm)

Bookmarklets are a [separate project](https://github.com/DayDve/ddblm). At install time you
may opt in to `blm` tweaks (custom icons + hidden labels on the Bookmarks Toolbar) and a
link to the bookmarklet gallery hosted on GitHub Pages
([https://daydve.github.io/ddblm/](https://daydve.github.io/ddblm/)). To manage them yourself:

```bash
cd bookmarklets
git submodule update --init --recursive   # if not cloned with --recurse-submodules
./blm config set ff_profile /path/to/profile
./blm build
./blm patchff
```

Then open `bookmarklets/docs/index.html`, enable the Bookmarks Toolbar (`Ctrl+Shift+B`)
and drag the cards onto it.

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
- Compact bookmarklets with custom icons and hidden text labels (when `blm` tweaks enabled).

## Development

Hot-reload of styles without restarting the browser is possible via the RDP proxy:

```bash
(cd bookmarklets && python3 firefox_rdp_proxy.py 34423)
python3 scratch/reload_userchrome.py
```

Architecture details: [docs/logic.md](docs/logic.md).
Test plan: [tests/README.md](tests/README.md).

License: [MIT](LICENSE) © DayDve.