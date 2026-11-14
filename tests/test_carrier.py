# Created by nc.ai 1.2.11 on Papasha 2026-11-14 19:43:07
"""Тесты носителя: обратный отсчёт до прыжка и тритий."""
from __future__ import annotations

import sys
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud import model  # noqa: E402


def _iso_in(minutes: float) -> str:
    moment = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _state() -> model.GameState:
    state = model.GameState()
    state.system.name = "Origin"
    state.apply(
        {
            "timestamp": _iso_in(-30),
            "event": "CarrierStats",
            "CarrierID": 12345,
            "Callsign": "ABC-123",
            "Name": "BIG SHIP",
            "FuelLevel": 512,
            "FuelCapacity": 1000,
        }
    )
    return state


class CarrierModelTests(unittest.TestCase):
    def test_stats_give_fuel(self) -> None:
        state = _state()
        self.assertEqual(state.carrier.callsign, "ABC-123")
        self.assertEqual(state.carrier.fuel_level, 512.0)
        self.assertEqual(state.carrier.fuel_capacity, 1000.0)

    def test_deposit_updates_fuel(self) -> None:
        state = _state()
        state.apply({"timestamp": _iso_in(0), "event": "CarrierDepositFuel", "CarrierID": 12345, "Amount": 88, "Total": 600})
        self.assertEqual(state.carrier.fuel_level, 600.0)

    def test_jump_request_sets_countdown(self) -> None:
        state = _state()
        state.apply(
            {
                "timestamp": _iso_in(0),
                "event": "CarrierJumpRequest",
                "CarrierID": 12345,
                "SystemName": "Target",
                "DepartureTime": _iso_in(12),
            }
        )
        self.assertTrue(state.carrier.jump_pending)
        self.assertEqual(state.carrier.jump_dest_system, "Target")
        left = state.carrier.jump_remaining()
        assert left is not None
        self.assertAlmostEqual(left, 12 * 60, delta=90)

    def test_jump_done_or_cancelled_clears_countdown(self) -> None:
        state = _state()
        state.apply(
            {
                "timestamp": _iso_in(0),
                "event": "CarrierJumpRequest",
                "CarrierID": 12345,
                "SystemName": "Target",
                "DepartureTime": _iso_in(5),
            }
        )
        state.apply(
            {
                "timestamp": _iso_in(1),
                "event": "CarrierJumpCancelled",
                "CarrierID": 12345,
            }
        )
        self.assertFalse(state.carrier.jump_pending)
        self.assertIsNone(state.carrier.jump_remaining())

    def test_past_departure_gives_zero_not_negative(self) -> None:
        carrier = model.Carrier(jump_dest_system="Target", jump_departure=time.time() - 120)
        self.assertEqual(carrier.jump_remaining(), 0.0)


class CarrierWindowTests(unittest.TestCase):
    def test_header_shows_countdown_and_tritium(self) -> None:
        import tkinter as tk

        from edhud.mainwindow import MainWindow

        root_ = tk.Tk()
        root_.withdraw()
        window = MainWindow(root_)
        try:
            state = _state()
            state.apply(
                {
                    "timestamp": _iso_in(0),
                    "event": "CarrierJumpRequest",
                    "CarrierID": 12345,
                    "SystemName": "Target",
                    "DepartureTime": _iso_in(9),
                }
            )
            window.update_state(state)
            root_.update_idletasks()
            text = window.lbl_carrier_info.cget("text")
            self.assertIn("тритий", text)
            self.assertIn("512/1 000", text)
            self.assertIn("через", text)
            self.assertRegex(text, r"через \d+:\d\d")
        finally:
            window.destroy()
            root_.destroy()


if __name__ == "__main__":
    unittest.main()
