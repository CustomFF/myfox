"""profiles.ini / installs.ini handling, headless install-hash pinning.

TODO(pass 2): port lib/profile.sh — configparser instead of the hand-rolled
awk INI parser (this is genuine domain logic: Firefox's own [Install<HASH>]
pinning has no public API, we still have to run it headless once and diff
profiles.ini/installs.ini before/after to see what it wrote).
"""

from __future__ import annotations
