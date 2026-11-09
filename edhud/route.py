"""Маршрут: NavRoute.json игры, заблокированный/импортированный маршрут, прогресс.

Идея как в EDEB (Exploration Buddy): маршрут берётся из игры, но его можно
«залочить» (заморозить копию), экспортировать/импортировать и подсунуть
маршрут плоттера — оверлей при этом продолжает показывать прогресс по залоченной
копии, даже если в игре задан другой маршрут.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

SCOOPABLE = set("KGBFOAM")


@dataclass
class RouteHop:
    system: str
    address: int | None = None
    star_pos: tuple[float, float, float] | None = None
    star_class: str | None = None
    distance: float = 0.0  # расстояние до предыдущей точки маршрута, св. лет
    jumps: int = 0  # сколько обычных прыжков до этой точки (маршрут плоттера)
    neutron: bool = False
    # кто открыл систему (EDSM); discovered_by_me — открыли мы
    discovered_by: str | None = None
    discovered_by_me: bool = False
    # состав по EDSM (до визита); None = ещё не спрашивали
    edsm_stars: int | None = None
    edsm_planets: int | None = None
    edsm_bodies: int | None = None
    edsm_missing: bool = False  # системы нет в EDSM

    def to_dict(self) -> dict:
        return {
            "system": self.system,
            "address": self.address,
            "star_pos": list(self.star_pos) if self.star_pos else None,
            "star_class": self.star_class,
            "jumps": self.jumps,
            "neutron": self.neutron,
            "discovered_by": self.discovered_by,
            "discovered_by_me": self.discovered_by_me,
            "edsm_stars": self.edsm_stars,
            "edsm_planets": self.edsm_planets,
            "edsm_bodies": self.edsm_bodies,
            "edsm_missing": self.edsm_missing,
        }

    def opened_label(self) -> str:
        from .i18n import t

        if self.discovered_by_me:
            return t("route.your_discovery")
        if self.discovered_by:
            return self.discovered_by
        return "—"

    def bodies_label(self) -> str:
        """Краткий состав системы для колонки Route (данные EDSM)."""
        from .i18n import t

        if self.edsm_missing:
            return t("route.not_in_edsm")
        if self.edsm_stars is None and self.edsm_planets is None:
            return "—"
        parts: list[str] = []
        if self.edsm_stars:
            parts.append(f"★{self.edsm_stars}")
        if self.edsm_planets:
            parts.append(t("route.planets", n=self.edsm_planets))
        if not parts and (self.edsm_bodies or 0) > 0:
            parts.append(t("route.n_bodies", n=self.edsm_bodies))
        return " · ".join(parts) if parts else "—"

    @property
    def scoopable(self) -> bool:
        if not self.star_class:
            return False
        return self.star_class[0].upper() in SCOOPABLE


def _pos(value) -> tuple[float, float, float] | None:
    if isinstance(value, (list, tuple)) and len(value) == 3:
        try:
            return (float(value[0]), float(value[1]), float(value[2]))
        except (TypeError, ValueError):
            return None
    return None


def distance_ly(a: tuple[float, float, float] | None, b: tuple[float, float, float] | None) -> float:
    if not a or not b:
        return 0.0
    return math.dist(a, b)


@dataclass
class Route:
    hops: list[RouteHop] = field(default_factory=list)
    source: str = "game"  # game | locked | import | plotter
    locked: bool = False

    # ------------------------------------------------------------- загрузка
    @classmethod
    def from_navroute(cls, data: dict | None) -> "Route":
        hops: list[RouteHop] = []
        for raw in (data or {}).get("Route") or []:
            name = raw.get("StarSystem")
            if not name:
                continue
            hops.append(
                RouteHop(
                    system=name,
                    address=raw.get("SystemAddress"),
                    star_pos=_pos(raw.get("StarPos")),
                    star_class=raw.get("StarClass"),
                )
            )
        route = cls(hops=hops, source="game")
        route._recalc()
        return route

    @classmethod
    def load(cls, path: Path) -> "Route":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "Route":
        hops = [
            RouteHop(
                system=h["system"],
                address=h.get("address"),
                star_pos=_pos(h.get("star_pos")),
                star_class=h.get("star_class"),
                jumps=int(h.get("jumps") or 0),
                neutron=bool(h.get("neutron")),
                discovered_by=h.get("discovered_by"),
                discovered_by_me=bool(h.get("discovered_by_me")),
                edsm_stars=h.get("edsm_stars"),
                edsm_planets=h.get("edsm_planets"),
                edsm_bodies=h.get("edsm_bodies"),
                edsm_missing=bool(h.get("edsm_missing")),
            )
            for h in data.get("hops") or []
            if h.get("system")
        ]
        route = cls(hops=hops, source=data.get("source", "import"), locked=bool(data.get("locked", True)))
        route._recalc()
        return route

    @classmethod
    def from_spansh(cls, result: dict, source: str = "plotter") -> "Route":
        """Маршрут из ответа Galaxy Plotter (spansh.co.uk/api/route)."""
        hops: list[RouteHop] = []
        for raw in result.get("system_jumps") or []:
            name = raw.get("system")
            if not name:
                continue
            pos = None
            if all(raw.get(k) is not None for k in ("x", "y", "z")):
                pos = (float(raw["x"]), float(raw["y"]), float(raw["z"]))
            hops.append(
                RouteHop(
                    system=name,
                    address=raw.get("id64"),
                    star_pos=pos,
                    jumps=int(raw.get("jumps") or 0),
                    neutron=bool(raw.get("neutron_star")),
                )
            )
        route = cls(hops=hops, source=source, locked=True)
        route._recalc()
        return route

    @classmethod
    def from_names(cls, names: list[str], source: str = "import") -> "Route":
        route = cls(hops=[RouteHop(system=n.strip()) for n in names if n.strip()], source=source, locked=True)
        route._recalc()
        return route

    def _recalc(self) -> None:
        prev = None
        for hop in self.hops:
            hop.distance = distance_ly(prev, hop.star_pos) if prev and hop.star_pos else 0.0
            prev = hop.star_pos

    # ------------------------------------------------------------- состояние
    def to_dict(self) -> dict:
        return {"source": self.source, "locked": self.locked, "hops": [h.to_dict() for h in self.hops]}

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def __bool__(self) -> bool:
        return bool(self.hops)

    def __len__(self) -> int:
        return len(self.hops)

    @property
    def total_jumps(self) -> int:
        total = sum(hop.jumps for hop in self.hops)
        return total or len(self.hops)

    # ------------------------------------------------------------- прогресс
    def index_of(self, system: str | None) -> int | None:
        if not system:
            return None
        for i, hop in enumerate(self.hops):
            if hop.system.lower() == system.lower():
                return i
        return None

    def next_hop(self, system: str | None) -> RouteHop | None:
        idx = self.index_of(system)
        if idx is None:
            return self.hops[0] if self.hops else None
        if idx + 1 < len(self.hops):
            return self.hops[idx + 1]
        return None

    def remaining(self, system: str | None) -> int:
        idx = self.index_of(system)
        if idx is None:
            return len(self.hops)
        return max(0, len(self.hops) - 1 - idx)

    def distance_remaining(self, system: str | None, pos: tuple[float, float, float] | None = None) -> float:
        idx = self.index_of(system)
        start = idx + 1 if idx is not None else 0
        total = 0.0
        prev = pos if pos else (self.hops[idx].star_pos if idx is not None else None)
        for hop in self.hops[start:]:
            total += distance_ly(prev, hop.star_pos)
            prev = hop.star_pos
        return total

    def progress(self, system: str | None) -> tuple[int, int]:
        """(пройдено, всего) в шагах маршрута — для полоски прогресса."""
        if not self.hops:
            return (0, 0)
        idx = self.index_of(system)
        if idx is None:
            return (0, len(self.hops))
        return (idx, max(1, len(self.hops) - 1))


def parse_route_text(text: str) -> list[str]:
    """Импорт маршрута из текста/CSV: по одному имени системы на строку.

    Понимает выгрузки Galaxy Plotter (CSV с колонкой System / system) и просто
    список систем. Строки-комментарии (#) и заголовки пропускаются.
    """
    names: list[str] = []
    seen: set[str] = set()
    column = 0  # индекс колонки с именем системы в CSV

    def add(name: str) -> None:
        name = name.strip().strip('"')
        if name and name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        if "," in line:
            parts = [p.strip().strip('"') for p in line.split(",")]
            lower = [p.lower() for p in parts]
            if "system" in lower:  # это заголовок CSV
                column = lower.index("system")
                continue
            add(parts[column] if column < len(parts) else "")
        else:
            add(line)
    return names
