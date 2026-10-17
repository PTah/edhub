# Created by nc.ai 0.8.8.0 on macbook 2026-10-17 20:12:54
"""Windows-специфика оверлея: DPI, сквозной режим, «поверх всех» и fullscreen.

Эксклюзивный полноэкранный режим DirectX на Windows не даёт рисовать поверх себя
никаким сторонним окнам (это ограничение драйвера, а не наша недоработка).
Что можно и что сделано:
  * окно помечается `WS_EX_TOPMOST` и удерживается поверх каждые 2 секунды —
    игра/система иногда сбрасывают topmost, и оверлей «пропадает»;
  * `WS_EX_NOACTIVATE` — клики и фокус не забираются у игры;
  * `WS_EX_TRANSPARENT` — сквозной режим мыши;
  * DPI-awareness (Per-Monitor v2) — на 125/150 % масштабе шрифт не мылится;
  * если в фокусе полноэкранное окно игры, HUD показывает подсказку переключиться
    в Borderless (Alt+Enter) — это единственный надёжный способ видеть оверлей.
"""
from __future__ import annotations

import ctypes
import sys
import threading
from typing import Callable

IS_WINDOWS = sys.platform == "win32"

GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_CAPTION = 0x00C00000
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
HWND_TOPMOST = -1
GA_ROOT = 2
MONITOR_DEFAULTTONEAREST = 2
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", ctypes.c_ulong),
    ]


def enable_dpi_awareness() -> bool:
    """Вызывать до создания окна Tk — иначе интерфейс будет мыльным."""
    if not IS_WINDOWS:
        return False
    try:
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(
            ctypes.c_void_p(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
        ):
            return True
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return True
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
        return True
    except (AttributeError, OSError):
        return False


def hwnd_of(widget) -> int:
    """HWND верхнего уровня для tkinter-виджета."""
    if not IS_WINDOWS:
        return 0
    try:
        user32 = ctypes.windll.user32
        return int(user32.GetAncestor(widget.winfo_id(), GA_ROOT))
    except Exception:
        try:
            return int(ctypes.windll.user32.GetParent(widget.winfo_id()))
        except Exception:
            return 0


def apply_overlay_styles(hwnd: int, click_through: bool, topmost: bool = True) -> bool:
    """Сквозной, неактивируемый, всегда сверху. Возвращает True при успехе."""
    if not IS_WINDOWS or not hwnd:
        return False
    try:
        user32 = ctypes.windll.user32
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style |= WS_EX_LAYERED | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        if click_through:
            style |= WS_EX_TRANSPARENT
        else:
            style &= ~WS_EX_TRANSPARENT
        if topmost:
            style |= WS_EX_TOPMOST
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        user32.SetWindowPos(
            hwnd,
            HWND_TOPMOST if topmost else 0,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )
        return True
    except Exception:
        return False


def keep_topmost(hwnd: int) -> bool:
    """Повторно «прибивает» окно поверх всех (игра сбрасывает topmost при старте)."""
    if not IS_WINDOWS or not hwnd:
        return False
    try:
        user32 = ctypes.windll.user32
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if not style & WS_EX_TOPMOST:
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_TOPMOST)
        user32.SetWindowPos(
            hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW
        )
        return True
    except Exception:
        return False


def foreground_fullscreen(exclude_hwnd: int = 0) -> bool | None:
    """Полноэкранное ли окно в фокусе (None — не Windows или нет окна)."""
    if not IS_WINDOWS:
        return None
    try:
        user32 = ctypes.windll.user32
        hwnd = int(user32.GetForegroundWindow() or 0)
        if not hwnd or hwnd == exclude_hwnd:
            return None
        if user32.IsZoomed(hwnd):
            return False
        rect = _RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return None
        mon = info.rcMonitor
        covers = (
            rect.left <= mon.left
            and rect.top <= mon.top
            and rect.right >= mon.right
            and rect.bottom >= mon.bottom
        )
        if not covers:
            return False
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        # безрамочное окно на весь монитор — либо borderless, либо exclusive
        return not bool(style & WS_CAPTION)
    except Exception:
        return None


class TopmostKeeper(threading.Thread):
    """Фоновый «сторож» topmost + детектор полноэкранного режима игры."""

    def __init__(
        self,
        hwnd_provider: Callable[[], int],
        interval: float = 2.0,
        on_fullscreen: Callable[[bool | None], None] | None = None,
    ) -> None:
        super().__init__(name="edhud-topmost", daemon=True)
        self.hwnd_provider = hwnd_provider
        self.interval = interval
        self.on_fullscreen = on_fullscreen
        self.fullscreen: bool | None = None
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                hwnd = self.hwnd_provider()
                if hwnd:
                    keep_topmost(hwnd)
                    state = foreground_fullscreen(exclude_hwnd=hwnd)
                    if state != self.fullscreen:
                        self.fullscreen = state
                        if self.on_fullscreen is not None:
                            self.on_fullscreen(state)
            except Exception:
                pass
            self._stop.wait(self.interval)
