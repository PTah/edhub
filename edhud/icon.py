# Edited by nc.ai 1.2.9 on new-admin-pc 2026-11-13 14:27:24
"""Иконка приложения: .ico для панели задач Windows, .png как запасной вариант."""
from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

from . import config, winapi

ICO_NAME = "edhud.ico"
PNG_NAME = "edhud.png"

WM_SETICON = 0x0080
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
SM_CXICON, SM_CYICON = 11, 12
SM_CXSMICON, SM_CYSMICON = 49, 50
ICON_SMALL, ICON_BIG = 0, 1

# HICON должны жить, пока живо окно: WM_SETICON не копирует ресурс.
_HANDLES: list[int] = []


def icon_path() -> Path | None:
    """Путь к .ico рядом с данными (в сборке — внутри _MEIPASS/data)."""
    path = config.data_dir() / ICO_NAME
    return path if path.exists() else None


def apply_icon(win: tk.Misc) -> None:
    """Поставить иконку окну и всем последующим окнам Tk.

    Tk на Windows применяет iconbitmap только к уже показанному окну, поэтому
    дополнительно ставим иконку через WM_SETICON — тогда она есть и у окна,
    которое ещё свернуто или создано до первого отображения.
    """
    path = icon_path()
    if path is not None:
        try:
            win.iconbitmap(str(path))
            win.iconbitmap(default=str(path))
        except tk.TclError:
            pass
        else:
            _set_win_icon(win, str(path))
            return
    png = config.data_dir() / PNG_NAME
    if not png.exists():
        return
    try:
        image = tk.PhotoImage(master=win, file=str(png))
        win.iconphoto(True, image)
    except tk.TclError:
        return
    setattr(win, "_edhud_icon", image)


def _set_win_icon(win: tk.Misc, path: str) -> None:
    if sys.platform != "win32":
        return
    try:
        hwnd = winapi.hwnd_of(win)
    except tk.TclError:
        return
    if not hwnd:
        return
    user32 = ctypes.windll.user32
    user32.LoadImageW.argtypes = [
        wintypes.HINSTANCE,
        wintypes.LPCWSTR,
        wintypes.UINT,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.restype = wintypes.LPARAM
    for kind, metric_x, metric_y, fallback in (
        (ICON_SMALL, SM_CXSMICON, SM_CYSMICON, 16),
        (ICON_BIG, SM_CXICON, SM_CYICON, 32),
    ):
        cx = user32.GetSystemMetrics(metric_x) or fallback
        cy = user32.GetSystemMetrics(metric_y) or fallback
        handle = user32.LoadImageW(None, path, IMAGE_ICON, cx, cy, LR_LOADFROMFILE)
        if not handle:
            continue
        user32.SendMessageW(wintypes.HWND(hwnd), WM_SETICON, kind, handle)
        _HANDLES.append(handle)
