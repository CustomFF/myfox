from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from myfox import __main__ as cli
from myfox import i18n
from myfox.state import State
from ._helpers import IsolatedStateCase


def _run(argv: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli.main(argv)
    return rc, buf.getvalue()


class _FakeUI:
    """Duck-types ui.Backend without going through a real terminal/stdin —
    the cmd_* functions are tested directly, argv/backend-selection wiring
    is covered separately in DispatchWiringTests."""

    def __init__(self, confirm_answer: bool = True):
        self.messages: list[str] = []
        self.confirm_answer = confirm_answer

    def confirm(self, prompt, default=True):
        return self.confirm_answer

    def choose(self, header, options, default=None):
        return default

    def input_dir(self, prompt, initial):
        return initial

    def message(self, text):
        self.messages.append(text)

    @contextlib.contextmanager
    def spin(self, title):
        yield


class UninstallTests(IsolatedStateCase):
    def test_not_installed_is_a_noop(self):
        ui = _FakeUI()
        self.assertEqual(cli.cmd_uninstall(State(), ui, noninteractive=True), 0)
        self.assertEqual(ui.messages, [i18n.t("err_not_installed")])

    def test_noninteractive_removes_the_install_dir_and_clears_state(self):
        with tempfile.TemporaryDirectory() as d:
            install_dir = Path(d) / "firefox"
            install_dir.mkdir()
            state = State()
            state.set("install_dir", str(install_dir))
            state.save()

            rc = cli.cmd_uninstall(state, _FakeUI(), noninteractive=True)

            self.assertEqual(rc, 0)
            self.assertFalse(install_dir.exists())
            self.assertIsNone(State().get("install_dir"))

    def test_interactive_decline_removes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            install_dir = Path(d) / "firefox"
            install_dir.mkdir()
            state = State()
            state.set("install_dir", str(install_dir))
            state.save()

            rc = cli.cmd_uninstall(state, _FakeUI(confirm_answer=False), noninteractive=False)

            self.assertEqual(rc, 1)
            self.assertTrue(install_dir.exists())
            self.assertEqual(State().get("install_dir"), str(install_dir))

    def test_unregisters_the_profile_without_touching_its_files(self):
        # Only the browser install is removed — the profile (bookmarks,
        # history) stays so a later reinstall can find it again (see
        # profiles.list_myfox's own docstring on orphaned myfox-* dirs).
        with tempfile.TemporaryDirectory() as d:
            install_dir = Path(d) / "firefox"
            profile_dir = Path(d) / "profile"
            install_dir.mkdir()
            profile_dir.mkdir()
            (profile_dir / "places.sqlite").write_text("", encoding="utf-8")
            state = State()
            state.set("install_dir", str(install_dir))
            state.set("profile_dir", str(profile_dir))
            state.set("install_hash", "DEADBEEF")
            state.save()

            with mock.patch("myfox.profiles.remove_myfox_section") as remove_section, \
                 mock.patch("myfox.profiles.unpin_install") as unpin:
                cli.cmd_uninstall(state, _FakeUI(), noninteractive=True)

            remove_section.assert_called_once_with(profile_dir)
            unpin.assert_called_once_with("DEADBEEF")
            self.assertTrue((profile_dir / "places.sqlite").exists())


class ReinstallTests(IsolatedStateCase):
    def test_not_installed_returns_an_error(self):
        self.assertEqual(cli.cmd_reinstall(State(), _FakeUI()), 1)

    def test_redownloads_firefox_and_reapplies_tweaks(self):
        with tempfile.TemporaryDirectory() as d:
            install_dir = Path(d) / "firefox"
            profile_dir = Path(d) / "profile"
            install_dir.mkdir()
            profile_dir.mkdir()
            state = State()
            state.set("install_dir", str(install_dir))
            state.set("profile_dir", str(profile_dir))
            state.set("lang", "ru")
            state.set("channel", "beta")
            state.save()

            with mock.patch.dict("os.environ", {}, clear=False), \
                 mock.patch("myfox.firefox.install_tarball", return_value="158.0") as install, \
                 mock.patch("myfox.apply.apply_autoconfig") as autoconfig, \
                 mock.patch("myfox.apply.apply_chrome") as chrome, \
                 mock.patch("myfox.apply.apply_theme_pref") as theme, \
                 mock.patch("myfox.addons.fetch_themes", return_value=[]) as themes, \
                 mock.patch("myfox.apply.apply_bookmarklets", return_value=None):
                os.environ.pop("MYFOX_TWEAKS_LOCAL", None)
                rc = cli.cmd_reinstall(state, _FakeUI())

            self.assertEqual(rc, 0)
            install.assert_called_once_with(install_dir, "ru", "beta")
            autoconfig.assert_called_once_with(install_dir)
            chrome.assert_called_once_with(profile_dir)
            theme.assert_called_once_with(profile_dir, "dark")
            themes.assert_called_once_with(profile_dir, local_dir=None)
            self.assertEqual(State().get("firefox_version"), "158.0")

    def test_skips_profile_steps_when_no_profile_is_recorded(self):
        with tempfile.TemporaryDirectory() as d:
            install_dir = Path(d) / "firefox"
            install_dir.mkdir()
            state = State()
            state.set("install_dir", str(install_dir))
            state.save()

            with mock.patch("myfox.firefox.install_tarball", return_value="158.0"), \
                 mock.patch("myfox.apply.apply_autoconfig") as autoconfig, \
                 mock.patch("myfox.apply.apply_chrome") as chrome:
                cli.cmd_reinstall(state, _FakeUI())

            autoconfig.assert_called_once()
            chrome.assert_not_called()


class RefreshTests(IsolatedStateCase):
    def test_not_installed_returns_an_error(self):
        self.assertEqual(cli.cmd_refresh(State(), _FakeUI(), force=False, gui=False, noninteractive=False), 1)

    def test_installed_hands_over_to_refresh_run(self):
        state = State()
        state.set("install_dir", "/opt/firefox")
        with mock.patch("myfox.refresh.run", return_value=0) as run:
            self.assertEqual(cli.cmd_refresh(state, _FakeUI(), force=True, gui=True, noninteractive=False), 0)
        run.assert_called_once_with(state, gui=True, noninteractive=False, force=True)


class DispatchWiringTests(IsolatedStateCase):
    """argv -> cmd_* wiring in main() — the commands' own logic is tested
    directly above, this only checks main() calls the right one with the
    right arguments."""

    def test_refresh_flags_are_forwarded(self):
        with mock.patch("myfox.__main__.cmd_refresh", return_value=0) as cmd:
            cli.main(["refresh", "--force", "--gui", "-y"])
        cmd.assert_called_once_with(mock.ANY, mock.ANY, force=True, gui=True, noninteractive=True)

    def test_reinstall_dispatches(self):
        with mock.patch("myfox.__main__.cmd_reinstall", return_value=0) as cmd:
            cli.main(["reinstall"])
        cmd.assert_called_once()

    def test_uninstall_forwards_the_noninteractive_flag(self):
        with mock.patch("myfox.__main__.cmd_uninstall", return_value=0) as cmd:
            cli.main(["uninstall", "-y"])
        cmd.assert_called_once_with(mock.ANY, mock.ANY, True)


class BrowserCommandTests(IsolatedStateCase):
    def test_not_installed_reports_and_exits_nonzero(self):
        rc, out = _run(["browser"])
        self.assertEqual(rc, 1)
        self.assertTrue(out.strip())  # some message was actually printed

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
