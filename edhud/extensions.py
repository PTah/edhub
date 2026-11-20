"""Необязательные локальные расширения.

Если в каталоге настроек есть ``private/ext.py`` с функцией ``create(app)``,
программа подключает его и показывает вкладку в окне «Сводка». Нет файла —
нет вкладки и нет никакого кода расширения.

Объект расширения: ``tab_title`` (str), ``build_tab(parent, colors, set_title)``,
необязательные ``on_show()`` и ``stop()``.
"""
from __future__ import annotations

import importlib.util
import sys
import traceback
from pathlib import Path

from . import config


def private_dir() -> Path:
    return config.app_dir() / "private"


def _log(text: str) -> None:
    try:
        with open(config.app_dir() / "edhud.log", "a", encoding="utf-8") as fh:
            fh.write(text.rstrip() + "\n")
    except OSError:
        pass


def load(app, folder: Path | None = None) -> list:
    folder = folder or private_dir()
    entry = folder / "ext.py"
    if not entry.is_file():
        return []
    try:
        if str(folder) not in sys.path:
            sys.path.insert(0, str(folder))
        spec = importlib.util.spec_from_file_location("edhud_private_ext", entry)
        if spec is None or spec.loader is None:
            return []
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        ext = module.create(app)
    except Exception:  # noqa: BLE001 — расширение не должно ронять программу
        _log("extension load failed:\n" + traceback.format_exc())
        return []
    return [ext] if ext is not None else []


def stop_all(extensions: list) -> None:
    for ext in extensions:
        try:
            stop = getattr(ext, "stop", None)
            if callable(stop):
                stop()
        except Exception:  # noqa: BLE001
            _log("extension stop failed:\n" + traceback.format_exc())
