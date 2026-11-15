# Created by nc.ai 1.2.15 on Papasha 2026-11-15 16:21:08
"""Статистика по сессиям: каждый вход в игру отдельной строкой + итоги по всем.

Сессия = файл журнала игры (`Journal.2026-...log`): новый вход в игру создаёт
новый файл, значит и новую строку статистики. Счётчики берём из состояния
(`GameState.session_*`), поэтому ничего не пересчитываем заново — просто
периодически фиксируем снимок в `stats.json`.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from . import config

# Поля-счётчики: имя в записи -> имя в GameState
COUNTERS = {
    "jumps": "session_jumps",
    "new_systems": "session_new_systems",
    "scans": "session_scans",
    "new_bodies": "session_new_bodies",
    "mapped": "session_mapped",
    "bio_analyzed": "session_bio_analyzed",
}

VALUE_FIELDS = (
    "scan_cr",  # стоимость сканов тел (с множителями первооткрывателя)
    "map_cr",  # добавка за DSS
    "bio_estimate_cr",  # оценка сданной биологии
    "bio_sold_cr",  # реально продано биологии
    "sold_cr",  # реально продано данных картографии
)


@dataclass
class SessionStats:
    """Один вход в игру."""

    key: str  # имя файла журнала
    started: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)
    commander: str = ""
    jumps: int = 0
    new_systems: int = 0
    scans: int = 0
    new_bodies: int = 0
    mapped: int = 0
    bio_analyzed: int = 0
    distance_ly: float = 0.0
    scan_cr: int = 0
    map_cr: int = 0
    bio_estimate_cr: int = 0
    bio_sold_cr: int = 0
    sold_cr: int = 0

    @property
    def duration_sec(self) -> float:
        return max(0.0, float(self.updated) - float(self.started))

    def to_persist(self) -> dict:
        return asdict(self)

    @classmethod
    def from_persist(cls, data: dict) -> "SessionStats":
        known = {item.name for item in fields(cls)}
        clean: dict = {}
        for key, value in (data or {}).items():
            if key not in known:
                continue
            if key in ("started", "updated", "distance_ly"):
                try:
                    clean[key] = float(value)
                except (TypeError, ValueError):
                    continue
            elif key in ("key", "commander"):
                clean[key] = str(value or "")
            else:
                try:
                    clean[key] = int(value)
                except (TypeError, ValueError):
                    continue
        return cls(**clean)


class StatsStore:
    """`stats.json`: по строке на сессию, плюс агрегаты считаются на лету."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else config.app_dir() / "stats.json"
        self.sessions: list[SessionStats] = []
        self._by_key: dict[str, SessionStats] = {}
        self._last_save = 0.0
        self.load()

    # ---------------------------------------------------------------- файл
    def load(self) -> None:
        self.sessions = []
        self._by_key = {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        rows = raw.get("sessions") if isinstance(raw, dict) else raw
        if not isinstance(rows, list):
            return
        for item in rows:
            if not isinstance(item, dict) or not item.get("key"):
                continue
            session = SessionStats.from_persist(item)
            self.sessions.append(session)
            self._by_key[session.key] = session
        self.sessions.sort(key=lambda item: item.started)

    def save(self) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": 1,
                "sessions": [item.to_persist() for item in self.sessions],
            }
            self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
            self._last_save = time.time()
            return True
        except OSError:
            return False

    # -------------------------------------------------------------- запись
    def session(self, key: str) -> SessionStats:
        found = self._by_key.get(key)
        if found is None:
            found = SessionStats(key=key)
            self._by_key[key] = found
            self.sessions.append(found)
        return found

    def note(self, key: str | None, state, *, save_interval: float = 30.0) -> bool:
        """Зафиксировать текущие счётчики сессии. Возвращает True, если записали.

        `key` — имя файла журнала; None (демо/нет журнала) — писать нечего.
        """
        if not key:
            return False
        session = self.session(key)
        started = getattr(state, "session_started", None)
        if started and (session.started <= 0 or session.jumps == 0 and session.scans == 0):
            session.started = float(started)
        commander = getattr(state, "cmdr", "") or ""
        if commander:
            session.commander = commander
        for name, attr in COUNTERS.items():
            try:
                setattr(session, name, int(getattr(state, attr, 0) or 0))
            except (TypeError, ValueError):
                continue
        try:
            session.distance_ly = float(getattr(state, "session_distance_ly", 0.0) or 0.0)
        except (TypeError, ValueError):
            session.distance_ly = 0.0
        for name, attr in (
            ("scan_cr", "session_scan_value"),
            ("map_cr", "session_map_value"),
            ("bio_estimate_cr", "session_organic_estimate"),
            ("bio_sold_cr", "session_organic_sold"),
            ("sold_cr", "session_sold"),
        ):
            try:
                setattr(session, name, int(getattr(state, attr, 0) or 0))
            except (TypeError, ValueError):
                continue
        session.updated = time.time()
        if session.updated < session.started:
            session.started = session.updated
        if time.time() - self._last_save >= save_interval:
            self.save()
            return True
        return False

    # -------------------------------------------------------------- сводка
    def totals(self) -> dict:
        total = {
            "sessions": len(self.sessions),
            "jumps": 0,
            "new_systems": 0,
            "scans": 0,
            "new_bodies": 0,
            "mapped": 0,
            "bio_analyzed": 0,
            "distance_ly": 0.0,
            "hours": 0.0,
            "scan_cr": 0,
            "map_cr": 0,
            "bio_estimate_cr": 0,
            "bio_sold_cr": 0,
            "sold_cr": 0,
        }
        for item in self.sessions:
            for name in ("jumps", "new_systems", "scans", "new_bodies", "mapped", "bio_analyzed",
                         "scan_cr", "map_cr", "bio_estimate_cr", "bio_sold_cr", "sold_cr"):
                total[name] += int(getattr(item, name, 0) or 0)
            total["distance_ly"] += float(item.distance_ly or 0.0)
            total["hours"] += item.duration_sec / 3600.0
        return total

    def recent(self, limit: int = 30) -> list[SessionStats]:
        return sorted(self.sessions, key=lambda item: item.updated, reverse=True)[: max(1, int(limit))]
