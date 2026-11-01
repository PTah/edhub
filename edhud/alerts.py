"""Детектор голосовых событий: био-сигнал и первое открытие системы."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from . import bio
from .model import GameState


@dataclass
class Alert:
    kind: str  # bio | first_discovery
    text: str
    overlay: str | None = None


@dataclass
class AlertEngine:
    """Пока armed=False (replay журнала) события копятся в seen, но не озвучиваются."""

    armed: bool = False
    voice_enabled: bool = True
    voice_bio: bool = True
    voice_first_discovery: bool = True
    _bio_seen: set[tuple[int, int]] = field(default_factory=set)
    _system_seen: set[int] = field(default_factory=set)
    on_alert: Callable[[Alert], None] | None = None

    def configure(self, cfg) -> None:
        self.voice_enabled = bool(getattr(cfg, "voice_enabled", True))
        self.voice_bio = bool(getattr(cfg, "voice_bio", True))
        self.voice_first_discovery = bool(getattr(cfg, "voice_first_discovery", True))

    def arm(self) -> None:
        self.armed = True

    def reset_system(self) -> None:
        """При смене системы можно оставить seen — ключи включают address."""
        pass

    def handle(self, event: dict, state: GameState) -> list[Alert]:
        if not event:
            return []
        name = event.get("event") or ""
        fired: list[Alert] = []
        if name in ("FSSBodySignals", "SAASignalsFound"):
            alert = self._check_bio(event, state)
            if alert:
                fired.append(alert)
        elif name == "Scan":
            alert = self._check_discovery(event, state)
            if alert:
                fired.append(alert)
        for alert in fired:
            if self.on_alert:
                try:
                    self.on_alert(alert)
                except Exception:
                    pass
        return fired

    def _check_bio(self, event: dict, state: GameState) -> Alert | None:
        body_id = event.get("BodyID")
        address = state.system.address
        if body_id is None or address is None:
            return None
        # считаем сигналы из события (надёжнее, чем ждать merge)
        count = 0
        for sig in event.get("Signals") or []:
            kind = (sig.get("Type") or "").lower()
            if "biological" in kind:
                count = max(count, int(sig.get("Count") or 0))
        if count <= 0:
            body = state.system.bodies.get(body_id)
            count = int(body.bio_signals or 0) if body else 0
        if count <= 0:
            return None
        key = (int(address), int(body_id))
        if key in self._bio_seen:
            return None
        self._bio_seen.add(key)
        if not (self.armed and self.voice_enabled and self.voice_bio):
            return None
        body = state.system.bodies.get(body_id)
        body_name = (body.name if body else None) or event.get("BodyName") or "тело"
        short = body_name.split()[-1] if body_name else "тело"
        forecast = bio.forecast_names(body, state.system, limit=3) if body is not None else []
        possible = f" Возможно: {', '.join(forecast)}." if forecast else ""
        text = f"Биологический сигнал найден. {short}.{possible}"
        overlay = f"био ×{count}: {body_name}"
        if forecast:
            overlay += " · " + ", ".join(forecast)
        return Alert(kind="bio", text=text, overlay=overlay)

    def _check_discovery(self, event: dict, state: GameState) -> Alert | None:
        # Фраза про систему — только если не открыта сама звезда.
        # Первая неоткрытая планета в уже известной системе её не произносит.
        if event.get("WasDiscovered") is not False or not event.get("StarType"):
            return None
        address = state.system.address or event.get("SystemAddress")
        if address is None:
            return None
        address = int(address)
        if address in self._system_seen:
            return None
        self._system_seen.add(address)
        if not (self.armed and self.voice_enabled and self.voice_first_discovery):
            return None
        system = state.system.name or event.get("StarSystem") or "система"
        text = "Звёздная система открыта вами."
        return Alert(kind="first_discovery", text=text, overlay=f"первое открытие: {system}")
