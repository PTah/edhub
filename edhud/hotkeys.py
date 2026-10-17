"""Глобальные горячие клавиши (только Windows).

RegisterHotKey + собственный message loop в фоновом потоке: оверлей не
забирает фокус у игры, но реагирует на F8/F9/F10/F12.
"""
from __future__ import annotations

import sys
import threading
from typing import Callable

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

VK = {"F7": 0x76, "F8": 0x77, "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B}
VK_F12 = 0x7B


class Hotkeys(threading.Thread):
    def __init__(self, bindings: dict[int, Callable[[], None]]) -> None:
        super().__init__(name="edhud-hotkeys", daemon=True)
        self.bindings = bindings
        self.available = sys.platform == "win32"
        self._thread_id: int | None = None
        self._ready = threading.Event()

    def start(self) -> bool:  # type: ignore[override]
        if not self.available:
            return False
        super().start()
        self._ready.wait(2.0)
        return bool(self._ready.is_set())

    def stop(self) -> None:
        if not self.available or self._thread_id is None:
            return
        import ctypes

        ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

    def run(self) -> None:  # pragma: no cover - только Windows
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()
        registered = []
        for vk in self.bindings:
            if user32.RegisterHotKey(None, vk, 0, vk):
                registered.append(vk)
        self._ready.set()
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                if msg.message == WM_HOTKEY:
                    callback = self.bindings.get(int(msg.wParam))
                    if callback:
                        try:
                            callback()
                        except Exception:
                            pass
        finally:
            for vk in registered:
                user32.UnregisterHotKey(None, vk)
