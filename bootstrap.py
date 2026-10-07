"""MyFox bootstrap — what `curl -fsSL …/get.sh | sh` runs. Fetched fresh on
every call, so it has no version of its own; stdlib only, it can't import
myfox before downloading it.

Installed already: with arguments they go to the installed `myfox`;
without, it says so and offers to check for updates (`myfox refresh`).
Not installed: downloads the core archive (the myfox/ package) of the
latest core-* release into a temp dir, adds dearpygui there for
--gui, and runs the install form from it (`python3 -m myfox.wizard`); the
install copies MyFox into ~/.local/share/myfox.

Development:
  MYFOX_CORE_DIR=<working copy>   use it instead of downloading
  MYFOX_CORE_URL=<path or URL>    a core archive instead of the release
"""

import json
import locale
import os
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

REPO = "CustomFF/myfox"
CORE_ASSET = "myfox-core.tar.gz"

_MESSAGES = {
    "en": {
        "python_too_old": "MyFox needs Python 3.8 or newer.",
        "already_installed": "MyFox is already installed ({0}).",
        "check_updates": "Check for updates? [Y/n] ",
        "core_failed": "Could not download MyFox: {0}",
        "no_core_release": "no core-* release with {0} found",
    },
    "ru": {
        "python_too_old": "Для MyFox нужен Python 3.8 или новее.",
        "already_installed": "MyFox уже установлен ({0}).",
        "check_updates": "Проверить обновления? [Y/n] ",
        "core_failed": "Не удалось скачать MyFox: {0}",
        "no_core_release": "не найден релиз core-* с {0}",
    },
}


def _lang() -> str:
    # gettext's order, read directly: locale.getlocale() says "C" when the
    # system lacks the generated locale.
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = (os.environ.get(var) or "").split(":")[0]
        if value:
            return value[:2].lower()
    return (locale.getlocale()[0] or "en")[:2].lower()


def t(key: str, *args: object) -> str:
    lang = _lang()
    text = _MESSAGES.get(lang, _MESSAGES["en"]).get(key) or _MESSAGES["en"][key]
    return text.format(*args)


def _xdg(var: str, default: str) -> Path:
    return Path(os.environ.get(var) or Path.home() / default)


def installed_launcher():
    """The installed `myfox` launcher, or None when MyFox isn't installed."""
    state = _xdg("XDG_STATE_HOME", ".local/state") / "myfox" / "state.json"
    launcher = _xdg("XDG_DATA_HOME", ".local/share") / "myfox" / "bin" / "myfox"
    try:
        installed = bool(json.loads(state.read_text(encoding="utf-8")).get("install_dir"))
    except (OSError, ValueError):
        installed = False
    return launcher if installed and os.access(launcher, os.X_OK) else None


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": "myfox-bootstrap"})


def _core_url():
    """(archive URL or path, version tag)."""
    override = os.environ.get("MYFOX_CORE_URL")
    if override:
        return override, "dev"
    api = f"https://api.github.com/repos/{REPO}/releases?per_page=100"
    with urllib.request.urlopen(_request(api), timeout=30) as resp:
        releases = json.loads(resp.read().decode("utf-8"))
    for rel in releases:
        if rel.get("tag_name", "").startswith("core-"):
            for asset in rel.get("assets", []):
                if asset.get("name") == CORE_ASSET:
                    return asset["browser_download_url"], rel["tag_name"]
    raise OSError(t("no_core_release", CORE_ASSET))


def fetch_core(dest: Path) -> str:
    """Unpacks the core archive into dest; returns its version tag."""
    url, tag = _core_url()
    archive = dest / CORE_ASSET
    if "://" in url:
        with urllib.request.urlopen(_request(url), timeout=60) as resp:
            archive.write_bytes(resp.read())
    else:
        archive.write_bytes(Path(url).read_bytes())
    with tarfile.open(archive) as tf:
        for member in tf.getmembers():
            if member.name.startswith(("/", "..")) or "/../" in member.name:
                raise OSError(f"unsafe path in the archive: {member.name}")
        # "data" filter where Python has it (3.12+, 3.8.17+): 3.14 makes
        # it the default and earlier versions warn about the change.
        tf.extractall(dest, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
    archive.unlink()
    return tag


def _ask_yes(prompt: str) -> bool:
    try:
        answer = input(prompt).strip().lower()
    except EOFError:
        return False
    return answer in ("", "y", "yes", "д", "да")


def main(argv) -> int:
    if sys.version_info < (3, 8):
        print(t("python_too_old"), file=sys.stderr)
        return 1

    launcher = installed_launcher()
    if launcher:
        if argv:
            os.execv(str(launcher), [str(launcher), *argv])
        print(t("already_installed", launcher.parent.parent))
        if _ask_yes(t("check_updates")):
            os.execv(str(launcher), [str(launcher), "refresh"])
        return 0

    core_dir = os.environ.get("MYFOX_CORE_DIR")
    with tempfile.TemporaryDirectory(prefix="myfox-") as tmp:
        root = Path(core_dir) if core_dir else Path(tmp)
        if not core_dir:
            try:
                fetch_core(root)
            except OSError as exc:
                print(t("core_failed", getattr(exc, "reason", exc)), file=sys.stderr)
                return 1
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(p for p in (str(root), os.environ.get("PYTHONPATH")) if p)
        if "--gui" in argv:
            # The form itself needs dearpygui; the install then keeps this copy.
            subprocess.run([sys.executable, "-c", "from pathlib import Path; from myfox import gui_deps; "
                            f"gui_deps.install_into(Path({str(Path(tmp))!r}))"], env=env, check=False)
            env["PYTHONPATH"] = os.pathsep.join((env["PYTHONPATH"], tmp))
        return subprocess.run([sys.executable, "-m", "myfox.wizard", *argv], env=env).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
