"""Shell completion. The scripts only pass the command line to `myfox
_complete`, which answers from the argument parser itself and the
profiles on disk, so they never go stale after an update. MyFox puts them
where bash and fish look by themselves, and zsh's into a folder of the
user's own fpath if there is one; `myfox completion <shell>` prints them
for setting up by hand."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from . import i18n, profile_commands
from .state import State

COMMAND = "_complete"
SHELLS = ("bash", "zsh", "fish")
# Every script has it: a file there without it isn't ours to replace or delete.
MARK = "# myfox completion for"
ZSH_FPATH_TIMEOUT = 10

# Each takes the words after `myfox`, the last one the word being typed
# (empty after a space), and prints "candidate<TAB>description" lines.
SCRIPTS = {
    "bash": r"""# myfox completion for bash
_myfox() {
    local line=${COMP_LINE:0:COMP_POINT} cur prefix
    local -a words
    read -ra words <<<"$line"
    [[ $line == *[[:space:]] ]] && words+=("")
    if [[ ${words[1]} == browser && ${#words[@]} -gt 2 ]]; then
        compopt -o default
        COMPREPLY=()
        return
    fi
    local IFS=$'\n'
    COMPREPLY=($("$1" _complete "${words[@]:1}" 2>/dev/null | cut -f1))
    # bash completes only what follows the last ":" of an ID like snap:<folder>.
    cur=${words[${#words[@]}-1]}
    if [[ $cur == *:* ]]; then
        prefix=${cur%"${cur##*:}"}
        COMPREPLY=("${COMPREPLY[@]#"$prefix"}")
    fi
}
complete -F _myfox myfox
""",
    "zsh": r"""#compdef myfox
# myfox completion for zsh
_myfox() {
    if [[ ${words[2]} == browser && $CURRENT -gt 2 ]]; then
        _files
        return
    fi
    local -a items
    local line
    for line in "${(@f)$("${words[1]}" _complete "${(@Q)words[2,CURRENT]}" 2>/dev/null)}"; do
        [[ -n $line ]] || continue
        if [[ -n ${line#*$'\t'} ]]; then
            items+=("${${line%%$'\t'*}//:/\\:}:${line#*$'\t'}")
        else
            items+=("${${line%%$'\t'*}//:/\\:}")
        fi
    done
    _describe -t values myfox items
}
if [[ $zsh_eval_context[-1] == loadautofunc ]]; then
    _myfox "$@"
else
    compdef _myfox myfox
fi
""",
    "fish": r"""# myfox completion for fish
function __myfox_browser
    set -l words (commandline -opc)
    test (count $words) -ge 2; and test "$words[2]" = browser
end
function __myfox_complete
    set -l words (commandline -opc) (commandline -ct)
    $words[1] _complete $words[2..-1] 2>/dev/null
end
complete -c myfox -n 'not __myfox_browser' -f -a '(__myfox_complete)'
complete -c myfox -n __myfox_browser -F
""",
}


def _subcommands(parser: argparse.ArgumentParser) -> argparse._SubParsersAction | None:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def _option(parser: argparse.ArgumentParser, word: str) -> argparse.Action | None:
    for action in parser._actions:
        if word in action.option_strings:
            return action
    return None


def _help(action: argparse.Action) -> str:
    text = action.help if action.help and action.help != argparse.SUPPRESS else ""
    return " ".join(text.split())


def _profiles(state: State, command: str) -> list[tuple[str, str]]:
    try:
        found = profile_commands.candidates(state, command)
    except OSError:
        return []
    return [(p.id, "" if p.name in (p.id, p.path.name) else p.name) for p in found]


def complete(words: list[str], state: State, parser: argparse.ArgumentParser,
             profiles: Callable[[State, str], list[tuple[str, str]]] = _profiles) -> list[tuple[str, str]]:
    """The candidates for the last of `words` (what follows `myfox`), each
    with a description or ""."""
    *done, cur = words or [""]
    if done and done[0] == "browser":
        return []
    current, path, given, value_of = parser, [], 0, None
    for word in done:
        if value_of is not None:
            value_of = None
            continue
        if word.startswith("-"):
            action = _option(current, word.split("=", 1)[0])
            if action is not None and action.nargs != 0 and "=" not in word:
                value_of = action
            continue
        sub = _subcommands(current)
        if sub is not None and word in sub.choices and given == 0:
            current, given = sub.choices[word], 0
            path.append(word)
            continue
        given += 1

    if value_of is not None:
        found = [(c, "") for c in (value_of.choices or [])]
    elif cur.startswith("-"):
        found = [(s, _help(a)) for a in current._actions for s in a.option_strings]
    else:
        found = []
        sub = _subcommands(current)
        if sub is not None and given == 0:
            if not path:
                found.append(("browser", i18n.t("cmd_browser")))
            found += [(a.dest, _help(a)) for a in sub._choices_actions]
        positionals = [a for a in current._actions
                       if not a.option_strings and not isinstance(a, argparse._SubParsersAction)]
        if given < len(positionals):
            action = positionals[given]
            if action.choices:
                found += [(c, "") for c in action.choices]
            elif action.dest == "profile" and path:
                found += profiles(state, path[-1])
    return [(c, d) for c, d in found if c.startswith(cur)]


def run_complete(words: list[str], state: State, parser: argparse.ArgumentParser) -> int:
    for candidate, description in complete(words, state, parser):
        print(f"{candidate}\t{description}")
    return 0


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def _bash_file() -> Path:
    # bash-completion reads BASH_COMPLETION_USER_DIR (its first entry), else XDG_DATA_HOME.
    user_dir = (os.environ.get("BASH_COMPLETION_USER_DIR") or "").split(":")[0]
    return (Path(user_dir) if user_dir else _data_home() / "bash-completion") / "completions" / "myfox"


def _fish_file() -> Path:
    return _data_home() / "fish" / "vendor_completions.d" / "myfox.fish"


def _in_a_repo(folder: Path, home: Path) -> bool:
    """A plugin manager's checkout (oh-my-zsh, zinit…): not ours to add to."""
    for parent in (folder, *folder.parents):
        if (parent / ".git").exists():
            return True
        if parent == home:
            return False
    return False


def _zsh_fpath() -> list[Path]:
    """The user's fpath as an interactive zsh sets it up (.zshrc)."""
    try:
        out = subprocess.run(["zsh", "-i", "-c", "print -rl -- $fpath"], stdin=subprocess.DEVNULL,
                             capture_output=True, text=True, timeout=ZSH_FPATH_TIMEOUT,
                             env={**os.environ, "TERM": "dumb"}).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [Path(line) for line in out.splitlines() if line.startswith("/")]


def zsh_file(fpath: Callable[[], list[Path]] = _zsh_fpath) -> Path | None:
    """`_myfox` in the first folder of fpath that is the user's own: in
    the home, writable, not in a git checkout. One already there wins."""
    home = Path.home().resolve()
    folders = []
    for folder in fpath():
        try:
            real = folder.resolve()
        except OSError:
            continue
        if real.is_dir() and home in real.parents and os.access(real, os.W_OK) and not _in_a_repo(real, home):
            folders.append(folder)
    for folder in folders:
        if _ours(folder / "_myfox"):
            return folder / "_myfox"
    return folders[0] / "_myfox" if folders else None


def _ours(path: Path) -> bool:
    try:
        return MARK in path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False


def install(fpath: Callable[[], list[Path]] = _zsh_fpath, recorded: list[str] | None = None) -> list[Path]:
    """Writes the scripts for the shells this system has; what it wrote
    (or found up to date). A file of the same name that isn't ours stays.
    zsh's goes where it was put before (`recorded`), if it's still there:
    asking zsh for its fpath runs the user's .zshrc, which can take seconds."""
    targets = []
    if shutil.which("bash"):
        targets.append(("bash", _bash_file()))
    if shutil.which("fish"):
        targets.append(("fish", _fish_file()))
    if shutil.which("zsh"):
        before = [Path(p) for p in recorded or [] if Path(p).name == "_myfox" and _ours(Path(p))]
        target = before[0] if before else zsh_file(fpath)
        if target is not None:
            targets.append(("zsh", target))
    written = []
    for shell, path in targets:
        if path.exists() and not _ours(path):
            continue
        try:
            if not path.is_file() or path.read_text(encoding="utf-8") != SCRIPTS[shell]:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(SCRIPTS[shell], encoding="utf-8")
        except OSError:
            continue
        written.append(path)
    return written


def remove(recorded: list[str] | None = None) -> None:
    """Deletes the scripts MyFox wrote: the recorded ones and those where
    bash and fish look, each only if it is ours."""
    for path in {Path(p) for p in recorded or []} | {_bash_file(), _fish_file()}:
        if _ours(path):
            try:
                path.unlink()
            except OSError:
                pass


def zsh_by_hand(written: list[Path]) -> bool:
    """zsh is there but its script went nowhere (no folder of the user's own)."""
    return bool(shutil.which("zsh")) and not any(p.name == "_myfox" for p in written)
