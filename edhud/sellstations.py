# Created by nc.ai 1.2.15 on Papasha 2026-11-15 17:07:32
"""Станции сбыта: ранг «цена × достижимость» по прыжковому радиусу.

Цены у нас — свой индекс (`prices.json`: журнал `Market` + поток EDDN
`commodity`). У станции из своего журнала есть координаты системы, у EDDN —
нет, поэтому для чужих станций расстояние считается только если координаты
системы уже известны (база Spansh / свой кэш систем).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import values


@dataclass
class SellChoice:
    """Куда везти: станция, система, цена и насколько это далеко."""

    commodity: str
    station: str
    system: str
    price: int
    distance_ly: float | None = None
    jumps: int | None = None
    score: float = 0.0

    def label(self) -> str:
        """«Station (System) — 1 200 000 cr · 45.2 ly · 3 jumps»."""
        from .i18n import jumps_word, t

        parts = [f"{self.station or '—'} ({self.system or '—'})", f"{values.credits(self.price)}"]
        if self.distance_ly is not None:
            parts.append(f"{self.distance_ly:.1f} ly")
        if self.jumps:
            parts.append(t("sell.jumps", n=self.jumps, word=jumps_word(self.jumps)))
        return " — ".join(parts[:1]) + " · " + " · ".join(parts[1:])


def _distance(a, b) -> float | None:
    if not a or not b:
        return None
    try:
        ax, ay, az = float(a[0]), float(a[1]), float(a[2])
        bx, by, bz = float(b[0]), float(b[1]), float(b[2])
    except (TypeError, ValueError, IndexError):
        return None
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2)


def rank(
    quotes,
    origin=None,
    jump_range: float | None = None,
) -> list[SellChoice]:
    """Отсортировать предложения сбыта: сначала выгодные и достижимые.

    Цена штрафуется за расстояние: одна прыжковая дистанция считается «за один
    прыжок» (`jump_range`, по умолчанию 20 ly).
    """
    step = float(jump_range or 20.0)
    if step <= 0:
        step = 20.0
    choices: list[SellChoice] = []
    for quote in quotes or []:
        price = int(getattr(quote, "price", 0) or 0)
        if price <= 0:
            continue
        distance = _distance(origin, getattr(quote, "coords", None))
        jumps = None
        if distance is not None:
            jumps = max(1, int(math.ceil(distance / step)))
        penalty = 1.0 + (jumps - 1) * 0.15 if jumps else 1.6  # неизвестно — считаем далёким
        choices.append(
            SellChoice(
                commodity=str(getattr(quote, "commodity", "") or ""),
                station=str(getattr(quote, "station", "") or ""),
                system=str(getattr(quote, "system", "") or ""),
                price=price,
                distance_ly=round(distance, 1) if distance is not None else None,
                jumps=jumps,
                score=price / penalty,
            )
        )
    choices.sort(key=lambda item: -item.score)
    return choices


def best_sell(price_index, commodity: str, origin=None, jump_range: float | None = None) -> SellChoice | None:
    """Лучшая станция сбыта для минерала (учитывая расстояние, если оно известно)."""
    if price_index is None or not commodity:
        return None
    getter = getattr(price_index, "top", None)
    if callable(getter):
        quotes = getter(commodity, limit=5)
    else:  # старый индекс — одно предложение
        quote = price_index.best(commodity)
        quotes = [quote] if quote is not None else []
    ranked = rank(quotes, origin, jump_range)
    return ranked[0] if ranked else None
