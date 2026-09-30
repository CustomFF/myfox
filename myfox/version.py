"""Checks the two independent release tracks (tweaks, core) against GitHub
Releases — a small JSON request (releases/latest), never the tarball itself,
just to decide whether refresh has anything to do.

TODO(pass 5): real GitHub API calls + comparison against state's recorded
tags. Deliberately not semver-aware — see docs/python-rewrite-plan.md: the
tweaks tag is <firefox-beta-major>.<patch>, compared for inequality only,
never ordered.
"""

from __future__ import annotations


def tweaks_update_available() -> str | None:
    """Returns the new tag if there's an update, else None."""
    raise NotImplementedError


def core_update_available() -> str | None:
    raise NotImplementedError
