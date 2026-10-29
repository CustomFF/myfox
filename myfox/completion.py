"""`myfox completion bash|zsh|fish`: the shell's completion script. The
scripts only pass the command line to `myfox _complete`, which answers
from the argument parser itself and the profiles on disk, so they never
go stale after an update."""

from __future__ import annotations

import argparse
from typing import Callable

from . import i18n, profile_commands
from .state import State

COMMAND = "_complete"
SHELLS = ("bash", "zsh", "fish")

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
