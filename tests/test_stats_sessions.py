# Created by nc.ai 1.2.15 on Papasha 2026-11-15 16:23:30
"""Статистика сессий: по каждому входу в игру и суммарная."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("EDHUD_LANG", "ru")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud.model import GameState  # noqa: E402
from edhud.stats import SessionStats, StatsStore  # noqa: E402


def played_state(systems: int = 1, scans: int = 2, bio: int = 1) -> GameState:
    state = GameState()
    for index in range(systems):
        state.apply(
            {
                "event": "FSDJump",
                "StarSystem": f"System {index}",
                "SystemAddress": 100 + index,
                "StarPos": [index, 0.0, 0.0],
                "JumpDist": 10.0,
                "WasDiscovered": False,
            }
        )
    for index in range(scans):
        state.apply(
            {
                "event": "Scan",
                "BodyID": index + 1,
                "BodyName": f"Body {index}",
                "SystemAddress": 100,
                "PlanetClass": "Icy body",
                "WasDiscovered": False,
            }
        )
    state.apply({"event": "SAAScanComplete", "BodyID": 1, "BodyName": "Body 0", "SystemAddress": 100})
    for _ in range(bio):
        state.apply(
            {
                "event": "ScanOrganic",
                "ScanType": "Analyse",
                "BodyID": 1,
                "Genus": "$Codex_Ent_Bacterial_Genus_Name;",
                "Species": "$Codex_Ent_Bacterial_01_Name;",
            }
        )
    return state


class StatsStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "stats.json"
        self.store = StatsStore(self.path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_session_counters(self):
        state = played_state(systems=2, scans=3, bio=2)
        self.store.note("Journal.2026-01-01.log", state, save_interval=0)
        session = self.store.recent(1)[0]
        self.assertEqual(session.jumps, 2)
        self.assertEqual(session.scans, 3)
        self.assertEqual(session.new_bodies, 3)  # WasDiscovered False у каждого Scan
        self.assertEqual(session.mapped, 1)
        self.assertEqual(session.bio_analyzed, 2)
        self.assertAlmostEqual(session.distance_ly, 20.0)
        self.assertGreaterEqual(session.duration_sec, 0.0)

    def test_new_journal_is_new_session(self):
        state = played_state()
        self.store.note("Journal.2026-01-01.log", state, save_interval=0)
        self.store.note("Journal.2026-01-02.log", state, save_interval=0)
        self.assertEqual(len(self.store.sessions), 2)
        total = self.store.totals()
        self.assertEqual(total["sessions"], 2)
        self.assertEqual(total["jumps"], 2)  # по одному прыжку в каждой сессии
        self.assertEqual(total["scans"], 4)

    def test_survives_reload(self):
        state = played_state()
        self.store.note("Journal.2026-01-01.log", state, save_interval=0)
        self.store.save()
        again = StatsStore(self.path)
        self.assertEqual(len(again.sessions), 1)
        self.assertEqual(again.sessions[0].scans, state.session_scans)

    def test_no_key_writes_nothing(self):
        self.assertFalse(self.store.note(None, played_state(), save_interval=0))
        self.assertEqual(self.store.sessions, [])

    def test_broken_json_is_ignored(self):
        self.path.write_text("{не json", encoding="utf-8")
        store = StatsStore(self.path)
        self.assertEqual(store.sessions, [])

    def test_from_persist_cleans_junk(self):
        session = SessionStats.from_persist(
            {"key": "J.log", "jumps": "7", "scans": None, "distance_ly": "12.5", "лишнее": 1}
        )
        self.assertEqual(session.key, "J.log")
        self.assertEqual(session.jumps, 7)
        self.assertEqual(session.scans, 0)
        self.assertAlmostEqual(session.distance_ly, 12.5)


if __name__ == "__main__":
    unittest.main()
