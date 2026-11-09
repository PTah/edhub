"""Язык интерфейса и голоса."""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("EDHUD_LANG", "ru")

from edhud import i18n
from edhud.voice import voice_script


class LanguageTests(unittest.TestCase):
    def tearDown(self) -> None:
        i18n.set_language("ru")

    def test_catalogs_have_the_same_keys(self) -> None:
        self.assertEqual(set(i18n._STRINGS["ru"]), set(i18n._STRINGS["en"]))

    def test_russian_windows_only(self) -> None:
        self.assertEqual(i18n.language_from_langids([0x0419], "win32"), "ru")
        self.assertEqual(i18n.language_from_langids([0x0409], "win32"), "en")
        self.assertEqual(i18n.language_from_langids([0x0419, 0x0409], "win32"), "ru")
        self.assertEqual(i18n.language_from_langids([0x0419], "linux"), "en")

    def test_english_voice_phrase_and_sapi(self) -> None:
        i18n.set_language("en")
        self.assertEqual(i18n.t("voice.brake"), "Slow down")
        self.assertIn("Biological signal", i18n.t("voice.bio", short="2", count=1, possible=""))
        script = voice_script("hello", 0, "en")
        self.assertIn("0409", script)
        self.assertNotIn("-ExecutionPolicy", script)
        self.assertNotIn(".ps1", script)

    def test_russian_voice_uses_russian_sapi(self) -> None:
        i18n.set_language("ru")
        self.assertEqual(i18n.t("voice.brake"), "Тормози")
        script = voice_script("привет", 0, "ru")
        self.assertIn("0419", script)
        self.assertIn("привет", script)
