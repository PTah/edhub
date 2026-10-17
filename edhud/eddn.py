# Created by nc.ai 0.8.8.0 on macbook 2026-10-17 20:21:55
"""Собственный слушатель EDDN (ZeroMQ).

EDDN — общая шина данных Elite Dangerous: EDMC/EDDLite/другие клиенты публикуют
сюда события журнала (`Scan`, `FSSBodySignals`, `SAASignalsFound`, ...), а EDSM и
Spansh их разбирают. Здесь мы подписываемся сами: либо через pyzmq (если он
установлен), либо через встроенный минимальный ZMTP-клиент (edhud/zmtp.py), так
что внешние пакеты не обязательны.

Сообщение EDDN — zlib-сжатый JSON вида
    {"$schemaRef": "...", "header": {...}, "message": {"event": "Scan", ...}}
Фильтруем по интересующей системе, чтобы не молотить весь фид.
"""
from __future__ import annotations

import json
import threading
import zlib
from typing import Callable

from . import zmtp

try:  # pyzmq не обязателен
    import zmq as _zmq
except ImportError:  # pragma: no cover - зависит от окружения
    _zmq = None

DEFAULT_ENDPOINT = "tcp://eddn.edcd.io:9500"
SYSTEM_KEYS = ("StarSystem", "SystemName", "System")
INTERESTING_EVENTS = {
    "Scan",
    "FSSBodySignals",
    "SAASignalsFound",
    "SAAScanComplete",
    "ScanOrganic",
    "CodexEntry",
}


def decode_message(raw: bytes) -> dict | None:
    """zlib -> JSON. Возвращает словарь сообщения EDDN целиком."""
    if not raw:
        return None
    try:
        payload = zlib.decompress(raw)
    except zlib.error:
        payload = raw  # уже распакованное (бывает у тестовых/старых клиентов)
    try:
        data = json.loads(payload.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def message_system(message: dict) -> tuple[str | None, int | None]:
    """Имя и SystemAddress из события журнала."""
    name = None
    for key in SYSTEM_KEYS:
        value = message.get(key)
        if isinstance(value, str) and value:
            name = value
            break
    address = message.get("SystemAddress")
    return name, int(address) if isinstance(address, int) else None


class SetFilter:
    """Что слушаем: адреса систем и/или имена (без учёта регистра)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._addresses: set[int] = set()
        self._names: set[str] = set()

    def update(self, names: set[str] | None = None, addresses: set[int] | None = None) -> None:
        with self._lock:
            self._names = {n.lower() for n in (names or set()) if n}
            self._addresses = {int(a) for a in (addresses or set()) if a}

    def __call__(self, message: dict) -> bool:
        with self._lock:
            if not self._names and not self._addresses:
                return False
            name, address = message_system(message)
            if address is not None and address in self._addresses:
                return True
            return bool(name) and name.lower() in self._names


class EddnListener(threading.Thread):
    """Фоновый поток: подписка на EDDN, фильтр по системам, колбэк на сообщение."""

    def __init__(
        self,
        endpoint: str = DEFAULT_ENDPOINT,
        on_message: Callable[[dict], None] | None = None,
        system_filter: Callable[[dict], bool] | None = None,
        timeout: float = 20.0,
        reconnect: float = 8.0,
    ) -> None:
        super().__init__(name="edhud-eddn", daemon=True)
        self.endpoint = endpoint
        self.on_message = on_message
        self.system_filter = system_filter
        self.timeout = timeout
        self.reconnect = reconnect
        self.stats: dict = {
            "backend": "pyzmq" if _zmq is not None else "zmtp",
            "received": 0,
            "matched": 0,
            "errors": 0,
            "connected": False,
            "last_error": None,
        }
        self._stop = threading.Event()

    # ------------------------------------------------------------------ API
    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                if _zmq is not None:
                    self._run_zmq()
                else:
                    self._run_zmtp()
            except Exception as exc:  # сеть рвётся — переподключаемся
                self.stats["errors"] += 1
                self.stats["last_error"] = f"{type(exc).__name__}: {exc}"
            finally:
                self.stats["connected"] = False
            self._stop.wait(self.reconnect)

    # -------------------------------------------------------------- бэкенды
    def _run_zmtp(self) -> None:
        subscriber = zmtp.ZmtpSubscriber(self.endpoint, timeout=self.timeout)
        subscriber.connect()
        self.stats["connected"] = True
        try:
            while not self._stop.is_set():
                raw = subscriber.recv()
                if raw is None:
                    continue
                self._handle_raw(raw)
        finally:
            subscriber.close()

    def _run_zmq(self) -> None:  # pragma: no cover - зависит от окружения
        context = _zmq.Context.instance()
        sock = context.socket(_zmq.SUB)
        sock.setsockopt_string(_zmq.SUBSCRIBE, "")
        sock.setsockopt(_zmq.RCVTIMEO, int(self.timeout * 1000))
        sock.connect(self.endpoint)
        self.stats["connected"] = True
        try:
            while not self._stop.is_set():
                try:
                    raw = sock.recv()
                except _zmq.Again:
                    continue
                self._handle_raw(raw)
        finally:
            sock.close(0)

    # -------------------------------------------------------------- обработка
    def _handle_raw(self, raw: bytes) -> None:
        self.stats["received"] += 1
        envelope = decode_message(raw)
        if not envelope:
            return
        message = envelope.get("message")
        if not isinstance(message, dict):
            return
        if self.system_filter is not None and not self.system_filter(message):
            return
        self.stats["matched"] += 1
        if self.on_message is not None:
            self.on_message(message)
