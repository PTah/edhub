"""Hotspot-минералы колец: средние рыночные цены и сортировка.

Цены — ориентир galactic average (Inara / mining-гайды, ~2025), не live-рынок.
"""
from __future__ import annotations

# Средняя цена продажи NPC, cr/t. Имена как в журнале Elite (SAASignalsFound).
HOTSPOT_AVG_PRICE_CR: dict[str, int] = {
    "Monazite": 309_000,
    "Musgravite": 239_000,
    "Alexandrite": 236_000,
    "Grandidierite": 224_000,
    "Serendibite": 204_000,
    "Rhodplumsite": 197_000,
    "Benitoite": 184_000,
    "Void Opals": 162_000,
    "Void Opal": 162_000,
    "Low Temperature Diamonds": 147_000,
    "Low-Temperature Diamonds": 147_000,
    "Platinum": 79_000,
    "Painite": 65_000,
    "Osmium": 64_000,
    "Tritium": 54_000,
    "Palladium": 52_000,
    "Gold": 48_000,
    "Bromellite": 38_000,
    "Silver": 38_000,
    "Samarium": 30_000,
    "Bertrandite": 18_000,
    "Gallite": 12_000,
    "Indite": 11_000,
    "Coltan": 6_000,
    "Lithium Hydroxide": 5_800,
    "Cobalt": 5_500,
    "Rutile": 3_600,
    "Hydrogen Peroxide": 3_100,
    "Bauxite": 2_900,
    "Uraninite": 2_700,
    "Lepidolite": 1_500,
    "Methanol Monohydrate Crystals": 1_300,
    "Methane Clathrate": 1_100,
    "Liquid Oxygen": 1_600,
}


def hotspot_avg_price(name: str | None) -> int:
    """Средняя цена cr/t; 0 если минерал неизвестен."""
    if not name:
        return 0
    direct = HOTSPOT_AVG_PRICE_CR.get(name)
    if direct is not None:
        return int(direct)
    lower = {k.lower(): v for k, v in HOTSPOT_AVG_PRICE_CR.items()}
    return int(lower.get(str(name).lower()) or 0)


def sorted_hotspots(hotspots: dict[str, int] | None) -> list[tuple[str, int, int]]:
    """Список (имя, count, avg_price) от самых дорогих к дешёвым."""
    if not hotspots:
        return []
    rows = [(name, int(count or 0), hotspot_avg_price(name)) for name, count in hotspots.items()]
    rows.sort(key=lambda item: (-item[2], -item[1], item[0].lower()))
    return rows


def format_hotspots(hotspots: dict[str, int] | None) -> str:
    """«Musgravite ×2, Alexandrite» — сначала дороже."""
    rows = sorted_hotspots(hotspots)
    if not rows:
        return "—"
    parts: list[str] = []
    for name, count, _price in rows:
        parts.append(name if count <= 1 else f"{name} ×{count}")
    return ", ".join(parts)


def format_hotspots_tip(hotspots: dict[str, int] | None) -> str | None:
    """Тултип: минерал, ×N, средняя цена на рынке (max → min)."""
    rows = sorted_hotspots(hotspots)
    if not rows:
        return None
    lines = ["Hotspot в кольце (ср. цена рынка):"]
    for name, count, price in rows:
        label = name if count <= 1 else f"{name} ×{count}"
        if price > 0:
            price_txt = f"{price:,}".replace(",", " ")
            lines.append(f"• {label} — ≈{price_txt} cr/t")
        else:
            lines.append(f"• {label}")
    return "\n".join(lines)
