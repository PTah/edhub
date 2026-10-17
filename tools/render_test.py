#!/usr/bin/env python3
"""Проверка отрисовки оверлея без игры: рисует HUD и сохраняет canvas.

  python3 tools/render_test.py [out.ps]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud import config, demo, hudmodel, journal  # noqa: E402
from edhud.overlay import Overlay  # noqa: E402


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/edhud_hud.ps")
    folder = config.app_dir() / "demo"
    demo.write_all(folder)
    state = journal.load_snapshot(folder)
    cfg = config.Config()
    overlay = Overlay(cfg)
    view = hudmodel.build_view(state, cfg, expanded=True)
    overlay._draw(view)
    overlay.root.update()
    overlay.canvas.postscript(file=str(out), colormode="color")
    overlay.destroy()
    text = out.read_text(encoding="latin-1", errors="replace")
    checks = ["HIP 36601", "DSS", "Icy", "Bacterium"]
    missing = [c for c in checks if c not in text]
    print(f"postscript: {out} ({out.stat().st_size} байт)")
    print("нет в отрисовке: " + ", ".join(missing) if missing else "все ключевые надписи нарисованы")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
