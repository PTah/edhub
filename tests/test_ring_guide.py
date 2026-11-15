# Created by nc.ai 1.2.15 on Papasha 2026-11-15 16:44:44
"""Копание в кольцах: справочник по типам, плотность (edtools), двойные хотспоты."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("EDHUD_LANG", "ru")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud import mining  # noqa: E402
from edhud.hotspots import HotspotStore  # noqa: E402
from edhud.miningui import ring_hint, rows_from_state  # noqa: E402
from edhud.model import GameState  # noqa: E402

SYSTEM = "Cegreeth"
ADDRESS = 7262632435282
POS = [1.0, 2.0, 3.0]
PLANET = "Cegreeth 4"
RING = f"{PLANET} A Ring"
# журнальные единицы: масса кольца в кг, радиусы в метрах (пример из доки edtools)
RING_MASS_KG = 4.4934e19
RING_INNER_M = 108_800_000.0
RING_OUTER_M = 115_180_000.0


class RowShapeTests(unittest.TestCase):
    def test_cells_match_columns(self):
        from edhud.miningui import COLUMNS, MiningRow

        row = MiningRow(system="S", body="B", material="Tritium", density=10.0, price=54000)
        self.assertEqual(len(row.cells()), len(COLUMNS))
        self.assertIn("лазер", row.cells()[COLUMNS_INDEX_MATERIAL])
        self.assertEqual(row.cells()[COLUMNS_INDEX_DENSITY], "10.00")


COLUMNS_INDEX_MATERIAL = 4
COLUMNS_INDEX_DENSITY = 9


class RingKindTests(unittest.TestCase):
    def test_normalizes_journal_names(self):
        self.assertEqual(mining.normalize_ring_kind("eRingClass_Icy"), "Icy")
        self.assertEqual(mining.normalize_ring_kind("eRingClass_MetalRich"), "Metal-Rich")
        self.assertEqual(mining.normalize_ring_kind("metal rich"), "Metal-Rich")
        self.assertIsNone(mining.normalize_ring_kind("eRingClass_BeltCluster"))
        self.assertEqual(mining.ring_kinds(["eRingClass_Icy", "Icy", "eRingClass_Rocky"]), ["Icy", "Rocky"])


class RingMineralsTests(unittest.TestCase):
    def test_ice_ring_contents(self):
        table = mining.ring_minerals(["Icy"])
        self.assertIn("Void Opals", table["core"])
        self.assertIn("Tritium", table["laser"])
        self.assertIn("Bromellite", table["core"])
        # дорогое всегда впереди
        self.assertGreaterEqual(
            mining.hotspot_avg_price(table["core"][0]),
            mining.hotspot_avg_price(table["core"][-1]),
        )

    def test_high_only_skips_cheap_minerals(self):
        table = mining.ring_minerals(["Metallic"], high_only=True)
        self.assertIn("Platinum", table["laser"])
        self.assertNotIn("Indite", table["laser"])

    def test_methods(self):
        self.assertEqual(mining.mineral_method("Alexandrite"), mining.METHOD_CORE)
        self.assertEqual(mining.mineral_method("tritium"), mining.METHOD_LASER)
        self.assertIsNone(mining.mineral_method("Iron"))
        self.assertIsNone(mining.mineral_method(None))
        self.assertTrue(mining.is_high_value("Void Opals"))
        self.assertFalse(mining.is_high_value("Water"))

    def test_canonical_mineral_names(self):
        self.assertEqual(mining.canonical_mineral("tritium"), "Tritium")
        self.assertEqual(mining.canonical_mineral("lowtemperaturediamonds"), "Low Temperature Diamonds")
        self.assertEqual(mining.canonical_mineral("Alexandrite"), "Alexandrite")
        self.assertEqual(mining.canonical_mineral("iron"), "Iron")
        self.assertEqual(mining.canonical_mineral(None), "")

    def test_unknown_ring_type_gives_nothing(self):
        self.assertEqual(mining.ring_minerals(["eRingClass_BeltCluster"]), {"core": [], "laser": []})

    def test_overlap_labels(self):
        holes = {"Alexandrite": 3, "Tritium": 1}
        self.assertEqual(mining.hotspot_count(holes, "Alexandrite"), 3)
        self.assertEqual(mining.hotspot_count(holes, "alexandrite"), 3)
        self.assertEqual(mining.hotspot_count(holes, "Monazite"), 0)
        self.assertEqual(mining.overlap_label(3), "triple")
        self.assertEqual(mining.overlap_label(2), "double")
        self.assertEqual(mining.overlap_label(1), "")


class RingDensityTests(unittest.TestCase):
    def test_edtools_example(self):
        # формула edtools: M[MT] / π(Rout² − Rin²) [км²] ≈ 10.01
        self.assertAlmostEqual(mining.ring_density(RING_MASS_KG, RING_INNER_M, RING_OUTER_M), 10.009, places=2)

    def test_rejects_broken_data(self):
        self.assertIsNone(mining.ring_density(0, RING_INNER_M, RING_OUTER_M))
        self.assertIsNone(mining.ring_density(RING_MASS_KG, RING_OUTER_M, RING_INNER_M))
        self.assertIsNone(mining.ring_density(None, None, None))


class ScannedRingTests(unittest.TestCase):
    def make_state(self) -> GameState:
        state = GameState()
        state.apply({"event": "Location", "StarSystem": SYSTEM, "SystemAddress": ADDRESS, "StarPos": POS})
        state.apply(
            {
                "event": "Scan",
                "ScanType": "Detailed",
                "BodyName": PLANET,
                "BodyID": 4,
                "SystemAddress": ADDRESS,
                "PlanetClass": "Icy body",
                "ReserveLevel": "eReserveLevel_Pristine",
                "Rings": [
                    {
                        "Name": RING,
                        "RingClass": "eRingClass_Icy",
                        "Mass": RING_MASS_KG,
                        "InnerRad": RING_INNER_M,
                        "OuterRad": RING_OUTER_M,
                    }
                ],
            }
        )
        state.apply(
            {
                "event": "SAASignalsFound",
                "BodyName": RING,
                "BodyID": 5,
                "SystemAddress": ADDRESS,
                "Signals": [
                    {"Type": "Alexandrite", "Count": 3},
                    {"Type": "Tritium", "Count": 1},
                ],
            }
        )
        return state

    def test_density_reaches_state_and_rows(self):
        state = self.make_state()
        body = [item for item in state.system.bodies.values() if getattr(item, "hotspots", None)][0]
        self.assertAlmostEqual(body.ring_density, 10.009, places=2)
        row = [item for item in rows_from_state(state) if item.hotspots][0]
        self.assertAlmostEqual(row.density, 10.009, places=2)
        self.assertEqual(row.subtype, "Icy")
        self.assertIn("Pristine", row.sites)

    def test_hint_says_what_to_mine(self):
        state = self.make_state()
        body = [item for item in state.system.bodies.values() if getattr(item, "hotspots", None)][0]
        hint = ring_hint(body.ring_types, body.reserve_level, body.ring_density)
        self.assertIn("Icy", hint)
        self.assertIn("Pristine", hint)
        self.assertIn("ядро", hint)
        self.assertIn("Alexandrite", hint)

    def test_store_keeps_density(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = HotspotStore(Path(tmp) / "hotspots.json")
            store.harvest(self.make_state())
            ring = store.list()[0]
            self.assertAlmostEqual(ring.density, 10.009, places=2)
            again = HotspotStore(store.path)
            self.assertAlmostEqual(again.list()[0].density, 10.009, places=2)


if __name__ == "__main__":
    unittest.main()
