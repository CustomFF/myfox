from __future__ import annotations

import io
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from myfox import __main__, completion, i18n

from ._helpers import IsolatedStateCase


def _profiles(state, command):
    return {"use": [("x7k2p9qa.myfox-1", "Work")],
            "import": [("snap:abc.default", ""), ("ab12cd34.default-release", "")]}.get(command, [])


class CompleteTests(IsolatedStateCase):
    def _words(self, *words: str) -> list[str]:
        found = completion.complete(list(words), None, __main__.build_parser(), profiles=_profiles)
        return [c for c, _ in found]

    def test_commands_with_browser_and_without_the_hidden_ones(self):
        found = self._words("")
        self.assertEqual(found[0], "browser")
        self.assertIn("completion", found)
        self.assertNotIn(completion.COMMAND, found)
        self.assertNotIn("_sync", found)

    def test_a_prefix_narrows_them(self):
        self.assertEqual(self._words("re"), ["refresh", "reinstall"])

    def test_commands_come_with_their_description(self):
        found = dict(completion.complete(["prof"], None, __main__.build_parser(), profiles=_profiles))
        self.assertEqual(found, {"profile": i18n.t("cmd_profile")})

    def test_subcommands_of_profile(self):
        self.assertEqual(self._words("profile", ""), ["list", "new", "import", "apply", "use", "remove"])

    def test_options_of_the_command_typed(self):
        found = self._words("refresh", "--")
        self.assertIn("--check", found)
        self.assertIn("--yes", found)
        self.assertNotIn("--remove-profile", found)

    def test_an_options_value(self):
        self.assertEqual(self._words("profile", "import", "--sync", ""), ["none", "copy", "move"])

    def test_a_free_value_is_not_taken_for_the_profile(self):
        self.assertEqual(self._words("profile", "import", "--name", ""), [])
        self.assertEqual(self._words("profile", "import", "--name", "Mine", "snap"), ["snap:abc.default"])

    def test_profile_ids_for_the_subcommand(self):
        self.assertEqual(self._words("profile", "use", "--gui", ""), ["x7k2p9qa.myfox-1"])
        self.assertEqual(self._words("profile", "import", ""), ["snap:abc.default", "ab12cd34.default-release"])

    def test_one_profile_only(self):
        self.assertEqual(self._words("profile", "use", "x7k2p9qa.myfox-1", ""), [])

    def test_positional_choices(self):
        self.assertEqual(self._words("command", ""), ["on", "off"])
        self.assertEqual(self._words("completion", ""), ["bash", "zsh", "fish"])

    def test_nothing_for_firefoxs_own_arguments(self):
        self.assertEqual(self._words("browser", "--new"), [])

    def test_the_hidden_command_prints_tab_separated_lines(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(__main__.main([completion.COMMAND, "command", "o"]), 0)
        self.assertEqual(out.getvalue(), "on\t\noff\t\n")

    def test_completion_prints_the_script(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(__main__.main(["completion", "fish"]), 0)
        self.assertEqual(out.getvalue(), completion.SCRIPTS["fish"])


class InstallTests(IsolatedStateCase):
    def setUp(self):
        super().setUp()
        self.home = self.tmp_path / "home"
        self.zfunc = self.home / ".zsh" / "completions"
        self.zfunc.mkdir(parents=True)
        patcher = mock.patch.dict("os.environ")
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("BASH_COMPLETION_USER_DIR", None)
        self.bash = self.tmp_path / "data" / "bash-completion" / "completions" / "myfox"
        self.fish = self.tmp_path / "data" / "fish" / "vendor_completions.d" / "myfox.fish"

    def _install(self, fpath, shells=completion.SHELLS) -> list[Path]:
        with mock.patch("shutil.which", side_effect=lambda name: name if name in shells else None):
            return completion.install(fpath=lambda: fpath)

    def test_each_shell_where_it_looks_by_itself(self):
        written = self._install([Path("/usr/share/zsh/functions"), self.zfunc])
        self.assertEqual(written, [self.bash, self.fish, self.zfunc / "_myfox"])
        self.assertEqual(self.bash.read_text(encoding="utf-8"), completion.SCRIPTS["bash"])
        self.assertEqual(self.fish.read_text(encoding="utf-8"), completion.SCRIPTS["fish"])
        self.assertEqual((self.zfunc / "_myfox").read_text(encoding="utf-8"), completion.SCRIPTS["zsh"])

    def test_only_the_shells_the_system_has(self):
        self.assertEqual(self._install([self.zfunc], shells=("bash",)), [self.bash])
        self.assertFalse(self.fish.exists())

    def test_zsh_skips_a_plugin_managers_checkout(self):
        plugin = self.home / ".oh-my-zsh" / "plugins" / "git"
        plugin.mkdir(parents=True)
        (self.home / ".oh-my-zsh" / ".git").mkdir()
        self.assertEqual(completion.zsh_file(lambda: [plugin, self.zfunc]), self.zfunc / "_myfox")
        self.assertIsNone(completion.zsh_file(lambda: [plugin]))

    def test_zsh_keeps_the_folder_it_has_already_used(self):
        later = self.home / ".zfunc"
        later.mkdir()
        (later / "_myfox").write_text(completion.SCRIPTS["zsh"], encoding="utf-8")
        self.assertEqual(completion.zsh_file(lambda: [self.zfunc, later]), later / "_myfox")

    def test_zsh_goes_where_it_went_before_without_asking_zsh(self):
        first = self._install([self.zfunc])

        def ask():
            raise AssertionError("asked zsh")

        with mock.patch("shutil.which", side_effect=lambda name: name):
            self.assertEqual(completion.install(fpath=ask, recorded=[str(p) for p in first]), first)

    def test_zsh_without_a_folder_of_ones_own_is_set_up_by_hand(self):
        written = self._install([Path("/usr/share/zsh/functions")])
        self.assertEqual(written, [self.bash, self.fish])
        with mock.patch("shutil.which", return_value="zsh"):
            self.assertTrue(completion.zsh_by_hand(written))

    def test_a_file_that_isnt_ours_stays(self):
        self.bash.parent.mkdir(parents=True)
        self.bash.write_text("# someone else's\n", encoding="utf-8")
        self.assertNotIn(self.bash, self._install([self.zfunc]))
        completion.remove([str(self.bash)])
        self.assertEqual(self.bash.read_text(encoding="utf-8"), "# someone else's\n")

    def test_remove_takes_what_was_recorded_and_the_usual_places(self):
        written = self._install([self.zfunc])
        completion.remove([str(self.zfunc / "_myfox")])
        self.assertEqual([p for p in written if p.exists()], [])


class ScriptTests(unittest.TestCase):
    """The scripts against a `myfox` that answers like `_complete` would."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        fake = self.dir / "myfox"
        fake.write_text('#!/bin/sh\necho "$@" > "$(dirname "$0")/args"\n'
                        'printf "snap:abc.default\\tMain\\nsnap:abd\\t\\n"\n', encoding="utf-8")
        fake.chmod(0o755)
        self.env = {**os.environ, "PATH": f"{self.dir}:{os.environ['PATH']}"}
        for shell in completion.SHELLS:
            (self.dir / f"c.{shell}").write_text(completion.SCRIPTS[shell], encoding="utf-8")

    @unittest.skipUnless(shutil.which("bash"), "no bash")
    def test_bash_completes_after_the_colon_of_an_id(self):
        script = ('source c.bash; l="myfox profile import snap:ab"; COMP_LINE="$l"; COMP_POINT=${#l}; '
                  '_myfox myfox; printf "%s\\n" "${COMPREPLY[@]}"')
        out = subprocess.run(["bash", "-c", script], cwd=self.dir, env=self.env, capture_output=True,
                             text=True, check=True).stdout
        self.assertEqual(out.split(), ["abc.default", "abd"])
        self.assertEqual((self.dir / "args").read_text().split(), ["_complete", "profile", "import", "snap:ab"])

    @unittest.skipUnless(shutil.which("fish"), "no fish")
    def test_fish_passes_the_words_and_shows_descriptions(self):
        script = "source c.fish; complete -C'myfox profile import '"
        out = subprocess.run(["fish", "--no-config", "-c", script], cwd=self.dir, env=self.env,
                             capture_output=True, text=True, check=True).stdout
        self.assertIn("snap:abc.default\tMain", out)
        self.assertEqual((self.dir / "args").read_text().split(), ["_complete", "profile", "import"])

    @unittest.skipUnless(shutil.which("zsh"), "no zsh")
    def test_zsh_script_parses(self):
        subprocess.run(["zsh", "-n", "c.zsh"], cwd=self.dir, check=True)


if __name__ == "__main__":
    unittest.main()
