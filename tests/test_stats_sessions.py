# Created by nc.ai 1.2.15 on Papasha 2026-11-15 16:23:30
"""Статистика сессий: по каждому входу в игру и суммарная."""
from __future__ import annotations

import calendar
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("EDHUD_LANG", "ru")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud.model import GameState  # noqa: E402
from edhud.stats import SessionStats, StatsStore, session_started_from_name  # noqa: E402


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


class SessionResetTests(unittest.TestCase):
    """Смена журнала = новая сессия: счётчики не переезжают в неё."""

    def test_reset_session_zeroes_counters(self):
        state = GameState()
        state.apply({"event": "LoadGame", "Commander": "Tester", "FID": "F1"})
        state.session_jumps = 5
        state.session_scans = 40
        state.session_new_bodies = 20
        state.session_organic_sold = 187_683_000
        state.session_sold = 96_518_500
        state.mining.apply({"event": "MiningRefined", "Type": "tritium"}, now=1.0)

        state.reset_session(1_700_000_000.0)
        self.assertEqual(state.session_jumps, 0)
        self.assertEqual(state.session_scans, 0)
        self.assertEqual(state.session_new_bodies, 0)
        self.assertEqual(state.session_organic_sold, 0)
        self.assertEqual(state.session_sold, 0)
        self.assertEqual(state.session_distance_ly, 0.0)
        self.assertEqual(state.mining.refined_total, 0)
        self.assertAlmostEqual(state.session_started, 1_700_000_000.0)

    def test_fileheader_starts_new_session_with_its_timestamp(self):
        state = GameState()
        state.session_jumps = 7
        state.session_organic_sold = 187_683_000
        state.apply(
            {
                "event": "Fileheader",
                "part": 1,
                "language": "Russian/RU",
                "gameversion": "4.0.0.100",
                "build": "r1",
                "timestamp": "2026-11-15T19:19:23Z",
            }
        )
        self.assertEqual(state.session_jumps, 0)
        self.assertEqual(state.session_organic_sold, 0)
        self.assertAlmostEqual(state.session_started, calendar.timegm((2026, 11, 15, 19, 19, 23, 0, 0, 0)))

    def test_two_sessions_do_not_share_sales(self):
        state = GameState()
        state.apply({"event": "Fileheader", "part": 1, "timestamp": "2026-11-15T09:00:00Z"})
        state.apply({"event": "SellOrganicData", "MarketID": 1, "BioData": [{"Value": 5_000, "Bonus": 1_000}]})
        self.assertEqual(state.session_organic_sold, 6_000)
        # новая сессия
        state.apply({"event": "Fileheader", "part": 1, "timestamp": "2026-11-15T19:19:23Z"})
        self.assertEqual(state.session_organic_sold, 0)


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

    def test_session_start_comes_from_journal_name(self):
        started = session_started_from_name("Journal.2026-11-15T191923.01.log")
        self.assertIsNotNone(started)
        self.assertEqual(time.strftime("%Y-%m-%d %H:%M", time.localtime(started)), "2026-11-15 19:19")
        self.assertIsNone(session_started_from_name("нет имени"))
        self.assertIsNone(session_started_from_name(None))

    def test_note_does_not_overwrite_existing_start(self):
        state = played_state()
        state.session_started = time.time()
        key = "Journal.2026-11-15T191923.01.log"
        self.store.note(key, state, save_interval=0)
        first = self.store.recent(1)[0].started
        state.session_started = time.time() + 3600
        self.store.note(key, state, save_interval=0)
        self.assertEqual(self.store.recent(1)[0].started, first)
        self.assertEqual(
            time.strftime("%Y-%m-%d %H:%M", time.localtime(first)), "2026-11-15 19:19"
        )

    def test_sanitize_restores_start_and_drops_duplicates(self):
        rows = {
            "version": 1,
            "sessions": [
                # старый баг: время начала перезаписано запуском EDHUD, счётчики пустые
                {"key": "Journal.2026-11-15T145743.01.log", "started": 1_800_000_000, "jumps": 0},
                {"key": "Journal.2026-11-15T191923.01.log", "started": 1_800_000_000, "jumps": 1, "scans": 30},
                # дубль того же журнала, но пустой
                {"key": "Journal.2026-11-15T191923.01.log", "started": 1_800_000_000, "jumps": 0},
            ],
        }
        self.path.write_text(json.dumps(rows), encoding="utf-8")
        store = StatsStore(self.path)
        self.assertEqual(len(store.sessions), 2)  # дубль убран
        by_key = {item.key: item for item in store.sessions}
        evening = by_key["Journal.2026-11-15T191923.01.log"]
        self.assertEqual(evening.jumps, 1)  # осталась содержательная запись
        afternoon = by_key["Journal.2026-11-15T145743.01.log"]
        self.assertEqual(
            time.strftime("%Y-%m-%d %H:%M", time.localtime(afternoon.started)), "2026-11-15 14:57"
        )

    def test_clear_wipes_history(self):
        self.store.note("Journal.2026-11-15T191923.01.log", played_state(), save_interval=0)
        self.assertEqual(len(self.store.sessions), 1)
        self.assertTrue(self.store.clear())
        self.assertEqual(StatsStore(self.path).sessions, [])


class RebuildTests(unittest.TestCase):
    """Пересборка статистики по журналам: одна сессия = один файл."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root / "stats.json"
        self.journals = self.root / "journals"
        self.journals.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_journal(self, name: str, events: list[dict]) -> None:
        lines = [json.dumps(event) for event in events]
        (self.journals / name).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_rebuild_recounts_each_session_from_its_journal(self):
        self.write_journal(
            "Journal.2026-11-15T145743.01.log",
            [
                {"event": "Fileheader", "part": 1, "timestamp": "2026-11-15T04:57:43Z"},
                {"event": "LoadGame", "Commander": "Tester", "FID": "F1"},
                {"event": "FSDJump", "StarSystem": "A", "SystemAddress": 1, "JumpDist": 10.0},
                {"event": "SellOrganicData", "MarketID": 1, "BioData": [{"Value": 96_000_000, "Bonus": 518_500}]},
            ],
        )
        self.write_journal(
            "Journal.2026-11-15T191923.01.log",
            [
                {"event": "Fileheader", "part": 1, "timestamp": "2026-11-15T09:19:23Z"},
                {"event": "LoadGame", "Commander": "Tester", "FID": "F1"},
                {"event": "FSDJump", "StarSystem": "B", "SystemAddress": 2, "JumpDist": 7.0},
            ],
        )
        store = StatsStore(self.path)
        count = store.rebuild_from_journals(self.journals)
        self.assertEqual(count, 2)

        by_key = {item.key: item for item in store.sessions}
        afternoon = by_key["Journal.2026-11-15T145743.01.log"]
        evening = by_key["Journal.2026-11-15T191923.01.log"]
        # продажа осталась только в своей сессии
        self.assertEqual(afternoon.bio_sold_cr, 96_518_500)
        self.assertEqual(evening.bio_sold_cr, 0)
        self.assertEqual(evening.jumps, 1)
        self.assertAlmostEqual(evening.distance_ly, 7.0)
        self.assertEqual(
            time.strftime("%H:%M", time.localtime(evening.started)), "19:19"
        )

        # результат сохранён на диск
        again = StatsStore(self.path)
        self.assertEqual(len(again.sessions), 2)
        self.assertEqual(
            {item.key: item.bio_sold_cr for item in again.sessions}[
                "Journal.2026-11-15T191923.01.log"
            ],
            0,
        )

    def test_rebuild_skips_broken_lines(self):
        path = self.journals / "Journal.2026-11-15T120000.01.log"
        path.write_text(
            '{"event":"Fileheader","part":1}\nне json\n{"event":"FSDJump","JumpDist":5}\n',
            encoding="utf-8",
        )
        store = StatsStore(self.path)
        self.assertEqual(store.rebuild_from_journals(self.journals), 1)
        self.assertAlmostEqual(store.sessions[0].distance_ly, 5.0)


if __name__ == "__main__":
    unittest.main()
