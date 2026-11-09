# Created by nc.ai 0.8.8.0 on macbook 2026-10-17 20:13:46
"""Тесты стоимости скана тел и множителей первооткрывателя."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud import values  # noqa: E402
from edhud.model import Body, System  # noqa: E402


class FormulaTests(unittest.TestCase):
    def test_star_value(self):
        # kk + mass*kk/66.25 — без множителей
        self.assertEqual(values.body_value("G", 1.0), round(1200 + 1200 / 66.25))
        self.assertEqual(values.body_value("H", 10.0), round(22628 + 10 * 22628 / 66.25))
        self.assertGreater(values.body_value("W", 1.0), values.body_value("G", 1.0))

    def test_earthlike_base(self):
        value = values.body_value("Earthlike body", 1.0)
        expected = values.EARTHLIKE_K + values.EARTHLIKE_K * values.Q
        self.assertEqual(value, round(expected))

    def test_first_discovery_multiplier(self):
        plain = values.body_value("Icy body", 0.9)
        first = values.body_value("Icy body", 0.9, first_discoverer=True)
        self.assertAlmostEqual(first / plain, values.DISCOVERY_MULTIPLIER, places=2)

    def test_mapping_multipliers(self):
        plain = values.body_value("Rocky body", 0.3)
        plain_map = values.body_value("Rocky body", 0.3, mapped=True)
        mapper_only = values.body_value("Rocky body", 0.3, mapped=True, first_mapper=True)
        both = values.body_value("Rocky body", 0.3, first_discoverer=True, mapped=True, first_mapper=True)
        self.assertGreater(plain_map, plain)
        self.assertGreater(mapper_only, plain_map)
        # первооткрыватель + картограф: множитель картографии ниже, но добавляется ×2.6
        self.assertGreater(both, mapper_only)

    def test_terraformable_bonus(self):
        self.assertGreater(
            values.body_value("Rocky body", 0.3, terraformable=True),
            values.body_value("Rocky body", 0.3),
        )

    def test_minimum_value(self):
        self.assertGreaterEqual(values.body_value("Rocky body", 0.0001), 500)

    def test_is_star_class(self):
        self.assertTrue(values.is_star_class("K"))
        self.assertTrue(values.is_star_class("TTS"))
        self.assertFalse(values.is_star_class("Icy body"))
        self.assertFalse(values.is_star_class("Water world"))

    def test_credits_format(self):
        self.assertEqual(values.credits(0), "—")
        self.assertEqual(values.credits(2_500_000), "2 500 000")
        self.assertEqual(values.credits(450_000), "450 000")
        self.assertEqual(values.credits(7_006), "7 006")
        self.assertEqual(values.credits(999), "999")


class BodyValueTests(unittest.TestCase):
    def _system(self) -> System:
        system = System(address=1, name="Test")
        system.bodies[0] = Body(
            body_id=0, name="Test A", star_type="K", is_star=True, stellar_mass=0.8, surface_temp=4500
        )
        system.bodies[1] = Body(
            body_id=1,
            name="Test 1 a",
            planet_class="Icy body",
            mass_em=0.9,
            landable=True,
            was_discovered=False,
            was_mapped=False,
        )
        system.bodies[2] = Body(
            body_id=2,
            name="Test 2",
            planet_class="Water world",
            mass_em=1.2,
            terraform_state="Terraformable",
            was_discovered=True,
            was_mapped=True,
        )
        return system

    def test_breakdown(self):
        system = self._system()
        first = values.body_values(system.bodies[1])
        assert first is not None
        self.assertTrue(first.first_discoverer)
        self.assertTrue(first.first_mapper)
        self.assertGreater(first.mapped, first.scan)

        known = values.body_values(system.bodies[2])
        assert known is not None
        self.assertFalse(known.first_discoverer)
        self.assertFalse(known.first_mapper)

    def test_star_breakdown(self):
        breakdown = values.body_values(self._system().bodies[0])
        assert breakdown is not None
        self.assertTrue(breakdown.star)
        self.assertEqual(breakdown.scan, breakdown.mapped)

    def test_system_totals(self):
        scan, mapped = values.system_totals(self._system())
        self.assertGreater(scan, 0)
        self.assertGreater(mapped, scan)

    def test_unknown_body(self):
        self.assertIsNone(values.body_values(Body(body_id=9, name="X")))


if __name__ == "__main__":
    unittest.main()
