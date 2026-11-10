"""Отправка журнала на EDSM (api-journal-v1).

Ключ и имя командира из настроек. Сдача картографии в игре координаты на EDSM
не кладёт: туда попадает журнал с StarPos (FSDJump, Location, CarrierJump).
EDHUD раньше этот ключ только читал.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

from . import config
from .journal import journal_files

JOURNAL_URL = "https://www.edsm.net/api-journal-v1"
DISCARD_URL = "https://www.edsm.net/api-journal-v1/discard"
SOFTWARE = "EDHUD"
POSITION_EVENTS = frozenset({"FSDJump", "Location", "CarrierJump"})
LIVE_EVENTS = POSITION_EVENTS | frozenset(
    {
        "CarrierLocation",
        "Docked",
        "Undocked",
        "Scan",
        "FSSDiscoveryScan",
        "FSSAllBodiesFound",
        "SAAScanComplete",
        "ApproachBody",
        "LeaveBody",
        "Touchdown",
        "Liftoff",
    }
)
SKIP_SYSTEMS = frozenset({"ProvingGround", "CQC"})
OK_CODES = frozenset({100, 101, 102, 103, 304})
BATCH = 20


def event_key(event: dict) -> str:
    address = event.get("SystemAddress")
    body = event.get("BodyID")
    return "|".join(
        (
            str(event.get("timestamp") or ""),
            str(event.get("event") or ""),
            "" if address is None else str(address),
            "" if body is None else str(body),
        )
    )


def annotate(event: dict, system_name: str | None, system_address, star_pos) -> dict:
    """Копия события плюс transient-поля, которые просит EDSM."""
    item = dict(event)
    if system_address is not None:
        item["_systemAddress"] = int(system_address)
    if system_name:
        item["_systemName"] = system_name
    coords = star_pos
    if not (isinstance(coords, (list, tuple)) and len(coords) == 3):
        coords = event.get("StarPos")
    if isinstance(coords, (list, tuple)) and len(coords) == 3:
        item["_systemCoordinates"] = [float(coords[0]), float(coords[1]), float(coords[2])]
    return item


def usable(event: dict, *, live: bool) -> bool:
    name = event.get("event")
    if not event.get("timestamp") or name not in (LIVE_EVENTS if live else POSITION_EVENTS):
        return False
    if not live and not (isinstance(event.get("StarPos"), (list, tuple)) and len(event["StarPos"]) == 3):
        return False
    system = event.get("StarSystem")
    return system not in SKIP_SYSTEMS


def game_identity(version: str | None, build: str | None) -> tuple[str, str] | None:
    if not version or not build:
        return None
    ver = str(version).strip()
    if ver.startswith("3."):
        return None
    bld = str(build).strip()
    if not ver or not bld:
        return None
    return ver, bld


def build_form(commander: str, api_key: str, version: str, game_version: str, game_build: str, events: list[dict]) -> dict[str, str]:
    return {
        "commanderName": commander,
        "apiKey": api_key,
        "fromSoftware": SOFTWARE,
        "fromSoftwareVersion": version,
        "fromGameVersion": game_version,
        "fromGameBuild": game_build,
        "message": json.dumps(events, ensure_ascii=False, separators=(",", ":")),
    }


class EdsmUploader:
    def __init__(self, cfg_provider: Callable, software_version: str) -> None:
        self._cfg = cfg_provider
        self.software_version = software_version
        self._lock = threading.Lock()
        self._queue: list[tuple[dict, str, str]] = []
        self._queued: set[str] = set()
        self._sent: set[str] = set()
        self._discard: set[str] = set()
        self._discard_loaded = False
        self._backfilled = False
        self._running = False
        self._live = False
        self._auth_failed = False
        self._sent_path = config.app_dir() / "edsm-sent.json"
        self._load_sent()

    def enabled(self) -> bool:
        cfg = self._cfg()
        if self._auth_failed or not getattr(cfg, "allow_network", True):
            return False
        return bool((getattr(cfg, "edsm_commander", "") or "").strip() and (getattr(cfg, "edsm_api_key", "") or "").strip())

    def note(self, event: dict, state) -> None:
        """Поставить событие текущего журнала в очередь. Сеть не трогает."""
        if not self.enabled() or getattr(state, "legacy", False):
            return
        if not usable(event, live=True):
            return
        if self._discard_loaded and event.get("event") in self._discard:
            return
        identity = game_identity(getattr(state, "game_version", None), getattr(state, "build", None))
        if identity is None:
            return
        key = event_key(event)
        system = state.system
        item = annotate(event, system.name, system.address, system.star_pos)
        with self._lock:
            if key in self._sent or key in self._queued:
                return
            self._queued.add(key)
            self._queue.append((item, identity[0], identity[1]))
        if self._live:
            self.flush_async(None)

    def enable_live(self, folder: Path | None) -> None:
        self._live = True
        self.flush_async(folder)

    def flush_async(self, folder: Path | None) -> None:
        if not self.enabled():
            return

        def run() -> None:
            with self._lock:
                if self._running:
                    return
                self._running = True
            try:
                self._load_discard()
                if folder is not None and not self._backfilled:
                    self._backfill(folder)
                    self._backfilled = True
                while not self._auth_failed:
                    with self._lock:
                        batch = list(self._queue)
                        self._queue.clear()
                    if not batch:
                        break
                    if not self._post_groups(batch):
                        break
            finally:
                with self._lock:
                    self._running = False
                self._save_sent()

        threading.Thread(target=run, name="edhud-edsm", daemon=True).start()

    def _load_sent(self) -> None:
        try:
            data = json.loads(self._sent_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(data, list):
            self._sent = {str(item) for item in data}

    def _save_sent(self) -> None:
        try:
            self._sent_path.parent.mkdir(parents=True, exist_ok=True)
            self._sent_path.write_text(json.dumps(sorted(self._sent)), encoding="utf-8")
        except OSError:
            pass

    def _load_discard(self) -> None:
        if self._discard_loaded:
            return
        try:
            request = urllib.request.Request(DISCARD_URL, headers={"User-Agent": f"{SOFTWARE}/{self.software_version}"})
            with urllib.request.urlopen(request, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            return
        if isinstance(data, list):
            self._discard = {str(item) for item in data}
            self._discard_loaded = True
            with self._lock:
                kept: list[tuple[dict, str, str]] = []
                for item in self._queue:
                    if item[0].get("event") in self._discard:
                        self._queued.discard(event_key(item[0]))
                    else:
                        kept.append(item)
                self._queue = kept

    def _backfill(self, folder: Path) -> None:
        """Старые журналы: только прыжки и Location со StarPos — от них на EDSM появляются координаты."""
        found: list[tuple[str, dict, str, str]] = []
        for path in journal_files(folder):
            version = build = None
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue
                if event.get("event") == "Fileheader":
                    version = event.get("gameversion") or event.get("GameVersion")
                    build = event.get("build")
                    continue
                if not usable(event, live=False):
                    continue
                identity = game_identity(version, build)
                if identity is None:
                    continue
                key = event_key(event)
                item = annotate(event, event.get("StarSystem"), event.get("SystemAddress"), event.get("StarPos"))
                found.append((key, item, identity[0], identity[1]))
        found.sort(key=lambda row: str(row[1].get("timestamp") or ""))
        with self._lock:
            for key, item, ver, bld in found:
                if key in self._sent or key in self._queued:
                    continue
                self._queued.add(key)
                self._queue.append((item, ver, bld))

    def _post_groups(self, batch: list[tuple[dict, str, str]]) -> bool:
        groups: dict[tuple[str, str], list[dict]] = {}
        for item, ver, bld in batch:
            groups.setdefault((ver, bld), []).append(item)
        cfg = self._cfg()
        commander = str(getattr(cfg, "edsm_commander", "") or "").strip()
        api_key = str(getattr(cfg, "edsm_api_key", "") or "").strip()
        for (ver, bld), events in groups.items():
            events.sort(key=lambda item: str(item.get("timestamp") or ""))
            for start in range(0, len(events), BATCH):
                chunk = events[start : start + BATCH]
                code = self._post(commander, api_key, ver, bld, chunk)
                if code is None:
                    with self._lock:
                        for item in chunk:
                            key = event_key(item)
                            self._queued.discard(key)
                            self._queue.append((item, ver, bld))
                    return False
                if 200 <= code < 300:
                    self._auth_failed = True
                    return False
                if code in OK_CODES or 100 <= code < 200 or 400 <= code < 500:
                    with self._lock:
                        for item in chunk:
                            key = event_key(item)
                            self._queued.discard(key)
                            self._sent.add(key)
                else:
                    with self._lock:
                        for item in chunk:
                            self._queued.discard(event_key(item))
                time.sleep(0.35)
        return True

    def _post(self, commander: str, api_key: str, game_version: str, game_build: str, events: list[dict]) -> int | None:
        form = build_form(commander, api_key, self.software_version, game_version, game_build, events)
        data = urllib.parse.urlencode(form).encode("utf-8")
        request = urllib.request.Request(
            JOURNAL_URL,
            data=data,
            headers={"User-Agent": f"{SOFTWARE}/{self.software_version}", "Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            return None
        try:
            return int(body.get("msgnum"))
        except (TypeError, ValueError, AttributeError):
            return None
