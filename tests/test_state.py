# Edited by nc.ai 0.8.8.0 on macbook 2026-10-17 20:13:56
"""Тесты конвейера: журнал -> состояние -> HUD, кэш систем, залоченный маршрут."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud import demo, hudmodel, journal  # noqa: E402
from edhud.config import Config  # noqa: E402
from edhud.model import GameState, surface_distance  # noqa: E402
from edhud.route import Route  # noqa: E402
from edhud.store import SystemStore  # noqa: E402


class JournalPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.tmp.name)
        demo.write_all(cls.folder)
        cls.state = journal.load_snapshot(cls.folder)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_commander_and_ship(self):
        self.assertEqual(self.state.cmdr, "JAMESON")
        self.assertEqual(self.state.ship, "Anaconda")

    def test_system(self):
        self.assertEqual(self.state.system.name, "Synuefe GG-O c22-4")
        self.assertEqual(self.state.system.address, 3932277477892)
        self.assertEqual(len(self.state.system.bodies), 2)

    def test_route_from_files_and_events(self):
        route = self.state.route
        self.assertEqual(route.hops[0].system, "Synuefe EN-H d11-97")
        self.assertEqual(route.remaining(self.state.system.name), 2)

    def test_bio_signals_and_genuses(self):
        body = self.state.system.body(1)
        assert body is not None
        self.assertTrue(body.landable)
        self.assertEqual(body.bio_signals, 2)
        self.assertEqual(len(body.genuses), 2)
        self.assertTrue(body.dss_scanned)

    def test_organic_progress(self):
        body = self.state.system.body(1)
        organelles = list(body.organisms.values())
        self.assertEqual(len(organelles), 2)
        bacterium = next(o for o in organelles if "Bacterial" in (o.genus or ""))
        self.assertEqual(bacterium.samples, 2)
        self.assertFalse(bacterium.analysed)
        fungus = next(o for o in organelles if "Fungoids" in (o.genus or ""))
        self.assertTrue(fungus.analysed)
        self.assertEqual(fungus.variant_short, "Gold")
        self.assertGreater(fungus.reward, 0)

    def test_colony_distance(self):
        state = self.state
        organic = state.active_organic()
        assert organic is not None
        # при живом игре позиция пробы берётся из Status.json в момент сканирования
        last_lat, last_lon = 12.36, -45.70
        organic.sample_pos = [(last_lat, last_lon)]
        state.apply_status(
            {
                "Flags": (1 << 1) | (1 << 21),
                "Latitude": last_lat + 0.01,
                "Longitude": last_lon,
                "PlanetRadius": 6_100_000.0,
                "BodyID": 1,
                "BodyName": "Synuefe GG-O c22-4 1",
                "Fuel": {"FuelMain": 20.0},
            }
        )
        colony = state.colony_distance()
        assert colony is not None
        dist, need = colony
        expected = surface_distance(last_lat + 0.01, last_lon, last_lat, last_lon, 6_100_000.0)
        self.assertAlmostEqual(dist, expected, places=1)
        self.assertGreater(need, 0)

    def test_hud_rows(self):
        cfg = Config()
        view = hudmodel.build_view(self.state, cfg, expanded=True)
        route_row, body_row = view.route_row.text, view.body_row.text
        self.assertIn("МАРШРУТ", route_row)
        self.assertIn("HIP 36601", route_row)
        self.assertIn("ТЕЛО", body_row)
        self.assertIn("БИО", body_row)
        detail = "\n".join(row.text for row in view.detail)
        self.assertIn("Bacterium Cerbrus", detail)
        self.assertTrue(view.progress[1] > 0)
        self.assertGreaterEqual(len(view.dots), 1)

    def test_cache_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SystemStore(Path(tmp))
            self.assertTrue(store.save(self.state.system))
            loaded = store.load(self.state.system.address, self.state.system.name)
            assert loaded is not None
            self.assertEqual(len(loaded.bodies), len(self.state.system.bodies))
            body = loaded.body(1)
            assert body is not None
            self.assertEqual(body.bio_signals, 2)
            self.assertEqual(body.atmosphere_type, "Neon")

    def test_locked_route_is_not_overwritten(self):
        state = GameState()
        watcher = journal.JournalWatcher(self.folder, state)
        state.route = Route.from_names(["Sol", "Alpha"])
        state.route.locked = True
        watcher.read_navroute()
        self.assertEqual([h.system for h in state.route.hops], ["Sol", "Alpha"])

    def test_session_values(self):
        # демо: скан тел + DSS по телу 1 → сессия считает и скан, и картографию
        self.assertGreater(self.state.session_scan_value, 0)
        self.assertGreater(self.state.session_map_value, 0)
        self.assertGreater(self.state.session_organic_estimate, 0)

    def test_hud_value_rows(self):
        view = hudmodel.build_view(self.state, Config(), expanded=True)
        detail = "\n".join(row.text for row in view.detail)
        self.assertIn("стоимость:", detail)
        self.assertIn("система:", detail)
        self.assertIn("сессия:", detail)
        self.assertIn("скан", detail)
        self.assertIn("×2.6", view.body_row.text + detail)

    def test_remote_bodies_are_merged(self):
        from edhud import remote
        from edhud.model import Body, System

        state = GameState()
        state.system = System(address=123, name="Test")
        state.system.bodies[1] = Body(body_id=1, name="Test 1", landable=True)
        parsed = remote._parse_spansh(  # noqa: SLF001
            "Test",
            {
                "results": [
                    {
                        "body_id": 1,
                        "name": "Test 1",
                        "type": "Planet",
                        "subtype": "Icy world",
                        "is_landable": True,
                        "signals": [{"count": 2, "name": "Biological"}],
                    },
                    {"body_id": 2, "name": "Test 2", "type": "Star", "subtype": "K Star"},
                ]
            },
        )
        added = remote.merge_into_system(state.system, parsed)
        self.assertEqual(added, 1)
        state.current_body_id = 1
        view = hudmodel.build_view(state, Config())
        self.assertIn("БИО 2", view.body_row.text)  # сигналы пришли от других командиров
        self.assertEqual(state.system.body(1).bio_signals, 2)

        state.current_body_id = 2
        view = hudmodel.build_view(state, Config())
        self.assertIn("[spansh]", view.body_row.text)  # тело добавлено из Spansh
        self.assertIn("звезда", view.body_row.text)
        star = state.system.body(2)
        assert star is not None
        self.assertTrue(star.remote)
        self.assertTrue(star.is_star)

    def test_dump_lines(self):
        from edhud.app import dump

        lines = dump(self.folder)
        self.assertTrue(any("JAMESON" in line for line in lines))
        self.assertTrue(any("БИО" in line for line in lines))


class StatusTests(unittest.TestCase):
    def test_flags(self):
        state = GameState()
        state.apply_status(
            {
                "Flags": (1 << 4) | (1 << 14),
                "Fuel": {"FuelMain": 3.2, "FuelReserve": 0.5},
                "GuiFocus": 9,
            }
        )
        self.assertTrue(state.status.supercruise)
        self.assertTrue(state.status.low_fuel)
        self.assertAlmostEqual(state.status.fuel_main, 3.2)
        self.assertEqual(state.status.gui_focus, 9)
        self.assertFalse(state.status.docked)


if __name__ == "__main__":
    unittest.main()
