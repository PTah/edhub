# Created by nc.ai 1.2.11 on Papasha 2026-11-14 17:40:46
"""Отправка событий журнала в EDDN (https://eddn.edcd.io:4430/upload/).

EDDN — общая шина данных Elite: отсюда сообщения разбирают Spansh, EDSM,
INARA, edastro и другие инструменты. Ключ не нужен, достаточно имени
командира как uploaderID. Отправляем только live-события текущей сессии
(старые журналы не заливаем — EDDN просит не слать неживые данные).

Схемы (live, 2025):
  - journal/1            FSDJump, Location, CarrierJump, Docked, Scan,
                         SAASignalsFound
  - fssbodysignals/1     FSSBodySignals
  - codexentry/1         CodexEntry
  - fssdiscoveryscan/1   FSSDiscoveryScan

Правила EDDN: HTTPS POST на порт 4430, gzip по желанию, при 400/426/413
сообщение не повторять, сетевые ошибки — повтор не раньше чем через минуту.
"""
from __future__ import annotations

import gzip
import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from . import config

UPLOAD_URL = "https://eddn.edcd.io:4430/upload/"
SOFTWARE = "EDHUD"

JOURNAL_SCHEMA = "https://eddn.edcd.io/schemas/journal/1"
SCHEMAS: dict[str, str] = {
    "FSDJump": JOURNAL_SCHEMA,
    "Location": JOURNAL_SCHEMA,
    "CarrierJump": JOURNAL_SCHEMA,
    "Docked": JOURNAL_SCHEMA,
    "Scan": JOURNAL_SCHEMA,
    "SAASignalsFound": JOURNAL_SCHEMA,
    "FSSBodySignals": "https://eddn.edcd.io/schemas/fssbodysignals/1",
    "CodexEntry": "https://eddn.edcd.io/schemas/codexentry/1",
    "FSSDiscoveryScan": "https://eddn.edcd.io/schemas/fssdiscoveryscan/1",
}
RETRY_MIN = 60.0  # EDDN: минимум 60 секунд перед повтором


def _strip_localised(value):
    if isinstance(value, dict):
        return {k: _strip_localised(v) for k, v in value.items() if not k.endswith("_Localised")}
    if isinstance(value, list):
        return [_strip_localised(item) for item in value]
    return value


def _iso_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def build_envelope(event: dict, state, software_version: str) -> dict | None:
    """Событие журнала → сообщение EDDN (или None, если нечего слать)."""
    name = event.get("event")
    schema = SCHEMAS.get(name)
    if not schema or not event.get("timestamp"):
        return None
    if getattr(state, "legacy", False):
        return None

    message = dict(event)
    system = getattr(state, "system", None)
    address = event.get("SystemAddress")
    if address is None and system is not None and system.address is not None:
        address = int(system.address)
    if address is not None:
        message["SystemAddress"] = int(address)
    # Scan/SAASignalsFound не несут StarSystem/StarPos — дополняем из состояния
    if not message.get("StarSystem") and system is not None and system.name:
        message["StarSystem"] = system.name
    if not message.get("StarPos") and system is not None and system.star_pos:
        message["StarPos"] = [float(c) for c in system.star_pos]

    # локализованные дубликаты не нужны (FSSBodySignals, SAASignalsFound)
    if name in ("FSSBodySignals", "SAASignalsFound"):
        message = _strip_localised(message)

    odyssey = bool(getattr(state, "odyssey", False))
    if name in ("FSSBodySignals", "CodexEntry", "SAASignalsFound"):
        message["odyssey"] = odyssey

    commander = (getattr(state, "cmdr", None) or "").strip() or "unknown"
    return {
        "$schemaRef": schema,
        "header": {
            "uploaderID": commander,
            "softwareName": SOFTWARE,
            "softwareVersion": software_version,
            "gameversion": str(getattr(state, "game_version", "") or ""),
            "gamebuild": str(getattr(state, "build", "") or ""),
        },
        "message": message,
    }


def _post(envelope: dict) -> int:
    body = gzip.compress(json.dumps(envelope, ensure_ascii=False).encode("utf-8"))
    request = urllib.request.Request(
        UPLOAD_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Content-Encoding": "gzip",
            "User-Agent": f"{SOFTWARE}/1.3",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return int(response.status or 200)


class EddnUploader:
    """Очередь live-сообщений EDDN с дедупликацией и мягкими повторами."""

    def __init__(self, cfg_provider: Callable, software_version: str) -> None:
        self._cfg = cfg_provider
        self.software_version = software_version
        self._lock = threading.Lock()
        self._queue: list[dict] = []
        self._queued: set[str] = set()
        self._sent: set[str] = set()
        self._running = False
        self._sent_path = config.app_dir() / "eddn-sent.json"
        self._load_sent()

    def enabled(self) -> bool:
        cfg = self._cfg()
        return bool(getattr(cfg, "allow_network", True) and getattr(cfg, "eddn_upload", False))

    def note(self, event: dict, state) -> None:
        if not self.enabled():
            return
        envelope = build_envelope(event, state, self.software_version)
        if envelope is None:
            return
        message = envelope["message"]
        key = "|".join(
            (
                str(message.get("timestamp") or ""),
                str(message.get("event") or ""),
                str(message.get("SystemAddress") or ""),
                str(message.get("BodyID") or ""),
                str(message.get("BodyName") or ""),
            )
        )
        with self._lock:
            if key in self._sent or key in self._queued:
                return
            self._queued.add(key)
            self._queue.append(envelope)
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
                while True:
                    with self._lock:
                        envelope = self._queue[0] if self._queue else None
                    if envelope is None:
                        break
                    code = None
                    try:
                        code = _post(envelope)
                    except (urllib.error.URLError, TimeoutError, OSError):
                        # сеть: оставляем в очереди и ждём EDDN-минимум 60 c
                        time.sleep(RETRY_MIN)
                        continue
                    with self._lock:
                        self._queue.pop(0)
                        message = envelope["message"]
                        key = "|".join(
                            (
                                str(message.get("timestamp") or ""),
                                str(message.get("event") or ""),
                                str(message.get("SystemAddress") or ""),
                                str(message.get("BodyID") or ""),
                                str(message.get("BodyName") or ""),
                            )
                        )
                        self._queued.discard(key)
                        if code is not None and 200 <= code < 300:
                            self._sent.add(key)
                        # 4xx/413 — сообщение битое/устаревшее: выбросить и не повторять
                    if code is not None and not 200 <= code < 300:
                        continue
            finally:
                with self._lock:
                    self._running = False
                self._save_sent()

        threading.Thread(target=run, name="edhud-eddn-upload", daemon=True).start()

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
