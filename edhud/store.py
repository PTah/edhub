"""Кэш просканированных систем на диске.

Журнал игры содержит только текущую сессию, поэтому данные о телах/биологии
переживают перезапуск (как SystemData в SrvSurvey): одна JSON-ка на систему.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import config
from .model import System


class SystemStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else config.app_dir() / "systems"

    def path(self, address: int) -> Path:
        return self.root / f"{address}.json"

    def load(self, address: int | None, name: str | None = None) -> System | None:
        if not address:
            return None
        try:
            data = json.loads(self.path(address).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if name and data.get("name") and data["name"] != name:
            return None
        try:
            return System.from_persist(data)
        except (TypeError, ValueError, KeyError):
            return None

    def save(self, system: System) -> bool:
        if not system.address or not system.bodies:
            return False
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            self.path(system.address).write_text(
                json.dumps(system.to_persist(), ensure_ascii=False), encoding="utf-8"
            )
            return True
        except OSError:
            return False
