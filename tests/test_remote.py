# Created by nc.ai 0.8.8.0 on macbook 2026-10-17 20:13:46
"""Тесты догрузки тел (EDSM/Spansh) и галактических ориентиров."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud import galaxy, remote  # noqa: E402
from edhud.model import Body, System  # noqa: E402

EDSM_SAMPLE = {
    "id": 1,
    "id64": 3932277477892,
    "name": "Test System",
    "bodies": [
        {
            "bodyId": 1,
            "name": "Test System A",
            "type": "Star",
            "subType": "K (Yellow-Orange) Star",
            "spectralClass": "K",
            "solarMasses": 0.78,
            "solarRadius": 0.72,
            "distanceToArrival": 0,
        },
        {
            "bodyId": 2,
            "name": "Test System 1 a",
            "type": "Planet",
            "subType": "Icy world",
            "parents": [{"Star": 0}, {"Planet": 1}],
            "distanceToArrival": 1180,
            "isLandable": True,
            "gravity": 0.5709,
            "earthMasses": 0.94,
            "radius": 6100.0,
            "surfaceTemperature": 118,
            "surfacePressure": 0.0054,
            "volcanismType": "No volcanism",
            "atmosphereType": "Thin Neon",
            "atmosphereComposition": {"Neon": 100.0},
            "materials": {"Iron": 19.1, "Sulphur": 15.6, "Carbon": 21.2, "Technetium": 0.71},
            "terraformingState": "Not terraformable",
            "discovery": {"commander": "Somebody", "date": "2019-01-28 02:33:01"},
        },
    ],
}

SPANSH_SAMPLE = {
    "count": 2,
    "results": [
        {
            "body_id": 2,
            "name": "Test System 1 a",
            "type": "Planet",
            "subtype": "Icy world",
            "gravity": 0.5709,
            "surface_temperature": 118,
            "surface_pressure": 0.0054,
            "atmosphere": "Thin Neon atmosphere",
            "atmosphere_composition": [{"name": "Neon", "share": 100.0}],
            "materials": [{"name": "Iron", "share": 19.1}],
            "is_landable": True,
            "distance_to_arrival": 1180,
            "radius": 6100.0,
            "earth_masses": 0.94,
            "estimated_scan_value": 12264,
            "signals": [{"count": 3, "name": "Biological"}, {"count": 1, "name": "Geological"}],
        }
    ],
}


class ParseTests(unittest.TestCase):
    def test_normalize_planet_class(self):
        self.assertEqual(remote.normalize_planet_class("Icy world"), "Icy body")
        self.assertEqual(remote.normalize_planet_class("High metal content world"), "High metal content body")
        self.assertEqual(remote.normalize_planet_class("Water world"), "Water world")
        self.assertEqual(remote.normalize_planet_class("Earth-like world"), "Earthlike body")

    def test_parse_edsm(self):
        system = remote._parse_edsm("Test System", EDSM_SAMPLE, timeout=1)  # noqa: SLF001
        self.assertEqual(system.address, 3932277477892)
        body = system.bodies[2]
        self.assertEqual(body.planet_class, "Icy body")
        self.assertEqual(body.discovered_by, "Somebody")
        self.assertAlmostEqual(body.gravity_g, 0.5709)
        model_body = body.to_body()
        self.assertAlmostEqual(model_body.surface_gravity or 0, 5.6, places=1)
        self.assertAlmostEqual(model_body.surface_pressure or 0, 540.0, places=0)
        self.assertEqual(model_body.radius, 6_100_000.0)
        self.assertTrue(model_body.remote)
        self.assertEqual(model_body.atmosphere_type, "Neon")
        self.assertTrue(model_body.landable)

    def test_parse_spansh(self):
        system = remote._parse_spansh("Test System", SPANSH_SAMPLE)  # noqa: SLF001
        body = system.bodies[2]
        self.assertEqual(body.bio_signals, 3)
        self.assertEqual(body.geo_signals, 1)
        self.assertEqual(body.scan_value, 12264)

    def test_merge_providers(self):
        base = remote._parse_edsm("Test System", EDSM_SAMPLE, timeout=1)  # noqa: SLF001
        extra = remote._parse_spansh("Test System", SPANSH_SAMPLE)  # noqa: SLF001
        merged = remote._merge(base, extra)
        assert merged is not None
        self.assertEqual(merged.bodies[2].bio_signals, 3)
        self.assertEqual(merged.sources, ["edsm", "spansh"])


class MergeTests(unittest.TestCase):
    def test_merge_into_system(self):
        local = System(address=3932277477892, name="Test System")
        local.bodies[2] = Body(body_id=2, name="Test System 1 a", planet_class="Icy body", landable=True)
        remote_system = remote._parse_spansh("Test System", SPANSH_SAMPLE)  # noqa: SLF001
        added = remote.merge_into_system(local, remote_system)
        self.assertEqual(added, 0)  # тело уже своё, только обогатили
        self.assertEqual(local.bodies[2].bio_signals, 3)
        self.assertTrue(local.bodies[2].signals_known)

        added = remote.merge_into_system(local, remote._parse_edsm("Test System", EDSM_SAMPLE, 1))  # noqa: SLF001
        self.assertEqual(added, 1)  # звезда добавилась
        self.assertTrue(local.bodies[1].is_star)
        self.assertIn("spansh", local.remote_sources)


class CacheTests(unittest.TestCase):
    def test_cache_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = remote.RemoteClient(cache_dir=Path(tmp), ttl=3600, timeout=0.01)
            system = remote._parse_spansh("Test System", SPANSH_SAMPLE)  # noqa: SLF001
            system.address = 42
            system.fetched_at = 1
            client._save(system)  # noqa: SLF001
            loaded = client.cached("Test System", 42)
            assert loaded is not None
            self.assertEqual(loaded.bodies[2].bio_signals, 3)
            self.assertEqual(loaded.bodies[2].name, "Test System 1 a")


class GalaxyTests(unittest.TestCase):
    def test_guardian_bubbles(self):
        self.assertTrue(galaxy.within_guardian_bubble((1099.21875, -146.6875, -133.59375)))
        self.assertTrue(galaxy.within_guardian_bubble((-840.65625, -561.15625, 13361.8125)))
        self.assertFalse(galaxy.within_guardian_bubble((0.0, 0.0, 0.0)))
        self.assertFalse(galaxy.within_guardian_bubble(None))

    def test_nearest_nebula(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nebulae.csv"
            path.write_text(
                "Name,System,X,Y,Z,Type,RegionID\n"
                "Near,Alpha,-10,0,0,planetary,1\n"
                "Far,Beta,100,0,0,nebula,2\n",
                encoding="utf-8",
            )
            original = galaxy.nebulae_cache
            galaxy.nebulae_cache = lambda: path  # type: ignore[assignment]
            galaxy._positions.cache_clear()
            try:
                self.assertAlmostEqual(galaxy.nearest_nebula((0.0, 0.0, 0.0)) or 0, 10.0, places=3)
                self.assertIsNone(galaxy.nearest_nebula(None))
            finally:
                galaxy.nebulae_cache = original  # type: ignore[assignment]
                galaxy._positions.cache_clear()

    def test_no_catalogue(self):
        original = galaxy.nebulae_cache
        galaxy.nebulae_cache = lambda: Path("/nonexistent/nebulae.csv")  # type: ignore[assignment]
        galaxy._positions.cache_clear()
        try:
            self.assertIsNone(galaxy.nearest_nebula((0.0, 0.0, 0.0)))
        finally:
            galaxy.nebulae_cache = original  # type: ignore[assignment]
            galaxy._positions.cache_clear()


if __name__ == "__main__":
    unittest.main()
