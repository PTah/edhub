"""Колонка «Тела» маршрута берёт состав из своего кэша, а не только из EDSM «до визита»."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from edhud.model import Body, GameState, System  # noqa: E402
from edhud.route import Route, RouteHop  # noqa: E402
from edhud.store import SystemStore  # noqa: E402


def _system(name: str = "Alpha", address: int = 11, by_me: bool = False) -> System:
    system = System(address=address, name=name, discovered_by_me=by_me)
    system.bodies[0] = Body(body_id=0, name=name, is_star=True)
    system.bodies[1] = Body(body_id=1, name=f"{name} 1")
    system.bodies[2] = Body(body_id=2, name=f"{name} 2")
    system.bodies[3] = Body(body_id=3, name=f"{name} 2 A Ring")
    system.bodies[4] = Body(body_id=4, name=f"{name} A Belt Cluster 1")
    return system


class LocalRouteStatsTests(unittest.TestCase):
    def test_route_stats_skip_rings_and_belts(self):
        self.assertEqual(_system().route_stats(), (1, 2, 3))

    def test_local_cache_overrides_stale_edsm_missing(self):
        state = GameState()
        state.cmdr = "PapaTramp"
        state.route = Route(hops=[RouteHop(system="Alpha")])
        # до визита EDSM ответил «систему не знаем»
        state.note_system_body_stats("Alpha", missing=True)
        self.assertTrue(state.route.hops[0].edsm_missing)
        # после визита система в своём кэше, и она наша
        state.note_local_system(_system(by_me=True))
        hop = state.route.hops[0]
        self.assertFalse(hop.edsm_missing)
        self.assertEqual((hop.edsm_stars, hop.edsm_planets), (1, 2))
        self.assertTrue(hop.discovered_by_me)
        self.assertIn("★1", hop.bodies_label())

    def test_richer_edsm_wins_over_partial_local(self):
        state = GameState()
        state.route = Route(hops=[RouteHop(system="Alpha")])
        state.note_system_body_stats("Alpha", stars=2, planets=9, bodies=11)
        state.note_local_system(_system())
        self.assertEqual(state.route.hops[0].edsm_planets, 9)

    def test_store_persists_flag_and_finds_by_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SystemStore(Path(tmp))
            seen: list[str] = []
            store.on_save = lambda system: seen.append(system.name or "")
            self.assertTrue(store.save(_system("Gildefarne", 77, by_me=True)))
            self.assertEqual(seen, ["Gildefarne"])
            fresh = SystemStore(Path(tmp))
            self.assertEqual(fresh.find_address("gildefarne"), 77)
            loaded = fresh.load(77, "Gildefarne")
            self.assertIsNotNone(loaded)
            self.assertTrue(loaded.discovered_by_me)


class CarrierApproxPositionTests(unittest.TestCase):
    def test_id64_position_matches_known_systems(self):
        import math

        from edhud import galaxy

        # (id64, реальные координаты) из кэша систем: позиция в пределах коробки
        known = [
            (10477373803, (0.0, 0.0, 0.0)),  # Sol
        ]
        for address, pos in known:
            got = galaxy.id64_position(address)
            size = 10.0 * (1 << (address & 7))
            self.assertLessEqual(math.dist(got, pos), size * math.sqrt(3) / 2 + 1e-6)
        self.assertIsNone(galaxy.id64_position(None))
        self.assertIsNone(galaxy.id64_position(0))

    def test_carrier_distance_falls_back_to_id64_then_exact_wins(self):
        from edhud import galaxy

        address = 10477373803  # Sol, масс-код 3
        state = GameState()
        state.apply({"event": "CarrierStats", "CarrierID": 7, "Callsign": "GHY-7TZ", "Name": "x"})
        state.apply(
            {"event": "Location", "StarSystem": "Away", "SystemAddress": 2, "StarPos": [0, 0, 400]}
        )
        state._move_carrier("Sol", address, None, None)
        self.assertTrue(state.carrier_pos_pending)
        self.assertIsNone(state.carrier_distance_ly())

        state.set_carrier_pos_approx(galaxy.id64_position(address))
        self.assertTrue(state.carrier_distance_is_approx())
        self.assertIsNotNone(state.carrier_distance_ly())
        self.assertTrue(state.carrier_pos_pending)  # точные координаты всё ещё ищутся

        from edhud import hudmodel
        from edhud.config import Config

        view = hudmodel.build_view(state, Config(), expanded=False)
        self.assertIn("≈", view.body_row.text)

        # точные координаты (EDSM/журнал) заменяют приблизительные
        state._remember_star(address, "Sol", (0.0, 0.0, 0.0))
        self.assertFalse(state.carrier_distance_is_approx())
        self.assertAlmostEqual(state.carrier_distance_ly(), 400.0, places=3)
        self.assertFalse(state.carrier_pos_pending)


class OnEventRegressionTests(unittest.TestCase):
    def test_on_event_does_not_raise_after_canonn(self):
        """Хвост _on_event когда-то попал в _load_canonn → NameError на каждом FSDJump."""
        from types import SimpleNamespace as NS

        from edhud.app import App

        calls: list = []
        state = GameState()
        state.persist_needed = True
        fake = NS(
            alerts=NS(handle=lambda e, s: None),
            edsm=NS(note=lambda e, s: None),
            eddn_upload=NS(note=lambda e, s: None),
            inara=NS(note=lambda e, s: None),
            state=state,
            cfg=NS(copy_next_system=False),
            overlay=None,
            prices=None,
            _load_canonn=lambda name: calls.append(("canonn", name)),
            _save_system_now=lambda: calls.append("save"),
        )
        App._on_event(fake, {"event": "FSDJump", "StarSystem": "X"})
        self.assertEqual(calls, [("canonn", "X"), "save"])
        self.assertFalse(state.persist_needed)


if __name__ == "__main__":
    unittest.main()
