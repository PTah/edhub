# Edited by nc.ai 1.2.11 on Papasha 2026-11-14 14:56:02
"""Диагностика флака Tk: как ведёт себя повторный Tk() в одном процессе.

Режимы:
    plain      — create/destroy, ссылка на root не держится
    keeprefs   — create/destroy, но объекты root остаются живыми в списке
    gc         — plain + gc.collect() перед каждым созданием

Запуск:
    python tools/tk_flake_probe.py plain 60
"""

from __future__ import annotations

import gc
import sys
import tkinter


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "plain"
    rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    kept: list[tkinter.Tk] = []
    fails = 0
    for index in range(rounds):
        if mode == "gc":
            gc.collect()
        try:
            root = tkinter.Tk()
            root.withdraw()
            root.destroy()
        except Exception as exc:  # noqa: BLE001 - диагностика
            fails += 1
            print(f"FAIL at {index} [{mode}]: {type(exc).__name__}: {str(exc).splitlines()[0][:120]}")
            break
        if mode == "keeprefs":
            kept.append(root)
        else:
            del root
    print(f"mode={mode} fails={fails} of {rounds}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
