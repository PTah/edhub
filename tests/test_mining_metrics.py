# Created by nc.ai 1.2.15 on Papasha 2026-11-15 17:03:20
"""Метрики добычи: качество камня (ProspectedAsteroid), выработка, трюм."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("EDHUD_LANG", "ru")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud import hudmodel, prices  # noqa: E402
from edhud.config import Config  # noqa: E402
from edhud.miningstats import MiningMetrics  # noqa: E402
from edhud.model import GameState  # noqa: E402


def prospect(target: str, share: float, content: str = "Medium", motherlode: bool = False) -> dict:
    return {
        "event": "ProspectedAsteroid",
        "Content": content,
        "Content_Localised": content,
        "Motherlode": motherlode,
        "Remaining": 100.0,
        "Materials": [
            {"Name": f"${target.lower()}_name;", "Name_Localised": target, "Proportion": share},
            {"Name": "$water_name;", "Name_Localised": "Water", "Proportion": max(0.0, 100.0 - share)},
        ],
    }


class ProspectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.metrics = MiningMetrics(target="Alexandrite")
        self.metrics.started = 1_000.0

    def test_share_of_target_mineral(self):
        self.metrics.apply(prospect("Alexandrite", 32.5), now=1_010.0)
        self.assertEqual(self.metrics.prospected, 1)
        self.assertEqual(self.metrics.last_rock.target, "Alexandrite")
        self.assertAlmostEqual(self.metrics.last_rock.share, 32.5)
        self.assertAlmostEqual(self.metrics.avg_share, 32.5)
        self.assertAlmostEqual(self.metrics.best_share, 32.5)

    def test_average_and_best_over_session(self):
        for share in (10.0, 30.0, 60.0, 0.0):  # последний камень без цели
            self.metrics.apply(prospect("Alexandrite", share), now=1_020.0)
        self.assertEqual(self.metrics.prospected, 4)
        self.assertAlmostEqual(self.metrics.avg_share, 100.0 / 3)  # 0% не считается
        self.assertAlmostEqual(self.metrics.best_share, 60.0)
        self.assertEqual(self.metrics.pure_rocks, 1)  # > 50%

    def test_target_falls_back_to_most_expensive(self):
        metrics = MiningMetrics(target="")
        metrics.apply(prospect("Tritium", 20.0), now=1.0)
        self.assertEqual(metrics.last_rock.target, "Tritium")  # дороже воды

    def test_motherlode_and_already_mined(self):
        event = prospect("Alexandrite", 40.0, motherlode=True)
        event["Remaining"] = 55.0
        self.metrics.apply(event, now=1.0)
        self.assertEqual(self.metrics.motherlodes, 1)
        self.assertEqual(self.metrics.already_mined, 1)

    def test_new_login_resets(self):
        self.metrics.apply(prospect("Alexandrite", 30.0), now=1.0)
        self.metrics.apply({"event": "LoadGame", "Commander": "Tester"}, now=2.0)
        self.assertEqual(self.metrics.prospected, 0)
        self.assertAlmostEqual(self.metrics.avg_share, 0.0)


class YieldTests(unittest.TestCase):
    def setUp(self) -> None:
        self.metrics = MiningMetrics(target="Tritium")
        self.metrics.started = 1.0

    def test_refined_counter_and_rate(self):
        for index in range(30):
            self.metrics.apply(
                {"event": "MiningRefined", "Type": "tritium", "Type_Localised": "Tritium"},
                now=1.0 + 60.0 * (index + 1),
            )
        self.assertEqual(self.metrics.refined_total, 30)
        self.assertEqual(self.metrics.refined["Tritium"], 30)
        # 30 т за полчаса → 60 т/ч
        self.assertAlmostEqual(self.metrics.tons_per_hour, 60.0, places=3)

    def test_cargo_and_sales(self):
        self.metrics.apply(
            {
                "event": "Cargo",
                "Count": 96,
                "Inventory": [
                    {"Name": "$tritium_name;", "Name_Localised": "Tritium", "Count": 80},
                    {"Name": "$water_name;", "Name_Localised": "Water", "Count": 16},
                ],
            },
            now=1.0,
        )
        self.assertEqual(self.metrics.cargo, 96)
        self.assertEqual(self.metrics.cargo_items["Tritium"], 80)

        self.metrics.apply(
            {"event": "MarketSell", "Type": "tritium", "Count": 80, "TotalSale": 4_320_000},
            now=2.0,
        )
        self.assertEqual(self.metrics.sold["Tritium"], 80)
        self.assertEqual(self.metrics.sold_cr, 4_320_000)

    def test_batch_value_uses_price_index(self):
        metrics = MiningMetrics()
        metrics.apply({"event": "Cargo", "Count": 10, "Inventory": [
            {"Name": "$tritium_name;", "Name_Localised": "Tritium", "Count": 10}
        ]}, now=1.0)
        # без индекса — средняя из справочника
        self.assertEqual(metrics.batch_value(), 10 * 54_000)
        with tempfile.TemporaryDirectory() as tmp:
            index = prices.MarketIndex(Path(tmp) / "prices.json")
            index.add("Tritium", "Station", "System", 70_000)
            self.assertEqual(metrics.batch_value(index), 10 * 70_000)


class HudRowTests(unittest.TestCase):
    def test_hud_row_appears_after_prospecting(self):
        state = GameState()
        state.mining.started = 0.0
        state.mining.target = "Alexandrite"
        empty = hudmodel.build_view(state, Config())
        self.assertNotIn("добыча", "\n".join(row.text for row in empty.detail))

        state.apply(prospect("Alexandrite", 32.0))
        state.apply({"event": "MiningRefined", "Type": "alexandrite", "Type_Localised": "Alexandrite"})
        view = hudmodel.build_view(state, Config())
        detail = "\n".join(row.text for row in view.detail)
        self.assertIn("добыча", detail)
        self.assertIn("Alexandrite 32%", detail)
        self.assertIn("1 т", detail)


if __name__ == "__main__":
    unittest.main()
