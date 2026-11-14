# Created by nc.ai 1.2.11 on Papasha 2026-11-14 17:43:27
"""Тесты отправки в EDDN: схемы и дополнение сообщений."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud import eddn_upload  # noqa: E402
from edhud.model import GameState  # noqa: E402


def state() -> GameState:
    st = GameState()
    st.cmdr = "CMDR Test"
    st.game_version = "4.0.0.1900"
    st.build = "r300000/r0 "
    st.system.name = "Test System"
    st.system.address = 42
    st.system.star_pos = (1.0, 2.0, 3.0)
    return st


class EnvelopeTests(unittest.TestCase):
    def test_scan_uses_journal_schema_and_augments_location(self) -> None:
        st = state()
        envelope = eddn_upload.build_envelope(
            {
                "timestamp": "2025-01-01T00:00:00Z",
                "event": "Scan",
                "BodyID": 3,
                "BodyName": "Test System 2 a",
            },
            st,
            "1.0.0",
        )
        assert envelope is not None
        self.assertEqual(envelope["$schemaRef"], "https://eddn.edcd.io/schemas/journal/1")
        self.assertEqual(envelope["header"]["uploaderID"], "CMDR Test")
        message = envelope["message"]
        self.assertEqual(message["SystemAddress"], 42)
        self.assertEqual(message["StarSystem"], "Test System")
        self.assertEqual(message["StarPos"], [1.0, 2.0, 3.0])

    def test_fss_body_signals_strips_localised(self) -> None:
        st = state()
        envelope = eddn_upload.build_envelope(
            {
                "timestamp": "2025-01-01T00:00:00Z",
                "event": "FSSBodySignals",
                "BodyID": 3,
                "Signals": [
                    {"Type": "$SAA_SignalType_Biological;", "Type_Localised": "Biological", "Count": 2}
                ],
            },
            st,
            "1.0.0",
        )
        assert envelope is not None
        self.assertEqual(envelope["$schemaRef"], "https://eddn.edcd.io/schemas/fssbodysignals/1")
        signal = envelope["message"]["Signals"][0]
        self.assertIn("Type", signal)
        self.assertNotIn("Type_Localised", signal)

    def test_legacy_events_are_skipped(self) -> None:
        st = state()
        st.legacy = True
        self.assertIsNone(
            eddn_upload.build_envelope(
                {"timestamp": "2025-01-01T00:00:00Z", "event": "Scan"},
                st,
                "1.0.0",
            )
        )


if __name__ == "__main__":
    unittest.main()
