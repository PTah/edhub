# Created by nc.ai 1.2.15 on Papasha 2026-11-15 12:12:05
"""Поиск тел для планетарной и кольцевой добычи через Spansh.

Spansh отдаёт тела с сигналами (`Planetary Mining Location`, `Geological`,
`Biological`), составом поверхности (`materials`, доли в процентах) и кольцами.
Фильтры по материалам/сигналам на стороне Spansh не работают (проверено:
запрос с фильтром возвращает то же, что и без него), поэтому:

* радиус и сортировка по расстоянию — на стороне Spansh (это работает);
* выбор «где есть чем копать» и сортировка по доле материала — у нас.

Ответ `POST /api/bodies/search` синхронный: результат приходит сразу, без job-id.
Страницы ограничены `size` (500 — максимум, что реально отдаётся).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

from .mining import SURFACE_SITE_SIGNALS, material_grade

SEARCH_URL = "https://spansh.co.uk/api/bodies/search"
MAX_SIZE = 500
MAX_PAGES = 12


class SpanshError(RuntimeError):
    """Сеть/ответ Spansh не в порядке."""


@dataclass
class RemoteBody:
    """Тело из индекса Spansh — только то, что нужно вкладке «Добыча»."""

    system: str
    name: str
    distance_ly: float = 0.0
    distance_ls: float | None = None
    subtype: str | None = None
    signals: dict[str, int] = field(default_factory=dict)
    materials: dict[str, float] = field(default_factory=dict)
    ring_types: list[str] = field(default_factory=list)
    is_landable: bool = False
    body_id: int | None = None
    address: int | None = None

    # ------------------------------------------------------------- признаки
    def surface_signals(self) -> list[tuple[str, int]]:
        return [(name, count) for name, count in self.signals.items() if name in SURFACE_SITE_SIGNALS]

    def has_surface_site(self) -> bool:
        return bool(self.surface_signals())

    def share(self, material: str | None) -> float:
        if not material:
            return 0.0
        return float(self.materials.get(material) or 0.0)

    def best_material(self) -> tuple[str, float] | None:
        """Самое дорогое по грейду сырьё поверхности (грейд, затем доля)."""
        if not self.materials:
            return None
        rows = sorted(
            self.materials.items(),
            key=lambda item: (-material_grade(item[0]), -float(item[1] or 0.0), item[0].lower()),
        )
        name, share = rows[0]
        return str(name), float(share or 0.0)

    def signals_label(self) -> str:
        return ", ".join(f"{name} ×{count}" for name, count in self.surface_signals()) or "—"


def _float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def parse_body(raw: dict) -> RemoteBody | None:
    """Одно тело из ответа Spansh; None если это не тело (звезда/непонятно)."""
    if not isinstance(raw, dict):
        return None
    name = raw.get("name")
    system = raw.get("system_name")
    if not isinstance(name, str) or not name:
        return None
    signals: dict[str, int] = {}
    for item in raw.get("signals") or []:
        if not isinstance(item, dict):
            continue
        signal_name = item.get("name")
        if isinstance(signal_name, str) and signal_name:
            signals[signal_name] = int(item.get("count") or 0)
    materials: dict[str, float] = {}
    for item in raw.get("materials") or []:
        if not isinstance(item, dict):
            continue
        material = item.get("name")
        if isinstance(material, str) and material:
            materials[material] = _float(item.get("share"))
    ring_types: list[str] = []
    for ring in raw.get("rings") or []:
        if isinstance(ring, dict):
            kind = ring.get("type")
            if isinstance(kind, str) and kind and kind not in ring_types:
                ring_types.append(kind)
    return RemoteBody(
        system=str(system or ""),
        name=name,
        distance_ly=_float(raw.get("distance")),
        distance_ls=_float(raw.get("distance_to_arrival")) or None,
        subtype=(str(raw["subtype"]) if raw.get("subtype") else None),
        signals=signals,
        materials=materials,
        ring_types=ring_types,
        is_landable=bool(raw.get("is_landable")),
        body_id=int(raw["body_id"]) if raw.get("body_id") is not None else None,
        address=int(raw["system_id64"]) if raw.get("system_id64") is not None else None,
    )


def parse_bodies(payload: dict) -> list[RemoteBody]:
    bodies: list[RemoteBody] = []
    for raw in (payload or {}).get("results") or []:
        body = parse_body(raw)
        if body is not None:
            bodies.append(body)
    return bodies


def _post(payload: dict, timeout: float = 30.0) -> dict:
    request = urllib.request.Request(
        SEARCH_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "EDHUD"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise SpanshError(f"{type(exc).__name__}: {exc}") from exc


def search_bodies(
    reference: str,
    radius_ly: float = 25.0,
    *,
    pages: int = 4,
    size: int = MAX_SIZE,
    timeout: float = 30.0,
    on_page: Callable[[int, int], None] | None = None,
) -> list[RemoteBody]:
    """Тела в радиусе `radius_ly` от системы `reference`, постранично.

    Возвращает до `pages * size` ближайших тел; фильтрация — на вызывающей
    стороне (`pick_surface` / `pick_rings`).
    """
    system = (reference or "").strip()
    if not system:
        raise SpanshError("не указана система")
    size = max(1, min(int(size), MAX_SIZE))
    pages = max(1, min(int(pages), MAX_PAGES))
    found: list[RemoteBody] = []
    seen: set[str] = set()
    for page in range(pages):
        payload = {
            "filters": {},
            "reference_system": system,
            "radius": float(radius_ly),
            "size": size,
            "page": page,
            "sort": [{"distance": {"direction": "asc"}}],
        }
        batch = parse_bodies(_post(payload, timeout=timeout))
        fresh = 0
        for body in batch:
            key = f"{body.address}:{body.body_id}:{body.name}"
            if key in seen:
                continue
            seen.add(key)
            found.append(body)
            fresh += 1
        if on_page is not None:
            on_page(page + 1, len(found))
        if fresh == 0:
            break
    return found


def pick_surface(
    bodies: list[RemoteBody],
    material: str | None = None,
    *,
    min_share: float = 0.0,
    only_landable: bool = True,
) -> list[RemoteBody]:
    """Тела с точками поверхностной добычи, сначала где материала больше."""
    picked: list[RemoteBody] = []
    for body in bodies:
        if only_landable and not body.is_landable:
            continue
        if not body.has_surface_site():
            continue
        if material and body.share(material) < float(min_share):
            continue
        picked.append(body)
    if material:
        picked.sort(key=lambda body: (-body.share(material), body.distance_ly, body.name.lower()))
    else:
        picked.sort(key=lambda body: (body.distance_ly, body.name.lower()))
    return picked


def pick_rings(bodies: list[RemoteBody], system: str = "") -> list[RemoteBody]:
    """Тела с кольцами (там добывают минералы-товары)."""
    picked = [body for body in bodies if body.ring_types]
    if system:
        wanted = system.strip().lower()
        picked.sort(key=lambda body: (body.system.lower() != wanted, body.distance_ly, body.name.lower()))
    else:
        picked.sort(key=lambda body: (body.distance_ly, body.system.lower(), body.name.lower()))
    return picked
