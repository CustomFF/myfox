"""Copies autoconfig/chrome/bookmarklet tweaks into the install/profile.

TODO(pass 2): port lib/apply.sh — apply_autoconfig, apply_chrome (keeps the
one-time userChrome.css.myfox-backup dance), apply_theme_pref, bookmarklets
(urllib instead of curl for the ddblm fetch).
"""

from __future__ import annotations
