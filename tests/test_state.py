# Edited by nc.ai 0.8.8.0 on macbook 2026-10-17 20:13:56
"""Тесты конвейера: журнал -> состояние -> HUD, кэш систем, залоченный маршрут."""
from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud import demo, hudmodel, journal  # noqa: E402
from edhud.config import Config  # noqa: E402
from edhud.model import Body, GameState, System, surface_distance  # noqa: E402
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
        self.assertIn("осталось 2 прыжка из ", route_row)
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

    def test_first_logged_payout(self):
        body = self.state.system.body(1)
        organismes = list(body.organisms.values())
        bacter = next(o for o in organismes if o.genus and "Bacterial" in o.genus)
        self.assertFalse(bacter.was_logged)
        self.assertTrue(bacter.first_logged)
        self.assertEqual(bacter.payout, bacter.reward * 5)
        fungus = next(o for o in organismes if o.genus and "Fungoids" in o.genus)
        self.assertTrue(fungus.was_logged)
        self.assertFalse(fungus.first_logged)
        self.assertEqual(fungus.payout, fungus.reward)

    def test_sold_totals(self):
        # демо в конце продаёт данные: суммы из SellExplorationData/SellOrganicData
        self.assertGreater(self.state.session_organic_sold, 0)
        self.assertGreater(self.state.session_sold, 0)
        view = hudmodel.build_view(self.state, Config(), expanded=True)
        self.assertIn("продано", "\n".join(row.text for row in view.detail))

    def test_hud_first_logged_marker(self):
        view = hudmodel.build_view(self.state, Config(), expanded=True)
        detail = "\n".join(row.text for row in view.detail)
        self.assertIn("×5 First Logged", detail)

    def test_dump_lines(self):
        from edhud.app import dump

        lines = dump(self.folder)
        self.assertTrue(any("JAMESON" in line for line in lines))
        self.assertTrue(any("БИО" in line for line in lines))


class LegacyTests(unittest.TestCase):
    def test_legacy_version(self):
        state = GameState()
        state.apply({"event": "Fileheader", "part": 1, "gameversion": "3.8.0.400", "build": "r286858/r0 "})
        self.assertTrue(state.legacy)
        self.assertFalse(state.odyssey)
        view = hudmodel.build_view(state, Config(), expanded=True)
        self.assertIn("Legacy 3.8", view.body_row.text + "\n".join(r.text for r in view.detail))

    def test_live_version(self):
        state = GameState()
        state.apply({"event": "Fileheader", "part": 1, "gameversion": "4.9.0.100"})
        self.assertFalse(state.legacy)
        self.assertTrue(state.odyssey)

    def test_odyssey_bonus_changes_value(self):
        from edhud import values

        body = Body(
            body_id=1,
            name="Test",
            planet_class="Icy body",
            mass_em=0.9,
            was_discovered=True,
            was_mapped=True,
        )
        live = values.body_values(body, odyssey=True)
        legacy = values.body_values(body, odyssey=False)
        assert live is not None and legacy is not None
        self.assertGreater(live.mapped, legacy.mapped)
        self.assertEqual(live.scan, legacy.scan)

    def test_no_predictions_in_legacy(self):
        from edhud import hudmodel as hm

        state = GameState()
        state.legacy = True
        state.system = System(address=1, name="Test")
        state.system.bodies[0] = Body(body_id=0, name="A", star_type="K", is_star=True)
        state.system.bodies[1] = Body(
            body_id=1,
            name="Test 1",
            planet_class="Icy body",
            landable=True,
            mass_em=0.9,
            surface_gravity=5.6,
            surface_temp=118.0,
            surface_pressure=540.0,
            atmosphere="thin neon atmosphere",
            atmosphere_composition={"Neon": 100.0},
            materials={"Technetium": 0.7},
            parent_ids=[0],
        )
        state.current_body_id = 1
        cfg = Config()
        cfg.expanded = True
        view = hm.build_view(state, cfg, expanded=True)
        detail = "\n".join(row.text for row in view.detail)
        self.assertNotIn("предсказание:", detail)


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


class ScanOrganicBodyIdTests(unittest.TestCase):
    def test_scanorganic_body_int_does_not_break_hud(self):
        """ScanOrganic пишет Body как BodyID (число) без BodyName — имя не должно стать int."""
        from edhud.config import Config
        from edhud import hudmodel

        state = GameState()
        state.apply(
            {
                "event": "FSDJump",
                "StarSystem": "Test",
                "SystemAddress": 7,
                "StarPos": [0, 0, 0],
                "JumpDist": 10.0,
            }
        )
        state.apply(
            {
                "event": "Scan",
                "BodyID": 25,
                "BodyName": "Test 5",
                "PlanetClass": "Icy body",
                "Landable": True,
                "Radius": 6e6,
                "WasDiscovered": True,
                "WasMapped": False,
            }
        )
        state.apply(
            {
                "event": "ScanOrganic",
                "ScanType": "Log",
                "Genus": "$Codex_Ent_Fonticulus_Genus_Name;",
                "Genus_Localised": "Fonticulua",
                "Species": "$Codex_Ent_Fonticulus_01_Name;",
                "Species_Localised": "Fonticulua Segmentatus",
                "Body": 25,
                "SystemAddress": 7,
            }
        )
        body = state.system.bodies[25]
        self.assertIsInstance(body.name, str)
        self.assertEqual(body.name, "Test 5")
        view = hudmodel.build_view(state, Config(), expanded=True)
        self.assertTrue(any(isinstance(line, str) for line in view.plain()))
        self.assertIn("Test", view.plain()[0] + view.plain()[1])


class RouteFileTests(unittest.TestCase):
    def test_journal_navroute_without_list_reloads_file(self):
        """Игра пишет в журнал {"event":"NavRoute"} без Route, список — в NavRoute.json."""
        import json

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            payload = {
                "event": "NavRoute",
                "Route": [
                    {"StarSystem": "Sol", "SystemAddress": 1, "StarPos": [0, 0, 0], "StarClass": "G"},
                    {"StarSystem": "Alpha", "SystemAddress": 2, "StarPos": [0, 0, 10], "StarClass": "K"},
                ],
            }
            (folder / "NavRoute.json").write_text(json.dumps(payload), encoding="utf-8")
            (folder / "Journal.2026-11-01T000000.01.log").write_text("", encoding="utf-8")
            state = GameState()
            watcher = journal.JournalWatcher(folder, state, replay=True)
            watcher.read_navroute()
            self.assertEqual([h.system for h in state.route.hops], ["Sol", "Alpha"])

            with (folder / "Journal.2026-11-01T000000.01.log").open("a", encoding="utf-8") as handle:
                handle.write('{"event":"NavRoute"}\n')
            watcher.read_journal()
            self.assertTrue(state.navroute_stale)
            self.assertEqual([h.system for h in state.route.hops], ["Sol", "Alpha"])
            watcher.read_navroute()
            self.assertFalse(state.navroute_stale)
            self.assertEqual([h.system for h in state.route.hops], ["Sol", "Alpha"])


class FirstDiscoveryTests(unittest.TestCase):
    def _jump(self, state: GameState, name: str, address: int) -> None:
        state.apply(
            {
                "event": "FSDJump",
                "StarSystem": name,
                "SystemAddress": address,
                "StarPos": [0, 0, 0],
                "JumpDist": 20.0,
            }
        )

    def _star(self, state: GameState, name: str, address: int, discovered: bool) -> None:
        state.apply(
            {
                "event": "Scan",
                "ScanType": "AutoScan",
                "BodyName": name,
                "BodyID": 0,
                "StarSystem": name,
                "SystemAddress": address,
                "StarType": "M",
                "StellarMass": 0.3,
                "WasDiscovered": discovered,
                "WasMapped": False,
            }
        )

    def test_new_star_marks_system_and_session(self):
        state = GameState()
        self._jump(state, "New A", 1)
        self._star(state, "New A", 1, discovered=False)
        self.assertTrue(state.system.discovered_by_me)
        self.assertEqual(state.session_new_systems, 1)
        # повторный скан той же звезды не увеличивает счётчик
        self._star(state, "New A", 1, discovered=False)
        self.assertEqual(state.session_new_systems, 1)

        self._jump(state, "Known", 2)
        self._star(state, "Known", 2, discovered=True)
        self.assertFalse(state.system.discovered_by_me)
        self.assertEqual(state.session_new_systems, 1)

        self._jump(state, "New B", 3)
        # неоткрытая планета — это не «система открыта вами»
        state.apply(
            {
                "event": "Scan",
                "BodyName": "New B 1",
                "BodyID": 1,
                "SystemAddress": 3,
                "PlanetClass": "Icy body",
                "WasDiscovered": False,
            }
        )
        self.assertFalse(state.system.discovered_by_me)
        self._star(state, "New B", 3, discovered=False)
        self.assertTrue(state.system.discovered_by_me)
        self.assertEqual(state.session_new_systems, 2)

        view = hudmodel.build_view(state, Config(), expanded=True)
        detail = "\n".join(row.text for row in view.detail)
        self.assertIn("New B", detail)
        self.assertIn("открыта вами", detail)
        self.assertIn("новых систем: 2", detail)


class CarrierClickTests(unittest.TestCase):
    def test_carrier_label_includes_system(self):
        state = GameState()
        state.carrier.carrier_id = 1
        state.carrier.callsign = "GHY-7TZ"
        state.carrier.system = "Home Base"
        state.carrier.address = 1
        state.carrier.star_pos = (0, 0, 0)
        state.system.address = 2
        state.system.name = "Away"
        state.system.star_pos = (0, 0, 40)
        label = hudmodel._carrier_label(state)
        self.assertIsNotNone(label)
        self.assertIn("Home Base", label)
        self.assertIn("GHY-7TZ", label)

    def test_carrier_jump_pending_shown_in_header(self):
        import time
        import tkinter as tk

        from edhud.mainwindow import MainWindow

        state = GameState()
        state.carrier.carrier_id = 7
        state.carrier.callsign = "GHY-7TZ"
        state.carrier.system = "FromSys"
        state.apply(
            {
                "event": "CarrierJumpRequest",
                "CarrierID": 7,
                "SystemName": "ToSys",
                "SystemAddress": 99,
                "DepartureTime": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 600)),
            }
        )
        self.assertTrue(state.carrier.jump_pending)
        self.assertEqual(state.carrier.jump_from_system, "FromSys")
        label = hudmodel._carrier_label(state)
        self.assertIn("FromSys", label or "")
        self.assertIn("ToSys", label or "")
        self.assertNotIn("карриер карриер", (label or "").lower())

        root = tk.Tk()
        root.withdraw()
        try:
            window = MainWindow(root)
            window.update_state(state)
            text = window.lbl_carrier.cget("text")
            self.assertIn("готовится прыгать", text)
            self.assertIn("FromSys", text)
            self.assertIn("ToSys", text)
            self.assertNotIn("Карриер карриер", text)
            self.assertIn("2× копия", window.lbl_carrier_hint.cget("text"))
            window.destroy()
        finally:
            root.destroy()

    def test_carrier_header_not_duplicated(self):
        import tkinter as tk

        from edhud.mainwindow import MainWindow

        root = tk.Tk()
        root.withdraw()
        try:
            window = MainWindow(root)
            state = GameState()
            state.carrier.carrier_id = 1
            state.carrier.system = "Somewhere"
            state.carrier.star_pos = (0, 0, 0)
            state.system.star_pos = (0, 0, 40)
            state.system.address = 2
            window.update_state(state)
            text = window.lbl_carrier.cget("text")
            self.assertTrue(text.startswith("Карриер:"))
            self.assertNotIn("Карриер карриер", text)
            window.destroy()
        finally:
            root.destroy()

    def test_mainwindow_copies_system_on_double_click(self):
        import tkinter as tk

        from edhud.mainwindow import MainWindow

        copied: list[str] = []
        root = tk.Tk()
        root.withdraw()
        try:
            window = MainWindow(root, on_copy_system=copied.append, on_copy_carrier=copied.append)
            state = GameState()
            state.system.name = "Alpha Centauri"
            state.carrier.carrier_id = 7
            state.carrier.system = "Carrier Home"
            state.carrier.callsign = "ABC-123"
            window.update_state(state)
            window._on_system_double()
            window._on_carrier_double()
            self.assertEqual(copied, ["Alpha Centauri", "Carrier Home"])
            self.assertNotIn("карриер карриер", window.lbl_carrier.cget("text").lower())
            plotted: list[int] = []
            window.on_plot_to_carrier = lambda: plotted.append(1)
            window._carrier_clicks = 3
            window._on_carrier_triple()
            self.assertEqual(plotted, [1])
            window.destroy()
        finally:
            root.destroy()


class RouteOpenedColumnTests(unittest.TestCase):
    def test_route_hop_shows_discoverer_or_ours(self):
        from edhud.mainwindow import ROUTE_COLUMNS, MainWindow
        from edhud.route import Route, RouteHop

        state = GameState()
        state.cmdr = "PapaTramp"
        state.route = Route(
            hops=[
                RouteHop(system="Home", star_class="K", discovered_by_me=True),
                RouteHop(system="Sol", star_class="G", discovered_by="Redfoxxx"),
                RouteHop(system="Unknown", star_class="M"),
            ]
        )
        state.note_system_discoverer("Home", None, by_me=True)
        self.assertEqual(state.route.hops[0].opened_label(), "Ваше открытие")
        self.assertEqual(state.route.hops[1].opened_label(), "Redfoxxx")
        self.assertEqual(state.route.hops[2].opened_label(), "—")

        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        try:
            window = MainWindow(root)
            window.update_state(state)
            window.win.update_idletasks()
            columns = {key: index for index, (key, *_rest) in enumerate(ROUTE_COLUMNS)}
            self.assertIn("opened", columns)
            box = window._route_inner.grid_slaves(row=0, column=columns["opened"])[0]
            label = box.winfo_children()[0]
            self.assertEqual(label.cget("text"), "Ваше открытие")
            box2 = window._route_inner.grid_slaves(row=1, column=columns["opened"])[0]
            self.assertEqual(box2.winfo_children()[0].cget("text"), "Redfoxxx")
            window.destroy()
        finally:
            root.destroy()


class JumpTabTests(unittest.TestCase):
    def test_hyperspace_opens_route_and_arrival_opens_bodies(self):
        state = GameState()
        state.apply({"event": "StartJump", "JumpType": "Supercruise"})
        self.assertEqual(state.view_tab, "bodies")
        state.apply(
            {
                "event": "StartJump",
                "JumpType": "Hyperspace",
                "StarSystem": "Alpha",
                "SystemAddress": 2,
            }
        )
        self.assertEqual(state.view_tab, "route")
        state.apply(
            {
                "event": "FSDJump",
                "StarSystem": "Alpha",
                "SystemAddress": 2,
                "StarPos": [0, 0, 10],
                "JumpDist": 10,
            }
        )
        self.assertEqual(state.view_tab, "bodies")

    def test_fsd_charging_to_other_system_opens_route(self):
        state = GameState()
        state.system.address = 1
        state.system.name = "Here"
        # зарядка суперкруиза в той же системе — вкладку не трогаем
        state.apply_status(
            {
                "Flags": 1 << 17,
                "Destination": {"System": 1, "Body": 0, "Name": "Here"},
            }
        )
        self.assertEqual(state.view_tab, "bodies")
        # зарядка гиперпрыжка (даже без суперкруиза) → Route
        state.apply_status(
            {
                "Flags": 1 << 17,
                "Destination": {"System": 2, "Body": 0, "Name": "There"},
            }
        )
        self.assertEqual(state.view_tab, "route")
        state.apply(
            {
                "event": "FSDJump",
                "StarSystem": "There",
                "SystemAddress": 2,
                "StarPos": [0, 0, 10],
                "JumpDist": 10,
            }
        )
        self.assertEqual(state.view_tab, "bodies")
        state.apply(
            {
                "event": "Scan",
                "BodyName": "There 1",
                "BodyID": 1,
                "SystemAddress": 2,
                "PlanetClass": "Icy body",
                "Materials": [{"Name": "iron", "Percent": 20.0}],
            }
        )
        self.assertEqual(state.system.name, "There")
        self.assertIn(1, state.system.bodies)
        self.assertEqual(state.system.bodies[1].materials.get("iron"), 20.0)
        from edhud.remote import apply_eddn

        self.assertTrue(
            apply_eddn(
                state.system,
                {
                    "event": "Scan",
                    "BodyID": 2,
                    "BodyName": "There 2",
                    "SystemAddress": 2,
                    "PlanetClass": "Rocky body",
                    "Materials": [{"Name": "iron", "Percent": 11.5}],
                },
            )
        )
        self.assertEqual(state.system.bodies[2].materials.get("iron"), 11.5)


class AtmosphereDimTests(unittest.TestCase):
    def test_glide_dims_until_leave_or_high_altitude(self):
        state = GameState()
        # орбитальный круиз высоко — ещё не атмосфера
        state.apply_status(
            {
                "Flags": 1 << 21,
                "Flags2": 0,
                "Latitude": 10.0,
                "Longitude": 20.0,
                "Altitude": 250_000,
            }
        )
        self.assertFalse(state.in_atmosphere)
        # вход в атмосферу (Glide)
        state.apply_status(
            {
                "Flags": 1 << 21,
                "Flags2": 1 << 12,
                "Latitude": 10.0,
                "Longitude": 20.0,
                "Altitude": 40_000,
            }
        )
        self.assertTrue(state.in_atmosphere)
        # после глида всё ещё низко
        state.apply_status(
            {
                "Flags": 1 << 21,
                "Flags2": 0,
                "Latitude": 10.0,
                "Longitude": 20.0,
                "Altitude": 2_000,
            }
        )
        self.assertTrue(state.in_atmosphere)
        state.apply({"event": "Touchdown", "Body": "World 1", "BodyID": 1})
        self.assertTrue(state.in_atmosphere)
        state.apply({"event": "Liftoff"})
        self.assertTrue(state.in_atmosphere)
        # набор высоты / LeaveBody — снова обычный HUD
        state.apply_status(
            {
                "Flags": 1 << 21,
                "Flags2": 0,
                "Latitude": 10.0,
                "Longitude": 20.0,
                "Altitude": 150_000,
            }
        )
        self.assertFalse(state.in_atmosphere)
        state.apply_status(
            {
                "Flags": 1 << 21,
                "Flags2": 1 << 12,
                "Latitude": 10.0,
                "Longitude": 20.0,
                "Altitude": 30_000,
            }
        )
        self.assertTrue(state.in_atmosphere)
        state.apply({"event": "LeaveBody", "Body": "World 1", "BodyID": 1})
        self.assertFalse(state.in_atmosphere)


class CarrierDistanceTests(unittest.TestCase):
    def test_distance_from_carrier_system(self):
        state = GameState()
        state.apply(
            {
                "event": "CarrierLocation",
                "CarrierID": 7,
                "StarSystem": "Home",
                "SystemAddress": 1,
                "BodyID": 0,
            }
        )
        state.apply({"event": "CarrierStats", "CarrierID": 7, "Callsign": "GHY-7TZ", "Name": "pedrikakis"})
        state.apply(
            {
                "event": "Location",
                "StarSystem": "Home",
                "SystemAddress": 1,
                "StarPos": [0, 0, 0],
            }
        )
        self.assertEqual(state.carrier.callsign, "GHY-7TZ")
        self.assertEqual(state.carrier_distance_ly(), 0.0)
        state.apply(
            {
                "event": "FSDJump",
                "StarSystem": "Away",
                "SystemAddress": 2,
                "StarPos": [0, 0, 40],
                "JumpDist": 40,
            }
        )
        self.assertAlmostEqual(state.carrier_distance_ly(), 40.0, places=3)
        view = hudmodel.build_view(state, Config(), expanded=False)
        self.assertIn("GHY-7TZ", view.route_row.text)
        self.assertIn("40.0 ly", view.route_row.text)

    def test_carrier_relocation_drops_the_old_distance(self):
        from edhud.route import Route, RouteHop

        state = GameState()
        state.apply(
            {
                "event": "CarrierLocation",
                "CarrierID": 7,
                "StarSystem": "Home",
                "SystemAddress": 1,
            }
        )
        state.apply({"event": "CarrierStats", "CarrierID": 7, "Callsign": "GHY-7TZ", "Name": "pedrikakis"})
        state.apply(
            {
                "event": "Location",
                "StarSystem": "Home",
                "SystemAddress": 1,
                "StarPos": [0, 0, 0],
            }
        )
        state.apply(
            {
                "event": "FSDJump",
                "StarSystem": "Away",
                "SystemAddress": 2,
                "StarPos": [0, 0, 40],
                "JumpDist": 40,
            }
        )
        state.route = Route(
            hops=[
                RouteHop(system="Away", address=2, star_pos=(0, 0, 40)),
                RouteHop(system="Near", address=3, star_pos=(0, 0, 10)),
            ]
        )
        self.assertAlmostEqual(state.carrier_distance_ly(), 40.0, places=3)
        state.apply(
            {
                "event": "CarrierLocation",
                "CarrierID": 7,
                "StarSystem": "Near",
                "SystemAddress": 3,
                "BodyID": 1,
            }
        )
        self.assertEqual(state.carrier.system, "Near")
        self.assertFalse(state.carrier_pos_pending)
        self.assertAlmostEqual(state.carrier_distance_ly(), 30.0, places=3)
        view = hudmodel.build_view(state, Config(), expanded=False)
        self.assertIn("30.0 ly", view.route_row.text)

    def test_carrier_jump_request_moves_after_departure(self):
        state = GameState()
        state.apply(
            {
                "event": "CarrierLocation",
                "CarrierID": 7,
                "StarSystem": "Home",
                "SystemAddress": 1,
            }
        )
        state.apply({"event": "CarrierStats", "CarrierID": 7, "Callsign": "GHY-7TZ", "Name": "pedrikakis"})
        state.apply(
            {
                "event": "Location",
                "StarSystem": "Away",
                "SystemAddress": 2,
                "StarPos": [0, 0, 40],
            }
        )
        state._remember_star(1, "Home", (0, 0, 0))
        self.assertAlmostEqual(state.carrier_distance_ly(), 40.0, places=3)
        past = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 120))
        state.apply(
            {
                "event": "CarrierJumpRequest",
                "CarrierID": 7,
                "SystemName": "Near",
                "SystemAddress": 3,
                "BodyID": 1,
                "DepartureTime": past,
            }
        )
        self.assertEqual(state.carrier.system, "Near")
        self.assertEqual(state.carrier.address, 3)
        self.assertTrue(state.carrier_pos_pending)
        self.assertIsNone(state.carrier_distance_ly())
        state._remember_star(3, "Near", (0, 0, 10))
        self.assertAlmostEqual(state.carrier_distance_ly(), 30.0, places=3)
        view = hudmodel.build_view(state, Config(), expanded=False)
        self.assertIn("30.0 ly", view.route_row.text)

    def test_rings_mark_mineable_belt(self):
        state = GameState()
        state.apply(
            {
                "event": "FSDJump",
                "StarSystem": "Ringed",
                "SystemAddress": 3,
                "StarPos": [1, 2, 3],
                "JumpDist": 5,
            }
        )
        state.apply(
            {
                "event": "Scan",
                "BodyName": "Ringed",
                "BodyID": 0,
                "StarType": "M",
                "StellarMass": 0.4,
                "Rings": [
                    {"Name": "Ringed A Belt", "RingClass": "eRingClass_Rocky"},
                    {"Name": "Ringed B Belt", "RingClass": "eRingClass_Icy"},
                ],
                "WasDiscovered": True,
            }
        )
        state.apply(
            {
                "event": "Scan",
                "BodyName": "Ringed 1",
                "BodyID": 1,
                "PlanetClass": "Icy body",
                "WasDiscovered": True,
            }
        )
        state.apply(
            {
                "event": "Scan",
                "BodyName": "Ringed 2",
                "BodyID": 2,
                "PlanetClass": "High metal content body",
                "Rings": [{"Name": "Ringed 2 A Ring", "RingClass": "eRingClass_Icy"}],
                "WasDiscovered": True,
            }
        )
        state.apply(
            {
                "event": "Scan",
                "BodyName": "Ringed B A Belt Cluster 1",
                "BodyID": 3,
                "WasDiscovered": False,
            }
        )
        star = state.system.body(0)
        planet = state.system.body(1)
        ringed = state.system.body(2)
        cluster = state.system.body(3)
        assert star is not None and planet is not None and ringed is not None and cluster is not None
        self.assertFalse(star.has_rings)
        self.assertFalse(planet.has_rings)
        self.assertTrue(ringed.has_rings)
        self.assertTrue(cluster.has_rings)

    def test_planetary_mining_locations(self):
        state = GameState()
        state.apply(
            {
                "event": "FSSBodySignals",
                "BodyName": "Ringed 1",
                "BodyID": 1,
                "SystemAddress": 3,
                "Signals": [
                    {
                        "Type": "$PlanetaryMiningLocation_Name;",
                        "Type_Localised": "Planetary Mining Location",
                        "Count": 15,
                    },
                    {"Type": "$SAA_SignalType_Geological;", "Count": 2},
                ],
            }
        )
        body = state.system.body(1)
        assert body is not None
        self.assertEqual(body.mining_locations, 15)
        self.assertEqual(body.geo_signals, 2)
        state.apply(
            {
                "event": "SAASignalsFound",
                "BodyName": "Ringed 1",
                "BodyID": 1,
                "SystemAddress": 3,
                "Signals": [
                    {"Type": "$SAA_SignalType_Geological;", "Count": 2},
                    {
                        "Type": "$PlanetaryMiningLocation_Name;",
                        "Type_Localised": "Planetary Mining Location",
                        "Count": 15,
                    },
                ],
            }
        )
        self.assertEqual(state.system.body(1).mining_locations, 15)
        self.assertTrue(state.system.body(1).dss_scanned)


class RouteMarkTests(unittest.TestCase):
    def test_passed_are_gray_and_current_is_larger(self):
        from edhud.mainwindow import route_tag

        self.assertEqual(route_tag(0, 2), "done")
        self.assertEqual(route_tag(1, 2), "done")
        self.assertEqual(route_tag(2, 2), "here")
        self.assertEqual(route_tag(3, 2), "")
        self.assertEqual(route_tag(0, None), "")

    def test_route_table_marks_current(self):
        import tkinter as tk

        from edhud.mainwindow import BODY_COLUMNS, COLORS, MainWindow, ROUTE_COLUMNS
        from edhud.route import Route, RouteHop

        root = tk.Tk()
        root.withdraw()
        try:
            window = MainWindow(root)
            state = GameState()
            state.system.name = "Beta"
            state.route = Route(
                hops=[
                    RouteHop(system="Alpha", star_class="K"),
                    RouteHop(system="Beta", star_class="G"),
                    RouteHop(system="Gamma", star_class="M"),
                ]
            )
            window.update_state(state)
            window.win.update_idletasks()
            columns = {key: index for index, (key, *_rest) in enumerate(ROUTE_COLUMNS)}
            rows = {}
            for box in window._route_inner.winfo_children():
                info = box.grid_info()
                label = box.winfo_children()[0] if box.winfo_children() else box
                rows.setdefault(int(info["row"]), {})[int(info["column"])] = (box, label)
            self.assertEqual(rows[0][columns["system"]][1].cget("fg"), COLORS["muted"])
            self.assertTrue(str(rows[1][columns["system"]][1].cget("text")).startswith("▶ "))
            self.assertEqual(int(rows[0][columns["system"]][0].cget("highlightthickness")), 1)
            self.assertEqual(len(BODY_COLUMNS), len(window._header_labels))
            window.destroy()
        finally:
            root.destroy()

    def test_column_widths_persist(self):
        import tempfile
        from pathlib import Path
        import tkinter as tk

        from edhud.config import Config
        from edhud.mainwindow import MainWindow

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            cfg = Config()
            cfg.bodies_columns = {"name": 260, "bio": 64}
            cfg.route_columns = {"system": 400}
            cfg.main_geometry = "1000x500+10+20"
            cfg.save(path)
            loaded = Config.load(path)
            self.assertEqual(loaded.bodies_columns["name"], 260)
            self.assertEqual(loaded.route_columns["system"], 400)
            self.assertEqual(loaded.main_geometry, "1000x500+10+20")

            root = tk.Tk()
            root.withdraw()
            try:
                window = MainWindow(root, cfg=loaded)
                self.assertEqual(window._body_widths["name"], 260)
                self.assertEqual(window._body_widths["bio"], 64)
                self.assertEqual(window._route_widths["system"], 400)
                window._set_col_width("bodies", 1, 300)
                self.assertEqual(window._body_widths["name"], 300)
                window.destroy()
            finally:
                root.destroy()

    def test_route_columns_do_not_autostretch_system(self):
        import tkinter as tk

        from edhud.mainwindow import MainWindow, ROUTE_COLUMNS

        root = tk.Tk()
        root.withdraw()
        try:
            window = MainWindow(root)
            window._route_widths["system"] = 200
            window._route_widths["ly"] = 160
            widths = window._effective_widths("route")
            keys = [key for key, *_rest in ROUTE_COLUMNS]
            self.assertEqual(widths[keys.index("system")], 200)
            self.assertEqual(widths[keys.index("ly")], 160)
            # сужение Sistema и расширение ly сохраняются — без отката stretch
            window._set_col_width("route", keys.index("system"), 160)
            window._set_col_width("route", keys.index("ly"), 200)
            again = window._effective_widths("route")
            self.assertEqual(again[keys.index("system")], 160)
            self.assertEqual(again[keys.index("ly")], 200)
            window.destroy()
        finally:
            root.destroy()


class BodyColorTests(unittest.TestCase):
    def test_signal_colors(self):
        from edhud.mainwindow import signal_colors

        self.assertIsNone(signal_colors("bio", 0))
        self.assertIsNone(signal_colors("bio", None))
        self.assertEqual(signal_colors("bio", 2)[0], "#7ddb6a")
        self.assertEqual(signal_colors("geo", 1)[0], "#ff5f56")
        fg, bg = signal_colors("pml", 15)
        self.assertEqual(fg, "#000000")
        self.assertNotEqual(bg, "#161616")

    def test_bodies_table_paints_counts(self):
        import tkinter as tk

        from edhud.mainwindow import BODY_COLUMNS, MainWindow

        root = tk.Tk()
        root.withdraw()
        try:
            window = MainWindow(root)
            state = GameState()
            state.system.bodies[1] = Body(
                body_id=1,
                name="Test 1",
                planet_class="Icy body",
                bio_signals=2,
                geo_signals=3,
                mining_locations=15,
                signals_known=True,
            )
            state.system.bodies[2] = Body(
                body_id=2,
                name="Test 2",
                planet_class="Rocky body",
                bio_signals=0,
                geo_signals=0,
                mining_locations=0,
                signals_known=True,
            )
            window.update_state(state)
            window.win.update_idletasks()
            columns = {key: index for index, (key, *_rest) in enumerate(BODY_COLUMNS)}

            def _label(row: int, col: int):
                box = window._bodies_inner.grid_slaves(row=row, column=col)[0]
                kids = box.winfo_children()
                return kids[0] if kids else box

            painted = {
                col: (_label(0, col).cget("text"), _label(0, col).cget("fg"))
                for col in (columns["bio"], columns["geo"], columns["pml"])
            }
            self.assertEqual(painted[columns["bio"]][1], "#7ddb6a")
            self.assertEqual(painted[columns["geo"]][1], "#ff5f56")
            self.assertEqual(painted[columns["pml"]][1], "#000000")
            zeros = {
                col: _label(1, col).cget("fg")
                for col in (columns["bio"], columns["geo"], columns["pml"])
            }
            self.assertEqual(zeros[columns["bio"]], "#e8e8e8")
            self.assertEqual(zeros[columns["geo"]], "#e8e8e8")
            self.assertEqual(zeros[columns["pml"]], "#e8e8e8")
            # хедер и строка одной ширины — колонки не разъезжаются
            for col in range(len(BODY_COLUMNS)):
                head = window._bodies_header.grid_slaves(row=0, column=col)[0]
                body = window._bodies_inner.grid_slaves(row=0, column=col)[0]
                self.assertEqual(int(head.cget("width")), int(body.cget("width")))
            window.destroy()
        finally:
            root.destroy()

    def test_bodies_table_shows_bio_forecast(self):
        import tkinter as tk

        from edhud.mainwindow import BODY_COLUMNS, COLORS, MainWindow, _forecast_tip

        root = tk.Tk()
        root.withdraw()
        try:
            window = MainWindow(root)
            state = GameState()
            state.system.star_pos = (0.0, 0.0, 0.0)
            state.system.bodies[0] = Body(
                body_id=0, name="Test A", star_type="K", is_star=True, radius=5e8, surface_temp=4500.0
            )
            state.system.bodies[1] = Body(
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
                bio_signals=2,
                signals_known=True,
            )
            window.update_state(state)
            window.win.update_idletasks()
            columns = {key: index for index, (key, *_rest) in enumerate(BODY_COLUMNS)}
            guess_box = window._bodies_inner.grid_slaves(row=1, column=columns["guess"])[0]
            guess = guess_box.winfo_children()[0]
            bio_box = window._bodies_inner.grid_slaves(row=1, column=columns["bio"])[0]
            bio_cell = bio_box.winfo_children()[0]
            text, fg = guess.cget("text"), guess.cget("fg")
            self.assertTrue(text.startswith("≈ "))
            self.assertIn("Bacterium", text)
            self.assertEqual(fg, COLORS["accent"])
            tip = _forecast_tip(state.system.bodies[1], state)
            self.assertIsNotNone(tip)
            self.assertTrue(tip.startswith("Предположительно:"))
            self.assertIn("Bacterium", tip)
            self.assertTrue(hasattr(bio_cell, "tip"))
            self.assertEqual(bio_cell.tip.text, tip)
            window.destroy()
        finally:
            root.destroy()

    def test_forecast_tip_uses_dss_names(self):
        from edhud.mainwindow import _forecast_tip

        state = GameState()
        body = Body(
            body_id=1,
            name="Test 1",
            planet_class="Icy body",
            bio_signals=1,
            signals_known=True,
            genuses={"$Codex_Ent_Bacterial_Genus_Name;": 1},
            dss_scanned=True,
        )
        state.system.bodies[1] = body
        tip = _forecast_tip(body, state)
        self.assertIsNotNone(tip)
        assert tip is not None
        self.assertTrue(tip.startswith("DSS"))
        self.assertIn("Bacterium", tip)

    def test_forecast_tip_explains_missing_scan(self):
        from edhud.mainwindow import _forecast_tip

        state = GameState()
        body = Body(body_id=1, name="Test 1", bio_signals=2, signals_known=True)
        tip = _forecast_tip(body, state)
        self.assertIsNotNone(tip)
        self.assertIn("детальный скан", tip)


class BioBoardTests(unittest.TestCase):
    def _icy(self, state: GameState, body_id: int = 1, signals: int = 2) -> Body:
        state.system.address = 1
        state.system.name = "Test"
        state.system.star_pos = (0.0, 0.0, 0.0)
        state.system.bodies[0] = Body(
            body_id=0, name="Test A", star_type="K", is_star=True, radius=5e8, surface_temp=4500.0
        )
        body = Body(
            body_id=body_id,
            name=f"Test {body_id}",
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
            bio_signals=signals,
            signals_known=True,
            signals_local=True,
        )
        state.system.bodies[body_id] = body
        return body

    def test_remote_bio_does_not_open_the_board(self):
        state = GameState()
        state.system.bodies[1] = Body(
            body_id=1, name="Far 1", bio_signals=3, signals_known=True, remote=True, source="edsm"
        )
        self.assertIsNone(hudmodel.build_bio_board(state))

    def test_fss_marks_local_and_lists_the_body(self):
        state = GameState()
        state.system.name = "Test"
        state.apply(
            {
                "event": "FSSBodySignals",
                "BodyID": 3,
                "BodyName": "Test 3",
                "Signals": [{"Type": "Biological", "Count": 2}],
            }
        )
        body = state.system.bodies[3]
        self.assertTrue(body.signals_local)
        self.assertEqual(state.last_fss_body_id, 3)
        board = hudmodel.build_bio_board(state)
        self.assertIsNotNone(board)
        assert board is not None
        self.assertEqual(board.title, "биосигналы ×2")
        self.assertIn("3", board.lines[0].text)
        self.assertIn("×2", board.lines[0].text)

    def test_fss_body_card_names_possible_organisms(self):
        state = GameState()
        body = self._icy(state)
        state.last_fss_body_id = body.body_id
        state.status.gui_focus = 9  # FSS
        board = hudmodel.build_bio_board(state)
        self.assertIsNotNone(board)
        assert board is not None
        self.assertEqual(board.title, "1 · био ×2")
        text = "\n".join(board.plain())
        self.assertIn("Bacterium", text)
        self.assertIn("итого", text)
        self.assertIn("футфол", text)

    def test_dss_bio_board_shows_species_and_price(self):
        state = GameState()
        body = self._icy(state)
        body.genuses = {"$Codex_Ent_Bacterial_Genus_Name;": 1}
        body.dss_scanned = True
        state.last_fss_body_id = body.body_id
        state.status.gui_focus = 9
        board = hudmodel.build_bio_board(state)
        self.assertIsNotNone(board)
        assert board is not None
        text = "\n".join(board.plain())
        self.assertIn("Bacterium Acies", text)
        self.assertRegex(text, r"1[\s]?000[\s]?000|1\.0")
        from edhud.mainwindow import _forecast, _forecast_tip

        guess, color = _forecast(body, state)
        self.assertIn("Bacterium Acies", guess)
        self.assertEqual(color, "ok")
        tip = _forecast_tip(body, state)
        self.assertIsNotNone(tip)
        assert tip is not None
        self.assertIn("Bacterium Acies", tip)
        self.assertIn("DSS:", tip)

    def test_outside_fss_the_board_lists_every_scanned_body(self):
        state = GameState()
        self._icy(state, 1, 2)
        second = self._icy(state, 2, 1)
        second.distance_ls = 400.0
        second.name = "Test 2"
        board = hudmodel.build_bio_board(state)
        self.assertIsNotNone(board)
        assert board is not None
        self.assertEqual(board.title, "биосигналы ×3")
        self.assertEqual(len(board.lines), 2)
        self.assertTrue(any("Bacterium" in line.text for line in board.lines))

    def test_jump_hides_the_board(self):
        state = GameState()
        self._icy(state)
        state.apply({"event": "FSDJump", "StarSystem": "Next", "SystemAddress": 99})
        self.assertIsNone(state.last_fss_body_id)
        self.assertIsNone(hudmodel.build_bio_board(state))

    def test_panel_draws_the_title(self):
        import tkinter as tk

        from edhud.biooverlay import BioPanel
        from edhud.config import Config

        state = GameState()
        body = self._icy(state)
        state.last_fss_body_id = body.body_id
        state.status.gui_focus = 9
        board = hudmodel.build_bio_board(state)
        root = tk.Tk()
        root.withdraw()
        try:
            panel = BioPanel(root, Config())
            assert board is not None
            panel._draw(board)
            panel.win.update_idletasks()
            texts = [
                panel.canvas.itemcget(item, "text")
                for item in panel.canvas.find_withtag("all")
                if panel.canvas.type(item) == "text"
            ]
            self.assertIn(board.title, texts)
            self.assertTrue(any("Bacterium" in text for text in texts))
            self.assertLess(panel._x, 80)
            panel.destroy()
        finally:
            root.destroy()


class SampleGuideTests(unittest.TestCase):
    def _state(self) -> GameState:
        state = GameState()
        state.system.address = 1
        state.system.name = "Test"
        state.system.bodies[4] = Body(body_id=4, name="Test 1 a", radius=6_000_000.0, landable=True)
        state.apply(
            {
                "event": "ScanOrganic",
                "ScanType": "Log",
                "Genus": "$Codex_Ent_Fonticulus_Genus_Name;",
                "Genus_Localised": "Fonticulua",
                "Species": "$Codex_Ent_Fonticulus_01_Name;",
                "Species_Localised": "Fonticulua Segmentatus",
                "BodyID": 4,
                "BodyName": "Test 1 a",
                "SystemAddress": 1,
            }
        )
        state.system.bodies[4].organisms[
            "$Codex_Ent_Fonticulus_01_Name;"
        ].sample_pos = [(0.0, 0.0)]
        return state

    def _status(self, state: GameState, lat: float, lon: float, heading: float = 0.0) -> None:
        state.apply_status(
            {
                "Latitude": lat,
                "Longitude": lon,
                "Heading": heading,
                "PlanetRadius": 6_000_000.0,
                "BodyID": 4,
                "Flags": 1 << 19,
            }
        )

    def test_close_sample_points_away_even_from_the_ship(self):
        state = self._state()
        self._status(state, 0.0, 0.001, heading=0.0)
        self.assertEqual(state.mode, "Ship")
        plan = state.sample_plan()
        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.need_m, 500)
        self.assertFalse(plan.ready)
        sample = next(guide for guide in plan.guides if guide.kind == "sample")
        away = next(guide for guide in plan.guides if guide.kind == "away")
        self.assertAlmostEqual(sample.distance_m, 104.7, delta=2)
        self.assertFalse(sample.ready)
        self.assertAlmostEqual(sample.bearing or 0, 270, delta=2)
        self.assertAlmostEqual(away.bearing or 0, 90, delta=2)
        self.assertGreater(away.distance_m, 300)
        view = hudmodel.build_view(state, Config(), expanded=False)
        text = "\n".join(view.plain())
        self.assertIn("интервал 500 м", text)
        self.assertIn("дальше", text)
        self.assertIn("курс", text)

    def test_far_enough_sample_can_be_taken(self):
        state = self._state()
        self._status(state, 0.0, 0.01, heading=90.0)
        plan = state.sample_plan()
        assert plan is not None
        self.assertTrue(plan.ready)
        self.assertTrue(all(guide.kind != "away" for guide in plan.guides))

    def test_codex_spot_is_a_bearing_when_outside_the_colony(self):
        state = self._state()
        state.apply(
            {
                "event": "CodexEntry",
                "Name": "$Codex_Ent_Fonticulus_01_M_Name;",
                "Name_Localised": "Fonticulua Segmentatus - Amethyst",
                "Category": "$Codex_Category_Biology;",
                "SubCategory": "$Codex_SubCategory_Organic_Structures;",
                "SystemAddress": 1,
                "BodyID": 4,
                "Latitude": 0.02,
                "Longitude": 0.01,
            }
        )
        self._status(state, 0.0, 0.01, heading=0.0)
        plan = state.sample_plan()
        assert plan is not None
        spots = [guide for guide in plan.guides if guide.kind == "spot"]
        self.assertEqual(len(spots), 1)
        self.assertIn("Fonticulua", spots[0].title)
        self.assertAlmostEqual(spots[0].bearing or 0, 0, delta=5)
        self.assertTrue(spots[0].ready)

    def test_without_coordinates_there_is_no_plan(self):
        state = self._state()
        self.assertIsNone(state.sample_plan())

    def test_radar_shows_colony_ring_and_same_genus_spots(self):
        state = self._state()
        state.system.bodies[4].bio_signals = 2
        state.system.bodies[4].signals_local = True
        state.apply(
            {
                "event": "CodexEntry",
                "Name": "$Codex_Ent_Fonticulus_01_M_Name;",
                "Name_Localised": "Fonticulua Segmentatus - Amethyst",
                "Category": "$Codex_Category_Biology;",
                "SubCategory": "$Codex_SubCategory_Organic_Structures;",
                "SystemAddress": 1,
                "BodyID": 4,
                "Latitude": 0.02,
                "Longitude": 0.01,
            }
        )
        self._status(state, 0.0, 0.001, heading=0.0)
        radar = state.radar_view()
        self.assertIsNotNone(radar)
        assert radar is not None
        self.assertEqual(radar.need_m, 500)
        self.assertFalse(radar.ready)
        self.assertTrue(any(blip.kind == "sample" for blip in radar.blips))
        self.assertTrue(any(blip.kind == "away" for blip in radar.blips))
        board = hudmodel.build_bio_board(state)
        self.assertIsNotNone(board)
        assert board is not None
        self.assertIsNotNone(board.radar)
        self.assertTrue(any(line.startswith("radar:") for line in board.plain()))

    def test_radar_lists_any_spots_before_first_sample(self):
        state = GameState()
        state.system.address = 1
        state.system.name = "Test"
        body = Body(
            body_id=4,
            name="Test 1 a",
            radius=6_000_000.0,
            landable=True,
            bio_signals=1,
            signals_local=True,
            bio_spots=[{"lat": 0.01, "lon": 0.0, "genus": "$Codex_Ent_Bacterial_Genus_Name;", "name": "Bacterium"}],
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
        radar = state.radar_view()
        self.assertIsNotNone(radar)
        assert radar is not None
        self.assertEqual(radar.need_m, 0)
        self.assertEqual(radar.blips[0].kind, "spot")
        self.assertIn("Bacterium", radar.blips[0].label)


class AppearanceTests(unittest.TestCase):
    def test_light_palette_and_settings_tab(self):
        import tkinter as tk
        from tkinter import ttk

        from edhud.config import Config, palette
        from edhud.settings import SettingsDialog, _parse_color

        self.assertEqual(_parse_color("#ABC"), "#aabbcc")
        self.assertIsNone(_parse_color("нет"))
        light = palette("light")
        self.assertNotEqual(light["bg"], palette("dark")["bg"])
        self.assertNotEqual(light["text"], palette("dark")["text"])

        root = tk.Tk()
        root.withdraw()
        try:
            dialog = SettingsDialog(root, Config())
            titles: list[str] = []

            def walk(widget) -> None:
                if isinstance(widget, ttk.Notebook):
                    titles.extend(widget.tab(tab, "text") for tab in widget.tabs())
                for child in widget.winfo_children():
                    walk(child)

            walk(dialog.win)
            self.assertIn("Оформление", titles)
            self.assertIn("Окна", titles)
            dialog.theme.set("light")
            dialog._apply_theme_to_fields()
            self.assertEqual(dialog.color_vars["bg"].get(), light["bg"])
            self.assertEqual(dialog.color_vars["text"].get(), light["text"])
            self.assertTrue(hasattr(dialog, "main_x"))
            self.assertTrue(hasattr(dialog, "bio_opacity"))
            dialog.win.destroy()
        finally:
            root.destroy()

    def test_geometry_xy_parser(self):
        from edhud.mainwindow import _geometry_xy

        self.assertEqual(_geometry_xy("980x520+12+40"), (12, 40))
        self.assertEqual(_geometry_xy("800x600-10+20"), (-10, 20))


if __name__ == "__main__":
    unittest.main()
