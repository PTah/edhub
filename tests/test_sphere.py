"""Обход систем в шаре и галочка «система открыта нами» на строке ЗВЕЗДА."""
from __future__ import annotations

import math
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("EDHUD_LANG", "ru")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud import hudmodel  # noqa: E402
from edhud.config import Config  # noqa: E402
from edhud.model import Body, GameState  # noqa: E402
from edhud.sphere import SphereHop, _two_opt, parse_sphere, plan_tour  # noqa: E402


class SphereTourTests(unittest.TestCase):
    def test_parse_keeps_center_and_drops_outside_radius(self):
        rows = [
            {
                "name": "Sol",
                "distance": 0,
                "coords": {"x": 0, "y": 0, "z": 0},
                "primaryStar": {"type": "G (White-Yellow) Star"},
                "id64": 1,
            },
            {
                "name": "Alpha Centauri",
                "distance": 4.37,
                "coords": {"x": 4, "y": 1, "z": 0},
                "primaryStar": {"type": "G (White-Yellow) Star"},
            },
            {
                "name": "Far",
                "distance": 40,
                "coords": {"x": 40, "y": 0, "z": 0},
                "primaryStar": {"type": "M (Red dwarf) Star"},
            },
        ]
        systems = parse_sphere(rows, "Sol", (0, 0, 0), 10)
        names = [hop.name for hop in systems]
        self.assertEqual(names, ["Sol", "Alpha Centauri"])
        self.assertEqual(systems[0].star_class, "G")
        self.assertEqual(systems[1].star_class, "G")
        self.assertAlmostEqual(systems[1].from_center, 4.37)

    def test_tour_visits_each_once_and_returns(self):
        systems = [
            SphereHop("A", (0, 0, 0)),
            SphereHop("B", (1, 0, 0), from_center=1),
            SphereHop("C", (1, 1, 0), from_center=math.sqrt(2)),
            SphereHop("D", (0, 1, 0), from_center=1),
        ]
        tour = plan_tour(systems)
        names = [hop.name for hop in tour]
        self.assertEqual(names[0], "A")
        self.assertEqual(names[-1], "A")
        self.assertTrue(tour[-1].returning)
        self.assertEqual(sorted(names[:-1]), ["A", "B", "C", "D"])
        self.assertEqual(len(set(names[:-1])), 4)
        self.assertEqual(tour[0].leg_ly, 0)
        self.assertGreater(tour[-1].leg_ly, 0)
        for prev, hop in zip(tour, tour[1:]):
            self.assertAlmostEqual(hop.leg_ly, math.dist(prev.pos, hop.pos), places=6)

    def test_two_opt_shortens_crossing(self):
        coords = [(0, 0, 0), (1, 1, 0), (1, 0, 0), (0, 1, 0)]
        order = _two_opt(coords, [0, 1, 2, 3], 5)
        length = 0.0
        for a, b in zip(order, order[1:]):
            length += math.dist(coords[a], coords[b])
        length += math.dist(coords[order[-1]], coords[order[0]])
        self.assertLess(length, 2 + 2 * math.sqrt(2) - 0.01)

    def test_single_system_has_no_duplicate_return(self):
        tour = plan_tour([SphereHop("Solo", (1, 2, 3))])
        self.assertEqual([hop.name for hop in tour], ["Solo"])
        self.assertFalse(tour[0].returning)


class SphereWindowTests(unittest.TestCase):
    def test_table_lists_return_hop(self):
        import tkinter as tk

        from edhud.mainwindow import MainWindow

        hops = plan_tour(
            [
                SphereHop("Sol", (0, 0, 0), star_class="G"),
                SphereHop("Barnard", (2, 0, 0), star_class="M", from_center=2),
            ]
        )
        root = tk.Tk()
        root.withdraw()
        try:
            window = MainWindow(root)
            window._show_sphere(hops, None)
            rows = window.sphere_tree.get_children()
            self.assertEqual(len(rows), 3)
            last = window.sphere_tree.item(rows[-1], "values")
            self.assertEqual(last[0], "↩")
            self.assertEqual(last[1], "Sol")
            self.assertIn("2", window.sphere_status.cget("text"))
            window.sphere_system.delete(0, "end")
            window._calc_sphere()
            self.assertEqual(window.sphere_status.cget("text"), "укажите звёздную систему")
            window.destroy()
        finally:
            root.destroy()


class DiscoveredMarkTests(unittest.TestCase):
    def test_gold_check_on_star_line_when_we_discovered_the_system(self):
        state = GameState()
        state.system.name = "Blu Thua UJ-K b37-0"
        state.system.body_count = 16
        state.system.discovered_by_me = True
        row = hudmodel.build_view(state, Config()).body_row
        self.assertTrue(row.text.startswith("ЗВЕЗДА "))
        self.assertIn("тел 16", row.text)
        self.assertIn("✔", row.text)
        self.assertTrue(any(seg.style == "gold" and "✔" in seg.text for seg in row.segments))

        state.system.discovered_by_me = False
        plain = hudmodel.build_view(state, Config()).body_row
        self.assertNotIn("✔", plain.text)

    def test_gold_check_on_selected_star_not_on_planet(self):
        state = GameState()
        state.system.name = "Sol"
        state.system.discovered_by_me = True
        state.system.bodies[0] = Body(body_id=0, name="Sol", is_star=True, star_type="G")
        state.system.bodies[1] = Body(body_id=1, name="Mercury", planet_class="Rock")
        state.current_body_id = 0
        star = hudmodel.build_view(state, Config()).body_row
        self.assertTrue(star.text.startswith("ЗВЕЗДА "))
        self.assertIn("✔", star.text)
        self.assertTrue(any(seg.style == "gold" for seg in star.segments))

        state.current_body_id = 1
        planet = hudmodel.build_view(state, Config()).body_row
        self.assertTrue(planet.text.startswith("ТЕЛО "))
        self.assertNotIn("✔", planet.text)


if __name__ == "__main__":
    unittest.main()
