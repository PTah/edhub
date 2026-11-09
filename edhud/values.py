# Edited by nc.ai 0.8.8.0 on macbook 2026-10-17 20:15:24
"""Стоимость скана тел и множители первооткрывателя.

Формула и множители — из темы «Exploration Value Formulae»
(forums.frontier.co.uk/threads/exploration-value-formulae.232000), порт
`Util.GetBodyValue` из SrvSurvey (GPLv3):

  value = (k + k*q*mass^0.2) * mappingMultiplier
  mappingMultiplier: 3.699622554 (первооткрыватель + первый картограф),
                     8.0956       (первый картограф),
                     3.3333333333 (картография не первая)
  + Odyssey-бонус (30 % или минимум 555) и +25 % за эффективный DSS
  не ниже 500, затем ×2.6 за первое открытие.
Звёзды считаются отдельно: kk + mass*kk/66.25 (без множителей).
"""
from __future__ import annotations

from dataclasses import dataclass

Q = 0.56591828
MAPPING_FIRST_DISCOVERER_AND_MAPPER = 3.699622554
MAPPING_FIRST_MAPPER = 8.0956
MAPPING_OTHER = 3.3333333333
DISCOVERY_MULTIPLIER = 2.6
ODYSSEY_MIN_BONUS = 555.0
EFFICIENCY_BONUS = 1.25
MIN_VALUE = 500.0

STAR_K = 1200.0
STAR_K_REMNANT = 22628.0
STAR_K_WOLF_RAYET = 14057.0

PLANET_K = {
    "Metal rich body": 21790.0,
    "Ammonia world": 96932.0,
    "Sudarsky class I gas giant": 1656.0,
    "Sudarsky class II gas giant": 9654.0,
    "High metal content body": 9654.0,
    "Water world": 64831.0,
}
ROCKY_K = 300.0

TERRAFORM_BONUS = {
    "High metal content body": 100677.0,
    "Sudarsky class II gas giant": 100677.0,
    "Water world": 116295.0,
    "Rocky body": 93328.0,
}
EARTHLIKE_K = 64831.0 + 116295.0

STAR_TYPES_REMNANT = {"N", "H", "NS", "BH", "SupermassiveBlackHole"}
STAR_TYPES_NON_SEQUENCE = {"Nebula", "StellarRemnantNebula"}


def is_star_class(name: str | None) -> bool:
    """Отличает класс звезды ("K", "TTS", "N") от класса планеты ("Icy body")."""
    if not name:
        return False
    return len(name) < 8 or name[1:2] == "_" or name in STAR_TYPES_REMNANT | STAR_TYPES_NON_SEQUENCE


def star_k(star_class: str | None) -> float:
    if not star_class:
        return STAR_K
    if star_class[0] == "W":
        return STAR_K_WOLF_RAYET
    if star_class in STAR_TYPES_REMNANT:
        return STAR_K_REMNANT
    return STAR_K


def planet_k(planet_class: str | None, terraformable: bool = False) -> float:
    name = planet_class or ""
    if name.startswith("Earth"):
        return EARTHLIKE_K
    base = PLANET_K.get(name)
    if base is None:
        base = ROCKY_K
    if terraformable:
        base += TERRAFORM_BONUS.get(name, TERRAFORM_BONUS["Rocky body"])
    return base


def _mapping_multiplier(first_discoverer: bool, first_mapper: bool) -> float:
    if first_discoverer and first_mapper:
        return MAPPING_FIRST_DISCOVERER_AND_MAPPER
    if first_mapper:
        return MAPPING_FIRST_MAPPER
    return MAPPING_OTHER


def body_value(
    planet_class: str | None,
    mass: float,
    terraformable: bool = False,
    first_discoverer: bool = False,
    mapped: bool = False,
    first_mapper: bool = False,
    odyssey: bool = True,
    efficiency_bonus: bool = True,
) -> int:
    """Стоимость одного тела (cr) со всеми множителями."""
    if is_star_class(planet_class):
        kk = star_k(planet_class)
        return int(round(kk + (mass or 0.0) * kk / 66.25))

    k = planet_k(planet_class, terraformable)
    multiplier = _mapping_multiplier(first_discoverer, first_mapper) if mapped else 1.0
    value = (k + k * Q * max(mass or 0.0, 0.0) ** 0.2) * multiplier
    if mapped:
        if odyssey:
            bonus = value * 0.3
            value += bonus if bonus > ODYSSEY_MIN_BONUS else ODYSSEY_MIN_BONUS
        if efficiency_bonus:
            value *= EFFICIENCY_BONUS
    value = max(MIN_VALUE, value)
    if first_discoverer:
        value *= DISCOVERY_MULTIPLIER
    return int(round(value))


@dataclass(frozen=True)
class ValueBreakdown:
    scan: int  # цена скана (без DSS)
    mapped: int  # цена после DSS (с нашими множителями)
    first_discoverer: bool
    first_mapper: bool
    star: bool

    @property
    def discovery_multiplier(self) -> float:
        return DISCOVERY_MULTIPLIER if self.first_discoverer else 1.0


def _mass_of(body) -> float:
    if getattr(body, "is_star", False) or getattr(body, "star_type", None):
        return float(getattr(body, "stellar_mass", 0.0) or getattr(body, "mass_em", 0.0) or 0.0)
    return float(getattr(body, "mass_em", 0.0) or 0.0)


def _class_of(body) -> str | None:
    if getattr(body, "is_star", False) or getattr(body, "star_type", None):
        return getattr(body, "star_type", None)
    return getattr(body, "planet_class", None)


def body_values(body, mapped: bool | None = None, odyssey: bool = True) -> ValueBreakdown | None:
    """Стоимость тела по данным журнала. None — если нечего считать."""
    planet_class = _class_of(body)
    if not planet_class:
        return None
    mass = _mass_of(body)
    if mass <= 0:
        return None
    terraformable = (getattr(body, "terraform_state", None) or "") == "Terraformable"
    first_discoverer = not bool(getattr(body, "was_discovered", False))
    # для тел, известных только по данным других командиров, не считаем себя первым картографом
    first_mapper = not bool(getattr(body, "was_mapped", False)) and not bool(getattr(body, "remote", False))
    scan = body_value(
        planet_class,
        mass,
        terraformable=terraformable,
        first_discoverer=first_discoverer,
        mapped=False,
    )
    mapped_value = body_value(
        planet_class,
        mass,
        terraformable=terraformable,
        first_discoverer=first_discoverer,
        mapped=True,
        first_mapper=first_mapper,
        odyssey=odyssey,
        efficiency_bonus=True,
    )
    return ValueBreakdown(
        scan=scan,
        mapped=mapped_value,
        first_discoverer=first_discoverer,
        first_mapper=first_mapper,
        star=is_star_class(planet_class),
    )


def body_current_value(body, odyssey: bool = True) -> ValueBreakdown | None:
    """Что мы получим за это тело сейчас: скан или скан+DSS, если уже картографировали."""
    return body_values(body, odyssey=odyssey)


def system_totals(system, odyssey: bool = True) -> tuple[int, int]:
    """(сумма сканов, сумма сканов с DSS) по всем телам системы."""
    scan_sum = 0
    mapped_sum = 0
    for body in getattr(system, "bodies", {}).values():
        values = body_values(body, odyssey=odyssey)
        if values is None:
            continue
        scan_sum += values.scan
        mapped_sum += values.mapped
    return scan_sum, mapped_sum


def credits(value: int | None) -> str:
    """Полная сумма кредитов с разделителем тысяч: 7 006 / 2 500 000."""
    if not value:
        return "—"
    return f"{int(value):,}".replace(",", " ")
