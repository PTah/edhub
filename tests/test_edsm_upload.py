"""Выгрузка журнала на EDSM: что отправляем и как помечаем координаты."""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("EDHUD_LANG", "ru")

from edhud.edsm_upload import annotate, build_form, event_key, game_identity, usable


class EdsmUploadTests(unittest.TestCase):
    def test_position_event_carries_coordinates(self) -> None:
        event = {
            "timestamp": "2026-11-08T03:22:17Z",
            "event": "FSDJump",
            "StarSystem": "Smojai UC-C b1-0",
            "SystemAddress": 685182822921,
            "StarPos": [1063.5625, 376.1875, 2807.75],
        }
        self.assertTrue(usable(event, live=False))
        item = annotate(event, event["StarSystem"], event["SystemAddress"], event["StarPos"])
        self.assertEqual(item["_systemCoordinates"], [1063.5625, 376.1875, 2807.75])
        self.assertEqual(item["_systemName"], "Smojai UC-C b1-0")
        self.assertEqual(event_key(event), event_key(item))

    def test_scan_is_live_only(self) -> None:
        scan = {"timestamp": "2026-11-08T03:22:23Z", "event": "Scan", "BodyID": 1}
        self.assertTrue(usable(scan, live=True))
        self.assertFalse(usable(scan, live=False))

    def test_legacy_and_cqc_are_skipped(self) -> None:
        self.assertIsNone(game_identity("3.8.0.400", "r286858/r0"))
        self.assertEqual(game_identity("4.9.0.100", " r1 "), ("4.9.0.100", "r1"))
        jump = {
            "timestamp": "2026-11-08T03:22:17Z",
            "event": "FSDJump",
            "StarSystem": "CQC",
            "StarPos": [0, 0, 0],
        }
        self.assertFalse(usable(jump, live=True))

    def test_form_has_software_and_message(self) -> None:
        form = build_form("Cmdr", "secret", "1.3.2", "4.9.0.100", "r1", [{"event": "FSDJump"}])
        self.assertEqual(form["fromSoftware"], "EDHUD")
        self.assertEqual(form["commanderName"], "Cmdr")
        self.assertIn("FSDJump", form["message"])
        self.assertNotIn("secret", form["message"])
