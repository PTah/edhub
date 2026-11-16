"""Обход всех систем в шаре: EDSM sphere-systems и замкнутый маршрут.

Каждая система внутри радиуса — один раз, последняя точка снова старт.
Точный коммивояжёр на сотнях систем не считается: ближайший сосед и 2-opt.
"""
from __future__ import annotations

import math
import urllib.parse
from dataclasses import dataclass

from .i18n import t

MAX_RADIUS_LY = 100.0
_TWO_OPT_FULL = 80
_TWO_OPT_SOME = 250


@dataclass
class SphereHop:
    name: str
    pos: tuple[float, float, float]
    star_class: str | None = None
    from_center: float = 0.0
    leg_ly: float = 0.0
    returning: bool = False
    address: int | None = None


def _star_class(primary) -> str | None:
    if not isinstance(primary, dict):
        return None
    raw = str(primary.get("type") or "").strip()
    if not raw:
        return None
    head = raw.split("(", 1)[0].strip()
    return head[:16] or None


def _address(raw: dict) -> int | None:
    value = raw.get("id64")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coords(raw: dict) -> tuple[float, float, float] | None:
    coords = raw.get("coords")
    if not isinstance(coords, dict):
        return None
    try:
        return (float(coords["x"]), float(coords["y"]), float(coords["z"]))
    except (KeyError, TypeError, ValueError):
        return None


def parse_sphere(
    rows,
    center_name: str,
    center_pos: tuple[float, float, float],
    radius_ly: float,
) -> list[SphereHop]:
    """Системы ответа EDSM внутри радиуса плюс центр в начале списка."""
    name = center_name.strip()
    center_key = name.lower()
    origin = (float(center_pos[0]), float(center_pos[1]), float(center_pos[2]))
    limit = float(radius_ly) + 1e-4
    found: list[SphereHop] = []
    seen = {center_key}
    center_class = None
    for raw in rows or []:
        if not isinstance(raw, dict):
            continue
        sys_name = str(raw.get("name") or "").strip()
        if not sys_name:
            continue
        key = sys_name.lower()
        pos = _coords(raw)
        if pos is None:
            continue
        if raw.get("distance") is not None:
            try:
                dist = float(raw["distance"])
            except (TypeError, ValueError):
                dist = math.dist(origin, pos)
        else:
            dist = math.dist(origin, pos)
        if key == center_key:
            center_class = _star_class(raw.get("primaryStar")) or center_class
            continue
        if key in seen or dist > limit:
            continue
        seen.add(key)
        found.append(
            SphereHop(
                name=sys_name,
                pos=pos,
                star_class=_star_class(raw.get("primaryStar")),
                from_center=dist,
                address=_address(raw),
            )
        )
    start = SphereHop(name=name, pos=origin, star_class=center_class, from_center=0.0)
    found.sort(key=lambda hop: (hop.from_center, hop.name.lower()))
    return [start, *found]


def _nearest_order(coords: list[tuple[float, float, float]]) -> list[int]:
    count = len(coords)
    if count <= 1:
        return list(range(count))
    left = set(range(1, count))
    order = [0]
    current = 0
    while left:
        cx, cy, cz = coords[current]
        best_i = 0
        best_d = float("inf")
        for index in left:
            x, y, z = coords[index]
            dist = (x - cx) * (x - cx) + (y - cy) * (y - cy) + (z - cz) * (z - cz)
            if dist < best_d:
                best_d = dist
                best_i = index
        order.append(best_i)
        left.remove(best_i)
        current = best_i
    return order


def _two_opt(coords: list[tuple[float, float, float]], order: list[int], passes: int) -> list[int]:
    count = len(order)
    if count < 4 or passes <= 0:
        return order
    points = [coords[index] for index in order]

    def dist(a: int, b: int) -> float:
        return math.dist(points[a], points[b])

    for _ in range(passes):
        best = 0.0
        move = None
        for i in range(1, count - 1):
            for k in range(i + 1, count):
                nxt = (k + 1) % count
                if nxt == i:
                    continue
                gain = dist(i - 1, i) + dist(k, nxt) - dist(i - 1, k) - dist(i, nxt)
                if gain > best + 1e-7:
                    best = gain
                    move = (i, k)
        if move is None:
            break
        i, k = move
        order[i : k + 1] = reversed(order[i : k + 1])
        points = [coords[index] for index in order]
    return order


def _passes(count: int) -> int:
    if count <= _TWO_OPT_FULL:
        return 30
    if count <= _TWO_OPT_SOME:
        return 8
    return 0


def plan_tour(systems: list[SphereHop]) -> list[SphereHop]:
    """Порядок обхода: старт, каждая система один раз, снова старт.

    Первая точка списка — центр шара. При одной системе возврат не дублируется.
    """
    if not systems:
        return []
    coords = [hop.pos for hop in systems]
    order = _two_opt(coords, _nearest_order(coords), _passes(len(systems)))
    tour = [systems[index] for index in order]
    if len(tour) > 1:
        start = tour[0]
        tour.append(
            SphereHop(
                name=start.name,
                pos=start.pos,
                star_class=start.star_class,
                from_center=0.0,
                returning=True,
                address=start.address,
            )
        )
    prev = None
    for hop in tour:
        hop.leg_ly = 0.0 if prev is None else math.dist(prev, hop.pos)
        prev = hop.pos
    return tour


def fetch_sphere(
    name: str,
    radius_ly: float,
    center: tuple[float, float, float] | None = None,
    timeout: float = 30.0,
) -> list[SphereHop]:
    """Системы в шаре вокруг `name`. Координаты центра — из игры или EDSM."""
    system = (name or "").strip()
    if not system:
        raise ValueError(t("sphere.need_system"))
    try:
        radius = float(radius_ly)
    except (TypeError, ValueError):
        raise ValueError(t("sphere.bad_radius")) from None
    if not math.isfinite(radius) or radius < 0.1 or radius > MAX_RADIUS_LY:
        raise ValueError(t("sphere.bad_radius"))
    if center is None:
        from .remote import system_coordinates

        center = system_coordinates(system, timeout=min(12.0, timeout))
    if not center or len(center) != 3:
        raise RuntimeError(t("sphere.no_coords"))
    query_r = int(min(MAX_RADIUS_LY, max(1, math.ceil(radius))))
    url = (
        "https://www.edsm.net/api-v1/sphere-systems?systemName="
        + urllib.parse.quote(system)
        + f"&radius={query_r}&showCoordinates=1&showPrimaryStar=1&showId=1"
    )
    from .remote import _http_json

    raw = _http_json(url, timeout=timeout)
    if raw is None:
        raise RuntimeError(t("sphere.offline"))
    if isinstance(raw, dict):
        message = raw.get("msg") or raw.get("error") or t("sphere.bad_reply")
        raise RuntimeError(str(message))
    if not isinstance(raw, list):
        raise RuntimeError(t("sphere.bad_reply"))
    return parse_sphere(raw, system, (float(center[0]), float(center[1]), float(center[2])), radius)
