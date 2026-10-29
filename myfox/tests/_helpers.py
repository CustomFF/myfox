"""Shared test scaffolding — not a test module itself (no Test* classes)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock


def git_refs(*refs: str) -> bytes:
    """What GitHub answers on <repo>.git/info/refs: a pkt-line per ref,
    a peeled line for each tag, flushes in between."""
    def pkt(text: str) -> bytes:
        return b"%04x" % (len(text) + 4) + text.encode()
    lines = [pkt("# service=git-upload-pack\n"), b"0000"]
    for i, ref in enumerate(refs):
        sha = f"{i + 1:040x}"
        lines.append(pkt(f"{sha} {ref}" + ("\0multi_ack side-band-64k\n" if i == 0 else "\n")))
        if ref.startswith("refs/tags/"):
            lines.append(pkt(f"{i + 101:040x} {ref}^{{}}\n"))
    return b"".join(lines) + b"0000"


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
    """Points HOME and the XDG state/data/config dirs at a throwaway
    directory for the test's duration, so tests never touch the real
    ~/.local/{state,share}/myfox or the real Firefox profiles.ini."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self._env_patch = mock.patch.dict("os.environ", {
            "XDG_STATE_HOME": str(root), "XDG_DATA_HOME": str(root / "data"),
            "XDG_CONFIG_HOME": str(root / "config"), "HOME": str(root / "home"),
        })
        self._env_patch.start()
        self.addCleanup(self._env_patch.stop)

    @property
    def tmp_path(self) -> Path:
        return Path(self._tmp.name)
