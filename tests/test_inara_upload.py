# Created by nc.ai 1.2.11 on Papasha 2026-11-14 17:43:35
"""Тесты отправки travel-событий в INARA."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud import inara_upload  # noqa: E402
from edhud.model import GameState  # noqa: E402


def state() -> GameState:
    st = GameState()
    st.cmdr = "CMDR Test"
    st.fid = "F123"
    st.ship = "Asp"
    st.system.name = "Test System"
    return st


class InaraEventTests(unittest.TestCase):
    def test_fsdjump_payload(self) -> None:
        st = state()
        data = inara_upload._event_data(
            "FSDJump",
            {"StarSystem": "Elsewhere", "StarPos": [1, 2, 3], "JumpDist": 12.3, "ShipID": 7},
            st,
        )
        self.assertEqual(data["starsystemName"], "Elsewhere")
        self.assertEqual(data["starsystemCoords"], [1.0, 2.0, 3.0])
        self.assertEqual(data["jumpDistance"], 12.3)
        self.assertEqual(data["shipType"], "Asp")
        self.assertEqual(data["shipGameID"], 7)

    def test_touchdown_requires_body(self) -> None:
        st = state()
        self.assertIsNone(inara_upload._event_data("Touchdown", {"StarSystem": "S"}, st))
        data = inara_upload._event_data(
            "Touchdown",
            {"StarSystem": "S", "Body": "S 1 a", "Latitude": 1.5, "Longitude": 2.5},
            st,
        )
        assert data is not None
        self.assertEqual(data["starsystemName"], "S")
        self.assertEqual(data["latitude"], 1.5)

    def test_batch_header_uses_config_later(self) -> None:
        st = state()
        payload = inara_upload.build_batch(
            [({"timestamp": "2025-01-01T00:00:00Z", "event": "FSDJump", "StarSystem": "S"}, st)],
            "1.0.0",
        )
        assert payload is not None
        self.assertEqual(payload["header"]["commanderName"], "CMDR Test")
        self.assertEqual(payload["header"]["commanderFrontierID"], "F123")
        self.assertEqual(payload["events"][0]["eventName"], "addCommanderTravelFSDJump")


if __name__ == "__main__":
    unittest.main()
