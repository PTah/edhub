"""Тесты маршрутов: NavRoute, прогресс, импорт, плоттер."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud.route import Route, parse_route_text  # noqa: E402

NAVROUTE = {
    "event": "NavRoute",
    "Route": [
        {"StarSystem": "Sol", "SystemAddress": 1, "StarPos": [0, 0, 0], "StarClass": "G"},
        {"StarSystem": "Alpha", "SystemAddress": 2, "StarPos": [0, 0, 20.5], "StarClass": "K"},
        {"StarSystem": "Beta", "SystemAddress": 3, "StarPos": [0, 0, 44.0], "StarClass": "N"},
        {"StarSystem": "Gamma", "SystemAddress": 4, "StarPos": [0, 0, 70.0], "StarClass": "A"},
    ],
}


class NavRouteTests(unittest.TestCase):
    def test_progress(self):
        route = Route.from_navroute(NAVROUTE)
        self.assertEqual(len(route), 4)
        self.assertEqual(route.index_of("Alpha"), 1)
        self.assertEqual(route.remaining("Alpha"), 2)
        self.assertEqual(route.progress("Alpha"), (1, 3))
        self.assertAlmostEqual(route.hops[1].distance, 20.5, places=3)
        self.assertAlmostEqual(route.distance_remaining("Alpha"), 49.5, places=3)

    def test_next_hop(self):
        route = Route.from_navroute(NAVROUTE)
        hop = route.next_hop("Alpha")
        assert hop is not None
        self.assertEqual(hop.system, "Beta")
        self.assertFalse(hop.scoopable)
        self.assertTrue(route.next_hop("Sol").scoopable)

    def test_finish(self):
        route = Route.from_navroute(NAVROUTE)
        self.assertIsNone(route.next_hop("Gamma"))
        self.assertEqual(route.remaining("Gamma"), 0)

    def test_empty(self):
        route = Route.from_navroute({"event": "NavRouteClear", "Route": []})
        self.assertFalse(route)
        self.assertEqual(route.remaining("Sol"), 0)

    def test_unknown_system(self):
        route = Route.from_navroute(NAVROUTE)
        self.assertIsNone(route.index_of("Nowhere"))
        self.assertEqual(route.remaining("Nowhere"), 4)
        self.assertEqual(route.next_hop("Nowhere").system, "Sol")


class SpanshTests(unittest.TestCase):
    def test_from_spansh(self):
        result = {
            "system_jumps": [
                {"system": "Sol", "x": 0, "y": 0, "z": 0, "jumps": 0},
                {"system": "PSR J1752-2806", "x": -10.9, "y": -6.8, "z": 407.2, "jumps": 16, "neutron_star": True},
                {"system": "Colonia", "x": -9530.5, "y": -910.3, "z": 19808.1, "jumps": 12},
            ]
        }
        route = Route.from_spansh(result)
        self.assertEqual(route.source, "plotter")
        self.assertTrue(route.locked)
        self.assertEqual(len(route.hops), 3)
        self.assertEqual(route.total_jumps, 28)
        self.assertTrue(route.hops[1].neutron)
        self.assertAlmostEqual(route.hops[1].distance, 407.4, places=0)


class ImportTests(unittest.TestCase):
    def test_plain_list(self):
        names = parse_route_text("Sol\nAlpha\n\n# comment\nAlpha\n")
        self.assertEqual(names, ["Sol", "Alpha"])

    def test_csv(self):
        text = "System,Jump,Dist\nSol,0,0\nAlpha,1,20.5\nBeta,2,23.5\n"
        names = parse_route_text(text)
        self.assertEqual(names, ["Sol", "Alpha", "Beta"])

    def test_roundtrip(self):
        route = Route.from_names(["Sol", "Alpha"])
        data = route.to_dict()
        restored = Route.from_dict(data)
        self.assertEqual([h.system for h in restored.hops], ["Sol", "Alpha"])
        self.assertTrue(restored.locked)


if __name__ == "__main__":
    unittest.main()
