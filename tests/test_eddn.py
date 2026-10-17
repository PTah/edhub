# Created by nc.ai 0.8.8.0 on macbook 2026-10-17 20:23:36
"""Тесты собственного слушателя EDDN (ZMTP + фильтр + применение сообщений)."""
from __future__ import annotations

import json
import sys
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud import eddn, remote, zmtp  # noqa: E402
from edhud.model import Body, System  # noqa: E402


def envelope(message: dict) -> bytes:
    return zlib.compress(
        json.dumps({"$schemaRef": "https://eddn.edcd.io/schemas/journal/1", "message": message}).encode()
    )


SCAN = {
    "event": "Scan",
    "StarSystem": "Test System",
    "SystemAddress": 42,
    "BodyID": 3,
    "BodyName": "Test System 2 a",
    "PlanetClass": "Icy body",
    "MassEM": 0.9,
    "Radius": 6100000.0,
    "SurfaceGravity": 5.6,
    "SurfaceTemperature": 118.0,
    "SurfacePressure": 540.0,
    "Atmosphere": "thin neon atmosphere",
    "AtmosphereComposition": {"Neon": 100.0},
    "Volcanism": "None",
    "Materials": {"Iron": 19.1, "Technetium": 0.7},
    "Landable": True,
    "DistanceFromArrivalLS": 1180.0,
    "SemiMajorAxis": 1.2e10,
    "Parents": [{"Star": 0}],
    "WasDiscovered": False,
    "WasMapped": False,
    "WasFootfalled": False,
}

SIGNALS = {
    "event": "SAASignalsFound",
    "StarSystem": "Test System",
    "SystemAddress": 42,
    "BodyID": 3,
    "BodyName": "Test System 2 a",
    "Signals": [{"Type": "Biological", "Count": 3}, {"Type": "Geological", "Count": 1}],
    "Genuses": [{"Genus": "$Codex_Ent_Bacterial_Genus_Name;", "Count": 2}],
}


class ZmtpTests(unittest.TestCase):
    def test_parse_endpoint(self):
        self.assertEqual(zmtp.parse_endpoint("tcp://eddn.edcd.io:9500"), ("eddn.edcd.io", 9500))
        self.assertEqual(zmtp.parse_endpoint("localhost:9500"), ("localhost", 9500))
        with self.assertRaises(zmtp.ZmtpError):
            zmtp.parse_endpoint("udp://host:1")

    def test_encode_frame_short(self):
        frame = zmtp.encode_frame(b"abc")
        self.assertEqual(frame[0], 0)
        self.assertEqual(frame[1], 3)
        self.assertEqual(frame[2:], b"abc")

    def test_encode_frame_long(self):
        body = b"x" * 300
        frame = zmtp.encode_frame(body)
        self.assertTrue(frame[0] & zmtp.FLAG_LONG)
        self.assertEqual(int.from_bytes(frame[1:9], "big"), 300)
        self.assertEqual(frame[9:], body)

    def test_ping_pong(self):
        class FakeSock:
            def __init__(self) -> None:
                self.sent: list[bytes] = []

            def sendall(self, data: bytes) -> None:
                self.sent.append(data)

        subscriber = zmtp.ZmtpSubscriber("tcp://localhost:9500")
        fake = FakeSock()
        subscriber._sock = fake  # noqa: SLF001
        subscriber._handle_command(b"\x04PING\x00\x00ctx")  # noqa: SLF001
        self.assertEqual(fake.sent, [zmtp.encode_frame(b"\x04PONG\x00\x00ctx", command=True)])

    def test_greeting_size(self):
        self.assertEqual(len(zmtp.GREETING), 64)
        self.assertEqual(zmtp.GREETING[:2], b"\xff\x00")
        self.assertEqual(zmtp.GREETING[10:12], bytes([3, 1]))
        self.assertEqual(zmtp.GREETING[12:16], b"NULL")


class DecodeTests(unittest.TestCase):
    def test_decode_zlib(self):
        data = eddn.decode_message(envelope({"event": "Scan"}))
        assert data is not None
        self.assertEqual(data["message"]["event"], "Scan")

    def test_decode_plain_json(self):
        data = eddn.decode_message(json.dumps({"message": {"event": "Scan"}}).encode())
        assert data is not None
        self.assertEqual(data["message"]["event"], "Scan")

    def test_decode_broken(self):
        self.assertIsNone(eddn.decode_message(b"\x00\x01"))
        self.assertIsNone(eddn.decode_message(b""))

    def test_message_system(self):
        self.assertEqual(eddn.message_system({"StarSystem": "Sol", "SystemAddress": 1}), ("Sol", 1))
        self.assertEqual(eddn.message_system({"SystemName": "Sol"}), ("Sol", None))
        self.assertEqual(eddn.message_system({}), (None, None))


class FilterTests(unittest.TestCase):
    def test_empty_filter_blocks(self):
        flt = eddn.SetFilter()
        self.assertFalse(flt({"StarSystem": "Sol", "SystemAddress": 1}))

    def test_address_and_name(self):
        flt = eddn.SetFilter()
        flt.update(names={"Sol"}, addresses={42})
        self.assertTrue(flt({"SystemAddress": 42}))
        self.assertTrue(flt({"StarSystem": "sol"}))
        self.assertFalse(flt({"StarSystem": "Colonia", "SystemAddress": 9}))


class ListenerTests(unittest.TestCase):
    def test_handle_raw_filters(self):
        received: list[dict] = []
        flt = eddn.SetFilter()
        flt.update(addresses={42})
        listener = eddn.EddnListener(on_message=received.append, system_filter=flt)
        listener._handle_raw(envelope(SCAN))  # noqa: SLF001
        listener._handle_raw(envelope({"event": "Scan", "SystemAddress": 7}))  # noqa: SLF001
        listener._handle_raw(b"not json")  # noqa: SLF001
        self.assertEqual(len(received), 1)
        self.assertEqual(listener.stats["received"], 3)
        self.assertEqual(listener.stats["matched"], 1)


class ApplyTests(unittest.TestCase):
    def test_scan_creates_remote_body(self):
        system = System(address=42, name="Test System")
        self.assertTrue(remote.apply_eddn(system, SCAN))
        body = system.bodies[3]
        self.assertTrue(body.remote)
        self.assertEqual(body.source, "EDDN")
        self.assertTrue(body.landable)
        self.assertAlmostEqual(body.surface_gravity or 0, 5.6)
        self.assertEqual(body.atmosphere_type, "Neon")
        self.assertFalse(body.was_footfalled)
        self.assertIn("EDDN", system.remote_sources)

    def test_signals(self):
        system = System(address=42, name="Test System")
        self.assertTrue(remote.apply_eddn(system, SIGNALS))
        body = system.bodies[3]
        self.assertEqual(body.bio_signals, 3)
        self.assertEqual(body.geo_signals, 1)
        self.assertTrue(body.signals_known)
        self.assertTrue(body.dss_remote)
        self.assertFalse(body.dss_scanned)  # картографировали не мы
        self.assertIn("$Codex_Ent_Bacterial_Genus_Name;", body.genuses)

    def test_does_not_overwrite_local(self):
        system = System(address=42, name="Test System")
        system.bodies[3] = Body(body_id=3, name="Test System 2 a", planet_class="Rocky body", landable=True)
        remote.apply_eddn(system, SCAN)
        self.assertEqual(system.bodies[3].planet_class, "Rocky body")

    def test_other_system_ignored(self):
        system = System(address=99, name="Other")
        self.assertFalse(remote.apply_eddn(system, SCAN))
        self.assertEqual(system.bodies, {})


if __name__ == "__main__":
    unittest.main()
