"""Чтение журналов Elite Dangerous: Journal*.log, Status.json, NavRoute.json.

Подход тот же, что в EDMarketConnector/monitor.py: находим самый свежий файл
Journal*.log, читаем его целиком при старте (чтобы восстановить состояние), а
дальше читаем только новые строки. Status.json и NavRoute.json опрашиваются по
mtime — они перезаписываются игрой целиком.
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Callable

from .model import GameState
from .route import Route

LOG_RE = re.compile(r"^Journal(Alpha|Beta)?\.[0-9]{2,4}(-)?[0-9]{2}(-)?[0-9]{2}(T)?[0-9]{2}[0-9]{2}[0-9]{2}")


def journal_files(folder: Path) -> list[Path]:
    try:
        files = [p for p in folder.iterdir() if LOG_RE.match(p.name) and p.suffix == ".log"]
    except OSError:
        return []
    return sorted(files, key=lambda p: (p.stat().st_mtime, p.name))


def newest_journal(folder: Path) -> Path | None:
    files = journal_files(folder)
    return files[-1] if files else None


class JournalWatcher(threading.Thread):
    """Фоновый поток: журнал + Status.json + NavRoute.json -> GameState."""

    def __init__(
        self,
        folder: Path,
        state: GameState,
        poll_journal: float = 0.25,
        poll_status: float = 0.5,
        on_event: Callable[[dict], None] | None = None,
        on_status: Callable[[], None] | None = None,
        on_catchup_done: Callable[[], None] | None = None,
        replay: bool = True,
    ) -> None:
        super().__init__(name="edhud-journal", daemon=True)
        self.folder = Path(folder)
        self.state = state
        self.poll_journal = poll_journal
        self.poll_status = poll_status
        self.on_event = on_event
        self.on_status = on_status
        self.on_catchup_done = on_catchup_done
        self.replay = replay
        self._stop = threading.Event()
        self._file: Path | None = None
        self._offset = 0
        self._status_mtime = 0.0
        self._navroute_mtime = 0.0
        self._partial = ""
        self._catchup_pending = bool(replay)
        self.errors: list[str] = []

    # ------------------------------------------------------------------ API
    @property
    def catchup_pending(self) -> bool:
        """True, пока идёт первичный replay журнала — на диск писать рано."""
        return bool(self._catchup_pending)

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll()
            except Exception as exc:  # поток не должен падать
                self.errors.append(f"{type(exc).__name__}: {exc}")
            self._stop.wait(self.poll_journal)

    def poll(self) -> None:
        self.read_journal()
        self.read_status()
        self.read_navroute()

    # -------------------------------------------------------------- журнал
    def read_journal(self) -> None:
        latest = newest_journal(self.folder)
        if latest is None:
            self._finish_catchup()  # нечего replay — сразу live
            return
        if self._file != latest:
            self._file = latest
            self._offset = 0 if self.replay else latest.stat().st_size
            self._partial = ""
            if self.replay:
                self._catchup_pending = True
        try:
            size = latest.stat().st_size
        except OSError:
            return
        if size < self._offset:  # файл обрезали/пересоздали
            self._offset = 0
            self._partial = ""
            self._catchup_pending = True
        if size == self._offset:
            self._finish_catchup()
            return
        try:
            with latest.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(self._offset)
                chunk = handle.read()
                self._offset = handle.tell()
        except OSError:
            return
        data = self._partial + chunk
        lines = data.split("\n")
        self._partial = lines.pop() if lines else ""
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            self.state.apply(event)
            if self.on_event:
                self.on_event(event)
        if self._offset >= size and not self._partial:
            self._finish_catchup()

    def _finish_catchup(self) -> None:
        if not self._catchup_pending:
            return
        self._catchup_pending = False
        if self.on_catchup_done:
            try:
                self.on_catchup_done()
            except Exception:
                pass

    # -------------------------------------------------------------- status
    def read_status(self) -> None:
        path = self.folder / "Status.json"
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return
        if mtime == self._status_mtime:
            return
        self._status_mtime = mtime
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return
        self.state.apply_status(data)
        if self.on_status:
            self.on_status()

    # ------------------------------------------------------------- navroute
    def read_navroute(self) -> None:
        path = self.folder / "NavRoute.json"
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return
        stale = bool(self.state.navroute_stale)
        if mtime == self._navroute_mtime and not stale:
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            # mtime не трогаем: при частичной записи игры повторим на следующем poll
            return
        self._navroute_mtime = mtime
        self.state.navroute_stale = False
        if self.state.route.locked:
            return
        route = Route.from_navroute(data)
        if route.hops:
            self.state.route = route
            self.state.sync_route_discoverers()
        elif self.state.route.source == "game" and not self.state.route.locked:
            self.state.route = Route()


def load_snapshot(folder: Path) -> GameState:
    """Одноразовое чтение журнала/статуса (для --dump и тестов)."""
    state = GameState()
    watcher = JournalWatcher(folder, state)
    watcher.read_journal()
    watcher.read_status()
    watcher.read_navroute()
    return state
