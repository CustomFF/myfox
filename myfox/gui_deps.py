"""dearpygui for the GUI views. It's a compiled wheel per Python version x
architecture, not portable source, so it isn't in git: the install puts
the matching one next to MyFox's own copy (share_dir()/dearpygui), from
this project's own GitHub release — never PyPI/pip at runtime.

MYFOX_DEARPYGUI_DIR=<dir with the wheels> replaces the release (dev use).
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from . import firefox, net

VERSION = "2.3.1"
RELEASE_URL = f"https://github.com/CustomFF/myfox/releases/download/dearpygui-{VERSION}"

# The unchanged PyPI wheels the release carries; sha256 from PyPI.
_SHA256 = {
    "cp38-cp38-manylinux1_x86_64": "cd7d63969fb174388bc8c99357fc71c796a8b799d53c03009c0d107fdbccdcad",
    "cp39-cp39-manylinux1_x86_64": "fc965058229e5c5fd448bce1e3f749174fc7c68c0616bef5d06f5d30a7689ec6",
    "cp310-cp310-manylinux1_x86_64": "55ce713722583f1c874bfdb458cc3c0c09200c200419a31128534f7a86f9ccff",
    "cp311-cp311-manylinux1_x86_64": "686423b4f8a30aaf57f1044ec4e3b087beb9cc9b25be812cf92f4e7feff44fd6",
    "cp312-cp312-manylinux1_x86_64": "364b5b6a0953999fec764d529d9bb0b2cc6ab6ed06188e0ded28237c1475ca98",
    "cp313-cp313-manylinux1_x86_64": "e3f64c8d4cae68a3b5be1b7531d08400ccbf1e4ff03c7acfc85954f98993f864",
    "cp314-cp314-manylinux1_x86_64": "953442c7272e57f3686e393edc5cf6ce73cc2f47142739735dfabed403e33770",
    "cp38-cp38-manylinux2014_aarch64": "10e6de05dd1441ad8200ff686ad204700dfb931f4fa00e6b58b49641f0d69a26",
    "cp39-cp39-manylinux2014_aarch64": "21bbdde9c77ee4472e47aea351e649b724bac599eb041515f10c8cd583dbc4ab",
    "cp310-cp310-manylinux2014_aarch64": "853e912c6d1d555711c002f0e1b7d3355b118fe56a42dda92b30e0dbd6528b76",
    "cp311-cp311-manylinux2014_aarch64": "0259a2db7b6c82459ac1402b0d42388a7cd180cd97d7dcb31a5210725c3171d3",
    "cp312-cp312-manylinux2014_aarch64": "199dffebda245c9f59aa7c10c3b7f62963237c5f744150ad9be409b27a2661d3",
    "cp313-cp313-manylinux2014_aarch64": "0d8b7a5a04cd4a6e25dbf162aa0405cf12143a1c82b33e371c20e5ba8d9349f3",
    "cp314-cp314-manylinux2014_aarch64": "43a561b5dc589944a3a2b469e5e68f1ab35ae38b3dcdf1f813ed9d6e024153f8",
}
_PLATFORM = {"amd64": "manylinux1_x86_64", "arm64": "manylinux2014_aarch64"}


def wheel_name(version_info=sys.version_info, arch: str | None = None) -> str | None:
    """The wheel for this Python and architecture, None if there is none."""
    platform = _PLATFORM.get(arch or firefox.detect_arch() or "")
    py = f"cp{version_info[0]}{version_info[1]}"
    tag = f"{py}-{py}-{platform}"
    return f"dearpygui-{VERSION}-{tag}.whl" if tag in _SHA256 else None


def install_into(target: Path) -> None:
    """Puts the dearpygui package at target/dearpygui. One that is already
    importable here (bootstrap fetched it for a --gui install, or a dev
    setup) is copied; otherwise the wheel is fetched and checked. Raises
    OSError/RuntimeError on failure."""
    dest = target / "dearpygui"
    spec = importlib.util.find_spec("dearpygui")
    if spec and spec.submodule_search_locations:
        source = Path(next(iter(spec.submodule_search_locations)))
        if source.resolve() != dest.resolve():
            shutil.rmtree(dest, ignore_errors=True)
            shutil.copytree(source, dest, ignore=shutil.ignore_patterns("__pycache__"))
        return

    name = wheel_name()
    if name is None:
        raise RuntimeError(f"no dearpygui {VERSION} wheel for Python {sys.version_info[0]}.{sys.version_info[1]} "
                           f"on {firefox.detect_arch() or 'this architecture'}")
    local = os.environ.get("MYFOX_DEARPYGUI_DIR")
    if local:
        data = (Path(local) / name).read_bytes()
    else:
        with urllib.request.urlopen(net.request(f"{RELEASE_URL}/{name}"), timeout=60) as resp:
            data = resp.read()
    tag = name[len(f"dearpygui-{VERSION}-"):-len(".whl")]
    if hashlib.sha256(data).hexdigest() != _SHA256[tag]:
        raise RuntimeError(f"{name}: checksum mismatch")

    with tempfile.TemporaryDirectory() as tmp:
        wheel = Path(tmp) / name
        wheel.write_bytes(data)
        with zipfile.ZipFile(wheel) as zf:
            members = [m for m in zf.namelist() if m.startswith("dearpygui/")]
            zf.extractall(tmp, members)
        shutil.rmtree(dest, ignore_errors=True)
        shutil.move(str(Path(tmp) / "dearpygui"), str(dest))

