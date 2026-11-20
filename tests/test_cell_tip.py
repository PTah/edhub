"""Подсказки ячеек сводки не остаются на экране после ухода курсора."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tkinter as tk  # noqa: E402

from edhud.mainwindow import _CellTip  # noqa: E402


class CellTipTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.geometry("300x120+20+20")
        self.a = tk.Label(self.root, text="a")
        self.b = tk.Label(self.root, text="b")
        self.a.pack()
        self.b.pack()
        self.root.update()

    def tearDown(self) -> None:
        _CellTip.hide_active()
        self.root.destroy()

    def test_hides_when_pointer_left_the_cell(self) -> None:
        tip = _CellTip(self.a, text="Predicted")
        tip._pointer_over_sources = lambda: True  # type: ignore[method-assign]
        tip._show()
        self.assertIsNotNone(tip._tip)
        tip._pointer_over_sources = lambda: False  # type: ignore[method-assign]
        tip._hide_if_outside()
        self.assertIsNone(tip._tip)
        self.assertIsNone(_CellTip._active)

    def test_second_tip_closes_the_first(self) -> None:
        first = _CellTip(self.a, text="one")
        second = _CellTip(self.b, text="two")
        first._pointer_over_sources = lambda: True  # type: ignore[method-assign]
        second._pointer_over_sources = lambda: True  # type: ignore[method-assign]
        first._show()
        stale = first._tip
        second._show()
        self.assertIsNone(first._tip)
        self.assertFalse(stale.winfo_exists())
        self.assertIs(second._tip, _CellTip._active and second._tip)
        self.assertIs(_CellTip._active, second)


if __name__ == "__main__":
    unittest.main()
