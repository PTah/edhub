# Edited by nc.ai 1.2.11 on Papasha 2026-11-14 19:18:16
"""Терминальный HUD: тот же вид, что в оверлее, но в консоли.

Полезно на macOS/Linux (игра там не идёт), для отладки и для демо-режима.
"""
from __future__ import annotations

import sys
import time

from .hudmodel import HudView, build_view

ANSI = {
    "text": "\033[97m",
    "fg": "\033[33m",
    "accent": "\033[96m",
    "ok": "\033[92m",
    "warn": "\033[93m",
    "gold": "\033[93m",
    "bad": "\033[91m",
    "dim": "\033[90m",
    "muted": "\033[37m",
}
RESET = "\033[0m"
CLEAR = "\033[2J\033[H"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"


def _paint(text: str, style: str) -> str:
    return f"{ANSI.get(style, ANSI['text'])}{text}{RESET}"


def progress_bar(view: HudView, width: int = 48) -> str:
    if not view.progress[1]:
        return _paint("·" * width, "dim")
    filled = int(round(view.fraction * width))
    return _paint("█" * filled, view.accent) + _paint("·" * (width - filled), "dim")


def render(view: HudView, width: int = 46) -> str:
    lines = [progress_bar(view, width)]
    for row in (view.route_row, view.body_row):
        lines.append("".join(_paint(seg.text, seg.style) for seg in row.segments))
    if view.alert:
        lines.append(_paint(f"! {view.alert}", "warn"))
    for row in view.detail:
        lines.append("".join(_paint(seg.text, seg.style) for seg in row.segments))
    return "\n".join(lines)


def run_tui(state, cfg, expanded: bool = True, interval: float = 0.3, once: bool = False) -> None:
    if not once:
        sys.stdout.write(HIDE_CURSOR)
    try:
        while True:
            view = build_view(state, cfg, expanded=expanded or cfg.expanded)
            frame = render(view)
            if once:
                sys.stdout.write(frame + "\n")
                return
            header = _paint(f" EDHUD · {state.cmdr or 'нет командира'} · {state.system.name or '—'} ", "dim")
            sys.stdout.write(CLEAR + header + "\n\n" + frame + "\n")
            sys.stdout.write(_paint("\n Ctrl-C — выход", "dim") + "\n")
            sys.stdout.flush()
            time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        if not once:
            sys.stdout.write(SHOW_CURSOR + "\n")
            sys.stdout.flush()
