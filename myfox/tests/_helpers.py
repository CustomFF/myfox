"""Shared test scaffolding — not a test module itself (no Test* classes)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock


def make_tweaks(root: Path) -> Path:
    """A minimal tweaks tree (autoconfig/ + chrome/) under root — what a
    release archive or paths.tweaks_dir() holds."""
    files = {
        "autoconfig/autoconfig.js": "pref('general.config.filename', 'myfox.cfg');\n",
        "autoconfig/myfox.cfg": "// myfox\n",
        "autoconfig/myfox/00-common.js": "// common\n",
        "chrome/userChrome.css": "@import 'user/10-x.css';\n",
        "chrome/user/10-x.css": "/* user */\n",
        "chrome/agent/10-y.css": "/* agent */\n",
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


class IsolatedStateCase(unittest.TestCase):
    """Points XDG_STATE_HOME and XDG_DATA_HOME at throwaway directories for
    the test's duration, so tests never touch ~/.local/state/myfox or
    ~/.local/share/myfox — real or otherwise."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._env_patch = mock.patch.dict("os.environ", {"XDG_STATE_HOME": self._tmp.name,
                                                         "XDG_DATA_HOME": str(Path(self._tmp.name) / "data")})
        self._env_patch.start()
        self.addCleanup(self._env_patch.stop)

    @property
    def tmp_path(self) -> Path:
        return Path(self._tmp.name)
