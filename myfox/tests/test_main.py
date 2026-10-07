from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from myfox import __main__ as cli
from myfox import i18n
from myfox.state import State, state_file
from ._helpers import IsolatedStateCase


def _run(argv: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli.main(argv)
    return rc, buf.getvalue()


class UninstallTests(IsolatedStateCase):
    def setUp(self):
        super().setUp()
        running = mock.patch("myfox.firefox.running_pids", return_value=[])
        running.start()
        self.addCleanup(running.stop)

    def _installed(self, d: str, **extra) -> tuple[State, Path]:
        install_dir = Path(d) / "firefox"
        install_dir.mkdir()
        state = State()
        state.set("install_dir", str(install_dir))
        for key, value in extra.items():
            state.set(key, value)
        state.save()
        return state, install_dir

    def test_not_installed_is_a_noop(self):
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(cli.cmd_uninstall(State(), noninteractive=True), 0)
        self.assertEqual(err.getvalue().strip(), i18n.t("err_not_installed"))

    def test_noninteractive_removes_the_install_dir_and_clears_state(self):
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
            state, install_dir = self._installed(d)
            rc = cli.cmd_uninstall(state, noninteractive=True)
            self.assertEqual(rc, 0)
            self.assertFalse(install_dir.exists())
            self.assertFalse(state_file().exists())
            self.assertFalse(state_file().parent.exists())

    def test_without_a_terminal_and_yes_removes_nothing(self):
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()) as err, \
             mock.patch("myfox.ui._has_tty", return_value=False):
            state, install_dir = self._installed(d)
            rc = cli.cmd_uninstall(state, noninteractive=False)
            self.assertEqual(rc, 1)
            self.assertTrue(install_dir.exists())
            self.assertEqual(State().get("install_dir"), str(install_dir))
        self.assertIn("myfox uninstall -y", err.getvalue())

    def test_running_firefox_blocks_it(self):
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stderr(io.StringIO()) as err, \
             mock.patch("myfox.firefox.running_pids", return_value=[42]):
            state, install_dir = self._installed(d)
            self.assertEqual(cli.cmd_uninstall(state, noninteractive=True), 1)
            self.assertTrue(install_dir.exists())
        self.assertIn(i18n.t("err_firefox_running"), err.getvalue())

    def test_unregisters_the_profile_without_touching_its_files(self):
        # Only the browser install is removed — the profile (bookmarks,
        # history) stays so a later reinstall can find it again.
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
            profile_dir = Path(d) / "profile"
            profile_dir.mkdir()
            (profile_dir / "places.sqlite").write_text("", encoding="utf-8")
            state, _install_dir = self._installed(d, profile_dir=str(profile_dir), install_hash="DEADBEEF")

            with mock.patch("myfox.profiles.remove_myfox_section") as remove_section, \
                 mock.patch("myfox.profiles.unpin_install") as unpin:
                cli.cmd_uninstall(state, noninteractive=True)

            remove_section.assert_called_once_with(profile_dir)
            unpin.assert_called_once_with("DEADBEEF")
            self.assertTrue((profile_dir / "places.sqlite").exists())

    def _with_profile(self, d: str, created: bool) -> tuple[State, Path]:
        profile_dir = Path(d) / "profile"
        profile_dir.mkdir()
        if created:
            (profile_dir / ".myfox-created").write_text("", encoding="utf-8")
        state, _install_dir = self._installed(d, profile_dir=str(profile_dir))
        return state, profile_dir

    def test_remove_profile_deletes_our_profile(self):
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
            state, profile_dir = self._with_profile(d, created=True)
            cli.cmd_uninstall(state, noninteractive=True, remove_profile=True)
            self.assertFalse(profile_dir.exists())

    def test_remove_profile_spares_a_profile_myfox_did_not_create(self):
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
            state, profile_dir = self._with_profile(d, created=False)
            cli.cmd_uninstall(state, noninteractive=True, remove_profile=True)
            self.assertTrue(profile_dir.exists())

    def test_without_yes_both_commands_are_named(self):
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()) as err, \
             mock.patch("myfox.ui._has_tty", return_value=False):
            state, profile_dir = self._with_profile(d, created=True)
            self.assertEqual(cli.cmd_uninstall(state, noninteractive=False), 1)
            self.assertTrue(profile_dir.exists())
        self.assertEqual(err.getvalue().splitlines(), [
            i18n.t("needs_yes_uninstall", "myfox uninstall -y"),
            i18n.t("needs_yes_uninstall_profile", "myfox uninstall -y --remove-profile"),
        ])


def _fake_tarball(dest, lang, channel, on_download=None, on_extract=None):
    (Path(dest) / "firefox").write_text("new", encoding="utf-8")
    return "158.0"


class ReinstallTests(IsolatedStateCase):
    def setUp(self):
        super().setUp()
        for target, value in (("myfox.firefox.running_pids", []), ("myfox.desktop.write_entry", None)):
            patcher = mock.patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _installed(self, d: str, **extra) -> tuple[State, Path]:
        install_dir = Path(d) / "firefox"
        install_dir.mkdir()
        (install_dir / "firefox").write_text("old", encoding="utf-8")
        state = State()
        state.set("install_dir", str(install_dir))
        for key, value in extra.items():
            state.set(key, value)
        state.save()
        return state, install_dir

    def test_not_installed_returns_an_error(self):
        self.assertEqual(cli.cmd_reinstall(State()), 1)

    def test_swaps_in_the_new_firefox_and_reapplies_tweaks(self):
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
            profile_dir = Path(d) / "profile"
            profile_dir.mkdir()
            state, install_dir = self._installed(d, profile_dir=str(profile_dir), lang="ru", channel="beta")

            with mock.patch("myfox.firefox.install_tarball", side_effect=_fake_tarball) as install, \
                 mock.patch("myfox.profiles.pin_install", return_value="HASH") as pin, \
                 mock.patch("myfox.apply.reapply_tweaks") as reapply:
                rc = cli.cmd_reinstall(state, noninteractive=True)

            self.assertEqual(rc, 0)
            self.assertEqual(install.call_args.args[1:], ("ru", "beta"))
            self.assertEqual((install_dir / "firefox").read_text(encoding="utf-8"), "new")
            self.assertTrue((install_dir / ".myfox-installed").is_file())
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ["firefox", "profile"])  # no leftovers
            pin.assert_called_once()
            self.assertEqual(reapply.call_args.args[:2], (install_dir, profile_dir))
            self.assertEqual(State().get("install_hash"), "HASH")
            self.assertEqual(State().get("firefox_version"), "158.0")

    def test_failed_download_keeps_the_current_firefox(self):
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()):
            state, install_dir = self._installed(d)
            with mock.patch("myfox.firefox.install_tarball", side_effect=OSError("offline")):
                self.assertEqual(cli.cmd_reinstall(state, noninteractive=True), 1)
            self.assertEqual((install_dir / "firefox").read_text(encoding="utf-8"), "old")
            self.assertEqual([p.name for p in Path(d).iterdir()], ["firefox"])

    def test_skips_profile_steps_when_no_profile_is_recorded(self):
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
            state, _install_dir = self._installed(d)
            with mock.patch("myfox.firefox.install_tarball", side_effect=_fake_tarball), \
                 mock.patch("myfox.profiles.pin_install") as pin, \
                 mock.patch("myfox.apply.reapply_tweaks") as reapply:
                self.assertEqual(cli.cmd_reinstall(state, noninteractive=True), 0)
            pin.assert_not_called()
            reapply.assert_not_called()


class RefreshTests(IsolatedStateCase):
    def test_not_installed_returns_an_error(self):
        self.assertEqual(cli.cmd_refresh(State(), force=False, gui=False, noninteractive=False), 1)

    def test_installed_hands_over_to_refresh_run(self):
        state = State()
        state.set("install_dir", "/opt/firefox")
        with mock.patch("myfox.refresh.run", return_value=0) as run:
            self.assertEqual(cli.cmd_refresh(state, force=True, gui=True, noninteractive=False), 0)
        run.assert_called_once_with(state, gui=True, noninteractive=False, force=True)


class DispatchWiringTests(IsolatedStateCase):
    """argv -> cmd_* wiring in main() — the commands' own logic is tested
    directly above, this only checks main() calls the right one with the
    right arguments."""

    def test_refresh_flags_are_forwarded(self):
        with mock.patch("myfox.__main__.cmd_refresh", return_value=0) as cmd:
            cli.main(["refresh", "--force", "--gui", "-y"])
        cmd.assert_called_once_with(mock.ANY, force=True, gui=True, noninteractive=True)

    def test_uninstall_forwards_remove_profile(self):
        with mock.patch("myfox.__main__.cmd_uninstall", return_value=0) as cmd:
            cli.main(["uninstall", "--remove-profile", "-y"])
        cmd.assert_called_once_with(mock.ANY, True, gui=False, remove_profile=True)

    def test_reinstall_dispatches(self):
        with mock.patch("myfox.__main__.cmd_reinstall", return_value=0) as cmd:
            cli.main(["reinstall"])
        cmd.assert_called_once()

    def test_uninstall_forwards_the_noninteractive_flag(self):
        with mock.patch("myfox.__main__.cmd_uninstall", return_value=0) as cmd:
            cli.main(["uninstall", "-y"])
        cmd.assert_called_once_with(mock.ANY, True, gui=False, remove_profile=False)


class BrowserCommandTests(IsolatedStateCase):
    def test_not_installed_reports_and_exits_nonzero(self):
        with contextlib.redirect_stderr(io.StringIO()) as err:
            rc, _out = _run(["browser"])
        self.assertEqual(rc, 1)
        self.assertEqual(err.getvalue().strip(), i18n.t("err_not_installed"))

    def test_execs_the_myfox_wrapper_when_present(self):
        state = State()
        state.set("install_dir", "/opt/firefox")
        state.save()

        with mock.patch("os.access", return_value=True) as access, \
             mock.patch("os.execv") as execv:
            cli.main(["browser", "--new-window"])

        access.assert_called_once_with("/opt/firefox/firefox-myfox", mock.ANY)
        execv.assert_called_once_with(
            "/opt/firefox/firefox-myfox",
            ["/opt/firefox/firefox-myfox", "--new-window"],
        )

    def test_falls_back_to_plain_firefox_binary_when_no_wrapper(self):
        state = State()
        state.set("install_dir", "/opt/firefox")
        state.save()

        with mock.patch("os.access", return_value=False), \
             mock.patch("os.execv") as execv:
            cli.main(["browser"])

        execv.assert_called_once_with("/opt/firefox/firefox", ["/opt/firefox/firefox"])

    def test_a_leading_dash_argument_reaches_firefox_untouched(self):
        # Regression: argparse.REMAINDER silently drops a leading "-"-style
        # token (a documented CPython limitation, confirmed independent of
        # this parser) — "browser" bypasses argparse entirely to dodge it,
        # see main(). --new-window is exactly the shape that broke.
        state = State()
        state.set("install_dir", "/opt/firefox")
        state.save()

        with mock.patch("os.access", return_value=True), \
             mock.patch("os.execv") as execv:
            cli.main(["browser", "--new-window"])

        execv.assert_called_once_with(
            "/opt/firefox/firefox-myfox",
            ["/opt/firefox/firefox-myfox", "--new-window"],
        )


class ParserStructureTests(IsolatedStateCase):
    def test_no_command_prints_help_and_exits_zero(self):
        rc, out = _run([])
        self.assertEqual(rc, 0)
        self.assertIn("myfox", out)

    def test_no_command_help_and_dash_h_help_agree_on_listing_browser(self):
        # "browser" isn't a real argparse subparser (see build_parser) —
        # both entry points into the top-level help must still mention it,
        # not just the bare-`myfox` one.
        _, bare = _run([])
        _, dash_h = _run(["--help"])
        self.assertIn("browser", bare)
        self.assertIn("browser", dash_h)

    def test_unknown_command_is_a_parser_error(self):
        with self.assertRaises(SystemExit) as ctx:
            cli.main(["nonsense"])
        self.assertEqual(ctx.exception.code, 2)

    def test_force_flag_only_exists_on_refresh(self):
        with self.assertRaises(SystemExit):
            cli.main(["uninstall", "--force"])


class VersionFlagTests(unittest.TestCase):
    def test_prints_the_package_version(self):
        import myfox

        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as exit_:
            cli.main(["--version"])
        self.assertEqual((exit_.exception.code, out.getvalue().strip()), (0, f"MyFox {myfox.__version__}"))


if __name__ == "__main__":
    unittest.main()
