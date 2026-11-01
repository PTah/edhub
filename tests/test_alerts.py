"""Тесты детектора голосовых алертов (без реального TTS)."""
from __future__ import annotations

import unittest

from edhud.alerts import AlertEngine
from edhud.model import GameState


class AlertEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fired: list = []
        self.engine = AlertEngine(on_alert=lambda a: self.fired.append(a))
        self.engine.configure(
            type("Cfg", (), {"voice_enabled": True, "voice_bio": True, "voice_first_discovery": True})()
        )
        self.state = GameState()
        self.state.system.address = 12345
        self.state.system.name = "Test System"

    def test_bio_ignored_during_replay(self) -> None:
        event = {
            "event": "FSSBodySignals",
            "BodyID": 2,
            "BodyName": "Test System 2",
            "Signals": [{"Type": "$SAA_SignalType_Biological;", "Count": 3}],
        }
        self.state.apply(event)
        alerts = self.engine.handle(event, self.state)
        self.assertEqual(alerts, [])
        self.assertEqual(self.fired, [])
        # повтор после arm тоже не должен дублировать (уже в seen)
        self.engine.arm()
        alerts = self.engine.handle(event, self.state)
        self.assertEqual(alerts, [])

    def test_bio_after_arm(self) -> None:
        self.engine.arm()
        event = {
            "event": "FSSBodySignals",
            "BodyID": 3,
            "BodyName": "Test System 3",
            "Signals": [{"Type": "Biological", "Count": 2}],
        }
        self.state.apply(event)
        alerts = self.engine.handle(event, self.state)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].kind, "bio")
        self.assertIn("Биологический", alerts[0].text)

    def test_bio_voice_names_possible_organisms(self) -> None:
        from edhud.model import Body

        self.engine.arm()
        self.state.system.star_pos = (0.0, 0.0, 0.0)
        self.state.system.bodies[0] = Body(body_id=0, name="Test System", star_type="K", is_star=True)
        self.state.system.bodies[3] = Body(
            body_id=3,
            name="Test System 3",
            planet_class="Icy body",
            landable=True,
            surface_temp=118.0,
            surface_gravity=5.6,
            surface_pressure=540.0,
            atmosphere="thin neon atmosphere",
            atmosphere_composition={"Neon": 100.0},
            volcanism="None",
            materials={"Iron": 19.1, "Sulphur": 15.6, "Carbon": 21.2, "Technetium": 0.71},
            parent_ids=[0],
            bio_signals=2,
            signals_known=True,
        )
        event = {
            "event": "FSSBodySignals",
            "BodyID": 3,
            "BodyName": "Test System 3",
            "Signals": [{"Type": "Biological", "Count": 2}],
        }
        alerts = self.engine.handle(event, self.state)
        self.assertEqual(len(alerts), 1)
        self.assertIn("Возможно:", alerts[0].text)
        self.assertIn("Bacterium", alerts[0].text)
        # дубль
        self.assertEqual(self.engine.handle(event, self.state), [])

    def test_first_discovery(self) -> None:
        self.engine.arm()
        event = {
            "event": "Scan",
            "BodyID": 0,
            "BodyName": "Test System",
            "StarType": "K",
            "StellarMass": 0.8,
            "WasDiscovered": False,
            "WasMapped": False,
            "SystemAddress": 12345,
            "StarSystem": "Test System",
        }
        self.state.apply(event)
        alerts = self.engine.handle(event, self.state)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].kind, "first_discovery")
        # второй скан в той же системе — тишина
        event2 = dict(event)
        event2["BodyID"] = 1
        event2["BodyName"] = "Test System 1"
        event2["PlanetClass"] = "Icy body"
        event2.pop("StarType", None)
        self.state.apply(event2)
        self.assertEqual(self.engine.handle(event2, self.state), [])

    def test_already_discovered_silent(self) -> None:
        self.engine.arm()
        event = {
            "event": "Scan",
            "BodyID": 0,
            "BodyName": "Known",
            "StarType": "G",
            "StellarMass": 1.0,
            "WasDiscovered": True,
            "SystemAddress": 99,
        }
        self.state.system.address = 99
        self.state.apply(event)
        self.assertEqual(self.engine.handle(event, self.state), [])
        # известная звезда, первая неоткрытая планета на FSS — не «система открыта вами»
        planet = {
            "event": "Scan",
            "BodyID": 1,
            "BodyName": "Known 1",
            "PlanetClass": "Icy body",
            "WasDiscovered": False,
            "SystemAddress": 99,
        }
        self.state.apply(planet)
        self.assertEqual(self.engine.handle(planet, self.state), [])

    def test_voice_flags(self) -> None:
        self.engine.arm()
        self.engine.voice_bio = False
        event = {
            "event": "SAASignalsFound",
            "BodyID": 7,
            "BodyName": "X 7",
            "Signals": [{"Type": "Biological", "Count": 1}],
        }
        self.state.apply(event)
        self.assertEqual(self.engine.handle(event, self.state), [])
        # seen уже записан — даже после включения флага не повторяем
        self.engine.voice_bio = True
        self.assertEqual(self.engine.handle(event, self.state), [])


if __name__ == "__main__":
    unittest.main()
