"""Иконка в системном трее Windows (Shell_NotifyIcon, без внешних пакетов)."""
from __future__ import annotations

import ctypes
import sys
import threading
from ctypes import wintypes
from pathlib import Path
from typing import Callable

from . import config

IS_WINDOWS = sys.platform == "win32"

NIM_ADD = 0x00000000
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_SHOWTIP = 0x00000080
WM_APP = 0x8000
WM_TRAY = WM_APP + 1
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_LBUTTONDBLCLK = 0x0203
WM_COMMAND = 0x0111
WM_NULL = 0x0000
WM_DESTROY = 0x0002
WM_QUIT = 0x0012
IDI_APPLICATION = 32512
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
LR_DEFAULTSIZE = 0x0040
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
MF_STRING = 0x0000
MF_SEPARATOR = 0x0800
MF_CHECKED = 0x0008
WS_POPUP = 0x80000000
WS_EX_TOOLWINDOW = 0x00000080

ID_TOGGLE_VISIBLE = 1001
ID_TOGGLE_MAIN = 1002
ID_TOGGLE_EXPANDED = 1003
ID_TOGGLE_CLICK = 1004
ID_OPEN_SPANSH = 1005
ID_OPEN_EDSM = 1006
ID_OPEN_MAP = 1007
ID_SETTINGS = 1008
ID_OPEN_CONFIG = 1009
ID_QUIT = 1099

# 64-bit: указатели, не c_long
HWND = ctypes.c_void_p
LRESULT = ctypes.c_ssize_t
WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t
HINSTANCE = ctypes.c_void_p
HICON = ctypes.c_void_p
HMENU = ctypes.c_void_p

WNDPROC = ctypes.WINFUNCTYPE(LRESULT, HWND, wintypes.UINT, WPARAM, LPARAM)


class NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", HICON),
        ("szTip", wintypes.WCHAR * 128),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", HINSTANCE),
        ("hIcon", HICON),
        ("hCursor", ctypes.c_void_p),
        ("hbrBackground", ctypes.c_void_p),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class TrayIcon(threading.Thread):
    """Фоновый поток со скрытым окном и иконкой в трее."""

    def __init__(
        self,
        on_command: Callable[[int], None],
        tip: str = "EDHUD",
        icon_path: Path | None = None,
        state_provider: Callable[[], dict] | None = None,
    ) -> None:
        super().__init__(name="edhud-tray", daemon=True)
        self.on_command = on_command
        self.tip = tip[:127]
        self.icon_path = icon_path or (config.data_dir() / "edhud.ico")
        self.state_provider = state_provider
        self.available = IS_WINDOWS
        self._ready = threading.Event()
        self._hwnd = None
        self._thread_id: int | None = None
        self._hicon = None
        self._nid = None
        self._wndproc = WNDPROC(self._on_wndproc)

    def start(self) -> bool:  # type: ignore[override]
        if not self.available:
            return False
        super().start()
        return bool(self._ready.wait(3.0))

    def stop(self) -> None:
        if not self.available or self._thread_id is None:
            return
        user32 = ctypes.windll.user32
        if self._hwnd:
            user32.PostMessageW(self._hwnd, WM_QUIT, 0, 0)
        user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

    def run(self) -> None:  # pragma: no cover - только Windows
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        shell32 = ctypes.windll.shell32

        user32.DefWindowProcW.argtypes = [HWND, wintypes.UINT, WPARAM, LPARAM]
        user32.DefWindowProcW.restype = LRESULT
        kernel32.GetModuleHandleW.restype = HINSTANCE
        user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
        user32.RegisterClassW.restype = wintypes.ATOM
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            HWND,
            HMENU,
            HINSTANCE,
            ctypes.c_void_p,
        ]
        user32.CreateWindowExW.restype = HWND
        user32.LoadImageW.restype = HICON

        self._thread_id = kernel32.GetCurrentThreadId()

        class_name = "EDHUDTrayClass"
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wndproc
        wc.hInstance = HINSTANCE(kernel32.GetModuleHandleW(None))
        wc.lpszClassName = class_name
        user32.RegisterClassW(ctypes.byref(wc))

        # скрытое popup-окно (HWND_MESSAGE на части Python/ctypes даёт err 1400)
        self._hwnd = user32.CreateWindowExW(
            WS_EX_TOOLWINDOW,
            class_name,
            "EDHUDTray",
            WS_POPUP,
            0,
            0,
            0,
            0,
            None,
            None,
            wc.hInstance,
            None,
        )
        if not self._hwnd:
            self._ready.set()
            return

        self._hicon = self._load_icon()
        nid = NOTIFYICONDATA()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
        nid.hWnd = self._hwnd
        nid.uID = 1
        # NIF_SHOWTIP требует расширенную структуру и на части систем иконку просто не ставит.
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = self._hicon
        nid.szTip = self.tip
        self._nid = nid
        shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATA)]
        shell32.Shell_NotifyIconW.restype = wintypes.BOOL
        if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)):
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
            nid.hIcon = self._load_icon()
            self._hicon = nid.hIcon
            shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
        user32.RegisterWindowMessageW.restype = wintypes.UINT
        self._taskbar_created = int(user32.RegisterWindowMessageW("TaskbarCreated") or 0)
        self._ready.set()

        msg = wintypes.MSG()
        try:
            while True:
                code = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if code == 0:
                    break
                if code < 0:
                    import time

                    time.sleep(0.05)
                    continue
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            if self._nid is not None:
                shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
            if self._hicon:
                user32.DestroyIcon(self._hicon)
            if self._hwnd:
                user32.DestroyWindow(self._hwnd)

    def _load_icon(self):
        user32 = ctypes.windll.user32
        user32.LoadImageW.argtypes = [
            HINSTANCE,
            wintypes.LPCWSTR,
            wintypes.UINT,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        user32.LoadImageW.restype = HICON
        user32.LoadIconW.argtypes = [HINSTANCE, ctypes.c_void_p]
        user32.LoadIconW.restype = HICON
        path = str(Path(self.icon_path).resolve()) if self.icon_path else ""
        if path and Path(path).exists():
            handle = user32.LoadImageW(None, path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)
            if handle:
                return handle
            handle = user32.LoadImageW(None, path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
            if handle:
                return handle
        return user32.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))

    def _on_wndproc(self, hwnd, msg, wparam, lparam):  # noqa: ANN001
        user32 = ctypes.windll.user32
        shell32 = ctypes.windll.shell32
        if msg == getattr(self, "_taskbar_created", 0) and self._nid is not None:
            shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self._nid))
            return 0
        if msg == WM_TRAY:
            if lparam in (WM_RBUTTONUP, WM_LBUTTONUP):
                self._popup_menu()
            elif lparam == WM_LBUTTONDBLCLK:
                self._fire(ID_TOGGLE_VISIBLE)
            return 0
        if msg == WM_COMMAND:
            self._fire(int(wparam) & 0xFFFF)
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _fire(self, command_id: int) -> None:
        try:
            self.on_command(command_id)
        except Exception:
            pass

    def _popup_menu(self) -> None:
        user32 = ctypes.windll.user32
        user32.CreatePopupMenu.restype = HMENU
        menu = user32.CreatePopupMenu()
        state = self.state_provider() if self.state_provider else {}
        visible = bool(state.get("visible", True))
        main_visible = bool(state.get("main_visible", False))
        expanded = bool(state.get("expanded", False))
        click_through = bool(state.get("click_through", True))

        def item(cid: int, text: str, checked: bool = False) -> None:
            flags = MF_STRING | (MF_CHECKED if checked else 0)
            user32.AppendMenuW(menu, flags, cid, text)

        item(ID_TOGGLE_VISIBLE, "Показать оверлей" if not visible else "Скрыть оверлей", visible)
        item(ID_TOGGLE_MAIN, "Окно EDHUD (Route / Bodies)", main_visible)
        item(ID_TOGGLE_EXPANDED, "Подробности (F8)", expanded)
        item(ID_TOGGLE_CLICK, "Сквозной режим мыши (F9)", click_through)
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        item(ID_OPEN_SPANSH, "Система на Spansh…")
        item(ID_OPEN_EDSM, "Система на EDSM…")
        item(ID_OPEN_MAP, "Галактическая карта Spansh…")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        item(ID_SETTINGS, "Настройки…")
        item(ID_OPEN_CONFIG, "Папка настроек и кэша…")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        item(ID_QUIT, "Выход (F12)")

        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(self._hwnd)
        cmd = user32.TrackPopupMenu(
            menu,
            TPM_RIGHTBUTTON | TPM_RETURNCMD,
            pt.x,
            pt.y,
            0,
            self._hwnd,
            None,
        )
        user32.DestroyMenu(menu)
        user32.PostMessageW(self._hwnd, WM_NULL, 0, 0)
        if cmd:
            self._fire(int(cmd))
