# Edited by nc.ai 1.2.15 on Papasha 2026-11-15 12:11:56
# Edited by nc.ai 1.2.15 on new-admin-pc 2026-11-17 16:27:34
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
    from .i18n import t

    rows = sorted_hotspots(hotspots)
    if not rows:
        return None
    lines = [t("tip.hotspot_header")]
    for name, count, price in rows:
        label = name if count <= 1 else f"{name} ×{count}"
        if price > 0:
            price_txt = f"{price:,}".replace(",", " ")
            lines.append(t("tip.hotspot_line_price", label=label, price=price_txt))
        else:
            lines.append(t("tip.hotspot_line", label=label))
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


# ---------------------------------------------------- что копать в кольце
# Списки минералов по типу кольца — внутриигровые данные (та же таблица, что в
# гайдах и в EliteMining `ring_guide_tab.py`; оттуда же и раскладка по способу).
#   core  — глубокое ядро: нужны seismic charges;
#   laser — лазерная/подповерхностная добыча теми же камнями;
#   high  — дорогие (стоит лететь), low — дешёвые (берут только попутно).
RING_MINERALS: dict[str, dict[str, tuple[str, ...]]] = {
    "Icy": {
        "core_high": ("Alexandrite", "Grandidierite", "Low Temperature Diamonds", "Void Opals"),
        "core_low": ("Bromellite",),
        "laser_high": ("Low Temperature Diamonds",),
        "laser_low": (
            "Bromellite",
            "Hydrogen Peroxide",
            "Liquid Oxygen",
            "Lithium Hydroxide",
            "Methane Clathrate",
            "Methanol Monohydrate Crystals",
            "Tritium",
            "Water",
        ),
    },
    "Metallic": {
        "core_high": ("Monazite", "Rhodplumsite", "Serendibite"),
        "core_low": ("Painite", "Platinum"),
        "laser_high": ("Osmium", "Painite", "Platinum"),
        "laser_low": (
            "Bertrandite",
            "Gold",
            "Indite",
            "Palladium",
            "Praseodymium",
            "Samarium",
            "Silver",
        ),
    },
    "Metal-Rich": {
        "core_high": ("Alexandrite", "Benitoite", "Monazite", "Rhodplumsite", "Serendibite"),
        "core_low": ("Painite", "Platinum"),
        "laser_high": ("Osmium",),
        "laser_low": (
            "Bertrandite",
            "Coltan",
            "Gallite",
            "Gold",
            "Indite",
            "Lepidolite",
            "Praseodymium",
            "Samarium",
            "Silver",
            "Uraninite",
        ),
    },
    "Rocky": {
        "core_high": ("Alexandrite", "Benitoite", "Monazite", "Musgravite", "Serendibite"),
        "core_low": (),
        "laser_high": (),
        "laser_low": (
            "Bauxite",
            "Cobalt",
            "Coltan",
            "Gallite",
            "Indite",
            "Lepidolite",
            "Rutile",
            "Samarium",
            "Uraninite",
        ),
    },
}

# как игра зовёт типы колец в журнале (`RingClass`) и как — в наших данных
RING_KIND_ALIASES: dict[str, str] = {
    "icy": "Icy",
    "eringclass_icy": "Icy",
    "metallic": "Metallic",
    "metalic": "Metallic",  # так пишет игра: eRingClass_Metalic
    "eringclass_metallic": "Metallic",
    "eringclass_metalic": "Metallic",
    "metal rich": "Metal-Rich",
    "metal-rich": "Metal-Rich",
    "metalrich": "Metal-Rich",
    "eringclass_metalrich": "Metal-Rich",
    "rocky": "Rocky",
    "eringclass_rocky": "Rocky",
}

METHOD_CORE = "core"
METHOD_LASER = "laser"


def normalize_ring_kind(kind: str | None) -> str | None:
    """`eRingClass_Icy` / `ICY` / `Metal Rich` → каноническое `Icy` / `Metal-Rich`."""
    if not kind:
        return None
    return RING_KIND_ALIASES.get(str(kind).strip().lower())


def ring_kinds(ring_types) -> list[str]:
    """Канонические типы колец без дублей: ["Icy"], ["Metallic", "Rocky"]."""
    kinds: list[str] = []
    for kind in ring_types or []:
        name = normalize_ring_kind(kind)
        if name and name not in kinds:
            kinds.append(name)
    return kinds


def ring_minerals(ring_types, *, high_only: bool = False) -> dict[str, list[str]]:
    """Что водится в кольце такого типа: {"core": [...], "laser": [...]} — дорогое вперёд."""
    out: dict[str, list[str]] = {METHOD_CORE: [], METHOD_LASER: []}
    for kind in ring_kinds(ring_types):
        table = RING_MINERALS.get(kind) or {}
        for group, method in (
            ("core_high", METHOD_CORE),
            ("core_low", METHOD_CORE),
            ("laser_high", METHOD_LASER),
            ("laser_low", METHOD_LASER),
        ):
            if high_only and not group.endswith("_high"):
                continue
            for name in table.get(group, ()):
                if name not in out[method]:
                    out[method].append(name)
    for method, names in out.items():
        names.sort(key=lambda item: -hotspot_avg_price(item))
    return out


def mineral_method(name: str | None) -> str | None:
    """Как добывают минерал в кольце: core (ядро), laser, либо None (не из колец)."""
    want = str(name or "").strip().lower()
    if not want:
        return None
    for table in RING_MINERALS.values():
        for group, method in (
            ("core_high", METHOD_CORE),
            ("core_low", METHOD_CORE),
            ("laser_high", METHOD_LASER),
            ("laser_low", METHOD_LASER),
        ):
            if any(item.lower() == want for item in table.get(group, ())):
                return method
    return None


def is_high_value(name: str | None) -> bool:
    """Минерал из «дорогой» половины таблицы — за ним стоит лететь."""
    want = str(name or "").strip().lower()
    for table in RING_MINERALS.values():
        for group in ("core_high", "laser_high"):
            if any(item.lower() == want for item in table.get(group, ())):
                return True
    return False


def ring_density(mass: float | None, inner_rad: float | None, outer_rad: float | None) -> float | None:
    """Плотность кольца по формуле edtools: M[MT] / π(Rout² − Rin²) [км²].

    В журнале `Scan` масса кольца в кг, радиусы в метрах — приводим к MT и км.
    Величина нужна для сравнения колец между собой: чем больше, тем плотнее
    камень в кольце (и тем выгоднее копать).
    """
    try:
        mass = float(mass or 0.0)
        inner_rad = float(inner_rad or 0.0)
        outer_rad = float(outer_rad or 0.0)
    except (TypeError, ValueError):
        return None
    if mass <= 0 or outer_rad <= inner_rad:
        return None
    mass_mt = mass / 1e9
    inner_km = inner_rad / 1000.0
    outer_km = outer_rad / 1000.0
    area = 3.141592653589793 * (outer_km * outer_km - inner_km * inner_km)
    if area <= 0:
        return None
    return round(mass_mt / area, 6)


def hotspot_count(hotspots: dict[str, int] | None, mineral: str | None) -> int:
    """Сколько хотспотов этого минерала в кольце (2+ — уже наложение искать)."""
    if not hotspots or not mineral:
        return 0
    want = str(mineral).strip().lower()
    for name, count in hotspots.items():
        if name.lower() == want:
            return int(count or 0)
    return 0


_COMMODITY_BY_KEY: dict[str, str] = {}


def _key(text: str) -> str:
    return "".join(ch for ch in str(text or "").lower() if ch.isalnum())


def _commodity_index() -> dict[str, str]:
    """Индекс «нормализованное имя → наше написание» по всем справочникам."""
    if _COMMODITY_BY_KEY:
        return _COMMODITY_BY_KEY
    names = set(HOTSPOT_AVG_PRICE_CR)
    for table in RING_MINERALS.values():
        for group in table.values():
            names.update(group)
    # при равном ключе предпочитаем написание без дефиса
    for name in sorted(names, key=lambda item: ("-" in item, item)):
        _COMMODITY_BY_KEY.setdefault(_key(name), name)
    return _COMMODITY_BY_KEY


def canonical_mineral(name: str | None) -> str:
    """Привести имя минерала к нашему написанию: «tritium» → «Tritium».

    Журнал в `MiningRefined`/`MarketSell` отдаёт `Type` в нижнем регистре
    (`lowtemperaturediamonds`), а `SAASignalsFound` — в обычном виде; счётчикам
    нужен один и тот же ключ.
    """
    text = str(name or "").strip()
    if not text:
        return ""
    hit = _commodity_index().get(_key(text))
    if hit:
        return hit
    return text.title() if text.islower() else text


def overlap_label(count: int) -> str:
    """Подпись к количеству хотспотов: 'double'/'triple' (переводит UI)."""
    count = int(count or 0)
    if count >= 3:
        return "triple"
    if count == 2:
        return "double"
    return ""


