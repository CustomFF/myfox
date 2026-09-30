from __future__ import annotations

import contextlib
import io
import unittest
from unittest import mock

from myfox import __main__ as cli
from myfox.state import State
from ._helpers import IsolatedStateCase


def _run(argv: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli.main(argv)
    return rc, buf.getvalue()


class StubbedCommandsTests(IsolatedStateCase):
    """refresh/reinstall/uninstall aren't built yet (pass 2+) — they must
    say so honestly and exit 0, never crash."""

    def test_refresh_is_an_honest_stub(self):
        rc, out = _run(["refresh"])
        self.assertEqual(rc, 0)
        self.assertIn("refresh", out)

    def test_refresh_force_is_still_an_honest_stub(self):
        rc, out = _run(["refresh", "--force"])
        self.assertEqual(rc, 0)
        self.assertIn("refresh", out)

    def test_reinstall_is_an_honest_stub(self):
        rc, out = _run(["reinstall"])
        self.assertEqual(rc, 0)

    def test_uninstall_is_an_honest_stub(self):
        rc, out = _run(["uninstall"])
        self.assertEqual(rc, 0)


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


if __name__ == "__main__":
    unittest.main()
