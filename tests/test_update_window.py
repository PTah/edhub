# Created by nc.ai 1.2.15 on Papasha 2026-11-15 20:02:16
"""Окно загрузки обновления: отмена, скорость, положение на экране."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("EDHUD_LANG", "ru")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud import app as app_mod  # noqa: E402
from edhud import update as upd  # noqa: E402


class SpeedTests(unittest.TestCase):
    def test_speed_needs_elapsed_time(self):
        self.assertEqual(upd.speed_bps(0, 5.0), 0.0)
        self.assertEqual(upd.speed_bps(1000, 0.1), 0.0)
        self.assertAlmostEqual(upd.speed_bps(2_000_000, 2.0), 1_000_000.0)


class CancelTests(unittest.TestCase):
    def test_download_raises_and_removes_partial_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "EDHUD.zip"
            flag = {"cancel": False}
            chunks = {"count": 0}

            def fake_get(url, timeout, on_chunk):
                for _ in range(5):
                    on_chunk(b"x" * 1024, 5 * 1024)
                return 200, None, 5 * 1024

            def progress(done, total):
                chunks["count"] += 1
                if chunks["count"] >= 2:
                    flag["cancel"] = True  # пользователь нажал «Отменить»

            with mock.patch.object(upd.sys, "platform", "win32"), mock.patch.object(
                upd, "_winhttp_get", fake_get
            ):
                with self.assertRaises(upd.UpdateCancelled):
                    upd.download("https://example.com/x.zip", dest, progress=progress, cancel=lambda: flag["cancel"])

            self.assertFalse(dest.exists())
            self.assertFalse(dest.with_suffix(dest.suffix + ".part").exists())

    def test_download_without_cancel_writes_file(self):
        payload = b"z" * 4096
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "EDHUD.zip"

            def fake_get(url, timeout, on_chunk):
                on_chunk(payload, len(payload))
                return 200, None, len(payload)

            with mock.patch.object(upd.sys, "platform", "win32"), mock.patch.object(
                upd, "_winhttp_get", fake_get
            ):
                upd.download("https://example.com/x.zip", dest, progress=lambda d, t: None)

            self.assertEqual(dest.read_bytes(), payload)


class FakeWindow:
    """Минимальный двойник Toplevel для проверки геометрии."""

    def __init__(self, screen=(1920, 1080), parent=None, req=(430, 180)):
        self.screen = screen
        self.parent = parent
        self.req = req
        self.geometry_value = None
        self.shown = False

    def update_idletasks(self):
        return None

    def winfo_reqwidth(self):
        return self.req[0]

    def winfo_reqheight(self):
        return self.req[1]

    def winfo_screenwidth(self):
        return self.screen[0]

    def winfo_screenheight(self):
        return self.screen[1]

    def geometry(self, value=None):
        if value is not None:
            self.geometry_value = value
        return self.geometry_value

    def deiconify(self):
        self.shown = True

    def lift(self):
        return None

    def focus_force(self):
        return None


class FakeParent:
    def __init__(self, x, y, w, h, viewable=True):
        self.box = (x, y, w, h)
        self.viewable = viewable

    def winfo_viewable(self):
        return self.viewable

    def winfo_rootx(self):
        return self.box[0]

    def winfo_rooty(self):
        return self.box[1]

    def winfo_width(self):
        return self.box[2]

    def winfo_height(self):
        return self.box[3]


class PlacementTests(unittest.TestCase):
    def test_window_has_geometry_and_is_shown(self):
        win = FakeWindow()
        app_mod._place_update_window(win, None)
        self.assertIsNotNone(win.geometry_value)
        self.assertIn("430x180", win.geometry_value)
        self.assertTrue(win.shown)

    def test_window_placed_over_parent(self):
        win = FakeWindow()
        app_mod._place_update_window(win, FakeParent(500, 300, 900, 600))
        self.assertTrue(win.geometry_value.endswith("+735+440"), win.geometry_value)

    def test_window_clamped_to_screen(self):
        # родитель уехал за правый нижний край — окно всё равно должно быть видно
        win = FakeWindow(screen=(1280, 720))
        app_mod._place_update_window(win, FakeParent(3000, 2000, 100, 100))
        geometry = win.geometry_value
        self.assertIn("430x180", geometry)
        x, y = geometry.split("+")[1:]
        self.assertLessEqual(int(x) + 430, 1280)
        self.assertLessEqual(int(y) + 180, 720)

    def test_not_viewable_parent_centers_on_screen(self):
        win = FakeWindow()
        app_mod._place_update_window(win, FakeParent(0, 0, 100, 100, viewable=False))
        self.assertTrue(win.geometry_value.endswith("+745+300"), win.geometry_value)


if __name__ == "__main__":
    unittest.main()
