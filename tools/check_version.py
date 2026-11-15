# Created by nc.ai 1.2.15 on Papasha 2026-11-15 11:22:52
"""Сверка версии программы и версии сборки.

Автообновление сравнивает `edhud.__version__` (её видит программа и показывает
в трее) с тегом последнего релиза на GitHub, а установщик и имена архивов берут
версию из `pyproject.toml`. Если они разошлись, приложение либо вечно считает
себя старым, либо не видит обновлений — поэтому сборка падает сразу.

Запускается из build_windows.bat перед PyInstaller.
"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    build_version = str(data["project"]["version"])
    from edhud import __version__ as code_version

    if build_version != code_version:
        print(f"Version mismatch: pyproject.toml={build_version} edhud/__init__.py={code_version}")
        print("Bump BOTH before building: auto-update compares edhud.__version__ with the GitHub tag.")
        return 1
    print(f"Version {code_version} OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
