"""Тесты базы сохранённых поясов и ПКМ в Bodies."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from edhud.belts import BeltStore, SavedBelt
from edhud.model import Body, GameState


class BeltStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "belts.json"
        self.store = BeltStore(self.path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_upsert_list_and_reload(self) -> None:
        belt = SavedBelt(
            system="Smojai ME-A c1-1",
            address=360542704906,
            body_id=51,
            body_name="Smojai ME-A c1-1 B 4",
            hotspots={"Musgravite": 2, "Alexandrite": 1, "Tritium": 4},
            planet_class="Sudarsky class I gas giant",
        )
        self.store.upsert(belt)
        self.assertEqual(len(self.store), 1)
        self.assertTrue(self.store.contains(360542704906, 51))
        rows = self.store.list()
        self.assertEqual(rows[0].system, "Smojai ME-A c1-1")
        # дороже по оценке раньше
        self.assertGreater(rows[0].estimate_cr(), 0)
        text = rows[0].minerals_label()
        self.assertLess(text.index("Musgravite"), text.index("Tritium"))

        again = BeltStore(self.path)
        self.assertEqual(len(again), 1)
        self.assertEqual(again.list()[0].hotspots.get("Musgravite"), 2)

    def test_remove(self) -> None:
        belt = SavedBelt(
            system="Test",
            address=1,
            body_id=2,
            body_name="Test 1",
            hotspots={"Alexandrite": 1},
        )
        self.store.upsert(belt)
        self.assertTrue(self.store.remove(belt.key()))
        self.assertEqual(len(self.store), 0)


class BeltSaveUiTests(unittest.TestCase):
    def test_save_body_belt_from_mainwindow(self) -> None:
        import tkinter as tk

        from edhud.mainwindow import MainWindow

        tmp = tempfile.TemporaryDirectory()
        try:
            store = BeltStore(Path(tmp.name) / "belts.json")
            root = tk.Tk()
            root.withdraw()
            window = MainWindow(root, belt_store=store)
            state = GameState()
            state.system.name = "Rich Ring"
            state.system.address = 42
            state.system.star_pos = (1.0, 2.0, 3.0)
            state.system.bodies[7] = Body(
                body_id=7,
                name="Rich Ring 2",
                planet_class="Sudarsky class II gas giant",
                has_rings=True,
                rings_mapped=True,
                hotspots={"Monazite": 1, "Alexandrite": 3},
            )
            window.update_state(state)
            window._save_body_belt(7)
            self.assertEqual(len(store), 1)
            saved = store.list()[0]
            self.assertEqual(saved.system, "Rich Ring")
            self.assertEqual(saved.hotspots.get("Alexandrite"), 3)
            self.assertEqual(saved.star_pos, [1.0, 2.0, 3.0])
            window.destroy()
            root.destroy()
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
