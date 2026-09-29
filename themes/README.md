# Theme sources

`myfox-dark/` and `myfox-light/` are our own fork of the two lightweight
themes the installer applies (previously AMO's "Google Chrome Dark/Light"
by Stylefox, fetched by slug at install time). Colors are currently an
exact copy, just under our own add-on IDs and names — a safe baseline
before any palette tuning.

A Firefox theme add-on here is nothing but `manifest.json`'s `theme.colors`
— no CSS, no JS, no images. It cannot carry any of MyFox's actual UI
tweaks (those live in `chrome/` and `autoconfig/myfox/`); forking only
buys color-palette control and independence from a third-party AMO
listing.

`scripts/build-themes.sh` zips each directory into an unsigned `.xpi`
(`build/themes/`). Unsigned XPIs only install with
`xpinstall.signatures.required=false` (sandbox/dev only — never set in
the installer) or via `about:debugging` → "Load Temporary Add-on"
pointing at the directory. Firefox stable/beta require an AMO-signed
XPI to sideload normally; production distribution needs a signed build
from AMO's "unlisted" (self-distribution) channel before `lib/addons.sh`
can switch from fetching the Stylefox slugs to bundling these.
