"""Installs the (already-signed) bundled themes and, optionally, the AMO
Plasma integration add-on.

TODO(pass 2): port lib/addons.sh — addons_install_themes is a plain file
copy already (no network); the AMO half (addon_guid/addon_fetch for Plasma)
becomes urllib.request + json instead of curl + awk.
"""

from __future__ import annotations
