"""Exclusive fullscreen: QUNS-детект и one-shot предупреждение."""
from __future__ import annotations

import ctypes
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from edhud import winapi
from edhud.app import App


class D3dExclusiveFullscreenTests(unittest.TestCase):
    def test_non_windows_returns_none(self):
        with patch.object(winapi, "IS_WINDOWS", False):
            self.assertIsNone(winapi.d3d_exclusive_fullscreen())

    def test_quns_running_d3d_full_screen(self):
        shell32 = MagicMock()

        def query(ptr):
            ctypes.cast(ptr, ctypes.POINTER(ctypes.c_int)).contents.value = (
                winapi.QUNS_RUNNING_D3D_FULL_SCREEN
            )
            return 0

        shell32.SHQueryUserNotificationState.side_effect = query
        with patch.object(winapi, "IS_WINDOWS", True), patch(
            "ctypes.windll.shell32", shell32, create=True
        ):
            self.assertTrue(winapi.d3d_exclusive_fullscreen())

    def test_quns_accepts_notifications(self):
        shell32 = MagicMock()

        def query(ptr):
            ctypes.cast(ptr, ctypes.POINTER(ctypes.c_int)).contents.value = (
                winapi.QUNS_ACCEPTS_NOTIFICATIONS
            )
            return 0

        shell32.SHQueryUserNotificationState.side_effect = query
        with patch.object(winapi, "IS_WINDOWS", True), patch(
            "ctypes.windll.shell32", shell32, create=True
        ):
            self.assertFalse(winapi.d3d_exclusive_fullscreen())

    def test_api_failure_returns_none(self):
        shell32 = MagicMock()
        shell32.SHQueryUserNotificationState.return_value = 0x80004005
        with patch.object(winapi, "IS_WINDOWS", True), patch(
            "ctypes.windll.shell32", shell32, create=True
        ):
            self.assertIsNone(winapi.d3d_exclusive_fullscreen())


class ExclusiveWarnSessionTests(unittest.TestCase):
    def _app(self, *, warn=True, voice=True, in_game=True, alive=True):
        app = App.__new__(App)
        app._fullscreen_warned = False
        app.cfg = SimpleNamespace(warn_fullscreen=warn, voice_enabled=voice)
        app.state = SimpleNamespace(in_game=in_game)
        app._game_alive = lambda: alive
        app.tray = MagicMock()
        app.voice = MagicMock()
        return app

    def test_notifies_once_per_exclusive_session(self):
        app = self._app()
        app.overlay = SimpleNamespace(fullscreen=True)
        app._on_exclusive_fullscreen(True)
        app._on_exclusive_fullscreen(True)
        self.assertEqual(app.tray.notify.call_count, 1)
        self.assertEqual(app.voice.speak.call_count, 1)
        app._on_exclusive_fullscreen(False)
        self.assertFalse(app._fullscreen_warned)
        app.overlay.fullscreen = True
        app._on_exclusive_fullscreen(True)
        self.assertEqual(app.tray.notify.call_count, 2)
        self.assertEqual(app.voice.speak.call_count, 2)

    def test_skips_when_disabled_or_not_in_game(self):
        app = self._app(warn=False)
        app.overlay = SimpleNamespace(fullscreen=True)
        app._on_exclusive_fullscreen(True)
        app.tray.notify.assert_not_called()

        app = self._app(in_game=False)
        app.overlay = SimpleNamespace(fullscreen=True)
        app._on_exclusive_fullscreen(True)
        app.tray.notify.assert_not_called()

        app = self._app(alive=False)
        app.overlay = SimpleNamespace(fullscreen=True)
        app._on_exclusive_fullscreen(True)
        app.tray.notify.assert_not_called()

    def test_retries_after_game_becomes_alive(self):
        app = self._app(in_game=False)
        app.overlay = SimpleNamespace(fullscreen=True)
        app._on_exclusive_fullscreen(True)
        app.tray.notify.assert_not_called()
        self.assertFalse(app._fullscreen_warned)
        app.state.in_game = True
        app._maybe_warn_exclusive_fullscreen()
        app.tray.notify.assert_called_once()

    def test_voice_off_still_trays(self):
        app = self._app(voice=False)
        app.overlay = SimpleNamespace(fullscreen=True)
        app._on_exclusive_fullscreen(True)
        app.tray.notify.assert_called_once()
        app.voice.speak.assert_not_called()


class TrayNotifyPayloadTests(unittest.TestCase):
    def test_notify_queues_pending_and_posts(self):
        from edhud import tray as tray_mod

        icon = tray_mod.TrayIcon.__new__(tray_mod.TrayIcon)
        icon.available = True
        icon._hwnd = 42
        icon._nid = tray_mod.NOTIFYICONDATA()
        icon._pending_notify = None
        icon._notify_lock = __import__("threading").Lock()
        with patch("ctypes.windll.user32") as user32:
            user32.PostMessageW.return_value = 1
            ok = tray_mod.TrayIcon.notify(icon, "Title", "Body text", timeout_ms=5000)
        self.assertTrue(ok)
        self.assertEqual(icon._pending_notify, ("Title", "Body text", 5000))
        user32.PostMessageW.assert_called_once()
        self.assertEqual(user32.PostMessageW.call_args[0][1], tray_mod.WM_TRAY_NOTIFY)


if __name__ == "__main__":
    unittest.main()
