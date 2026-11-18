# Created by nc.ai 1.2.15 on Papasha 2026-11-15 17:00:23
"""Счётчики добычи за сессию: качество камня, выработка, трюм.

Три потока журнала:
* `ProspectedAsteroid` — состав конкретного астероида (`Materials[].Proportion` в %);
* `MiningRefined` — один очищенный материал = 1 т в трюм;
* `Cargo` / `MarketSell` — что лежит в трюме и что продано.

Отсюда получаются «процент целевого минерала в камне», среднее по сессии,
лучший камень, тонны в час и оценка партии — то, что показывает верхний HUD и
вкладка «Добыча». Формулы подсмотрены в EDMC Mining Analytics и Mining Analyser.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import mining


@dataclass
class Rock:
    """Один проспект: состав камня и доля целевого минерала."""

    target: str = ""
    share: float = 0.0
    content: str = ""  # High / Medium / Low — «богатство» камня из журнала
    motherlode: bool = False
    remaining: float | None = None
    materials: dict[str, float] = field(default_factory=dict)
    ts: float = 0.0
    body: str = ""


class MiningMetrics:
    """Живые метрики добычи. Живут в `GameState.mining`, сбрасываются на новый вход."""

    def __init__(self, target: str = "") -> None:
        self.target = target
        self.reset()

    # ------------------------------------------------------------ состояние
    def reset(self) -> None:
        self.prospected = 0  # сколько камней проспектировали в сессии
        self.motherlodes = 0
        self.already_mined = 0
        self.share_sum = 0.0
        self.share_count = 0  # камни, где целевой минерал вообще был
        self.best_share = 0.0
        self.pure_rocks = 0  # камни, где целевого минерала > 50%
        self.last_rock: Rock | None = None
        self.history_limit = 40
        self.history: list[Rock] = []
        self.refined: dict[str, int] = {}  # MiningRefined: минерал → тонны
        self.cargo: int = 0  # Cargo.Count — занято в трюме
        self.cargo_items: dict[str, int] = {}
        self.sold: dict[str, int] = {}  # MarketSell по минералам
        self.sold_cr: int = 0
        self.started: float = 0.0
        self.last_event_ts: float = 0.0

    # --------------------------------------------------------------- приём
    def apply(self, event: dict, now: float | None = None) -> bool:
        """Разобрать событие журнала. True — что-то поменялось для HUD."""
        name = str(event.get("event") or "")
        now = now or time.time()
        if name == "ProspectedAsteroid":
            return self._on_prospected(event, now)
        if name == "MiningRefined":
            return self._on_refined(event, now)
        if name == "Cargo":
            return self._on_cargo(event, now)
        if name == "MarketSell":
            return self._on_sell(event, now)
        if name in ("LoadGame", "Fileheader"):
            self.reset()
            return True
        return False

    def _on_prospected(self, event: dict, now: float) -> bool:
        materials: dict[str, float] = {}
        for item in event.get("Materials") or []:
            if not isinstance(item, dict):
                continue
            label = _material_name(item)
            if not label:
                continue
            try:
                proportion = float(item.get("Proportion") or 0.0)
            except (TypeError, ValueError):
                continue
            materials[label] = max(materials.get(label, 0.0), proportion)

        target = self.target or _best_material(materials)
        share = 0.0
        for label, proportion in materials.items():
            if label.lower() == (target or "").lower():
                share = proportion
                target = label
                break

        remaining = event.get("Remaining")
        try:
            remaining_value: float | None = float(remaining) if remaining is not None else None
        except (TypeError, ValueError):
            remaining_value = None

        rock = Rock(
            target=target,
            share=share,
            content=str(event.get("Content_Localised") or event.get("Content") or ""),
            motherlode=bool(event.get("Motherlode")),
            remaining=remaining_value,
            materials=materials,
            ts=now,
            body=str(event.get("Body") or ""),
        )
        self.prospected += 1
        if rock.motherlode:
            self.motherlodes += 1
        if remaining_value is not None and remaining_value < 100:
            self.already_mined += 1
        if share > 0:
            self.share_sum += share
            self.share_count += 1
            self.best_share = max(self.best_share, share)
            if share > 50:
                self.pure_rocks += 1
        self.last_rock = rock
        self.history.append(rock)
        del self.history[: max(0, len(self.history) - self.history_limit)]
        self.last_event_ts = now
        return True

    def _on_refined(self, event: dict, now: float) -> bool:
        label = _material_name(event) or "?"
        self.refined[label] = self.refined.get(label, 0) + 1
        self.last_event_ts = now
        return True

    def _on_cargo(self, event: dict, now: float) -> bool:
        try:
            self.cargo = int(event.get("Count") or 0)
        except (TypeError, ValueError):
            self.cargo = 0
        items: dict[str, int] = {}
        for item in event.get("Inventory") or []:
            if not isinstance(item, dict):
                continue
            label = _material_name(item)
            if not label:
                continue
            try:
                items[label] = int(item.get("Count") or 0)
            except (TypeError, ValueError):
                continue
        self.cargo_items = items
        self.last_event_ts = now
        return True

    def _on_sell(self, event: dict, now: float) -> bool:
        label = _material_name(event)
        try:
            count = int(event.get("Count") or 0)
            total = int(event.get("TotalSale") or 0)
        except (TypeError, ValueError):
            return False
        if label and count > 0:
            self.sold[label] = self.sold.get(label, 0) + count
        self.sold_cr += max(0, total)
        self.last_event_ts = now
        return True

    # ------------------------------------------------------------- величины
    @property
    def avg_share(self) -> float:
        """Средний процент целевого минерала по камням, где он встретился."""
        if not self.share_count:
            return 0.0
        return self.share_sum / self.share_count

    @property
    def refined_total(self) -> int:
        return sum(self.refined.values())

    @property
    def hours(self) -> float:
        if not self.started:
            return 0.0
        return max(0.0, (self.last_event_ts or time.time()) - self.started) / 3600.0

    @property
    def tons_per_hour(self) -> float:
        hours = self.hours
        if hours <= 0:
            return 0.0
        return self.refined_total / hours

    def batch_value(self, price_index=None) -> int:
        """Сколько стоит трюм (по живому индексу цен, иначе по средним)."""
        return _hold_value(self.cargo_items or {name: count for name, count in self.refined.items()}, price_index)

    def has_data(self) -> bool:
        return bool(self.prospected or self.refined_total or self.cargo)

    def hud_text(self, now: float | None = None) -> str:
        """Строка для верхнего HUD: «Alexandrite 32% · avg 28% · 12 rocks · 45 t/h»."""
        from .i18n import t

        if not self.has_data():
            return ""
        parts: list[str] = []
        rock = self.last_rock
        if rock is not None and rock.target:
            parts.append(f"{rock.target} {rock.share:.0f}%")
        if self.share_count >= 2:
            parts.append(t("mining.hud_avg", pct=f"{self.avg_share:.0f}"))
        if self.prospected:
            parts.append(t("mining.hud_rocks", n=self.prospected))
        if self.best_share > 0:
            parts.append(t("mining.hud_best", pct=f"{self.best_share:.0f}"))
        if self.refined_total:
            parts.append(t("mining.hud_tons", n=self.refined_total))
            rate = self.tons_per_hour
            if rate > 0:
                parts.append(t("mining.hud_tph", rate=f"{rate:.0f}"))
        if self.cargo:
            parts.append(t("mining.hud_cargo", n=self.cargo))
        if self.motherlodes:
            parts.append(t("mining.hud_motherlodes", n=self.motherlodes))
        return " · ".join(parts)


def _material_name(item: dict) -> str:
    """Имя материала из журнала: `Type_Localised` / `Name_Localised` → человеческий вид."""
    for key in ("Name_Localised", "Type_Localised", "Name", "Type"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return _clean_name(value)
    return ""


def _clean_name(value: str) -> str:
    text = value.strip()
    if text.startswith("$") and text.endswith(";"):
        text = text[1:-1]
        for prefix in ("Codex_Ent_", "SAA_SignalType_"):
            if text.startswith(prefix):
                text = text[len(prefix):]
        text = text.replace("_Name", "").replace("_", " ")
    return mining.canonical_mineral(text)


def _best_material(materials: dict[str, float]) -> str:
    """Самый дорогой минерал камня — если целевой не выбран явно."""
    if not materials:
        return ""
    return max(materials, key=lambda name: mining.hotspot_avg_price(name))


def _hold_value(hold: dict[str, int], price_index=None) -> int:
    total = 0
    for name, count in (hold or {}).items():
        if count <= 0:
            continue
        price = 0
        if price_index is not None:
            quote = price_index.best(name)
            if quote is not None:
                price = int(quote.price)
        if price <= 0:
            price = mining.hotspot_avg_price(name)
        total += price * int(count)
    return total
