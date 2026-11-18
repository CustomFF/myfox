from __future__ import annotations

import os
import unittest

from ._helpers import WINDOWS, IsolatedStateCase


@unittest.skipUnless(WINDOWS, "Windows only")
class FirefoxTracesTests(IsolatedStateCase):
    """What Firefox registers for this user, under a hash of its own in the
    real HKCU (the function under test takes it away again)."""

    def setUp(self):
        super().setUp()
        import winreg

        from myfox import winshell

        self.winreg, self.winshell = winreg, winshell
        self.hash = os.urandom(8).hex().upper()
        self.install = self.tmp_path / "ff"
        self.install.mkdir()
        (self.install / "firefox.exe").write_bytes(b"")
        self.other = self.tmp_path / "other"
        self.other.mkdir()
        (self.other / "firefox.exe").write_bytes(b"")
        self.keys = [rf"Software\Classes\FirefoxHTML-{self.hash}", rf"Software\Clients\StartMenuInternet\Firefox-{self.hash}",
                     rf"Software\Mozilla\Firefox\Installer\{self.hash}"]
        for key in self.keys:
            winreg.CreateKey(winreg.HKEY_CURRENT_USER, key).Close()
        self._value(r"Software\RegisteredApplications", f"Firefox-{self.hash}", "x")
        self._value(r"Software\Classes\.myfoxtest\OpenWithProgids", f"FirefoxHTML-{self.hash}", "")
        self._value(r"Software\Classes\.myfoxtest\OpenWithProgids", "Other.Html", "")
        self._value(r"Software\Mozilla\Firefox\TaskBarIDs", str(self.install), "ABC")
        self._value(r"Software\Mozilla\Firefox\TaskBarIDs", str(self.other), "DEF")
        self.addCleanup(self._cleanup)

    def _value(self, path, name, data):
        with self.winreg.CreateKey(self.winreg.HKEY_CURRENT_USER, path) as key:
            self.winreg.SetValueEx(key, name, 0, self.winreg.REG_SZ, data)

    def _has_value(self, path, name):
        try:
            with self.winreg.OpenKey(self.winreg.HKEY_CURRENT_USER, path) as key:
                self.winreg.QueryValueEx(key, name)
                return True
        except OSError:
            return False

    def _cleanup(self):
        self.winshell._delete_tree(r"Software\Classes\.myfoxtest")
        for ext in (".myfoxtest", ".myfoxtest2"):
            self.winshell._delete_tree(rf"{self.winshell._FILE_CHOICES}\{ext}")
        # Keys the test made, left empty, go with it.
        self.winshell._drop_values(r"Software\Mozilla", lambda text: str(self.other) in text)

    def _shortcut(self, path, target):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.winshell._powershell(f"$l = (New-Object -ComObject WScript.Shell).CreateShortcut('{path}'); "
                                  f"$l.TargetPath = '{target}'; $l.Save()")

    def test_this_installs_registrations_and_shortcuts_go_anothers_stay(self):
        programs = self.tmp_path / "config" / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        ours, theirs = programs / "Firefox.lnk", programs / "Other Firefox.lnk"
        self._shortcut(ours, self.install / "firefox.exe")
        self._shortcut(theirs, self.other / "firefox.exe")

        self.winshell.remove_firefox_traces(self.install, self.hash)

        for key in self.keys:
            with self.assertRaises(OSError):
                self.winreg.OpenKey(self.winreg.HKEY_CURRENT_USER, key).Close()
        self.assertFalse(self._has_value(r"Software\RegisteredApplications", f"Firefox-{self.hash}"))
        self.assertFalse(self._has_value(r"Software\Classes\.myfoxtest\OpenWithProgids", f"FirefoxHTML-{self.hash}"))
        self.assertTrue(self._has_value(r"Software\Classes\.myfoxtest\OpenWithProgids", "Other.Html"))
        self.assertFalse(self._has_value(r"Software\Mozilla\Firefox\TaskBarIDs", str(self.install)))
        self.assertTrue(self._has_value(r"Software\Mozilla\Firefox\TaskBarIDs", str(self.other)))
        self.assertEqual((ours.exists(), theirs.exists()), (False, True))

    def test_default_app_choices_naming_this_install_go(self):
        files = self.winshell._FILE_CHOICES
        self._value(rf"{files}\.myfoxtest\UserChoice", "ProgId", f"FirefoxHTML-{self.hash}")
        self._value(rf"{files}\.myfoxtest\OpenWithProgids", f"FirefoxHTML-{self.hash}", "")
        self._value(rf"{files}\.myfoxtest2\UserChoice", "ProgId", "Other.Html")

        self.winshell.remove_firefox_traces(self.install, self.hash)

        self.assertFalse(self._has_value(rf"{files}\.myfoxtest\UserChoice", "ProgId"))
        self.assertFalse(self._has_value(rf"{files}\.myfoxtest\OpenWithProgids", f"FirefoxHTML-{self.hash}"))
        self.assertTrue(self._has_value(rf"{files}\.myfoxtest2\UserChoice", "ProgId"))


if __name__ == "__main__":
    unittest.main()
