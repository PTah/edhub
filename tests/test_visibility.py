# Created by nc.ai 1.2.15 on Papasha 2026-11-15 18:15:20
"""Панели только в игре и только в космосе: вне игры — прячем, на планете — глушим."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("EDHUD_LANG", "ru")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud.config import Config  # noqa: E402
from edhud.model import (  # noqa: E402
    FLAG_DOCKED,
    FLAG_IN_SRV,
    FLAG_LANDED,
    GameState,
)
from edhud.overlay import MENU_ALPHA, Overlay  # noqa: E402

LOAD_GAME = {"event": "LoadGame", "Commander": "Tester", "FID": "F1"}


class ModelVisibilityTests(unittest.TestCase):
    def test_not_running_means_not_in_game(self):
        state = GameState()
        self.assertFalse(state.in_game)
        self.assertFalse(state.in_space)

    def test_load_game_and_shutdown(self):
        state = GameState()
        state.apply(LOAD_GAME)
        self.assertTrue(state.in_game)
        self.assertTrue(state.in_space)
        state.apply({"event": "Shutdown"})
        self.assertFalse(state.in_game)

    def test_main_menu_music_is_not_in_game(self):
        state = GameState()
        state.apply(LOAD_GAME)
        state.apply({"event": "Music", "MusicTrack": "MainMenu"})
        self.assertFalse(state.in_game)
        state.apply({"event": "Music", "MusicTrack": "Supercruise"})
        self.assertTrue(state.in_game)

    def test_landed_and_srv_are_not_space(self):
        state = GameState()
        state.apply(LOAD_GAME)
        state.apply_status({"Flags": FLAG_LANDED})
        self.assertTrue(state.grounded)
        self.assertFalse(state.in_space)
        state.apply_status({"Flags": FLAG_IN_SRV})
        self.assertTrue(state.grounded)
        state.apply_status({"Flags": 0})
        self.assertFalse(state.grounded)
        self.assertTrue(state.in_space)

    def test_docked_is_not_space(self):
        state = GameState()
        state.apply(LOAD_GAME)
        state.apply_status({"Flags": FLAG_DOCKED})
        self.assertFalse(state.in_space)
        self.assertFalse(state.grounded)


class FakeRoot:
    def __init__(self) -> None:
        self.alpha = None

    def attributes(self, _name, value=None):
        if value is not None:
            self.alpha = float(value)
        return self.alpha


class FakeBio:
    def __init__(self) -> None:
        self._parent_visible = True
        self.dim = False

    def set_parent_visible(self, visible) -> None:
        self._parent_visible = bool(visible)

    def set_dim(self, dim) -> None:
        self.dim = bool(dim)


class OverlayVisibilityTests(unittest.TestCase):
    def make(self) -> SimpleNamespace:
        overlay = SimpleNamespace(
            root=FakeRoot(),
            bio=FakeBio(),
            cfg=Config(),
            _visible=True,
            _docked=False,
            _planet_dim=False,
            _menu_dim=False,
            _in_game=True,
            _grounded=False,
            _last_alpha=0,
        )
        overlay.apply_opacity = lambda: Overlay.apply_opacity(overlay)
        return overlay

    def test_in_space_uses_config_alpha(self):
        overlay = self.make()
        Overlay.apply_opacity(overlay)
        self.assertAlmostEqual(overlay.root.alpha, float(overlay.cfg.opacity))
        self.assertTrue(overlay.bio._parent_visible)

    def test_not_in_game_hides_hud_and_bio(self):
        overlay = self.make()
        Overlay.set_in_game(overlay, False)
        self.assertEqual(overlay.root.alpha, 0.0)
        self.assertFalse(overlay.bio._parent_visible)

    def test_grounded_dims_but_keeps_bio(self):
        overlay = self.make()
        Overlay.set_grounded(overlay, True)
        self.assertAlmostEqual(overlay.root.alpha, MENU_ALPHA)
        self.assertTrue(overlay.bio._parent_visible)

    def test_back_to_space_restores_alpha(self):
        overlay = self.make()
        Overlay.set_grounded(overlay, True)
        Overlay.set_grounded(overlay, False)
        self.assertAlmostEqual(overlay.root.alpha, float(overlay.cfg.opacity))

    def test_first_call_hides_everything(self):
        """На старте состояние неизвестно — первый set_in_game обязан примениться."""
        overlay = self.make()
        overlay._in_game = None
        self.assertTrue(overlay.bio._parent_visible)
        Overlay.set_in_game(overlay, False)
        self.assertEqual(overlay.root.alpha, 0.0)
        self.assertFalse(overlay.bio._parent_visible)


class StatusFreshnessTests(unittest.TestCase):
    def test_status_mtime_is_exposed(self):
        from edhud.journal import JournalWatcher

        watcher = JournalWatcher.__new__(JournalWatcher)  # без запуска потока
        watcher._status_mtime = 123.0
        self.assertEqual(watcher.status_mtime, 123.0)


if __name__ == "__main__":
    unittest.main()
