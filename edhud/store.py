"""Кэш просканированных систем на диске.

Журнал игры содержит только текущую сессию, поэтому данные о телах/биологии
переживают перезапуск (как SystemData в SrvSurvey): одна JSON-ка на систему.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

from . import config
from .model import System

_HEAD_NAME = re.compile(r'"name":\s*("(?:[^"\\]|\\.)*")')
_HEAD_BYTES = 600


class SystemStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else config.app_dir() / "systems"
        # вызывается после успешной записи (состав системы → колонка «Тела» маршрута)
        self.on_save: Callable[[System], None] | None = None
        self._names: dict[str, int] | None = None

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

    def find_address(self, name: str | None) -> int | None:
        """Адрес системы в кэше по имени (индекс строится один раз по началу файлов)."""
        key = (name or "").strip().lower()
        if not key:
            return None
        if self._names is None:
            self._names = self._build_names()
        return self._names.get(key)

    def _build_names(self) -> dict[str, int]:
        found: dict[str, int] = {}
        try:
            paths = list(self.root.glob("*.json"))
        except OSError:
            return found
        for path in paths:
            try:
                address = int(path.stem)
                with path.open("rb") as handle:
                    head = handle.read(_HEAD_BYTES).decode("utf-8", errors="replace")
            except (OSError, ValueError):
                continue
            match = _HEAD_NAME.search(head)
            if not match:
                continue
            try:
                found[json.loads(match.group(1)).strip().lower()] = address
            except (json.JSONDecodeError, AttributeError):
                continue
        return found

    def save(self, system: System) -> bool:
        if not system.address or not system.bodies:
            return False
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            self.path(system.address).write_text(
                json.dumps(system.to_persist(), ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            return False
        if self._names is not None and system.name:
            self._names[system.name.strip().lower()] = int(system.address)
        if self.on_save is not None:
            try:
                self.on_save(system)
            except Exception:
                pass
        return True
