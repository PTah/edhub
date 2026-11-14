# Created by nc.ai 1.2.11 on Papasha 2026-11-14 17:41:43
"""Отправка travel-событий в INARA (https://inara.cz/inapi/v1/).

INARA API принимает лог полёта и состояние командира. Координаты систем и
прыжки попадают сюда напрямую (нужен персональный API-ключ INARA), а вот
сканы тел/био INARA забирает из EDDN — отдельного события для Scan у неё нет.

События, которые мы шлём:
  - setCommanderTravelLocation   (Location)
  - addCommanderTravelFSDJump    (FSDJump)
  - addCommanderTravelCarrierJump(CarrierJump)
  - addCommanderTravelLand       (Touchdown)

Формат: JSON POST, header.appName/appVersion/APIkey/commanderName/
commanderFrontierID + events[]. Отправляем только live-события текущей сессии:
INARA просит не слать события старше 30 дней.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from . import config

ENDPOINT = "https://inara.cz/inapi/v1/"
SOFTWARE = "EDHUD"
BATCH = 20


def _iso(event_timestamp: str | None) -> str:
    if event_timestamp:
        return str(event_timestamp)
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _event_data(name: str, event: dict, state) -> dict | None:
    if name == "FSDJump":
        data: dict = {
            "starsystemName": event.get("StarSystem") or (state.system.name if state.system else None),
        }
        if event.get("StarPos"):
            data["starsystemCoords"] = [float(c) for c in event["StarPos"]]
        if event.get("JumpDist") is not None:
            data["jumpDistance"] = float(event["JumpDist"])
        if getattr(state, "ship", None):
            data["shipType"] = str(state.ship)
        if event.get("ShipID") is not None:
            data["shipGameID"] = int(event["ShipID"])
        return data or None
    if name == "CarrierJump":
        data = {
            "starsystemName": event.get("StarSystem") or (state.system.name if state.system else None),
            "stationName": event.get("StationName") or "Fleet Carrier",
        }
        if event.get("StarPos"):
            data["starsystemCoords"] = [float(c) for c in event["StarPos"]]
        return data
    if name == "Location":
        data = {
            "starsystemName": event.get("StarSystem") or (state.system.name if state.system else None),
        }
        if event.get("BodyType") == "Planet" and event.get("Body"):
            data["starsystemBodyName"] = event.get("Body")
        if event.get("Latitude") is not None and event.get("Longitude") is not None:
            data["starsystemBodyCoords"] = [float(event["Latitude"]), float(event["Longitude"])]
        return data
    if name == "Touchdown":
        system = event.get("StarSystem") or (state.system.name if state.system else None)
        body = event.get("Body")
        if not system or not body:
            return None
        data = {"starsystemName": system, "starsystemBodyName": body}
        if event.get("Latitude") is not None and event.get("Longitude") is not None:
            data["latitude"] = float(event["Latitude"])
            data["longitude"] = float(event["Longitude"])
        return data
    return None


INARA_EVENTS = {
    "FSDJump": "addCommanderTravelFSDJump",
    "CarrierJump": "addCommanderTravelCarrierJump",
    "Location": "setCommanderTravelLocation",
    "Touchdown": "addCommanderTravelLand",
}


def build_batch(events: list[tuple[dict, object]], software_version: str) -> dict | None:
    state = None
    payload_events = []
    for event, st in events:
        name = event.get("event")
        if state is None:
            state = st
        data = _event_data(name, event, st)
        if data is None:
            continue
        payload_events.append(
            {
                "eventName": INARA_EVENTS[name],
                "eventTimestamp": _iso(event.get("timestamp")),
                "eventData": data,
            }
        )
    if not payload_events or state is None:
        return None
    commander = (getattr(state, "cmdr", None) or "").strip()
    return {
        "header": {
            "appName": SOFTWARE,
            "appVersion": software_version,
            "isBeingDeveloped": False,
            "APIkey": "",  # подставит отправитель из настроек
            "commanderName": commander,
            "commanderFrontierID": getattr(state, "fid", None) or "",
        },
        "events": payload_events,
    }


class InaraUploader:
    """Очередь travel-событий INARA с дедупликацией и батчами."""

    def __init__(self, cfg_provider: Callable, software_version: str) -> None:
        self._cfg = cfg_provider
        self.software_version = software_version
        self._lock = threading.Lock()
        self._queue: list[tuple[dict, object]] = []
        self._queued: set[str] = set()
        self._sent: set[str] = set()
        self._running = False
        self._auth_failed = False
        self._sent_path = config.app_dir() / "inara-sent.json"
        self._load_sent()

    def enabled(self) -> bool:
        cfg = self._cfg()
        if self._auth_failed or not getattr(cfg, "allow_network", True):
            return False
        return bool(
            (getattr(cfg, "inara_api_key", "") or "").strip()
            and (getattr(cfg, "inara_commander", "") or "").strip()
        )

    def note(self, event: dict, state) -> None:
        if not self.enabled() or getattr(state, "legacy", False):
            return
        name = event.get("event")
        if name not in INARA_EVENTS or not event.get("timestamp"):
            return
        key = f"{event.get('timestamp')}|{name}|{event.get('SystemAddress') or ''}"
        with self._lock:
            if key in self._sent or key in self._queued:
                return
            self._queued.add(key)
            self._queue.append((event, state))
        self.flush_async()

    def flush_async(self) -> None:
        if not self.enabled():
            return

        def run() -> None:
            with self._lock:
                if self._running:
                    return
                self._running = True
            try:
                while not self._auth_failed:
                    with self._lock:
                        batch = list(self._queue[:BATCH])
                    if not batch:
                        break
                    ok = self._post(batch)
                    with self._lock:
                        del self._queue[: len(batch)]
                        for event, _st in batch:
                            key = f"{event.get('timestamp')}|{event.get('event')}|{event.get('SystemAddress') or ''}"
                            self._queued.discard(key)
                            if ok:
                                self._sent.add(key)
                    if not ok:
                        break
            finally:
                with self._lock:
                    self._running = False
                self._save_sent()

        threading.Thread(target=run, name="edhud-inara", daemon=True).start()

    def _post(self, batch: list[tuple[dict, object]]) -> bool:
        cfg = self._cfg()
        api_key = str(getattr(cfg, "inara_api_key", "") or "").strip()
        payload = build_batch(batch, self.software_version)
        if payload is None:
            return True
        payload["header"]["APIkey"] = api_key
        payload["header"]["commanderName"] = str(getattr(cfg, "inara_commander", "") or "").strip()
        request = urllib.request.Request(
            ENDPOINT,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": f"{SOFTWARE}/{self.software_version}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                result = json.loads(response.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            return False
        header_status = result.get("header", {}).get("eventStatus") if isinstance(result, dict) else None
        if header_status == 400:
            self._auth_failed = True
            return False
        return True

    # ------------------------------------------------------------- state on disk
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
