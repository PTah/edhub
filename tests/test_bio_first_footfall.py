# Created by nc.ai 1.2.15 on Papasha 2026-11-15 20:37:29
"""Метки первого шага (first footfall) в окне «Биосигналы»."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("EDHUD_LANG", "ru")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud import hudmodel  # noqa: E402
from edhud.model import Body, GameState  # noqa: E402


def make_state(was_footfalled: bool = False, landable: bool = True) -> GameState:
    state = GameState()
    state.system.name = "Alpha"
    state.system.address = 1
    state.system.bodies[1] = Body(
        body_id=1,
        name="Alpha 1",
        bio_signals=2,
        signals_known=True,
        signals_local=True,
        landable=landable,
        was_footfalled=was_footfalled,
        distance_ls=1200.0,
    )
    return state


class FirstFootfallTests(unittest.TestCase):
    def test_free_first_footfall_is_marked(self):
        board = hudmodel.build_bio_board(make_state(was_footfalled=False))
        assert board is not None
        text = "\n".join(board.plain())
        self.assertIn("FF+", text)
        self.assertIn("первый шаг свободен", text)  # сноска-легенда

    def test_taken_first_footfall_is_marked(self):
        board = hudmodel.build_bio_board(make_state(was_footfalled=True))
        assert board is not None
        header = "\n".join(board.plain()).splitlines()[1]  # строка тела: «1 ×2 FF …»
        self.assertIn("FF", header)
        self.assertNotIn("FF+", header)

    def test_gas_giant_has_no_marker(self):
        board = hudmodel.build_bio_board(make_state(landable=False))
        assert board is not None
        text = "\n".join(board.plain())
        self.assertNotIn("FF", text)

    def test_focus_card_title_has_marker(self):
        state = make_state(was_footfalled=False)
        state.status.gui_focus = 9  # FSS: карточка выбранного тела
        state.last_fss_body_id = 1
        board = hudmodel.build_bio_board(state)
        assert board is not None
        self.assertIn("FF+", board.title)


if __name__ == "__main__":
    unittest.main()
