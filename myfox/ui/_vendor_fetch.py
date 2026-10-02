"""Fetches the compiled dearpygui pair (its _dearpygui.so, built per
Python-minor-version x architecture — not portable source, see
docs/python-rewrite-plan.md's rejected-alternatives table) from this
project's own GitHub Release — never PyPI, never pip/venv. Only called
by dearpygui_backend.py, on first use of the GUI path.

The pairs themselves (3.10-3.13 x amd64/arm64) are built and signed once,
by hand, and uploaded to a release — not by this module, and not done
yet (see docs/python-rewrite-plan.md, Pass 4). This only implements the
client side: find the right asset, download it once, cache it, put it on
sys.path. ensure_available() no-ops if dearpygui is already importable
(e.g. a dev-only pip install already on sys.path), so development
doesn't need a real release to exist.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from .. import firefox, net, version

REPO = "CustomFF/myfox"
RELEASE_TAG_RE = re.compile(r"^dearpygui-")


def _cache_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "myfox" / ".dearpygui-cache"


def _asset_name() -> str:
    major, minor = sys.version_info[:2]
    arch = firefox.detect_arch()
    return f"dearpygui-cp{major}{minor}-{arch}.zip"


def ensure_available() -> None:
    try:
        import dearpygui.dearpygui  # noqa: F401

        return
    except ImportError:
        pass

    asset = _asset_name()
    target_dir = _cache_dir() / asset.removesuffix(".zip")
    if not target_dir.is_dir():
        _download_and_extract(asset, target_dir)
    sys.path.insert(0, str(target_dir))


def _download_and_extract(asset_name: str, target_dir: Path) -> None:
    tag = version.latest_tag(RELEASE_TAG_RE, repo=REPO)
    if tag is None:
        raise RuntimeError(
            f"no dearpygui-* release found in {REPO} — the prebuilt pairs haven't been "
            "built and uploaded yet (see docs/python-rewrite-plan.md, Pass 4)"
        )
    url = f"https://github.com/{REPO}/releases/download/{tag}/{asset_name}"
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        try:
            with urllib.request.urlopen(net.request(url), timeout=60) as resp:
                tmp.write(resp.read())
            tmp.flush()
            with zipfile.ZipFile(tmp_path) as zf:
                zf.extractall(target_dir)
        except (urllib.error.URLError, OSError, zipfile.BadZipFile):
            raise RuntimeError(f"couldn't fetch/extract {asset_name} from {REPO}'s {tag} release") from None
        finally:
            tmp_path.unlink(missing_ok=True)
