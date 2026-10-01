# MyFox — Firefox tweaks + installer

> **[Русская версия](README.ru.md)**

MyFox is a set of Firefox user-interface tweaks (floating "card" tabs, rounded corners,
aligned sidebar, Downloads and Extensions as sidebar views, compact search fields) bundled with an
**installer** that grabs Firefox (stable or beta) straight from Mozilla's official tarball
and applies the tweaks to it.

This repository only contains the **tweaks and the installer**. Bookmarklets live in a
separate project — **[ddblm](https://github.com/CustomFF/ddblm)** (DayDve BookmarkLet Manager). MyFox
downloads the ready-made tweak files (CSS + icons) from ddblm over raw.githubusercontent.com;
you do not need to build or clone ddblm yourself.

## Highlights

- **Wizard or one command** — in a terminal a step-by-step wizard (install directory, stable/beta,
  Firefox language, profile, tweaks, dark/light appearance); with `-y` it runs without questions.
- **Profile-local** — tweaks apply only to the profile the installer marked (`<profile>/.myfox`).
  Any other profile under the same install is stock Firefox; delete the profile and nothing of
  MyFox is left in it. No policies, nothing install-wide.
- **Both themes, your pick** — the Google Chrome dark and light themes are installed into the
  profile; the one you chose is enabled on first start (once — your later choice is never overwritten).
- **KDE Plasma integration** — the add-on is installed under a Plasma session (or with
  `--plasma-integration`).
- **A real command afterwards** — `myfox browser`, `myfox update`, `myfox uninstall`.
- **No root required** — Firefox lands in `~/.local/share/firefox` and the desktop shortcut
  is named **«Firefox (myfox)»** so it never conflicts with a system-installed Firefox.

## Requirements

- Linux (x86_64 or aarch64), bash 4+
- `curl`, `tar`, `awk`
- `dialog` or `whiptail` is optional (the wizard falls back to plain prompts without them)

## Quick start

From a clone:

```bash
git clone https://github.com/CustomFF/myfox.git
cd myfox
./bin/myfox-core install          # or: make install ARGS="-y"
```

The installer is designed to be served as a distribution tarball plus `get.sh`
(`curl -fsSL <url>/get.sh | bash`); no public URL is published yet, see
[Development](#development) for serving one locally.

## The `myfox` command

The installer puts a `myfox` command in `~/.local/bin` (make sure it is on your `PATH`):

```text
myfox                       Status line and help (does not start the browser)
myfox browser [args…]       Start the installed browser; all arguments go to Firefox
myfox ff [args…]            Alias for `myfox browser`
myfox update [--reinstall]  Re-apply tweaks (and, with --reinstall, re-download Firefox)
myfox uninstall [-y]        Remove MyFox
myfox help [command]        Help for one command
```

## Install options

```text
  --prefix <path>        Install Firefox to a custom path (default ~/.local/share/firefox).
  --profile <path>       Use a specific Firefox profile directory (skips detection).
  --lang <code>          Firefox language (validated against Mozilla; see --list-languages).
                         Also picks the installer's own interface language (ru/en).
  --list-languages       Print the available Firefox languages and exit.
  --reinstall            Force re-download of Firefox even if already installed.
  --browser-only         Only the tarball and the desktop entry: no profile, no tweaks.
  --nobl                 Skip bookmarklet tweaks.
  --theme <dark|light>   Appearance of a new profile (default: dark).
  --plasma-integration   Install the KDE Plasma integration add-on (no prompt),
                         even outside a Plasma session.
  --noplasma             Skip KDE Plasma integration even under Plasma.
  --force                Install even if already installed.
  -y, --yes              Non-interactive (no prompts).
  -v, --verbose          Verbose output.
  -h, --help             Show help.
```

Both `--flag value` and `--flag=value` work. `update` accepts `--reinstall`, `-y`, `-v`;
`uninstall` accepts `-y`, `-v`; other flags are rejected for those commands instead of being
silently ignored. The stable/beta channel is chosen in the wizard (stable when non-interactive).

## Updating

```bash
myfox update               # refreshes tweaks; does NOT re-download Firefox
myfox update --reinstall   # also pulls the latest Firefox build
```

Styles (`userChrome.css`) and `myfox.cfg` are read at browser start — restart Firefox after
an update.

## Uninstalling

```bash
myfox uninstall [-y]
```

It removes the application (autoconfig files, desktop entry, the `myfox` command) and asks
whether to delete the MyFox profile as well. For a profile you passed in with `--profile`
only the MyFox tweaks are removed (your own `userChrome.css` is restored from its backup).

## What gets installed

| Where | What |
|---|---|
| `~/.local/share/firefox` (`--prefix`) | Firefox itself, plus `defaults/pref/autoconfig.js`, `myfox.cfg` and `myfox/*.js` (privileged JS: registers the agent sheets, patches sidebar/downloads, sets profile-local prefs) |
| `~/.local/share/myfox/` | the installer itself: `bin/myfox`, `bin/myfox-core`, `lib/`, `i18n/`, `assets/` — so `update`/`uninstall`/`help` work offline |
| `~/.local/bin/myfox` | symlink to `~/.local/share/myfox/bin/myfox` |
| `<profile>/chrome/userChrome.css` + `user/*.css` | user-sheet styles (tabs, toolbar, cards, …) |
| `<profile>/chrome/agent/*.css` | agent-sheet styles (registered by `myfox.cfg`; reach into shadow DOM) |
| `<profile>/extensions/` | both theme add-ons, optionally Plasma integration |
| `<profile>/user.js` | one line, `myfox.theme`, read once by `myfox.cfg` |
| `<profile>/.myfox` | profile marker — only marked profiles get tweaks |
| `~/.local/share/applications/firefox-myfox.desktop` | launcher «Firefox (myfox)» |
| `~/.local/state/myfox/state` | installer state (flat `key=value`, see [docs/logic.md](docs/logic.md)) |

Profiles live in `~/.mozilla/firefox` when that directory exists, otherwise (Firefox 147+ on a
fresh system) in `$XDG_CONFIG_HOME/mozilla/firefox`; flatpak and snap locations are recognized too.

Required prefs (`toolkit.legacyUserProfileCustomizations.stylesheets`, `sidebar.revamp`) are set by
`myfox.cfg` on first start — **but only for the marked profile**. Any other profile stays a
pristine Firefox: `myfox.cfg` refuses to apply anything to it (no prefs, no styles, no window tweaks).

On the marked profile `myfox.cfg` also, once: adds two bookmarks to the Bookmarks Toolbar —
**«Расширенные настройки»** (about:config) and **«Добавить букмарклеты»** (the ddblm gallery —
bilingual, opens as `?lang=ru` for a Russian-locale Firefox) — enables the chosen theme, and sets
the fresh-profile defaults (compact UI, AI features/telemetry/sponsored content off).

## Add-ons

- **Google Chrome Dark / Light themes** — both are always installed; the wizard step (or `--theme`)
  decides which one is enabled, and also sets Firefox's "website appearance" to match.
- **KDE Plasma integration** — installed silently under a Plasma session (or with
  `--plasma-integration`).

The Plasma add-on additionally needs the system package `plasma-browser-integration` (the
native-messaging host). The installer checks for it: if it is missing, a note with the install
command is printed at the end of the setup — no `sudo` prompts interrupting the dialogs. Use
`--noplasma` to skip the add-on even under Plasma.

## Bookmarklets (ddblm)

Bookmarklets are a [separate project](https://github.com/CustomFF/ddblm). The tweaks (custom icons +
hidden labels on the Bookmarks Toolbar, from ddblm) come with "tweaks: yes"; `--nobl` skips them.
The installer copies `docs/blm_panel.css` and **all** `icons/*.svg` from ddblm
(raw.githubusercontent.com for the published ddblm; a local checkout via
`MYFOX_DDBLM_LOCAL=/path` while developing) into `<profile>/chrome/`, so you do not need to clone
or build ddblm yourself. The gallery itself is hosted on GitHub Pages
([https://daydve.github.io/ddblm/](https://daydve.github.io/ddblm/)).

After install, open the gallery (click **«Добавить букмарклеты»** on the Bookmarks Toolbar),
enable the toolbar (`Ctrl+Shift+B`) and drag the cards onto it.

## Applying to an existing Firefox (manual)

> The installer only creates a fresh tarball install. To attach the tweaks to an already
> installed Firefox, do these steps by hand:

1. **Locate the install directory**, e.g. `/usr/lib/firefox` (or `~/.local/share/firefox`).
2. Copy `autoconfig/autoconfig.js` into `<install>/defaults/pref/`.
3. Copy `autoconfig/myfox.cfg` and the `autoconfig/myfox/` directory into `<install>/` (next to the
   `firefox` binary).
4. Copy `chrome/userChrome.css`, `chrome/user/` and `chrome/agent/` into your profile's
   `chrome/` directory (path is shown at `about:support` → *Profile Folder*).
5. Create the marker file `<profile>/.myfox` — without it `myfox.cfg` leaves the profile alone.
6. Restart Firefox. The required prefs are applied automatically via autoconfig.

> **Note:** editing `/usr/lib/firefox` requires sudo. On systems where you cannot write to
> the install directory, this approach won't work — use the tarball install instead.

## What the tweaks look like

- Web pages render as a floating card with rounded corners and even margins; so does the sidebar.
- One corner radius (`--myfox-radius`) everywhere instead of Nova's assorted pill shapes.
- Compact rows in the sidebar panels (history, synced tabs, downloads, passwords), one 12px base
  font on internal pages, round close buttons, a blue accent instead of Nova's violet.
- The sidebar toggle button highlights when the panel is open and toggles on a single click.
- Compact bookmarklets with custom icons and hidden text labels (unless `--nobl`).

## Development

There is no build step and no automated test suite; see [tests/README.md](tests/README.md) for the
manual checklists. Before handing anything in:

```bash
bash -n get.sh bin/myfox-core lib/*.sh scripts/*.sh
shellcheck -S error get.sh bin/myfox-core lib/*.sh scripts/*.sh
python3 -m py_compile scratch/*.py        # if scratch/*.py was touched
```

Never run the installer against your real `$HOME` while developing — use the sandbox, which
redirects `$HOME` and every `$XDG_*` directory:

```bash
scratch/sandbox.sh /tmp/mf --fresh -- ./bin/myfox-core install -y --nobl
scratch/sandbox.sh /tmp/mf -- ./bin/myfox-core update -y
scratch/sandbox.sh /tmp/mf -- ./bin/myfox-core uninstall -y
```

To exercise the real `curl | bash` path locally: `scripts/dev-serve.sh` builds `dist/myfox-dist.tar.gz`
and serves it (with a `get.sh` pointing at itself) on `http://127.0.0.1:8787`.

Hot-reload of styles without restarting the browser is possible via the RDP proxy
(`firefox_rdp_proxy.py`, lives in [CustomFF/tweaks](https://github.com/CustomFF/tweaks)):

```bash
python3 firefox_rdp_proxy.py 34423     # from a tweaks checkout
python3 reload_userchrome.py           # also there, in scripts/
```

Architecture details: [docs/logic.md](docs/logic.md). Agent guidelines: [AGENTS.md](AGENTS.md).

License: [MIT](LICENSE) © DayDve.
