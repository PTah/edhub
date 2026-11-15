# Created by nc.ai 1.2.15 on Papasha 2026-11-15 16:09:12
"""Кэш хотспотов колец: всё, что игра рассказала про кольца, в одном JSON.

Spansh и EDSM в своих API по кольцам отдают только тип/массу/радиус — хотспотов
там нет вообще, поэтому вопрос «где александрит в 40 ly» по чужим данным не
решается. Зато решается по своим: каждый `SAASignalsFound` с минералом кольца
складывается в `hotspots.json` (%LOCALAPPDATA%/EliteDangerousHUD), и дальше
поиск по минералу и расстоянию идёт по этой базе.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import config, mining


@dataclass
class RingHotspots:
    """Кольцо (или тело с кольцами) и его хотспоты."""

    system: str
    body_name: str
    body_id: int
    hotspots: dict[str, int] = field(default_factory=dict)
    address: int | None = None
    planet_class: str | None = None
    ring_types: list[str] = field(default_factory=list)
    star_pos: list[float] | None = None
    distance_ls: float | None = None
    reserve_level: str | None = None
    density: float | None = None
    updated_at: float = 0.0

    def key(self) -> str:
        if self.address is not None:
            return f"{int(self.address)}:{int(self.body_id)}"
        return f"{(self.system or '').strip().lower()}:{int(self.body_id)}"

    def minerals_label(self) -> str:
        return mining.format_hotspots(self.hotspots)

    def signature(self) -> tuple:
        """Что именно поменялось — чтобы не перезаписывать файл зря."""
        return (
            (self.system or "").lower(),
            int(self.body_id or 0),
            tuple(sorted((str(k), int(v or 0)) for k, v in self.hotspots.items())),
            tuple(self.ring_types or ()),
        )

    def to_persist(self) -> dict:
        return asdict(self)

    @classmethod
    def from_persist(cls, data: dict) -> "RingHotspots":
        hotspots = {
            str(k).strip(): int(v or 0)
            for k, v in (data.get("hotspots") or {}).items()
            if str(k).strip()
        }
        rings = [str(kind) for kind in (data.get("ring_types") or []) if str(kind).strip()]
        pos = data.get("star_pos")
        star_pos = None
        if isinstance(pos, (list, tuple)) and len(pos) == 3:
            try:
                star_pos = [float(pos[0]), float(pos[1]), float(pos[2])]
            except (TypeError, ValueError):
                star_pos = None
        address = data.get("address")
        try:
            address = int(address) if address is not None else None
        except (TypeError, ValueError):
            address = None
        try:
            body_id = int(data.get("body_id") or 0)
        except (TypeError, ValueError):
            body_id = 0
        distance_ls = data.get("distance_ls")
        try:
            distance_ls = float(distance_ls) if distance_ls is not None else None
        except (TypeError, ValueError):
            distance_ls = None
        return cls(
            system=str(data.get("system") or ""),
            body_name=str(data.get("body_name") or ""),
            body_id=body_id,
            hotspots=hotspots,
            address=address,
            planet_class=(str(data["planet_class"]) if data.get("planet_class") else None),
            ring_types=rings,
            star_pos=star_pos,
            distance_ls=distance_ls,
            reserve_level=(str(data["reserve_level"]) if data.get("reserve_level") else None),
            density=_as_float(data.get("density")),
            updated_at=float(data.get("updated_at") or 0.0),
        )


@dataclass
class NearRing:
    """Найденное кольцо плюс расстояние от точки отсчёта."""

    ring: RingHotspots
    distance_ly: float | None = None


def distance_ly(a, b) -> float | None:
    """Расстояние между двумя StarPos, ly. None, если координат нет."""
    if not a or not b:
        return None
    try:
        ax, ay, az = float(a[0]), float(a[1]), float(a[2])
        bx, by, bz = float(b[0]), float(b[1]), float(b[2])
    except (TypeError, ValueError, IndexError):
        return None
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2)


class HotspotStore:
    """JSON-база хотспотов: %LOCALAPPDATA%/EliteDangerousHUD/hotspots.json."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else config.app_dir() / "hotspots.json"
        self._items: dict[str, RingHotspots] = {}
        self._local_signature: tuple | None = None
        self.load()

    # ---------------------------------------------------------------- файл
    def load(self) -> None:
        self._items = {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        rows = raw.get("rings") if isinstance(raw, dict) else raw
        if not isinstance(rows, list):
            return
        for item in rows:
            if not isinstance(item, dict):
                continue
            try:
                ring = RingHotspots.from_persist(item)
            except (TypeError, ValueError, KeyError):
                continue
            if ring.system and ring.hotspots:
                self._items[ring.key()] = ring

    def save(self) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": 1,
                "rings": [ring.to_persist() for ring in self._items.values()],
            }
            self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
            return True
        except OSError:
            return False

    # --------------------------------------------------------------- данные
    def list(self) -> list[RingHotspots]:
        return list(self._items.values())

    def upsert(self, ring: RingHotspots, *, save: bool = True) -> RingHotspots:
        if not ring.updated_at:
            ring.updated_at = time.time()
        self._items[ring.key()] = ring
        if save:
            self.save()
        return ring

    def remove(self, key: str) -> bool:
        if key not in self._items:
            return False
        del self._items[key]
        self.save()
        return True

    def __len__(self) -> int:
        return len(self._items)

    # ---------------------------------------------------------------- поиск
    def search(
        self,
        origin: list[float] | tuple[float, ...] | None = None,
        radius_ly: float | None = None,
        mineral: str | None = None,
        limit: int = 400,
    ) -> list[NearRing]:
        """Кольца с минералом в радиусе от origin; сначала близкие и дорогие."""
        want = (mineral or "").strip().lower()
        hits: list[NearRing] = []
        for ring in self._items.values():
            if want and not self._has_mineral(ring, want):
                continue
            dist = distance_ly(origin, ring.star_pos) if origin else None
            if radius_ly is not None and dist is not None and dist > float(radius_ly):
                continue
            if radius_ly is not None and dist is None and origin:
                # без координат радиус не проверить — такие кольца не показываем
                continue
            hits.append(NearRing(ring=ring, distance_ly=dist))
        hits.sort(
            key=lambda hit: (
                hit.distance_ly if hit.distance_ly is not None else 9e9,
                -mining.hotspot_avg_price(self._top_mineral(hit.ring, want)),
            )
        )
        return hits[: max(1, int(limit))]

    def count_by_mineral(self, mineral: str) -> int:
        want = (mineral or "").strip().lower()
        if not want:
            return len(self._items)
        return sum(1 for ring in self._items.values() if self._has_mineral(ring, want))

    # ------------------------------------------------------------- из журнала
    def harvest(self, state) -> int:
        """Сложить в базу кольца текущей системы из состояния игры.

        Возвращает число обновлённых записей; 0 — если ничего не поменялось
        (частый случай, файл не перезаписываем).
        """
        system = getattr(state, "system", None)
        if system is None:
            return 0
        bodies = getattr(system, "bodies", None) or {}
        pos = getattr(system, "star_pos", None)
        signature = tuple(
            sorted(
                (int(getattr(body, "body_id", 0) or 0), tuple(sorted((getattr(body, "hotspots", None) or {}).items())))
                for body in bodies.values()
                if getattr(body, "hotspots", None)
            )
        )
        if signature == self._local_signature:
            return 0
        self._local_signature = signature
        if not signature:
            return 0

        changed = 0
        for body in bodies.values():
            hotspots = {str(k): int(v or 0) for k, v in (getattr(body, "hotspots", None) or {}).items()}
            if not hotspots:
                continue
            ring = RingHotspots(
                system=system.name or "",
                body_name=getattr(body, "name", "") or f"Body {getattr(body, 'body_id', 0)}",
                body_id=int(getattr(body, "body_id", 0) or 0),
                hotspots=hotspots,
                address=int(system.address) if getattr(system, "address", None) is not None else None,
                planet_class=getattr(body, "planet_class", None),
                ring_types=_ring_types(body),
                star_pos=[float(pos[0]), float(pos[1]), float(pos[2])] if pos and len(pos) == 3 else None,
                distance_ls=_as_float(getattr(body, "distance_ls", None)),
                reserve_level=(getattr(body, "reserve_level", None) or None),
                density=getattr(body, "ring_density", None),
            )
            old = self._items.get(ring.key())
            if old is not None and old.signature() == ring.signature():
                # обновим только координаты/расстояние, если их не было
                if old.star_pos == ring.star_pos and old.distance_ls == ring.distance_ls:
                    continue
                ring.updated_at = old.updated_at
            self._items[ring.key()] = ring
            changed += 1
        if changed:
            self.save()
        return changed

    # ------------------------------------------------------------- служебное
    @staticmethod
    def _has_mineral(ring: RingHotspots, want: str) -> bool:
        return any(name.lower() == want for name in ring.hotspots)

    @staticmethod
    def _top_mineral(ring: RingHotspots, want: str) -> str:
        if want:
            for name in ring.hotspots:
                if name.lower() == want:
                    return name
        rows = mining.sorted_hotspots(ring.hotspots)
        return rows[0][0] if rows else ""


def _as_float(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _ring_types(body) -> list[str]:
    """Типы колец тела: «Icy», «Metallic» — из скана (`Body.ring_types`)."""
    kinds: list[str] = []
    for kind in getattr(body, "ring_types", None) or []:
        text = str(kind or "").strip()
        if text and text not in kinds:
            kinds.append(text)
    return kinds
