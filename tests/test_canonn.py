# Created by nc.ai 1.2.11 on Papasha 2026-11-14 19:33:27
"""Тесты Canonn POI (чужие био-точки на радаре)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud import canonn, model  # noqa: E402


class CanonnParseTests(unittest.TestCase):
    def test_keeps_only_biology_with_coords(self) -> None:
        payload = {
            "codex": [
                {
                    "body": "C 7",
                    "english_name": "Stratum Tectonicas - Lime",
                    "hud_category": "Biology",
                    "latitude": "44.2323",
                    "longitude": "-31.0063",
                },
                {  # геология — не нужна
                    "body": "C 7",
                    "english_name": "Sulphur Dioxide Fumarole",
                    "hud_category": "Geology",
                    "latitude": "44.1",
                    "longitude": "-31.1",
                },
                {  # без координат (ScanOrganic-агрегат)
                    "body": "C 7",
                    "english_name": "Bacterium Aurasus - Lime",
                    "hud_category": "Biology",
                    "latitude": None,
                    "longitude": None,
                },
            ]
        }
        points = canonn.parse_bio_points(payload)
        self.assertEqual(len(points), 1)
        body, lat, lon, label = points[0]
        self.assertEqual(body, "C 7")
        self.assertAlmostEqual(lat, 44.2323)
        self.assertAlmostEqual(lon, -31.0063)
        self.assertIn("Stratum", label)

    def test_empty_payload(self) -> None:
        self.assertEqual(canonn.parse_bio_points(None), [])
        self.assertEqual(canonn.parse_bio_points({}), [])


class RadarPriorTests(unittest.TestCase):
    def test_prior_point_appears_on_radar(self) -> None:
        """Чужая точка Canonn рядом — ромбом на радаре, с подписью вида."""
        state = model.GameState()
        state.system.name = "Test"
        body = model.Body(
            body_id=4,
            name="Test C 7",
            radius=6_000_000.0,
            landable=True,
            bio_signals=1,
        )
        state.system.bodies[4] = body
        state.apply_status(
            {
                "Latitude": 0.0,
                "Longitude": 0.0,
                "Heading": 0.0,
                "PlanetRadius": 6_000_000.0,
                "BodyID": 4,
                "Flags": 1 << 19,
            }
        )
        state.set_canonn_bio([("C 7", 0.00287, 0.0, "Stratum Tectonicas - Lime")])
        radar = state.radar_view()
        assert radar is not None
        prior = [blip for blip in radar.blips if blip.kind == "prior"]
        self.assertEqual(len(prior), 1)
        self.assertAlmostEqual(prior[0].distance_m, 300, delta=25)
        self.assertIn("Stratum", prior[0].label)
        self.assertAlmostEqual(prior[0].turn or 0.0, 0.0, delta=1.0)

    def test_far_prior_point_ignored(self) -> None:
        """Точки за 1.5 км не тянем — иначе радар уезжает в километры."""
        state = model.GameState()
        state.system.name = "Test"
        body = model.Body(body_id=4, name="Test C 7", radius=6_000_000.0, landable=True, bio_signals=1)
        state.system.bodies[4] = body
        state.apply_status(
            {
                "Latitude": 0.0,
                "Longitude": 0.0,
                "Heading": 0.0,
                "PlanetRadius": 6_000_000.0,
                "BodyID": 4,
                "Flags": 1 << 19,
            }
        )
        state.set_canonn_bio([("C 7", 0.09, 0.0, "Frutexa - Green")])  # ~10 км
        radar = state.radar_view()
        assert radar is not None
        self.assertFalse([blip for blip in radar.blips if blip.kind == "prior"])


if __name__ == "__main__":
    unittest.main()
