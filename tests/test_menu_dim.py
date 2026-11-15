# Created by nc.ai 1.2.15 on Papasha 2026-11-15 15:49:51
"""Панели прячутся под меню игры: карта, сервисы станции, Carrier Management."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("EDHUD_LANG", "ru")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud.model import GameState, menu_open  # noqa: E402


class MenuOpenTests(unittest.TestCase):
    def test_free_flight_keeps_panels(self):
        assert menu_open(0) is False
        assert menu_open(None) is False

    def test_fss_and_dss_keep_panels(self):
        # в FSS (9) и DSS/SAA (10) карточка био и радар нужны на экране
        assert menu_open(9) is False
        assert menu_open(10) is False

    def test_menus_dim_panels(self):
        for focus in (1, 2, 3, 4, 5, 6, 7, 8, 11):
            self.assertTrue(menu_open(focus), focus)

    def test_garbage_focus_is_not_menu(self):
        assert menu_open("") is False
        assert menu_open("нет") is False

    def test_music_track_dims_panels(self):
        """Carrier Management держит GuiFocus=0 — ловим его по треку из журнала."""
        for track in (
            "FleetCarrier_Managment",
            "GalaxyMap",
            "SystemMap",
            "Codex",
            "Squadrons",
            "GalacticPowers",
            "MainMenu",
            "Starport",
        ):
            self.assertTrue(menu_open(0, track), track)

    def test_flight_tracks_keep_panels(self):
        for track in (
            "Supercruise",
            "Exploration",
            "NoTrack",
            "NoInGameMusic",
            "SystemAndSurfaceScanner",  # DSS/FSS — панели нужны
            "DestinationFromHyperspace",
            "DestinationFromSupercruise",
            "Combat_Dogfight",
            "DockingComputer",
            "OnFoot",
            "GuardianSites",
            "",
            None,
        ):
            self.assertFalse(menu_open(0, track), track)

    def test_music_event_updates_state(self):
        state = GameState()
        state.apply({"event": "Music", "MusicTrack": "FleetCarrier_Managment"})
        self.assertEqual(state.music_track, "FleetCarrier_Managment")
        self.assertTrue(menu_open(state.status.gui_focus, state.music_track))
        state.apply({"event": "Music", "MusicTrack": "Supercruise"})
        self.assertFalse(menu_open(state.status.gui_focus, state.music_track))

    def test_junk_music_event_is_ignored(self):
        state = GameState()
        state.apply({"event": "Music", "MusicTrack": "GalaxyMap"})
        state.apply({"event": "Music"})
        self.assertEqual(state.music_track, "GalaxyMap")

    def test_shutdown_and_new_login_clear_track(self):
        state = GameState()
        state.apply({"event": "Music", "MusicTrack": "GalaxyMap"})
        state.apply({"event": "Shutdown"})
        self.assertEqual(state.music_track, "")
        state.apply({"event": "Music", "MusicTrack": "FleetCarrier_Managment"})
        state.apply({"event": "LoadGame", "Commander": "Tester", "FID": "F1"})
        self.assertEqual(state.music_track, "")
