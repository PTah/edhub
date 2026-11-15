# Created by nc.ai 1.2.15 on Papasha 2026-11-15 15:49:51
"""Панели прячутся под меню игры: карта, сервисы станции, Carrier Management."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud.model import menu_open  # noqa: E402


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
