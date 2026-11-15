# Created by nc.ai 1.2.15 on Papasha 2026-11-15 16:22:57
"""Автопереключение вкладок: ручной выбор не должен ломать его навсегда."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("EDHUD_LANG", "ru")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud.model import GameState  # noqa: E402


class ManualTabTests(unittest.TestCase):
    def setUp(self) -> None:
        import tkinter as tk

        from edhud.mainwindow import MainWindow

        self.root = tk.Tk()
        self.root.withdraw()
        self.window = MainWindow(self.root)
        self.state = GameState()
        self.state.system.address = 1
        self.state.system.name = "Here"
        self.state.view_tab = "bodies"

    def tearDown(self) -> None:
        self.window.destroy()
        self.root.destroy()

    def jump(self, address: int, name: str) -> None:
        self.state.apply(
            {
                "event": "FSDJump",
                "StarSystem": name,
                "SystemAddress": address,
                "StarPos": [1.0, 2.0, 3.0],
                "JumpDist": 12.5,
            }
        )

    def test_manual_mining_tab_survives_ticks_but_not_a_jump(self):
        w = self.window
        w.update_state(self.state)
        w.win.update()
        w.nb.select(w.tab_mining)
        w.win.update()
        w._on_tab_changed()
        self.assertEqual(w._shown_tab, "mining")

        # пока прыжка нет — ручную вкладку никто не отбирает
        w.update_state(self.state)
        w.win.update()
        self.assertEqual(w.nb.select(), str(w.tab_mining))

        # прыгнули в новую систему — снова Bodies
        self.jump(2, "There")
        w.update_state(self.state)
        w.win.update()
        self.assertEqual(w.nb.select(), str(w.tab_bodies))
        self.assertEqual(w._shown_tab, "bodies")

    def test_jump_always_returns_to_bodies_even_with_route(self):
        w = self.window
        w.update_state(self.state)
        w.win.update()
        w.nb.select(w.tab_mining)
        w.win.update()
        w._on_tab_changed()
        # маршрут проложен: игра сама переключает на Route (см. model._on_fsdjump)
        self.state.view_tab = "route"
        w.update_state(self.state)
        w.win.update()
        self.assertEqual(w.nb.select(), str(w.tab_route))
        # после прыжка модель отдаёт Bodies — окно следует за ней, а не остаётся на «Добыче»
        self.jump(3, "Elsewhere")
        w.update_state(self.state)
        w.win.update()
        self.assertEqual(w.nb.select(), str(w.tab_bodies))


if __name__ == "__main__":
    unittest.main()
