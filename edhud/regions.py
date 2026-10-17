"""Галактические регионы.

Данные: data/galaxy_regions.json — сжатая (RLE) карта регионов из
klightspeed/EliteDangerousRegionMap (через SrvSurvey). Регион определяется по
координатам x/z системы: карта разбита на 2048 строк по оси z, каждая строка —
набор отрезков (длина, id региона) по оси x.

Плюс таблица «рукав/группа -> id регионов», чтобы понимать клаузы вида
`regions [Orion-CygnusArm,CentreLeft]` в критериях биологии.
"""
from __future__ import annotations

import json
from functools import lru_cache

from . import config

# Из SrvSurvey/game/Data.cs (mapArmRegions) — сгруппированные регионы.
GROUP_TO_REGIONS: dict[str, tuple[int, ...]] = {
    "Orion-CygnusArm": (7, 8, 16, 17, 18, 35),
    "OuterArm": (5, 6, 13, 14, 27, 29, 31, 41, 37),
    "Scutum-CentaurusArm": (9, 10, 11, 12, 24, 25, 26, 42, 28),
    "PerseusArm": (15, 30, 32, 33, 34, 36, 38, 39),
    "Sagittarius-CarinaArm": (9, 18, 19, 20, 21, 22, 23, 40),
    "CentreLeft": (1, 4),
    "CentreTop": (1, 3, 7),
    "CentreRight": (1, 2),
    "AmphoraBatch": (10, 19, 20, 21, 22),
    "AnemoneBatch": (7, 8, 9, 13, 14, 15, 16, 17, 18, 27, 31),
    "BarkMoundBatch": (4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 15, 16, 17, 18, 19, 20, 25, 32, 33, 34),
    "BrainTreeBatch": (2, 9, 10, 17, 18, 35),
    "TubersBatch": (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 18, 19),
    "ShardBatch": (14, 21, 22, 23, 24, 25, 26, 27, 28, 29, 31, 34, 36, 37, 38, 39, 40, 41, 42),
}

# Журнал/критерии иногда пишут имена с пробелами и апострофами.
_ALIASES = {
    "Orion-Cygnus Arm": "Orion-CygnusArm",
    "Outer Arm": "OuterArm",
    "Scutum-Centaurus Arm": "Scutum-CentaurusArm",
    "Perseus Arm": "PerseusArm",
    "Sagittarius-Carina Arm": "Sagittarius-CarinaArm",
    "Inner Orion Spur": None,
}


@lru_cache(maxsize=1)
def _map() -> dict:
    path = config.data_dir() / "galaxy_regions.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"names": [], "rows": [], "x0": -49985, "z0": -24105, "scale": 83 / 4096}


def region_name(region_id: int | None) -> str:
    names = _map().get("names") or []
    if region_id is None or region_id <= 0 or region_id >= len(names):
        return "Unknown"
    return names[region_id] or "Unknown"


def region_id(x: float, z: float) -> int | None:
    """id галактического региона по координатам системы (0 = нет данных)."""
    m = _map()
    rows = m.get("rows") or []
    if not rows:
        return None
    scale = m.get("scale") or 83 / 4096
    px = int((x - m["x0"]) * scale)
    pz = int((z - m["z0"]) * scale)
    if px < 0 or pz < 0 or pz >= len(rows):
        return None
    rx = 0
    value = 0
    for length, rid in rows[pz]:
        if px < rx + length:
            value = rid
            break
        rx += length
    return value or None


def group_regions(name: str) -> tuple[int, ...] | None:
    """id регионов для «рукава»/группы (или None, если имя не распознано)."""
    if name in GROUP_TO_REGIONS:
        return GROUP_TO_REGIONS[name]
    alias = _ALIASES.get(name)
    if alias and alias in GROUP_TO_REGIONS:
        return GROUP_TO_REGIONS[alias]
    compact = name.replace(" ", "").replace("'", "")
    for key, value in GROUP_TO_REGIONS.items():
        if key.lower() == compact.lower():
            return value
    return None
