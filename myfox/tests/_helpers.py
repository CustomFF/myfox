"""Shared test scaffolding — not a test module itself (no Test* classes)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock


class IsolatedStateCase(unittest.TestCase):
    """Points XDG_STATE_HOME at a throwaway directory for the test's duration
    so tests never touch ~/.local/state/myfox — real or otherwise."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._env_patch = mock.patch.dict("os.environ", {"XDG_STATE_HOME": self._tmp.name})
        self._env_patch.start()
        self.addCleanup(self._env_patch.stop)

    @property
    def tmp_path(self) -> Path:
        return Path(self._tmp.name)
