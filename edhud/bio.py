# Edited by nc.ai 0.8.8.0 on macbook 2026-10-17 20:14:01
"""Предсказание биологии (порт движка SrvSurvey BioCriteria/BioPredictor).

Данные критериев — data/bio-criteria/*.json (SrvSurvey, GPLv3). Формат:
дерево условий, клауза = `<свойство> [значения]`, где
  * `temp [146 ~ 196]`      — числовой диапазон,
  * `atmosType [Neon]`      — одно из значений,
  * `mats &[Carbon,Sulphur]`— все значения присутствуют,
  * `mats ![Iron,Nickel]`   — ни одного из значений,
  * `atmosComp [Neon >= 99]`— доля газа в атмосфере не меньше N %,
  * `# текст`               — комментарий.
Родительские узлы задают genus/species/variant, дети наследуют условия.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterable

from . import codex, config, galaxy, regions

# Свойства критериев -> поля Scan-события (SrvSurvey BioCriteria.Map.properties)
MAP_PROPS = {
    "body": "PlanetClass",
    "gravity": "SurfaceGravity",
    "temp": "SurfaceTemperature",
    "pressure": "SurfacePressure",
    "atmosphere": "Atmosphere",
    "atmosType": "AtmosphereType",
    "atmosComp": "AtmosphereComposition",
    "matsComp": "Materials",
    "dist": "DistanceFromArrivalLS",
    "volcanism": "Volcanism",
    "mats": "Materials",
    "regions": "Region",
    "star": "Star",
    "parentStar": "ParentStar",
    "primaryStar": "PrimaryStar",
    "nebulae": "Nebulae",
    "guardian": "Guardian",
}

# Короткие коды классов тел -> префикс PlanetClass из журнала
BODY_CLASS_CODES = {
    "Icy": "Icy body",
    "Rocky": "Rocky body",
    "RockyIce": "Rocky ice ",
    "HMC": "High metal content ",
    "MRB": "Metal rich body",
}

# минимальная доля материала, чтобы считать его «присутствующим» (%)
MATS_MIN = 0.25

COMMENT = -1
IS, ALL, NOT, RANGE, COMPOSITION = 0, 1, 2, 3, 4

_CLAUSE_RE = re.compile(r"\s*(\w+)\s*[&!$]?\[(.+)\]")
_COMPO_RE = re.compile(r"([\w\s]+)(>=)\s*([\.\d]+)")


@dataclass
class Clause:
    raw: str
    prop: str
    op: int
    values: list[str] | None = None
    minimum: float | None = None
    maximum: float | None = None
    compositions: dict[str, float] | None = None

    @classmethod
    def parse(cls, text: str) -> "Clause | None":
        text = (text or "").strip()
        if not text or text.startswith("#"):
            return None
        m = _CLAUSE_RE.match(text)
        if not m:
            raise ValueError(f"плохая клауза критерия: {text!r}")
        prop, tail = m.group(1), m.group(2)
        clause = cls(raw=text, prop=prop, op=IS)

        if "~" in tail:
            clause.op = RANGE
            lo, _, hi = tail.partition("~")
            clause.minimum = float(lo.strip()) if lo.strip() else None
            clause.maximum = float(hi.strip()) if hi.strip() else None
            return clause

        if ">=" in tail:
            clause.op = COMPOSITION
            clause.compositions = {}
            for part in (p.strip() for p in tail.split("|")):
                if not part:
                    continue
                cm = _COMPO_RE.match(part)
                if not cm:
                    raise ValueError(f"плохая composition-клауза: {part!r}")
                clause.compositions[cm.group(1).strip()] = float(cm.group(3))
            return clause

        if "![" in text:
            clause.op = NOT
        elif "&[" in text or "$[" in text:
            clause.op = ALL
        values = [v.strip() for v in tail.split(",") if v.strip()]
        if prop == "body":
            values = [BODY_CLASS_CODES.get(v, v) for v in values]
        if not values:
            raise ValueError(f"пустой список значений: {text!r}")
        clause.values = values
        return clause


@dataclass
class Criteria:
    genus: str | None = None
    species: str | None = None
    variant: str | None = None
    query: list[Clause] = field(default_factory=list)
    children: list["Criteria"] = field(default_factory=list)
    common_children: list["Criteria"] = field(default_factory=list)
    use_common_children: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "Criteria":
        node = cls(
            genus=data.get("genus"),
            species=data.get("species"),
            variant=data.get("variant"),
            use_common_children=bool(data.get("useCommonChildren")),
        )
        for raw in data.get("query") or []:
            try:
                clause = Clause.parse(raw)
            except ValueError:
                continue
            if clause is not None:
                node.query.append(clause)
        node.children = [cls.from_dict(child) for child in data.get("children") or []]
        node.common_children = [cls.from_dict(child) for child in data.get("commonChildren") or []]
        return node


@lru_cache(maxsize=1)
def load_criteria() -> tuple[Criteria, ...]:
    folder = config.data_dir() / "bio-criteria"
    nodes: list[Criteria] = []
    for path in sorted(folder.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and (data.get("query") or data.get("children")):
            nodes.append(Criteria.from_dict(data))
    return tuple(nodes)


@dataclass(frozen=True)
class Prediction:
    genus: str
    species: str
    variant: str

    @property
    def label(self) -> str:
        return f"{self.genus} {self.species} - {self.variant}"

    @property
    def short(self) -> str:
        return f"{self.genus} {self.species}"

    @property
    def reward(self) -> int:
        return codex.reward_for(self.genus, self.species, self.variant)


# --------------------------------------------------------------------- матчинг
def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [str(k) for k in value]
    if isinstance(value, (list, tuple, set)):
        return [str(v) for v in value]
    return [str(value)]


def _clause_ok(clause: Clause, props: dict) -> bool:
    prop = MAP_PROPS.get(clause.prop, clause.prop)
    if prop not in props:
        return False
    value = props.get(prop)

    if clause.op == RANGE:
        if value is None:
            return False
        try:
            number = float(value)
        except (TypeError, ValueError):
            return False
        if clause.minimum is not None and number < clause.minimum:
            return False
        if clause.maximum is not None and number > clause.maximum:
            return False
        return True

    if clause.op == COMPOSITION:
        if not isinstance(value, dict):
            return False
        # в одной клаузе составы объединяются через ИЛИ (в отличие от остальных клауз)
        return any(
            float(value.get(key) or 0.0) >= threshold
            for key, threshold in (clause.compositions or {}).items()
        )

    values = clause.values or []

    if prop == "Region":
        body_region = value
        if body_region in (None, "", 0):
            return False
        current = int(body_region)
        allowed: set[int] = set()
        for raw in values:
            if raw.isdigit():
                allowed.add(int(raw))
            else:
                group = regions.group_regions(raw)
                if group:
                    allowed.update(group)
        hit = current in allowed
        return hit if clause.op != NOT else not hit

    if prop == "Materials" and clause.prop == "mats":
        materials = {str(k).lower(): float(v) for k, v in (value or {}).items()}
        present = {name for name, amount in materials.items() if amount > MATS_MIN}
        wanted = {v.lower() for v in values}
        if clause.op == ALL:
            return wanted.issubset(present)
        if clause.op == NOT:
            return not (wanted & present)
        return bool(wanted & present)

    if prop == "Volcanism":
        text = (str(value) if value is not None else "None") or "None"
        if values and values[0].lower() == "any":
            hit = text.lower() != "none"
        else:
            hit = any(v.lower() in text.lower() for v in values)
        return hit if clause.op != NOT else not hit

    body_values = _as_list(value)
    if not body_values:
        return False

    if prop == "PlanetClass":
        hit = any(bv.lower().startswith(v.lower()) for bv in body_values for v in values)
        return hit if clause.op != NOT else not hit

    lowered = [bv.lower() for bv in body_values]
    wanted = [v.lower() for v in values]
    if clause.op == ALL:
        return all(any(w == bv for bv in lowered) for w in wanted)
    if clause.op == NOT:
        return not any(w == bv for bv in lowered for w in wanted)
    if prop in ("Star", "ParentStar", "PrimaryStar"):
        return any(w == bv for bv in lowered for w in wanted)
    return any(w == bv for bv in lowered for w in wanted)


def _query_ok(query: Iterable[Clause], props: dict) -> bool:
    return all(_clause_ok(clause, props) for clause in query)


def _walk(
    node: Criteria,
    props: dict,
    genus: str | None,
    species: str | None,
    variant: str | None,
    common: list[Criteria],
    out: list[Prediction],
) -> None:
    common = node.common_children or common
    genus = node.genus or genus
    species = node.species or species
    variant = node.variant or variant

    if not _query_ok(node.query, props):
        return
    if genus and species and variant:
        prediction = Prediction(genus=genus, species=species, variant=variant)
        if prediction not in out:
            out.append(prediction)

    children = common if node.use_common_children else node.children
    for child in children or []:
        _walk(child, props, genus, species, variant, common, out)


def predict(props: dict, known_genuses: set[str] | None = None) -> list[Prediction]:
    """Предсказания genus/species/variant для набора свойств тела.

    Если набор родов уже известен (DSS/`SAASignalsFound`), остальные ветки не
    рассматриваются — как в SrvSurvey.
    """
    out: list[Prediction] = []
    for node in load_criteria():
        _walk(node, props, None, None, None, [], out)
    if known_genuses:
        lowered = {g.lower() for g in known_genuses}
        return [p for p in out if p.genus.lower() in lowered]
    return out


# --------------------------------------------------------------------- свойства
def flatten_star_type(star_type: str | None) -> str | None:
    """Схлопывает `K_RedGiant` -> `K`, `DAV` -> `D`, `K5` -> `K` (SrvSurvey Util.flattenStarType)."""
    if not star_type:
        return None
    if star_type[0] in "DWC":
        return star_type[0]
    if len(star_type) > 1 and (star_type[1] == "_" or star_type[1].isdigit()):
        return star_type[0]
    return star_type


def _ancestors(body, system) -> list:
    chain = []
    seen: set[int] = set()
    for parent in system.parents_of(body):
        if parent.body_id in seen:
            continue
        seen.add(parent.body_id)
        chain.append(parent)
        chain.extend(_ancestors(parent, system))
    return chain


def _brightest_star_type(body, system) -> str | None:
    ancestors = _ancestors(body, system)
    stars = [a for a in ancestors if a.is_star]
    if not stars:
        main = system.main_star()
        return flatten_star_type(main.star_type) if main else None

    def brightness(star) -> float:
        dist_sq = (body.semi_major_axis or 0.0) ** 2
        for node in _ancestors(body, system):
            dist_sq += (node.semi_major_axis or 0.0) ** 2
            if node.body_id == star.body_id:
                break
        dist = math.sqrt(dist_sq) if dist_sq > 0 else 0.0
        if dist <= 0:
            return 0.0
        temp = star.surface_temp or 0.0
        value = (star.radius or 0.0) * temp * temp / dist
        return value * value

    best = max(stars, key=brightness)
    return flatten_star_type(best.star_type)


def nebulae_distance(pos: tuple[float, float, float] | None, cache_dir=None) -> float | None:
    """Расстояние до ближайшей каталогизированной туманности (св. лет).

    Каталог кэширует edhud/galaxy.py (данные с edastro.com, как в SrvSurvey).
    Без сети и кэша возвращается None — критерии с `nebulae` просто не сработают.
    """
    return galaxy.nearest_nebula(pos)


def build_props(body, system, nebulae: float | None = None, guardian: bool = False) -> dict | None:
    """Словарь свойств тела для движка критериев (или None, если не посчитать)."""
    if body is None:
        return None
    # биосигналы только на посадочных; FSSBodySignals иногда раньше флага Landable
    if not body.landable and not (body.bio_signals or 0) and not body.genuses:
        return None
    star = _brightest_star_type(body, system)
    if not star:
        return None
    main_star = system.main_star()
    pos = system.star_pos
    region = regions.region_id(pos[0], pos[2]) if pos else None
    atmosphere = (body.atmosphere or "").replace(" atmosphere", "")
    composition = dict(body.atmosphere_composition or {})
    if len(composition) == 1:
        composition[next(iter(composition))] = 100.0
    return {
        "PlanetClass": body.planet_class or "",
        "SurfaceGravity": (body.surface_gravity or 0.0) / 10.0,
        "SurfaceTemperature": body.surface_temp,
        "SurfacePressure": (body.surface_pressure or 0.0) / 100000.0,
        "Atmosphere": atmosphere,
        "AtmosphereType": body.atmosphere_type,
        "AtmosphereComposition": composition,
        "DistanceFromArrivalLS": body.distance_ls,
        "Volcanism": body.volcanism or "None",
        "Materials": body.materials or {},
        "Region": str(region) if region else None,
        "Star": [star],
        "PrimaryStar": flatten_star_type(main_star.star_type) if main_star else None,
        "Nebulae": nebulae,
        "Guardian": "true" if guardian else "false",
    }


def forecast_names(body, system, limit: int = 4) -> list[str]:
    """Список организмов: до DSS — роды/виды по критериям; после DSS — виды и цвет.

    Как в SrvSurvey: `SAASignalsFound` фиксирует роды, дальше BioCriteria
    сужает до species/variant. Если прогноза нет — показываем хотя бы роды DSS.
    """
    if body is None:
        return []
    predictions = predict_for_body(body, system, limit=max(64, limit * 8))
    if not predictions:
        if body.genuses:
            return [codex.display_name(key) for key in body.genuses][:limit]
        return []

    by_genus: dict[str, dict[str, list[str]]] = {}
    order: list[str] = []
    for prediction in predictions:
        if prediction.genus not in by_genus:
            by_genus[prediction.genus] = {}
            order.append(prediction.genus)
        variants = by_genus[prediction.genus].setdefault(prediction.species, [])
        if prediction.variant and prediction.variant not in variants:
            variants.append(prediction.variant)

    names: list[str] = []
    after_dss = bool(body.genuses)
    for genus in order:
        species_map = by_genus[genus]
        # после DSS (или один вид у рода) — пишем вид и цвет, не голый род
        if after_dss or len(species_map) == 1:
            for species, variants in species_map.items():
                if len(variants) == 1:
                    names.append(f"{genus} {species} - {variants[0]}")
                else:
                    names.append(f"{genus} {species}")
                if len(names) >= limit:
                    return names
        else:
            names.append(genus)
            if len(names) >= limit:
                return names
    return names


def predict_for_body(body, system, limit: int = 24) -> list[Prediction]:
    """Предсказания для тела с учётом уже известных (DSS) родов."""
    props = build_props(
        body,
        system,
        nebulae=galaxy.nearest_nebula(system.star_pos),
        guardian=galaxy.within_guardian_bubble(system.star_pos),
    )
    if not props:
        return []
    known = {codex.display_name(key) for key in (body.genuses or {})}
    return predict(props, known_genuses=known or None)[:limit]
