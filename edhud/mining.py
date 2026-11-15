# Edited by nc.ai 1.2.15 on Papasha 2026-11-15 12:11:56
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


# ---------------------------------------------------------------- планеты
# Сырьё, которое копают на поверхности: имя → грейд (1 частое … 4 редкое).
# Грейды по инженерке Elite; нужны, чтобы отделить «металлолом» от Rare.
RAW_MATERIAL_GRADE: dict[str, int] = {
    "Iron": 1,
    "Nickel": 1,
    "Sulphur": 1,
    "Carbon": 1,
    "Phosphorus": 1,
    "Chromium": 1,
    "Manganese": 1,
    "Zinc": 1,
    "Vanadium": 2,
    "Germanium": 2,
    "Cadmium": 2,
    "Niobium": 2,
    "Molybdenum": 2,
    "Tin": 2,
    "Tungsten": 2,
    "Arsenic": 2,
    "Selenium": 3,
    "Mercury": 3,
    "Tellurium": 3,
    "Zirconium": 3,
    "Antimony": 4,
    "Polonium": 4,
    "Ruthenium": 4,
    "Technetium": 4,
    "Yttrium": 4,
}

# Сигналы, которыми игра помечает «на этом теле есть что копать».
SURFACE_SITE_SIGNALS = ("Planetary Mining Location", "Geological")
BIO_SITE_SIGNAL = "Biological"


def material_grade(name: str | None) -> int:
    """Грейд сырья; 0 для неизвестного."""
    if not name:
        return 0
    direct = RAW_MATERIAL_GRADE.get(name)
    if direct is not None:
        return int(direct)
    lower = {k.lower(): v for k, v in RAW_MATERIAL_GRADE.items()}
    return int(lower.get(str(name).lower()) or 0)


def material_rows(
    materials: dict[str, float] | None,
    *,
    min_share: float = 0.0,
    rare_first: bool = True,
) -> list[tuple[str, float, int]]:
    """(имя, доля %, грейд) — редкие (грейд 4) вперёд, затем по доле."""
    if not materials:
        return []
    rows = [
        (name, float(share or 0.0), material_grade(name))
        for name, share in materials.items()
        if float(share or 0.0) >= float(min_share)
    ]
    if rare_first:
        rows.sort(key=lambda item: (-item[2], -item[1], item[0].lower()))
    else:
        rows.sort(key=lambda item: (-item[1], -item[2], item[0].lower()))
    return rows


def format_materials(materials: dict[str, float] | None, limit: int = 4, min_share: float = 0.0) -> str:
    """«Polonium 1.8% · Iron 23.5%» — что копать на поверхности."""
    rows = material_rows(materials, min_share=min_share)[: max(1, int(limit))]
    if not rows:
        return "—"
    return " · ".join(f"{name} {share:.1f}%" for name, share, _grade in rows)


def has_surface_site(signals: dict[str, int] | None) -> bool:
    """Есть ли на теле точки поверхностной добычи."""
    if not signals:
        return False
    return any(name in signals for name in SURFACE_SITE_SIGNALS)


def ring_kind(rings: list | None) -> str:
    """«Icy», «Metallic», «Rocky · Metallic» — типы колец тела."""
    kinds: list[str] = []
    for ring in rings or []:
        if isinstance(ring, dict):
            kind = ring.get("type") or ring.get("Type")
        else:
            kind = getattr(ring, "type", None) or getattr(ring, "Type", None)
        if isinstance(kind, str) and kind and kind not in kinds:
            kinds.append(kind)
    return " · ".join(kinds)


def ring_revenue(hotspots: dict[str, int] | None, capacity: int) -> int:
    """Сколько вывезет трюм, если грести самый дорогой минерал кольца."""
    rows = sorted_hotspots(hotspots)
    if not rows or capacity <= 0:
        return 0
    return int(rows[0][2]) * int(capacity)

