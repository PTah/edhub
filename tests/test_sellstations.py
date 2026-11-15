# Created by nc.ai 1.2.15 on Papasha 2026-11-15 17:10:54
"""Станции сбыта: ранг «цена × достижимость» и альтернативные станции в индексе цен."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("EDHUD_LANG", "ru")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud import prices, sellstations  # noqa: E402


class RankTests(unittest.TestCase):
    def test_near_station_beats_far_when_price_similar(self):
        quotes = [
            prices.Quote("Tritium", "Near", "Here", 60_000, coords=(1.0, 0.0, 0.0)),
            prices.Quote("Tritium", "Far", "Away", 70_000, coords=(200.0, 0.0, 0.0)),
        ]
        ranked = sellstations.rank(quotes, origin=(0.0, 0.0, 0.0), jump_range=20.0)
        self.assertEqual(ranked[0].station, "Near")
        self.assertEqual(ranked[0].jumps, 1)
        self.assertEqual(ranked[1].jumps, 10)
        self.assertGreater(ranked[1].distance_ly, ranked[0].distance_ly)

    def test_big_price_wins_over_distance(self):
        quotes = [
            prices.Quote("Tritium", "Near", "Here", 52_000, coords=(1.0, 0.0, 0.0)),
            prices.Quote("Tritium", "Far", "Away", 120_000, coords=(60.0, 0.0, 0.0)),
        ]
        ranked = sellstations.rank(quotes, origin=(0.0, 0.0, 0.0), jump_range=20.0)
        self.assertEqual(ranked[0].station, "Far")

    def test_unknown_coords_are_penalised(self):
        quotes = [
            prices.Quote("Tritium", "Known", "Here", 60_000, coords=(1.0, 0.0, 0.0)),
            prices.Quote("Tritium", "Unknown", "Elsewhere", 62_000),
        ]
        ranked = sellstations.rank(quotes, origin=(0.0, 0.0, 0.0), jump_range=20.0)
        self.assertEqual(ranked[0].station, "Known")
        self.assertIsNone(ranked[1].distance_ly)

    def test_label_has_price_and_distance(self):
        choice = sellstations.SellChoice("Tritium", "Galileo", "Sol", 1_200_000, 45.2, 3)
        label = choice.label()
        self.assertIn("Galileo", label)
        self.assertIn("Sol", label)
        self.assertIn("45.2 ly", label)
        self.assertIn("3", label)


class MarketIndexTopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "prices.json"
        self.index = prices.MarketIndex(self.path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_keeps_alternative_stations(self):
        self.index.add("Tritium", "Best", "Sys1", 80_000, coords=(0.0, 0.0, 0.0))
        self.index.add("Tritium", "Alt", "Sys2", 70_000, coords=(30.0, 0.0, 0.0))
        self.index.add("Tritium", "Worst", "Sys3", 10_000)
        rows = self.index.top("Tritium")
        self.assertEqual([row.station for row in rows], ["Best", "Alt", "Worst"])
        self.assertEqual(self.index.best("Tritium").station, "Best")
        self.assertEqual(self.index.top("Musgravite"), [])

    def test_alts_survive_reload(self):
        self.index.add("Tritium", "Best", "Sys1", 80_000, coords=(1.0, 2.0, 3.0))
        self.index.add("Tritium", "Alt", "Sys2", 70_000)
        self.index.save()
        again = prices.MarketIndex(self.path)
        rows = again.top("Tritium")
        self.assertEqual([row.station for row in rows], ["Best", "Alt"])
        self.assertEqual(again.best("Tritium").coords, (1.0, 2.0, 3.0))

    def test_best_sell_uses_rank(self):
        self.index.add("Alexandrite", "Near", "Here", 200_000, coords=(2.0, 0.0, 0.0))
        self.index.add("Alexandrite", "Far", "Away", 205_000, coords=(150.0, 0.0, 0.0))
        choice = sellstations.best_sell(self.index, "Alexandrite", origin=(0.0, 0.0, 0.0), jump_range=20.0)
        self.assertIsNotNone(choice)
        self.assertEqual(choice.station, "Near")
        self.assertEqual(choice.price, 200_000)
        self.assertEqual(choice.jumps, 1)

    def test_best_sell_without_commodity(self):
        self.assertIsNone(sellstations.best_sell(self.index, "", origin=(0, 0, 0)))


if __name__ == "__main__":
    unittest.main()
