"""Тесты движка биологии и регионов."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud import bio, codex, regions  # noqa: E402
from edhud.model import Body, System  # noqa: E402


class ClauseTests(unittest.TestCase):
    def test_range(self):
        clause = bio.Clause.parse("temp [146 ~ 195.41]")
        assert clause is not None
        self.assertEqual(clause.prop, "temp")
        self.assertEqual((clause.minimum, clause.maximum), (146.0, 195.41))
        self.assertTrue(bio._clause_ok(clause, {"SurfaceTemperature": 150}))
        self.assertFalse(bio._clause_ok(clause, {"SurfaceTemperature": 250}))

    def test_open_range(self):
        clause = bio.Clause.parse("  pressure [0.01 ~ ]")
        assert clause is not None
        self.assertTrue(bio._clause_ok(clause, {"SurfacePressure": 1.5}))
        self.assertFalse(bio._clause_ok(clause, {"SurfacePressure": 0.001}))
        self.assertFalse(bio._clause_ok(clause, {"SurfacePressure": None}))

    def test_sets(self):
        is_clause = bio.Clause.parse("atmosType [CarbonDioxide,Water]")
        self.assertTrue(bio._clause_ok(is_clause, {"AtmosphereType": "Water"}))
        self.assertFalse(bio._clause_ok(is_clause, {"AtmosphereType": "Neon"}))

        all_clause = bio.Clause.parse("mats &[Carbon,Sulphur]")
        self.assertEqual(all_clause.op, bio.ALL)
        self.assertTrue(bio._clause_ok(all_clause, {"Materials": {"Carbon": 20, "Sulphur": 10}}))
        self.assertFalse(bio._clause_ok(all_clause, {"Materials": {"Carbon": 20}}))

        not_clause = bio.Clause.parse("mats ![Iron,Nickel]")
        self.assertEqual(not_clause.op, bio.NOT)
        self.assertTrue(bio._clause_ok(not_clause, {"Materials": {"Carbon": 20}}))
        self.assertFalse(bio._clause_ok(not_clause, {"Materials": {"Iron": 20, "Carbon": 3}}))

    def test_body_class_codes(self):
        clause = bio.Clause.parse("body [HMC,Rocky]")
        self.assertEqual(clause.values, ["High metal content ", "Rocky body"])
        self.assertTrue(bio._clause_ok(clause, {"PlanetClass": "High metal content body"}))
        self.assertFalse(bio._clause_ok(clause, {"PlanetClass": "Icy body"}))

    def test_composition_is_or(self):
        clause = bio.Clause.parse("atmosComp [Neon >= 100 | Nitrogen >= 46]")
        self.assertEqual(clause.op, bio.COMPOSITION)
        self.assertTrue(bio._clause_ok(clause, {"AtmosphereComposition": {"Neon": 100.0}}))
        self.assertTrue(bio._clause_ok(clause, {"AtmosphereComposition": {"Nitrogen": 50.0}}))
        self.assertFalse(bio._clause_ok(clause, {"AtmosphereComposition": {"Neon": 3.0}}))

    def test_comments_skipped(self):
        self.assertIsNone(bio.Clause.parse("# hit count: 62150"))
        node = bio.Criteria.from_dict({"genus": "X", "query": ["# note", "temp [1 ~ 2]"]})
        self.assertEqual(len(node.query), 1)


class RegionTests(unittest.TestCase):
    def test_sol(self):
        region = regions.region_id(0.0, 0.0)
        self.assertEqual(region, 18)
        self.assertEqual(regions.region_name(region), "Inner Orion Spur")

    def test_galactic_centre(self):
        region = regions.region_id(25.21875, 25899.96875)
        self.assertEqual(regions.region_name(region), "Galactic Centre")

    def test_group_regions(self):
        self.assertIn(18, regions.group_regions("Orion-CygnusArm") or ())
        self.assertIn(2, regions.group_regions("BrainTreeBatch") or ())
        self.assertIsNone(regions.group_regions("Нет такого"))


class PredictionTests(unittest.TestCase):
    def _system(self) -> System:
        system = System(address=1, name="Test", star_pos=(0.0, 0.0, 0.0))
        system.bodies[0] = Body(body_id=0, name="Test A", star_type="K", is_star=True, radius=5e8, surface_temp=4500.0)
        return system

    def _icy_body(self, system: System) -> Body:
        body = Body(
            body_id=1,
            name="Test 1",
            planet_class="Icy body",
            radius=6e6,
            surface_gravity=5.6,
            surface_temp=118.0,
            surface_pressure=540.0,
            atmosphere="thin neon atmosphere",
            atmosphere_composition={"Neon": 100.0},
            volcanism="None",
            materials={"Iron": 19.1, "Sulphur": 15.6, "Carbon": 21.2, "Technetium": 0.71},
            landable=True,
            distance_ls=1180.0,
            parent_ids=[0],
        )
        system.bodies[1] = body
        return body

    def test_atmosphere_type(self):
        system = self._system()
        body = self._icy_body(system)
        self.assertEqual(body.atmosphere_type, "Neon")
        body.atmosphere = "thin carbon dioxide atmosphere"
        self.assertEqual(body.atmosphere_type, "CarbonDioxide")
        body.atmosphere = "no atmosphere"
        self.assertIsNone(body.atmosphere_type)

    def test_icy_neon_predicts_bacterium(self):
        system = self._system()
        body = self._icy_body(system)
        predictions = bio.predict_for_body(body, system)
        labels = [p.label for p in predictions]
        self.assertIn("Bacterium Acies - Lime", labels)

    def test_dss_genuses_filter(self):
        system = self._system()
        body = self._icy_body(system)
        body.genuses = {"$Codex_Ent_Fungoids_Genus_Name;": 1}
        predictions = bio.predict_for_body(body, system)
        self.assertTrue(all(p.genus == "Fungoida" for p in predictions))

    def test_non_landable_has_no_predictions(self):
        system = self._system()
        body = self._icy_body(system)
        body.landable = False
        self.assertEqual(bio.predict_for_body(body, system), [])

    def test_codex_names(self):
        self.assertEqual(codex.display_name("$Codex_Ent_Bacterial_Genus_Name;"), "Bacterium")
        self.assertGreater(codex.reward_for("Bacterium", "Bacterium Cerbrus", "Lime"), 0)
        self.assertGreater(codex.sample_range("$Codex_Ent_Osseus_Genus_Name;"), 0)


if __name__ == "__main__":
    unittest.main()
