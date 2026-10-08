# MyFox — Firefox with tweaks, installed in one command

> **[Русская версия](README.ru.md)**

MyFox installs Firefox (stable or beta) straight from Mozilla's official tarball into your home
directory and applies the [MyFox tweaks](https://github.com/CustomFF/tweaks) to it: floating "card"
tabs, rounded corners, a reworked sidebar with Downloads and Extensions panels, dark and light
themes. No root, no packages, no pip.

```bash
curl -fsSL https://raw.githubusercontent.com/CustomFF/myfox/master/get.sh | sh
```

In a terminal this opens the install form; add `-s -- --gui` for a window instead, or `-s -- -y`
to install with the defaults without questions:

```bash
curl -fsSL https://raw.githubusercontent.com/CustomFF/myfox/master/get.sh | sh -s -- --gui
```

From a clone, the same thing with `make`:

```bash
git clone https://github.com/CustomFF/myfox.git && cd myfox
make install                    # the form in the terminal; `make install gui` for a window
MYFOX_INSTALL=AUTO make install # the defaults, no questions
```

`make refresh`, `make reinstall` and `make uninstall` (each with an optional `gui`) just run the
installed `myfox` command below.

## Requirements

- Linux, x86_64 or aarch64
- Python 3.8 or newer, `curl`
- For the window (`--gui`): a graphical session; the GUI library is downloaded by MyFox itself

## What you get

- **Firefox** in `~/.local/share/myfox/firefox` (or a directory you choose), in its own profile,
  with the shortcut **«Firefox (myfox)»** — it never clashes with a system Firefox.
- **The tweaks** in that profile only. Any other profile is stock Firefox; delete the MyFox profile
  and nothing of MyFox is left in it. Nothing is written install-wide (no policies).
- **Both themes**, dark and light; the one you picked is turned on at first start, once — your later
  choice in Firefox is never overwritten.
- **KDE Plasma integration** under a Plasma session.
- **Bookmarklet styling** from [ddblm](https://github.com/CustomFF/ddblm); the «Add bookmarklets»
  bookmark on the bookmarks toolbar opens the gallery.
- **The `myfox` command** in `~/.local/bin` (make sure it's on your `PATH`).

## The `myfox` command

```text
myfox browser [args…]                    Start the installed Firefox; arguments go to Firefox
myfox refresh [--force] [--gui]          Update the tweaks and MyFox itself
myfox reinstall [--gui]                  Download Firefox again and re-apply the tweaks
myfox uninstall [--remove-profile] [--gui]  Remove MyFox
myfox help                               This list
myfox --version
```

Every command shows what it is about to do and asks first — in the terminal, or in a window with
`--gui`; `-y` skips the question. Without a terminal (cron, a script) nothing is asked: MyFox shows
what it would do and the command to run with `-y`.

- **Updating.** Firefox updates itself. `myfox refresh` updates the tweaks and MyFox and shows
  what's new; the shortcut's context menu has «Update MyFox» too. New tweaks apply once Firefox
  restarts: `refresh` offers to restart it, and the shortcut's menu has «Restart» (windows and tabs
  come back).
- **Reinstalling.** `myfox reinstall` replaces Firefox only once the new copy is fully downloaded;
  your profile stays as it is.
- **Uninstalling.** `myfox uninstall` removes Firefox, the shortcut, the `myfox` command and
  `~/.local/share/myfox`. The profile (bookmarks, history, passwords) stays on disk unless you tick
  «also delete the profile» or pass `--remove-profile`.

None of these run while Firefox from this install is open.

## Applying the tweaks by hand

The tweaks also work without MyFox, including on a Firefox you already have — see
[CustomFF/tweaks](https://github.com/CustomFF/tweaks#apply-by-hand).

## Development

```bash
python3 -m unittest discover -t . -s myfox/tests -p "test_*.py" < /dev/null   # tests
python3 -m myfox.wizard --dry-run [--gui]                                     # the install form, installs nothing
```

Never run a real install against your own `$HOME` — use the sandbox, which redirects `$HOME` and
every `$XDG_*` directory:

```bash
R=$PWD
scratch/sandbox.sh /tmp/mf --fresh -- bash -c "cd /tmp && cat $R/get.sh | \
    MYFOX_BOOTSTRAP_URL=file://$R/bootstrap.py MYFOX_CORE_DIR=$R sh -s -- -y"
```

Manual checklist: [tests/README.md](tests/README.md). How it works: [docs/logic.md](docs/logic.md).

**Releasing MyFox:** bump `__version__` in `myfox/__init__.py`, add a `## <version> — <date>`
section to `CHANGELOG.md`, commit, push, then push the tag `core-<version>`. The `core.yml` workflow
checks that the three agree and publishes `myfox-core.tar.gz` and `changelog.json`; installed copies
pick it up with `myfox refresh`.

License: [MIT](LICENSE) © DayDve.
