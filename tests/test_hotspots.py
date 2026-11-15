# Created by nc.ai 1.2.15 on Papasha 2026-11-15 16:09:38
"""Хотспоты колец: скан → состояние → вкладка «Добыча» → база и поиск."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("EDHUD_LANG", "ru")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud import prices  # noqa: E402
from edhud.hotspots import HotspotStore, RingHotspots, distance_ly  # noqa: E402
from edhud.miningui import rows_from_hotspots, rows_from_state  # noqa: E402
from edhud.model import GameState  # noqa: E402

SYSTEM = "Smojai XP-N b20-0"
ADDRESS = 1234567890123
POS = [-10.5, 20.25, 30.0]
PLANET = f"{SYSTEM} 4"
RING = f"{PLANET} A Ring"


def scanned_state() -> GameState:
    """Система, где просканировали планету с кольцом и его хотспоты."""
    state = GameState()
    state.apply(
        {
            "event": "Location",
            "StarSystem": SYSTEM,
            "SystemAddress": ADDRESS,
            "StarPos": POS,
        }
    )
    state.apply(
        {
            "event": "Scan",
            "ScanType": "Detailed",
            "BodyName": PLANET,
            "BodyID": 4,
            "StarSystem": SYSTEM,
            "SystemAddress": ADDRESS,
            "PlanetClass": "Icy body",
            "DistanceFromArrivalLS": 1234.5,
            "ReserveLevel": "eReserveLevel_Pristine",
            "Rings": [{"Name": RING, "RingClass": "eRingClass_Icy", "Mass": 1e12}],
        }
    )
    state.apply(
        {
            "event": "SAASignalsFound",
            "BodyName": RING,
            "BodyID": 5,
            "StarSystem": SYSTEM,
            "SystemAddress": ADDRESS,
            "Signals": [
                {"Type": "Alexandrite", "Count": 2},
                {"Type": "Tritium", "Count": 3},
            ],
        }
    )
    return state


class StateRowsTests(unittest.TestCase):
    def test_scan_reaches_mining_tab(self):
        # то, на что жаловался пользователь: скан кольца должен быть виден в «Добыче»
        rows = rows_from_state(scanned_state())
        ring_rows = [row for row in rows if row.hotspots]
        assert ring_rows, "кольцо с хотспотами не попало в таблицу"
        assert ring_rows[0].hotspots == {"Alexandrite": 2, "Tritium": 3}
        assert "Alexandrite" in ring_rows[0].rings
        assert ring_rows[0].price > 0
        assert "Pristine" in ring_rows[0].sites  # запас кольца из Scan

    def test_material_filter_is_real(self):
        state = scanned_state()
        assert rows_from_state(state, material="Alexandrite")
        assert rows_from_state(state, material="Musgravite") == []
        row = rows_from_state(state, material="Tritium")[0]
        assert row.material == "Tritium"
        assert row.price == 54_000  # средняя, рынка ещё не видели


class HotspotStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = HotspotStore(Path(self.tmp.name) / "hotspots.json")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_harvest_keeps_scanned_rings(self):
        assert self.store.harvest(scanned_state()) == 1
        assert len(self.store) == 1
        ring = self.store.list()[0]
        assert ring.system == SYSTEM
        assert ring.hotspots["Tritium"] == 3
        assert ring.ring_types == ["Icy"]
        assert ring.reserve_level == "Pristine"
        # повторный harvest ничего не пишет
        assert self.store.harvest(scanned_state()) == 0

    def test_survives_reload(self):
        self.store.harvest(scanned_state())
        again = HotspotStore(self.store.path)
        assert len(again) == 1
        assert again.list()[0].hotspots["Alexandrite"] == 2

    def test_search_by_mineral_and_radius(self):
        self.store.harvest(scanned_state())
        self.store.upsert(
            RingHotspots(
                system="Far Away",
                body_name="Far Away 2 A Ring",
                body_id=7,
                hotspots={"Alexandrite": 1},
                address=42,
                star_pos=[POS[0] + 500, POS[1], POS[2]],
            )
        )
        near = self.store.search(POS, radius_ly=50)
        assert len(near) == 1
        assert near[0].distance_ly < 1

        both = self.store.search(POS, radius_ly=None, mineral="Alexandrite")
        assert len(both) == 2
        assert both[0].ring.system == SYSTEM  # сначала ближнее

        assert self.store.search(POS, radius_ly=50, mineral="Musgravite") == []
        assert self.store.count_by_mineral("tritium") == 1

    def test_mineral_search_rows(self):
        self.store.harvest(scanned_state())
        index = prices.MarketIndex(Path(self.tmp.name) / "prices.json")
        rows = rows_from_hotspots(self.store.search(POS, 50, "Tritium"), material="Tritium", price_index=index)
        assert len(rows) == 1
        assert rows[0].material == "Tritium"
        assert rows[0].distance_ly is not None
        assert rows[0].price == 54_000


class DistanceTests(unittest.TestCase):
    def test_distance(self):
        assert distance_ly([0, 0, 0], [3, 4, 0]) == 5
        assert distance_ly(None, [1, 2, 3]) is None
        assert distance_ly([0, 0, 0], ["x", 1, 2]) is None
