from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from myfox import i18n


class I18nStateGuard(unittest.TestCase):
    """load() mutates module-level globals — every test restores them so
    order between test files never matters."""

    def setUp(self) -> None:
        self._messages_before = dict(i18n._messages)
        self._lang_before = i18n.current_lang
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        i18n._messages = self._messages_before
        i18n.current_lang = self._lang_before


class NormalizeAndDetectTests(I18nStateGuard):
    def test_normalize_strips_encoding_country_and_case(self):
        self.assertEqual(i18n._normalize("ru_RU.UTF-8"), "ru")
        self.assertEqual(i18n._normalize("pt-BR"), "pt")
        self.assertEqual(i18n._normalize("EN"), "en")

    def test_detect_falls_back_to_en_for_a_locale_without_a_catalog(self):
        self.assertEqual(i18n.detect("xx_XX"), "en")

    def test_detect_accepts_a_locale_that_has_a_catalog(self):
        self.assertEqual(i18n.detect("ru_RU.UTF-8"), "ru")


class LoadOverlayMechanismTests(I18nStateGuard):
    """Uses fixture catalogs, not the real en/ru.json — the overlay
    mechanism shouldn't be coupled to the actual (still-changing) copy."""

    def setUp(self) -> None:
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp_dir = Path(self._tmp.name)
        (tmp_dir / "en.json").write_text(json.dumps({"a": "A-en", "b": "B-en"}), encoding="utf-8")
        (tmp_dir / "xx.json").write_text(json.dumps({"a": "A-xx"}), encoding="utf-8")
        patcher = mock.patch.object(i18n, "_LOCALES_DIR", tmp_dir)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_overlay_overrides_only_the_keys_it_has(self):
        i18n.load("xx")
        self.assertEqual(i18n.t("a"), "A-xx")  # overridden
        self.assertEqual(i18n.t("b"), "B-en")  # inherited from the base

    def test_loading_en_uses_the_base_untouched(self):
        i18n.load("en")
        self.assertEqual(i18n.t("a"), "A-en")


class TTests(I18nStateGuard):
    def test_unknown_key_returns_itself_instead_of_raising(self):
        i18n.load("en")
        self.assertEqual(i18n.t("no-such-key"), "no-such-key")

    def test_format_args_are_substituted(self):
        i18n._messages = {"greet": "hello {0}"}
        self.assertEqual(i18n.t("greet", "world"), "hello world")

    def test_no_args_does_not_call_format(self):
        # A literal "{}" in a key with no args must survive as-is, not raise
        # or get treated as a format placeholder.
        i18n._messages = {"literal": "just {} text"}
        self.assertEqual(i18n.t("literal"), "just {} text")


class RealCatalogsTests(I18nStateGuard):
    """Not isolated from the real locales/ dir on purpose — this is the one
    place that should notice a genuinely broken en.json/ru.json."""

    def test_real_catalogs_load_and_answer_a_known_key(self):
        i18n.load("en")
        self.assertNotEqual(i18n.t("usage_title"), "usage_title")
        i18n.load("ru")
        self.assertNotEqual(i18n.t("usage_title"), "usage_title")


if __name__ == "__main__":
    unittest.main()
