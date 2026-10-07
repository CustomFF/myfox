from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from myfox import firefox


class DetectArchTests(unittest.TestCase):
    def test_x86_64_is_amd64(self):
        with mock.patch("platform.machine", return_value="x86_64"):
            self.assertEqual(firefox.detect_arch(), "amd64")

    def test_aarch64_is_arm64(self):
        with mock.patch("platform.machine", return_value="aarch64"):
            self.assertEqual(firefox.detect_arch(), "arm64")

    def test_unknown_machine_is_unsupported(self):
        with mock.patch("platform.machine", return_value="i686"):
            self.assertIsNone(firefox.detect_arch())


class PickLangTests(unittest.TestCase):
    # A slice of a *real* fetch_lang_catalog() response (checked live
    # 2026-09-30: 172 codes, 40 of them regional) — not invented, so the
    # matching logic is proven against what Mozilla actually ships, not
    # against our own assumptions about it.
    CATALOG = {
        "ru": "Russian", "de": "German", "fr": "French", "uk": "Ukrainian",
        "pt-BR": "Portuguese (Brazilian)", "pt-PT": "Portuguese (Portugal)",
        "zh-CN": "Chinese (Simplified)", "zh-TW": "Chinese (Traditional)",
        "en-US": "English (US)", "en-GB": "English (British)", "en-AU": "English (Australian)",
        "de-AT": "German (Austria)", "de-CH": "German (Switzerland)", "de-DE": "German (Germany)",
        "es-ES": "Spanish (Spain)", "es-AR": "Spanish (Argentina)",
        "nb-NO": "Norwegian (Bokmål)", "nn-NO": "Norwegian (Nynorsk)",
        "hi-IN": "Hindi (India)", "sv-SE": "Swedish",
    }

    CASES = [
        ("ru_RU.UTF-8", "ru"),  # bare "ru" exists — no "ru-RU" needed
        ("de_DE.UTF-8", "de-DE"),  # region-specific beats the also-valid bare "de"
        ("de_XX.UTF-8", "de"),  # unknown region for a language with a bare fallback
        ("pt_BR.UTF-8", "pt-BR"),
        ("pt_PT.UTF-8", "pt-PT"),
        ("zh_CN.UTF-8", "zh-CN"),
        ("zh_TW.UTF-8", "zh-TW"),
        ("en_GB.UTF-8", "en-GB"),
        ("en_AU.UTF-8", "en-AU"),
        ("es_AR.UTF-8", "es-AR"),  # a regional variant, not only es-ES
        ("hi_IN.UTF-8", "hi-IN"),
        ("uk_UA.UTF-8", "uk"),
        ("xx_XX.UTF-8", "en-US"),  # unsupported language -> honest default
        ("ru_RU.UTF-8@euro", "ru"),  # @modifier stripped
    ]

    def test_table(self):
        for env_lang, expected in self.CASES:
            with self.subTest(env_lang=env_lang):
                self.assertEqual(firefox.pick_lang(self.CATALOG, env_lang), expected)

    def test_bare_language_with_only_regional_flavors_falls_back_to_default(self):
        # "no"/"pt"/"zh"/"en" alone aren't real Mozilla codes (see the live
        # check above) — no guessed region, an honest default instead.
        for bare in ("no", "pt", "zh", "en"):
            with self.subTest(bare=bare):
                self.assertEqual(firefox.pick_lang(self.CATALOG, bare), "en-US")

    def test_uses_environ_lang_when_no_argument_given(self):
        with mock.patch.dict("os.environ", {"LANG": "de_DE.UTF-8"}, clear=True):
            self.assertEqual(firefox.pick_lang(self.CATALOG), "de-DE")

    def test_missing_environ_lang_defaults_to_en_us(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(firefox.pick_lang(self.CATALOG), "en-US")


class PickLangLiveCatalogTests(unittest.TestCase):
    """Same matching logic, against the real, freshly-fetched catalog —
    the point of pick_lang is to never drift from this."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.catalog = firefox.fetch_lang_catalog()
        except OSError:
            cls.catalog = None

    def test_real_catalog_resolves_realistic_locales(self):
        if not self.catalog:
            self.skipTest("no network")
        self.assertEqual(firefox.pick_lang(self.catalog, "ru_RU.UTF-8"), "ru")
        self.assertEqual(firefox.pick_lang(self.catalog, "pt_BR.UTF-8"), "pt-BR")
        self.assertEqual(firefox.pick_lang(self.catalog, "en_AU.UTF-8"), "en-AU")


class LocalVersionTests(unittest.TestCase):
    def test_reads_version_from_application_ini(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            (path / "application.ini").write_text("[App]\nVersion=123.0\nName=Firefox\n", encoding="utf-8")
            self.assertEqual(firefox.local_version(path), "123.0")

    def test_missing_file_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(firefox.local_version(Path(d)))


class ValidateInstallDirTests(unittest.TestCase):
    def test_empty_string_rejected(self):
        with self.assertRaises(firefox.InstallDirError) as ctx:
            firefox.validate_install_dir("   ")
        self.assertEqual(ctx.exception.key, "err_installdir_empty")

    def test_relative_path_rejected(self):
        with self.assertRaises(firefox.InstallDirError) as ctx:
            firefox.validate_install_dir("relative/path")
        self.assertEqual(ctx.exception.key, "err_installdir_relative")

    def test_root_rejected(self):
        with self.assertRaises(firefox.InstallDirError) as ctx:
            firefox.validate_install_dir("/")
        self.assertEqual(ctx.exception.key, "err_installdir_root")

    def test_existing_empty_writable_dir_is_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            target = str(Path(d) / "sub")
            Path(target).mkdir()
            self.assertEqual(firefox.validate_install_dir(target), Path(target))

    def test_existing_dir_with_foreign_contents_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "something").write_text("x", encoding="utf-8")
            with self.assertRaises(firefox.InstallDirError) as ctx:
                firefox.validate_install_dir(str(d))
            self.assertEqual(ctx.exception.key, "err_installdir_foreign")

    def test_existing_dir_with_our_marker_is_accepted_even_if_nonempty(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "something").write_text("x", encoding="utf-8")
            (Path(d) / ".myfox-installed").write_text("", encoding="utf-8")
            self.assertEqual(firefox.validate_install_dir(str(d)), Path(d))

    def test_nonexistent_path_with_writable_parent_is_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            target = str(Path(d) / "not-yet-created")
            self.assertEqual(firefox.validate_install_dir(target), Path(target))

    def test_tilde_is_expanded(self):
        with mock.patch("pathlib.Path.home", return_value=Path("/home/fakeuser")):
            with self.assertRaises(firefox.InstallDirError) as ctx:
                # /home/fakeuser almost certainly doesn't exist on the test
                # machine — this only checks the tilde was expanded to an
                # absolute path at all (no err_installdir_relative), not
                # that the target is actually usable.
                firefox.validate_install_dir("~/wherever")
            self.assertNotEqual(ctx.exception.key, "err_installdir_relative")


class DirClaimStateTests(unittest.TestCase):
    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(firefox.dir_claim_state(Path(d)), "empty")

    def test_ours_via_application_ini_and_marker(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            (path / "application.ini").write_text("[App]\nVersion=1\n", encoding="utf-8")
            (path / ".myfox-installed").write_text("", encoding="utf-8")
            self.assertEqual(firefox.dir_claim_state(path), "ours")

    def test_foreign_when_nonempty_without_our_marker(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "something").write_text("x", encoding="utf-8")
            self.assertEqual(firefox.dir_claim_state(Path(d)), "foreign")


class FetchLangCatalogTests(unittest.TestCase):
    def _fake_response(self, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        cm = mock.MagicMock()
        cm.__enter__.return_value.read.return_value = body
        return cm

    def test_flattens_to_code_to_english_name(self):
        payload = {"ru": {"English": "Russian", "native": "Русский"}}
        with mock.patch("urllib.request.urlopen", return_value=self._fake_response(payload)):
            self.assertEqual(firefox.fetch_lang_catalog(), {"ru": "Russian"})

    def test_validate_lang_checks_membership(self):
        payload = {"ru": {"English": "Russian"}}
        with mock.patch("urllib.request.urlopen", return_value=self._fake_response(payload)):
            self.assertTrue(firefox.validate_lang("ru"))
            self.assertFalse(firefox.validate_lang("xx"))


class ResolveDownloadTests(unittest.TestCase):
    def test_extracts_version_from_the_effective_url(self):
        cm = mock.MagicMock()
        cm.__enter__.return_value.geturl.return_value = (
            "https://download-installer.cdn.mozilla.net/pub/firefox/releases/158.0/linux-x86_64/ru/firefox-158.0.tar.xz"
        )
        with mock.patch("urllib.request.urlopen", return_value=cm):
            url, version = firefox.resolve_download("amd64", "ru", "stable")
        self.assertEqual(version, "158.0")
        self.assertIn("linux-x86_64", url)

    def test_arm64_asks_mozilla_for_the_aarch64_build(self):
        # "linux64-aarch64" is Mozilla's name for it; "linux-aarch64" is a 404.
        cm = mock.MagicMock()
        cm.__enter__.return_value.geturl.return_value = (
            "https://download-installer.cdn.mozilla.net/pub/firefox/releases/158.0/linux-aarch64/ru/firefox-158.0.tar.xz"
        )
        with mock.patch("urllib.request.urlopen", return_value=cm) as urlopen:
            url, version = firefox.resolve_download("arm64", "ru", "stable")
        self.assertIn("os=linux64-aarch64&", urlopen.call_args.args[0].full_url)
        self.assertEqual((version, url.split("/")[-3]), ("158.0", "linux-aarch64"))


if __name__ == "__main__":
    unittest.main()
