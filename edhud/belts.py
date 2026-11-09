"""Сохранённые пояса/кольца с hotspot-минералами (локальная база EDHUD)."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import config
from .mining import format_hotspots, sorted_hotspots


@dataclass
class SavedBelt:
    system: str
    body_id: int
    body_name: str
    hotspots: dict[str, int] = field(default_factory=dict)
    address: int | None = None
    planet_class: str | None = None
    star_pos: list[float] | None = None
    saved_at: float = 0.0
    rings_mapped: bool = True

    def key(self) -> str:
        if self.address is not None:
            return f"{int(self.address)}:{int(self.body_id)}"
        return f"{(self.system or '').strip().lower()}:{int(self.body_id)}"

    def minerals_label(self) -> str:
        return format_hotspots(self.hotspots)

    def estimate_cr(self) -> int:
        """Грубая оценка: Σ (ср.цена × число hotspot)."""
        total = 0
        for name, count, price in sorted_hotspots(self.hotspots):
            total += int(price) * max(1, int(count or 0))
        return total

    def to_persist(self) -> dict:
        return asdict(self)

    @classmethod
    def from_persist(cls, data: dict) -> "SavedBelt":
        hotspots = data.get("hotspots") or {}
        cleaned = {str(k): int(v or 0) for k, v in hotspots.items() if str(k).strip()}
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
        return cls(
            system=str(data.get("system") or ""),
            body_id=int(data.get("body_id") or 0),
            body_name=str(data.get("body_name") or ""),
            hotspots=cleaned,
            address=address,
            planet_class=(str(data["planet_class"]) if data.get("planet_class") else None),
            star_pos=star_pos,
            saved_at=float(data.get("saved_at") or 0.0),
            rings_mapped=bool(data.get("rings_mapped", True)),
        )


class BeltStore:
    """JSON-база поясов: %LOCALAPPDATA%/EliteDangerousHUD/belts.json."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else config.app_dir() / "belts.json"
        self._items: dict[str, SavedBelt] = {}
        self.load()

    def load(self) -> None:
        self._items = {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        rows = raw.get("belts") if isinstance(raw, dict) else raw
        if not isinstance(rows, list):
            return
        for item in rows:
            if not isinstance(item, dict):
                continue
            try:
                belt = SavedBelt.from_persist(item)
            except (TypeError, ValueError, KeyError):
                continue
            if belt.system and belt.hotspots:
                self._items[belt.key()] = belt

    def save(self) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": 1,
                "belts": [b.to_persist() for b in self.list()],
            }
            self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
        except OSError:
            return False

    def list(self) -> list[SavedBelt]:
        """Сначала дороже по оценке, затем новее."""
        return sorted(
            self._items.values(),
            key=lambda b: (-b.estimate_cr(), -float(b.saved_at or 0.0), b.system.lower()),
        )

    def get(self, address: int | None, body_id: int, system: str = "") -> SavedBelt | None:
        key = f"{int(address)}:{int(body_id)}" if address is not None else f"{system.strip().lower()}:{int(body_id)}"
        found = self._items.get(key)
        if found is not None:
            return found
        if address is not None:
            return self._items.get(f"{system.strip().lower()}:{int(body_id)}")
        return None

    def contains(self, address: int | None, body_id: int, system: str = "") -> bool:
        return self.get(address, body_id, system) is not None

    def upsert(self, belt: SavedBelt) -> SavedBelt:
        if not belt.saved_at:
            belt.saved_at = time.time()
        self._items[belt.key()] = belt
        self.save()
        return belt

    def remove(self, key: str) -> bool:
        if key not in self._items:
            return False
        del self._items[key]
        self.save()
        return True

    def __len__(self) -> int:
        return len(self._items)
