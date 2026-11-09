"""Детектор голосовых событий: био-сигнал, первое открытие, зона DSS."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from . import bio
from . import values
from .model import GameState, format_dss_range


@dataclass
class Alert:
    kind: str  # bio | first_discovery | dss_range | expensive_planet
    text: str
    overlay: str | None = None


@dataclass
class AlertEngine:
    """Пока armed=False (replay журнала) события копятся в seen, но не озвучиваются."""

    armed: bool = False
    voice_enabled: bool = True
    voice_bio: bool = True
    voice_first_discovery: bool = True
    voice_dss_range: bool = True
    voice_expensive_planets: bool = True
    expensive_planet_credits: int = 2_500_000
    _bio_seen: set[tuple[int, int]] = field(default_factory=set)
    _system_seen: set[int] = field(default_factory=set)
    _dss_ready_seen: set[tuple[int, int]] = field(default_factory=set)
    _expensive_seen: set[tuple[int, int]] = field(default_factory=set)
    on_alert: Callable[[Alert], None] | None = None

    def configure(self, cfg) -> None:
        self.voice_enabled = bool(getattr(cfg, "voice_enabled", True))
        self.voice_bio = bool(getattr(cfg, "voice_bio", True))
        self.voice_first_discovery = bool(getattr(cfg, "voice_first_discovery", True))
        self.voice_dss_range = bool(getattr(cfg, "voice_dss_range", True))
        self.voice_expensive_planets = bool(getattr(cfg, "voice_expensive_planets", True))
        try:
            self.expensive_planet_credits = max(
                0, int(getattr(cfg, "expensive_planet_credits", 2_500_000) or 0)
            )
        except (TypeError, ValueError):
            self.expensive_planet_credits = 2_500_000

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
            alert = self._check_expensive_planet(event, state)
            if alert:
                fired.append(alert)
        for alert in fired:
            if self.on_alert:
                try:
                    self.on_alert(alert)
                except Exception:
                    pass
        return fired

    def handle_status(self, state: GameState) -> list[Alert]:
        """Проверка Status.json: зона запуска DSS-проб."""
        alert = self._check_dss_range(state)
        if not alert:
            return []
        if self.on_alert:
            try:
                self.on_alert(alert)
            except Exception:
                pass
        return [alert]

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
        # short — обозначение тела (часто «2»/«A 4»), count — число биосигналов
        text = f"Биологический сигнал найден на {short}. Сигналов: {count}.{possible}"
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

    def _check_dss_range(self, state: GameState) -> Alert | None:
        if not (self.armed and self.voice_enabled and self.voice_dss_range):
            return None
        if not state.dss_in_probe_range():
            return None
        body = state.dss_target_body()
        address = state.system.address or state.status.destination_system
        if body is None or address is None or body.body_id is None:
            return None
        key = (int(address), int(body.body_id))
        if key in self._dss_ready_seen:
            return None
        self._dss_ready_seen.add(key)
        radius = state.status.planet_radius or body.radius
        rng = format_dss_range(radius)
        short = (body.name or "тело").split()[-1]
        text = "Тормози"
        return Alert(kind="dss_range", text=text, overlay=f"DSS готов · {short} · {rng}")

    def _check_expensive_planet(self, event: dict, state: GameState) -> Alert | None:
        if event.get("StarType"):
            return None
        body_id = event.get("BodyID")
        address = state.system.address or event.get("SystemAddress")
        if body_id is None or address is None:
            return None
        key = (int(address), int(body_id))
        if key in self._expensive_seen:
            return None
        body = state.system.bodies.get(int(body_id))
        if body is None:
            return None
        breakdown = values.body_values(body, odyssey=bool(getattr(state, "odyssey", True)))
        if breakdown is None:
            return None
        payout = int(breakdown.mapped)
        threshold = int(self.expensive_planet_credits or 0)
        if payout < threshold:
            return None
        self._expensive_seen.add(key)
        if not (self.armed and self.voice_enabled and self.voice_expensive_planets):
            return None
        short = (body.name or event.get("BodyName") or "планета").split()[-1]
        amount = values.credits(payout)
        text = f"Дорогая планета {short}. Цена картографии {amount} кредитов"
        return Alert(
            kind="expensive_planet",
            text=text,
            overlay=f"дорого · {short} · {amount}",
        )
