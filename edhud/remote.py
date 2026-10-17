# Edited by nc.ai 0.8.8.0 on macbook 2026-10-17 20:13:51
"""Догрузка тел, открытых другими командирами: EDSM + Spansh (данные EDDN).

Идея как в EDEB: свой журнал знает только то, что сканировали вы. Если тела
системы уже открыты/просканированы другими (и они отправили данные через
EDMC/EDDN в EDSM), мы можем показать их параметры, найденные роды биологии и
стоимость — до собственного FSS/DSS-скана.

Источники (оба поверх EDDN, никаких ключей не нужно):
  * EDSM  /api-system-v1/bodies        — параметры тел + кто открыл/картографировал
  * EDSM  /api-system-v1/estimated-value — суммарная стоимость системы
  * Spansh /api/bodies/search          — сигналы (биология/геология), материалы,
                                         оценки стоимости скана/картографии
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from . import config
from .model import Body, System

USER_AGENT = "EDHUD/1.1 (+local overlay; python-urllib)"
EDSM_BODIES = "https://www.edsm.net/api-system-v1/bodies?systemName={name}"
EDSM_VALUE = "https://www.edsm.net/api-system-v1/estimated-value?systemName={name}&includeBodies=1"
SPANSH_SEARCH = "https://spansh.co.uk/api/bodies/search"
G_TO_MS2 = 9.80665
AU_TO_M = 1.495978707e11
DEFAULT_TTL = 6 * 3600

# EDSM/Spansh пишут классы тел как в EDSM — приводим к нотации журнала игры.
PLANET_ALIASES = {
    "earth-like world": "Earthlike body",
    "earthlike world": "Earthlike body",
    "earthlike body": "Earthlike body",
    "high metal content world": "High metal content body",
    "metal-rich body": "Metal rich body",
    "rocky ice world": "Rocky ice body",
    "gas giant with water based life": "Gas giant with water-based life",
    "gas giant with ammonia based life": "Gas giant with ammonia-based life",
    "class i gas giant": "Sudarsky class I gas giant",
    "class ii gas giant": "Sudarsky class II gas giant",
    "class iii gas giant": "Sudarsky class III gas giant",
    "class iv gas giant": "Sudarsky class IV gas giant",
    "class v gas giant": "Sudarsky class V gas giant",
    "helium-rich gas giant": "Helium rich gas giant",
    "water giant": "Water giant",
    "water world": "Water world",
    "ammonia world": "Ammonia world",
    "rocky body": "Rocky body",
    "icy body": "Icy body",
    "metal rich body": "Metal rich body",
    "high metal content body": "High metal content body",
}
KEEP_WORLD = {"water world", "ammonia world"}


def normalize_planet_class(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    alias = PLANET_ALIASES.get(text.lower())
    if alias:
        return alias
    lowered = text.lower()
    if lowered.endswith(" world") and lowered not in KEEP_WORLD:
        return text[:-6] + " body"
    return text


def _f(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _http_json(url: str, timeout: float = 10.0, payload: dict | None = None) -> dict | None:
    try:
        if payload is None:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        else:
            request = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
            )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None


@dataclass
class RemoteBody:
    body_id: int
    name: str
    planet_class: str | None = None
    star_type: str | None = None
    gravity_g: float | None = None
    surface_temp: float | None = None
    surface_pressure_bar: float | None = None
    atmosphere: str | None = None
    atmosphere_composition: dict[str, float] = field(default_factory=dict)
    volcanism: str | None = None
    materials: dict[str, float] = field(default_factory=dict)
    landable: bool = False
    distance_ls: float = 0.0
    radius_km: float = 0.0
    sma_au: float | None = None
    parents: list[int] = field(default_factory=list)
    terraform_state: str | None = None
    mass_em: float = 0.0
    stellar_mass: float = 0.0
    bio_signals: int | None = None
    geo_signals: int | None = None
    discovered_by: str | None = None
    mapped_by: str | None = None
    scan_value: int | None = None
    mapped_value: int | None = None
    source: str = "edsm"

    # ------------------------------------------------------------- приведение
    def to_body(self) -> Body:
        body = Body(
            body_id=self.body_id,
            name=self.name,
            planet_class=self.planet_class,
            star_type=self.star_type,
            is_star=bool(self.star_type),
            radius=(self.radius_km or 0.0) * 1000.0,
            mass_em=self.mass_em,
            stellar_mass=self.stellar_mass,
            surface_temp=self.surface_temp,
            surface_gravity=(self.gravity_g or 0.0) * G_TO_MS2 if self.gravity_g is not None else None,
            surface_pressure=(self.surface_pressure_bar or 0.0) * 100000.0
            if self.surface_pressure_bar is not None
            else None,
            atmosphere=self.atmosphere,
            atmosphere_composition=dict(self.atmosphere_composition),
            volcanism=self.volcanism,
            materials=dict(self.materials),
            landable=self.landable,
            distance_ls=self.distance_ls,
            semi_major_axis=(self.sma_au or 0.0) * AU_TO_M if self.sma_au is not None else None,
            parent_ids=list(self.parents),
            terraform_state=self.terraform_state,
            bio_signals=self.bio_signals,
            geo_signals=self.geo_signals,
            signals_known=self.bio_signals is not None,
            was_discovered=True,
            was_mapped=bool(self.mapped_by),
            remote=True,
            discovered_by=self.discovered_by,
            mapped_by=self.mapped_by,
            source=self.source,
        )
        return body

    def enrich(self, body: Body) -> bool:
        """Дополняет локальное тело недостающими данными. True — что-то добавили."""
        changed = False
        if body.bio_signals is None and self.bio_signals is not None:
            body.bio_signals = self.bio_signals
            body.signals_known = True
            body.source = body.source or self.source
            changed = True
        if body.geo_signals is None and self.geo_signals is not None:
            body.geo_signals = self.geo_signals
            changed = True
        if not body.discovered_by and self.discovered_by:
            body.discovered_by = self.discovered_by
            changed = True
        if not body.mapped_by and self.mapped_by:
            body.mapped_by = self.mapped_by
            changed = True
        return changed

    def to_cache(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_cache(cls, data: dict) -> "RemoteBody":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class RemoteSystem:
    name: str
    address: int | None = None
    bodies: dict[int, RemoteBody] = field(default_factory=dict)
    estimated_scan_value: int | None = None
    estimated_mapped_value: int | None = None
    region: str | None = None
    sources: list[str] = field(default_factory=list)
    fetched_at: float = 0.0

    def __bool__(self) -> bool:
        return bool(self.bodies)

    def to_cache(self) -> dict:
        return {
            "name": self.name,
            "address": self.address,
            "bodies": [b.to_cache() for b in self.bodies.values()],
            "estimated_scan_value": self.estimated_scan_value,
            "estimated_mapped_value": self.estimated_mapped_value,
            "region": self.region,
            "sources": self.sources,
            "fetched_at": self.fetched_at,
        }

    @classmethod
    def from_cache(cls, data: dict) -> "RemoteSystem":
        system = cls(
            name=data.get("name") or "",
            address=data.get("address"),
            estimated_scan_value=data.get("estimated_scan_value"),
            estimated_mapped_value=data.get("estimated_mapped_value"),
            region=data.get("region"),
            sources=list(data.get("sources") or []),
            fetched_at=float(data.get("fetched_at") or 0.0),
        )
        for raw in data.get("bodies") or []:
            body = RemoteBody.from_cache(raw)
            system.bodies[body.body_id] = body
        return system

    @property
    def total_bio_signals(self) -> int:
        return sum(b.bio_signals or 0 for b in self.bodies.values())


# ------------------------------------------------------------------- провайдеры
def _star_type_from_subtype(subtype: str | None, spectral: str | None) -> str | None:
    if spectral:
        return str(spectral).strip().upper()
    if not subtype:
        return None
    token = subtype.strip().split(" ")[0]
    return token.upper() if token else None


def _parse_edsm(name: str, data: dict, timeout: float) -> RemoteSystem:
    system = RemoteSystem(name=data.get("name") or name, address=data.get("id64"), sources=["edsm"])
    for raw in data.get("bodies") or []:
        body_id = raw.get("bodyId")
        if body_id is None:
            continue
        is_star = (raw.get("type") or "").lower() == "star"
        discovery = raw.get("discovery") or {}
        mapped = raw.get("mapped") or {}
        parents: list[int] = []
        for parent in raw.get("parents") or []:
            if isinstance(parent, dict):
                parents.extend(v for v in parent.values() if isinstance(v, int))
        body = RemoteBody(
            body_id=int(body_id),
            name=raw.get("name") or f"Body {body_id}",
            planet_class=None if is_star else normalize_planet_class(raw.get("subType")),
            star_type=_star_type_from_subtype(raw.get("subType"), raw.get("spectralClass")) if is_star else None,
            gravity_g=_f(raw.get("gravity")),
            surface_temp=_f(raw.get("surfaceTemperature")),
            surface_pressure_bar=_f(raw.get("surfacePressure")),
            atmosphere=(raw.get("atmosphereType") or None),
            atmosphere_composition={
                k: float(v) for k, v in (raw.get("atmosphereComposition") or {}).items()
            },
            volcanism=(raw.get("volcanismType") if (raw.get("volcanismType") or "").lower() != "no volcanism" else None),
            materials={k: float(v) for k, v in (raw.get("materials") or {}).items()},
            landable=bool(raw.get("isLandable")),
            distance_ls=_f(raw.get("distanceToArrival")) or 0.0,
            radius_km=_f(raw.get("radius")) or 0.0,
            sma_au=_f(raw.get("semiMajorAxis")),
            parents=parents,
            terraform_state=raw.get("terraformingState") or None,
            mass_em=_f(raw.get("earthMasses")) or 0.0,
            stellar_mass=_f(raw.get("solarMasses")) or 0.0,
            discovered_by=discovery.get("commander"),
            mapped_by=mapped.get("commander"),
            source="edsm",
        )
        system.bodies[body.body_id] = body
    return system


def _fetch_edsm_totals(system: RemoteSystem, timeout: float) -> None:
    url = EDSM_VALUE.format(name=urllib.parse.quote(system.name))
    data = _http_json(url, timeout=timeout)
    if not isinstance(data, dict):
        return
    try:
        system.estimated_scan_value = int(data.get("estimatedValue") or 0) or None
        system.estimated_mapped_value = int(data.get("estimatedValueMapped") or 0) or None
    except (TypeError, ValueError):
        pass


def _parse_spansh(name: str, data: dict, address: int | None = None) -> RemoteSystem:
    results = data.get("results") or []
    system = RemoteSystem(name=name, sources=["spansh"])
    for raw in results:
        body_id = raw.get("body_id")
        if body_id is None:
            continue
        # фильтр по id64/имени: поиск Spansh может вернуть соседние системы
        raw_address = raw.get("system_id64")
        raw_name = raw.get("system_name")
        if address and raw_address and int(raw_address) != int(address):
            continue
        if not address and raw_name and raw_name.strip().lower() != name.strip().lower():
            continue
        is_star = (raw.get("type") or "").lower() == "star"
        bio = geo = None
        for signal in raw.get("signals") or []:
            signal_name = (signal.get("name") or "").lower()
            count = int(signal.get("count") or 0)
            if "biological" in signal_name:
                bio = max(bio or 0, count)
            elif "geological" in signal_name:
                geo = max(geo or 0, count)
        atmosphere = raw.get("atmosphere")
        composition = raw.get("atmosphere_composition") or {}
        if isinstance(composition, list):
            composition = {
                str(item.get("name")): float(item.get("share") or 0.0)
                for item in composition
                if isinstance(item, dict)
            }
        materials = raw.get("materials") or {}
        if isinstance(materials, list):
            materials = {
                str(item.get("name")): float(item.get("share") or 0.0)
                for item in materials
                if isinstance(item, dict)
            }
        body = RemoteBody(
            body_id=int(body_id),
            name=raw.get("name") or f"Body {body_id}",
            planet_class=None if is_star else normalize_planet_class(raw.get("subtype")),
            star_type=_star_type_from_subtype(raw.get("subtype"), None) if is_star else None,
            gravity_g=_f(raw.get("gravity")),
            surface_temp=_f(raw.get("surface_temperature")),
            surface_pressure_bar=_f(raw.get("surface_pressure")),
            atmosphere=atmosphere,
            atmosphere_composition={k: float(v) for k, v in composition.items()},
            volcanism=(raw.get("volcanism_type") if (raw.get("volcanism_type") or "").lower() != "no volcanism" else None),
            materials={k: float(v) for k, v in materials.items()},
            landable=bool(raw.get("is_landable")),
            distance_ls=_f(raw.get("distance_to_arrival")) or 0.0,
            radius_km=_f(raw.get("radius")) or 0.0,
            sma_au=_f(raw.get("semi_major_axis")),
            terraform_state=raw.get("terraforming_state") or None,
            mass_em=_f(raw.get("earth_masses")) or 0.0,
            bio_signals=bio,
            geo_signals=geo,
            scan_value=int(raw.get("estimated_scan_value") or 0) or None,
            mapped_value=int(raw.get("estimated_mapping_value") or 0) or None,
            source="spansh",
        )
        system.bodies[body.body_id] = body
    return system


def _merge(base: RemoteSystem | None, extra: RemoteSystem | None) -> RemoteSystem | None:
    if base is None:
        return extra
    if extra is None:
        return base
    for body_id, body in extra.bodies.items():
        current = base.bodies.get(body_id)
        if current is None:
            base.bodies[body_id] = body
            continue
        for attr in ("bio_signals", "geo_signals", "scan_value", "mapped_value", "discovered_by", "mapped_by"):
            if getattr(current, attr) in (None, 0, "") and getattr(body, attr):
                setattr(current, attr, getattr(body, attr))
        if not current.materials and body.materials:
            current.materials = body.materials
        if not current.atmosphere and body.atmosphere:
            current.atmosphere = body.atmosphere
        if not current.mass_em and body.mass_em:
            current.mass_em = body.mass_em
    base.sources = sorted(set(base.sources) | set(extra.sources))
    return base


class RemoteClient:
    """Тянет данные о системе и кэширует их на диск (работает офлайн по кэшу)."""

    def __init__(self, cache_dir: Path | None = None, ttl: float = DEFAULT_TTL, timeout: float = 10.0) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else config.app_dir() / "remote"
        self.ttl = ttl
        self.timeout = timeout

    def cache_path(self, name: str, address: int | None) -> Path:
        key = str(address) if address else name.replace("/", "_").replace(" ", "_")
        return self.cache_dir / f"{key}.json"

    def cached(self, name: str, address: int | None) -> RemoteSystem | None:
        try:
            data = json.loads(self.cache_path(name, address).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        system = RemoteSystem.from_cache(data)
        if not system.bodies:
            return None
        return system

    def fetch(self, name: str, address: int | None = None, force: bool = False) -> RemoteSystem | None:
        cached = self.cached(name, address)
        if cached and not force and time.time() - cached.fetched_at < self.ttl:
            return cached

        quoted = urllib.parse.quote(name)
        result = self._fetch_edsm_bodies(name, quoted)
        resolved_address = address
        if result is not None:
            resolved_address = resolved_address or result.address
            _fetch_edsm_totals(result, self.timeout)
        result = _merge(result, self._fetch_spansh(name, resolved_address))
        if result is None:
            return cached  # сеть недоступна — отдаём старое, если есть
        result.fetched_at = time.time()
        result.address = result.address or resolved_address
        self._save(result)
        return result

    def _fetch_edsm_bodies(self, name: str, quoted: str) -> RemoteSystem | None:
        data = _http_json(EDSM_BODIES.format(name=quoted), timeout=self.timeout)
        if not isinstance(data, dict) or not data.get("bodies"):
            return None
        return _parse_edsm(name, data, self.timeout)

    def _fetch_spansh(self, name: str, address: int | None = None) -> RemoteSystem | None:
        if address:
            filters = {"system_id64": {"value": int(address)}}
        else:
            filters = {"system_name": {"value": name}}
        payload = {
            "filters": filters,
            "sort": [{"body_id": {"direction": "asc"}}],
            "size": 200,
            "page": 0,
        }
        data = _http_json(SPANSH_SEARCH, timeout=self.timeout, payload=payload)
        if not isinstance(data, dict) or not data.get("results"):
            return None
        return _parse_spansh(name, data, address)

    def _save(self, system: RemoteSystem) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self.cache_path(system.name, system.address).write_text(
                json.dumps(system.to_cache(), ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            pass


def body_from_journal_scan(event: dict) -> Body | None:
    """Тело из события журнала `Scan` (такой же формат приходит по EDDN)."""
    body_id = event.get("BodyID")
    if body_id is None:
        return None
    star_type = event.get("StarType")
    parents: list[int] = []
    for parent in event.get("Parents") or []:
        if isinstance(parent, dict):
            parents.extend(v for v in parent.values() if isinstance(v, int))
    return Body(
        body_id=int(body_id),
        name=event.get("BodyName") or f"Body {body_id}",
        planet_class=event.get("PlanetClass") or None,
        star_type=star_type or None,
        is_star=bool(star_type),
        radius=_f(event.get("Radius")) or 0.0,
        mass_em=_f(event.get("MassEM")) or 0.0,
        stellar_mass=_f(event.get("StellarMass")) or 0.0,
        surface_temp=_f(event.get("SurfaceTemperature")),
        surface_gravity=_f(event.get("SurfaceGravity")),
        surface_pressure=_f(event.get("SurfacePressure")),
        atmosphere=event.get("Atmosphere") or None,
        atmosphere_composition={
            k: float(v) for k, v in (event.get("AtmosphereComposition") or {}).items()
        },
        volcanism=event.get("Volcanism") or None,
        materials={k: float(v) for k, v in (event.get("Materials") or {}).items()},
        landable=bool(event.get("Landable")),
        distance_ls=_f(event.get("DistanceFromArrivalLS")) or 0.0,
        semi_major_axis=_f(event.get("SemiMajorAxis")),
        parent_ids=parents,
        terraform_state=event.get("TerraformState") or None,
        was_discovered=bool(event.get("WasDiscovered", True)),
        was_mapped=bool(event.get("WasMapped", False)),
        was_footfalled=bool(event.get("WasFootfalled", False)),
        remote=True,
        source="EDDN",
    )


def _journal_system_matches(system: System, message: dict) -> bool:
    address = message.get("SystemAddress")
    if system.address and isinstance(address, int) and address != int(system.address):
        return False
    name = message.get("StarSystem") or message.get("SystemName")
    if system.name and isinstance(name, str) and name:
        if not system.address and name.lower() != system.name.lower():
            return False
    return True


def apply_eddn(system: System, message: dict) -> bool:
    """Применяет живое сообщение EDDN к текущей системе (только чужие данные)."""
    changed = _apply_eddn_body(system, message)
    if changed:
        sources = set(getattr(system, "remote_sources", []) or [])
        if "EDDN" not in sources:
            sources.add("EDDN")
            system.remote_sources = sorted(sources)
    return changed


def _apply_eddn_body(system: System, message: dict) -> bool:
    event = message.get("event")
    if event not in ("Scan", "FSSBodySignals", "SAASignalsFound", "SAAScanComplete"):
        return False
    if not _journal_system_matches(system, message):
        return False

    body_id = message.get("BodyID")
    if body_id is None:
        return False
    body = system.bodies.get(int(body_id))
    changed = False

    if event == "Scan":
        incoming = body_from_journal_scan(message)
        if incoming is None:
            return False
        if body is None:
            system.bodies[incoming.body_id] = incoming
            return True
        # своё тело не перезаписываем — только дополняем недостающее
        for field_name in (
            "planet_class",
            "star_type",
            "atmosphere",
            "volcanism",
            "terraform_state",
        ):
            if getattr(body, field_name) in (None, "") and getattr(incoming, field_name):
                setattr(body, field_name, getattr(incoming, field_name))
                changed = True
        for field_name in ("mass_em", "stellar_mass", "radius", "distance_ls", "was_footfalled"):
            if not getattr(body, field_name) and getattr(incoming, field_name):
                setattr(body, field_name, getattr(incoming, field_name))
                changed = True
        if not body.materials and incoming.materials:
            body.materials = incoming.materials
            changed = True
        if not body.atmosphere_composition and incoming.atmosphere_composition:
            body.atmosphere_composition = incoming.atmosphere_composition
            changed = True
        return changed

    if body is None:
        body = Body(body_id=int(body_id), name=message.get("BodyName") or f"Body {body_id}", remote=True, source="EDDN")
        system.bodies[body.body_id] = body
        changed = True

    if event in ("FSSBodySignals", "SAASignalsFound"):
        for signal in message.get("Signals") or []:
            kind = (signal.get("Type") or "").lower()
            count = int(signal.get("Count") or 0)
            if "biological" in kind and body.bio_signals is None:
                body.bio_signals = count
                body.signals_known = True
                changed = True
            elif "geological" in kind and body.geo_signals is None:
                body.geo_signals = count
                changed = True
        genuses = message.get("Genuses") or []
        if genuses and not body.genuses:
            body.genuses = {
                str(item.get("Genus")): int(item.get("Count") or 1)
                for item in genuses
                if item.get("Genus")
            }
            changed = True
        if event == "SAASignalsFound" and not body.dss_scanned:
            body.dss_remote = True
            changed = True

    if event == "SAAScanComplete" and not body.dss_scanned:
        body.dss_remote = True
        changed = True

    if changed and body.source is None:
        body.source = "EDDN"
    return changed


def merge_into_system(system: System, remote: RemoteSystem) -> int:
    """Добавляет в систему тела, известные другим командирам. Возвращает число новых."""
    added = 0
    for body_id, remote_body in remote.bodies.items():
        local = system.bodies.get(body_id)
        if local is None:
            system.bodies[body_id] = remote_body.to_body()
            added += 1
        else:
            remote_body.enrich(local)
    if remote.address and not system.address:
        system.address = remote.address
    system.remote_sources = sorted(set(getattr(system, "remote_sources", []) or []) | set(remote.sources))
    if remote.estimated_scan_value:
        system.remote_scan_value = remote.estimated_scan_value
    if remote.estimated_mapped_value:
        system.remote_mapped_value = remote.estimated_mapped_value
    return added
