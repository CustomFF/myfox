"""Tar extraction with Python's "data" filter (no absolute or escaping
paths, no device files, sane permissions) where the running Python has it
(3.12+, backported to 3.8.17+); Python 3.14 makes it the default and
earlier versions warn about the change. Callers still check member names
themselves for the Pythons without it.
"""

from __future__ import annotations

import tarfile
from pathlib import Path

_FILTER = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}


def extract_all(tf: tarfile.TarFile, dest: Path) -> None:
    tf.extractall(dest, **_FILTER)


def extract(tf: tarfile.TarFile, member: tarfile.TarInfo, dest: Path) -> None:
    tf.extract(member, dest, **_FILTER)
