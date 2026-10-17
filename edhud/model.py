# Edited by nc.ai 0.8.8.0 on macbook 2026-10-17 20:16:06
"""Состояние игры: система, тела, биология, статус, маршрут.

Модель собирается из событий журнала (как это делает EDMarketConnector в
monitor.py) плюс периодических снимков Status.json. Всё, что нужно оверлею,
доступно через GameState — рендер ничего не знает про журналы.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

from . import codex
from .route import Route
from .values import body_values

# Биты Flags из Status.json (как в EDMC/dashboard.py)
FLAG_DOCKED = 1 << 0
FLAG_LANDED = 1 << 1
FLAG_SUPERCRUISE = 1 << 4
FLAG_SCOOPING = 1 << 11
FLAG_FSD_CHARGING = 1 << 12
FLAG_LOW_FUEL = 1 << 14
FLAG_IN_MAINSHIP = 1 << 19
FLAG_IN_FIGHTER = 1 << 20
FLAG_IN_SRV = 1 << 21
FLAG_FSD_JUMP = 1 << 25

GUI_FOCUS = {
    0: "None",
    1: "InternalPanel",
    2: "ExternalPanel",
    3: "Comms",
    4: "RolePanel",
    5: "StationServices",
    6: "GalaxyMap",
    7: "SystemMap",
    8: "Orrery",
    9: "FSS",
    10: "SAA",
    11: "Codex",
}


def surface_distance(lat1: float, lon1: float, lat2: float, lon2: float, radius: float) -> float:
    """Расстояние по поверхности сферы (метры) — гаверсинус."""
    if radius <= 0:
        radius = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


@dataclass
class Organic:
    key: str
    genus: str | None = None
    species: str | None = None
    variant: str | None = None
    genus_local: str | None = None
    species_local: str | None = None
    variant_local: str | None = None
    samples: int = 0
    analysed: bool = False
    sample_pos: list[tuple[float, float]] = field(default_factory=list)
    last_ts: float = 0.0

    @property
    def genus_en(self) -> str:
        return self.genus_local or codex.display_name(self.genus or self.species)

    @property
    def species_en(self) -> str | None:
        if self.species_local:
            return self.species_local
        return codex.display_name(self.species) if self.species else None

    @property
    def variant_en(self) -> str | None:
        return self.variant_local or (codex.display_name(self.variant) if self.variant else None)

    @property
    def variant_short(self) -> str | None:
        """Только название окраса: "Bacterium Cerbrus - Lime" -> "Lime"."""
        variant = self.variant_en
        if not variant:
            return None
        species = self.species_en
        if species and variant.startswith(species + " - "):
            return variant[len(species) + 3:]
        parts = variant.split(" - ")
        return parts[-1] if len(parts) > 1 else variant

    @property
    def label(self) -> str:
        base = self.species_en or self.genus_en
        variant = self.variant_short
        return f"{base} - {variant}" if variant and variant not in base else base

    @property
    def reward(self) -> int:
        return codex.reward_for(self.genus_en, self.species_en, self.variant_short)

    @property
    def scans_text(self) -> str:
        if self.analysed:
            return "готово"
        return f"{min(self.samples, 3)}/3"

    def to_persist(self) -> dict:
        return {
            "key": self.key,
            "genus": self.genus,
            "species": self.species,
            "variant": self.variant,
            "genus_local": self.genus_local,
            "species_local": self.species_local,
            "variant_local": self.variant_local,
            "samples": self.samples,
            "analysed": self.analysed,
            "sample_pos": [list(p) for p in self.sample_pos],
            "last_ts": self.last_ts,
        }

    @classmethod
    def from_persist(cls, data: dict) -> "Organic":
        return cls(
            key=data.get("key", ""),
            genus=data.get("genus"),
            species=data.get("species"),
            variant=data.get("variant"),
            genus_local=data.get("genus_local"),
            species_local=data.get("species_local"),
            variant_local=data.get("variant_local"),
            samples=int(data.get("samples") or 0),
            analysed=bool(data.get("analysed")),
            sample_pos=[(float(p[0]), float(p[1])) for p in data.get("sample_pos") or []],
            last_ts=float(data.get("last_ts") or 0.0),
        )


@dataclass
class Body:
    body_id: int
    name: str
    planet_class: str | None = None
    star_type: str | None = None
    is_star: bool = False
    sub_class: int | None = None
    radius: float = 0.0
    mass_em: float = 0.0
    stellar_mass: float = 0.0
    surface_temp: float | None = None
    surface_gravity: float | None = None
    surface_pressure: float | None = None
    atmosphere: str | None = None
    atmosphere_composition: dict[str, float] = field(default_factory=dict)
    volcanism: str | None = None
    materials: dict[str, float] = field(default_factory=dict)
    landable: bool = False
    distance_ls: float = 0.0
    semi_major_axis: float | None = None
    parent_ids: list[int] = field(default_factory=list)
    terraform_state: str | None = None
    has_rings: bool = False
    was_discovered: bool = False
    was_mapped: bool = False
    bio_signals: int | None = None
    geo_signals: int | None = None
    genuses: dict[str, int] = field(default_factory=dict)
    dss_scanned: bool = False
    signals_known: bool = False
    organisms: dict[str, Organic] = field(default_factory=dict)
    # данные от других командиров (EDSM/Spansh, т.е. EDDN)
    remote: bool = False
    source: str | None = None
    discovered_by: str | None = None
    mapped_by: str | None = None

    # ------------------------------------------------------------- удобное
    @property
    def is_landable(self) -> bool:
        return self.landable

    @property
    def bio_total(self) -> int:
        return self.bio_signals or 0

    @property
    def bio_analysed(self) -> int:
        return sum(1 for o in self.organisms.values() if o.analysed)

    @property
    def bio_started(self) -> int:
        return sum(1 for o in self.organisms.values() if o.samples > 0)

    @property
    def atmosphere_type(self) -> str | None:
        """Тип атмосферы в нотации критериев: "thin neon atmosphere" -> "Neon"."""
        if not self.atmosphere:
            return None
        text = self.atmosphere.lower().replace("-", " ").replace(" atmosphere", "").strip()
        for prefix in ("no ", "thin ", "thick "):
            if text.startswith(prefix):
                text = text[len(prefix):]
        words = [w for w in text.split() if w and w not in ("thin", "thick")]
        if not words or words == ["no"] or words == ["none"]:
            return None
        return "".join(w.capitalize() for w in words)

    def to_persist(self) -> dict:
        data = {k: v for k, v in self.__dict__.items() if k != "organisms"}
        data["organisms"] = [o.to_persist() for o in self.organisms.values()]
        return data

    @classmethod
    def from_persist(cls, data: dict) -> "Body":
        body = cls(body_id=int(data.get("body_id") or 0), name=data.get("name") or "")
        for key, value in data.items():
            if key in ("body_id", "name", "organisms"):
                continue
            if hasattr(body, key):
                setattr(body, key, value)
        for raw in data.get("organisms") or []:
            org = Organic.from_persist(raw)
            body.organisms[org.key] = org
        return body


@dataclass
class System:
    address: int | None = None
    name: str | None = None
    star_pos: tuple[float, float, float] | None = None
    body_count: int | None = None
    population: int | None = None
    bodies: dict[int, Body] = field(default_factory=dict)
    # суммарные оценки системы (EDSM/Spansh) и источники догрузки
    remote_sources: list[str] = field(default_factory=list)
    remote_scan_value: int | None = None
    remote_mapped_value: int | None = None

    def body(self, body_id: int | None) -> Body | None:
        if body_id is None:
            return None
        return self.bodies.get(body_id)

    def body_by_name(self, name: str | None) -> Body | None:
        if not name:
            return None
        for body in self.bodies.values():
            if body.name == name:
                return body
        return None

    def main_star(self) -> Body | None:
        for candidate in (self.bodies.get(0), ):
            if candidate and candidate.is_star:
                return candidate
        stars = [b for b in self.bodies.values() if b.is_star]
        if not stars:
            return None
        return min(stars, key=lambda b: (len(b.parent_ids), -b.stellar_mass or 0))

    def parents_of(self, body: Body) -> list[Body]:
        return [self.bodies[pid] for pid in body.parent_ids if pid in self.bodies]

    @property
    def bio_bodies(self) -> list[Body]:
        return [b for b in self.bodies.values() if (b.bio_signals or 0) > 0]

    def to_persist(self) -> dict:
        return {
            "address": self.address,
            "name": self.name,
            "star_pos": list(self.star_pos) if self.star_pos else None,
            "body_count": self.body_count,
            "population": self.population,
            "remote_sources": list(self.remote_sources),
            "remote_scan_value": self.remote_scan_value,
            "remote_mapped_value": self.remote_mapped_value,
            "bodies": [b.to_persist() for b in self.bodies.values()],
        }

    @classmethod
    def from_persist(cls, data: dict) -> "System":
        pos = data.get("star_pos")
        system = cls(
            address=data.get("address"),
            name=data.get("name"),
            star_pos=(float(pos[0]), float(pos[1]), float(pos[2])) if pos else None,
            body_count=data.get("body_count"),
            population=data.get("population"),
            remote_sources=list(data.get("remote_sources") or []),
            remote_scan_value=data.get("remote_scan_value"),
            remote_mapped_value=data.get("remote_mapped_value"),
        )
        for raw in data.get("bodies") or []:
            body = Body.from_persist(raw)
            system.bodies[body.body_id] = body
        return system


@dataclass
class Status:
    raw: dict = field(default_factory=dict)
    flags: int = 0
    fuel_main: float = 0.0
    fuel_reserve: float = 0.0
    cargo: float = 0.0
    lat: float | None = None
    lon: float | None = None
    altitude: float | None = None
    heading: float | None = None
    planet_radius: float | None = None
    temperature: float | None = None
    gravity: float | None = None
    oxygen: float | None = None
    body_name: str | None = None
    body_id: int | None = None
    balance: int | None = None
    gui_focus: int = 0
    legal_state: str | None = None
    ts: float = 0.0

    def update(self, data: dict) -> None:
        self.raw = data
        self.flags = int(data.get("Flags") or 0)
        fuel = data.get("Fuel") or {}
        if isinstance(fuel, dict):
            self.fuel_main = float(fuel.get("FuelMain") or 0.0)
            self.fuel_reserve = float(fuel.get("FuelReserve") or 0.0)
        self.cargo = float(data.get("Cargo") or 0.0)
        self.lat = _f(data.get("Latitude"))
        self.lon = _f(data.get("Longitude"))
        self.altitude = _f(data.get("Altitude"))
        self.heading = _f(data.get("Heading"))
        self.planet_radius = _f(data.get("PlanetRadius"))
        self.temperature = _f(data.get("Temperature"))
        self.gravity = _f(data.get("Gravity"))
        self.oxygen = _f(data.get("Oxygen"))
        self.body_name = data.get("BodyName")
        self.body_id = data.get("BodyID")
        self.balance = data.get("Balance")
        self.gui_focus = int(data.get("GuiFocus") or 0)
        self.legal_state = data.get("LegalState")
        self.ts = time.time()

    def flag(self, bit: int) -> bool:
        return bool(self.flags & bit)

    @property
    def docked(self) -> bool:
        return self.flag(FLAG_DOCKED)

    @property
    def landed(self) -> bool:
        return self.flag(FLAG_LANDED)

    @property
    def supercruise(self) -> bool:
        return self.flag(FLAG_SUPERCRUISE)

    @property
    def srv(self) -> bool:
        return self.flag(FLAG_IN_SRV)

    @property
    def in_ship(self) -> bool:
        return self.flag(FLAG_IN_MAINSHIP) or self.flag(FLAG_IN_FIGHTER)

    @property
    def fsd_charging(self) -> bool:
        return self.flag(FLAG_FSD_CHARGING)

    @property
    def low_fuel(self) -> bool:
        return self.flag(FLAG_LOW_FUEL)

    @property
    def scooping(self) -> bool:
        return self.flag(FLAG_SCOOPING)

    @property
    def on_foot(self) -> bool:
        return (
            not self.docked
            and not self.supercruise
            and not self.srv
            and not self.flag(FLAG_IN_MAINSHIP)
            and not self.flag(FLAG_IN_FIGHTER)
            and self.lat is not None
        )


def _f(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class GameState:
    cmdr: str | None = None
    fid: str | None = None
    ship: str | None = None
    ship_name: str | None = None
    game_mode: str | None = None
    mode: str = "Ship"  # Ship | SRV | OnFoot
    system: System = field(default_factory=System)
    current_body_id: int | None = None
    current_body_name: str | None = None
    status: Status = field(default_factory=Status)
    route: Route = field(default_factory=Route)
    fsd_target: str | None = None
    fsd_target_class: str | None = None
    jumps_in_route: int | None = None
    jump_dist: float = 0.0
    session_jumps: int = 0
    last_jump_ts: float = 0.0
    avg_jump_sec: float = 0.0
    session_started: float = field(default_factory=time.time)
    last_event_ts: float = 0.0
    last_event: str | None = None
    game_running: bool = False
    organic_alert: str | None = None
    organic_alert_ts: float = 0.0
    # стоимость данных за сессию (cr)
    session_scan_value: int = 0  # сканы тел с множителями первооткрывателя
    session_map_value: int = 0  # добавка за DSS (картография)
    session_organic_estimate: int = 0  # оценка сданной биологии
    session_sold: int = 0  # реально проданные данные (SellExplorationData)
    session_organic_sold: int = 0  # реально проданная биология (SellOrganicData)
    _jump_times: list[float] = field(default_factory=list)
    _valued_bodies: dict[tuple[int, int], tuple[int, int]] = field(default_factory=dict)

    # ------------------------------------------------------------- события
    def apply(self, event: dict) -> None:
        name = event.get("event") or ""
        handler = getattr(self, f"_on_{name.lower()}", None)
        self.last_event = name
        self.last_event_ts = time.time()
        if name.startswith("Scan") or name in ("LoadGame", "Location", "FSDJump"):
            self.game_running = True
        if handler is not None:
            handler(event)

    # --- запуск/система
    def _on_loadgame(self, e: dict) -> None:
        self.cmdr = e.get("Commander")
        self.fid = e.get("FID")
        self.ship = e.get("Ship")
        self.ship_name = e.get("ShipName")
        self.game_mode = e.get("GameMode")
        self.game_running = True
        if e.get("Fuel") is not None:
            self.status.fuel_main = float(e.get("Fuel") or 0.0)

    def _on_loadout(self, e: dict) -> None:
        self.ship = e.get("Ship") or self.ship
        if e.get("ShipName") is not None:
            self.ship_name = e.get("ShipName") or self.ship_name

    def _on_shutdown(self, _e: dict) -> None:
        self.game_running = False

    def _set_system(self, e: dict) -> None:
        pos = e.get("StarPos")
        address = e.get("SystemAddress")
        name = e.get("StarSystem")
        changed = address is not None and address != self.system.address
        if changed:
            self.system = System(address=address, name=name)
            self.current_body_id = None
            self.current_body_name = None
        self.system.address = address or self.system.address
        self.system.name = name or self.system.name
        if isinstance(pos, (list, tuple)) and len(pos) == 3:
            self.system.star_pos = (float(pos[0]), float(pos[1]), float(pos[2]))
        if e.get("Population") is not None:
            self.system.population = e.get("Population")
        if e.get("FuelLevel") is not None:
            self.status.fuel_main = float(e.get("FuelLevel") or 0.0)
        body = e.get("Body")
        if body:
            self.current_body_name = body
            if e.get("BodyID") is not None:
                self.current_body_id = e.get("BodyID")

    def _on_location(self, e: dict) -> None:
        self._set_system(e)
        if e.get("Docked"):
            self.mode = "Ship"

    _on_carrierjump = _on_location

    def _on_fsdjump(self, e: dict) -> None:
        self._set_system(e)
        now = time.time()
        if self.last_jump_ts:
            self._jump_times.append(now - self.last_jump_ts)
            self._jump_times = self._jump_times[-10:]
            self.avg_jump_sec = sum(self._jump_times) / len(self._jump_times)
        self.last_jump_ts = now
        self.session_jumps += 1
        self.jump_dist = float(e.get("JumpDist") or 0.0)
        if e.get("FuelLevel") is not None:
            self.status.fuel_main = float(e.get("FuelLevel") or 0.0)
        self.current_body_id = None
        self.current_body_name = None

    def _on_navroute(self, e: dict) -> None:
        if not self.route.locked:
            self.route = Route.from_navroute(e)

    def _on_navrouteclear(self, _e: dict) -> None:
        if not self.route.locked and self.route.source == "game":
            self.route = Route()

    def _on_fsdtarget(self, e: dict) -> None:
        self.fsd_target = e.get("Name")
        self.fsd_target_class = e.get("StarClass")
        self.jumps_in_route = e.get("RemainingJumpsInRoute")

    # --- тела и биология
    def _on_scan(self, e: dict) -> None:
        body_id = e.get("BodyID")
        if body_id is None:
            return
        body = self.system.bodies.get(body_id)
        if body is None:
            body = Body(body_id=body_id, name=e.get("BodyName") or "")
            self.system.bodies[body_id] = body
        body.name = e.get("BodyName") or body.name
        if e.get("StarType"):
            body.is_star = True
            body.star_type = e.get("StarType")
            body.sub_class = e.get("Subclass")
            body.stellar_mass = float(e.get("StellarMass") or 0.0)
        body.planet_class = e.get("PlanetClass") or body.planet_class
        if e.get("Radius") is not None:
            body.radius = float(e.get("Radius") or 0.0)
        if e.get("MassEM") is not None:
            body.mass_em = float(e.get("MassEM") or 0.0)
        body.surface_temp = _f(e.get("SurfaceTemperature")) or body.surface_temp
        body.surface_gravity = _f(e.get("SurfaceGravity")) or body.surface_gravity
        body.surface_pressure = _f(e.get("SurfacePressure"))
        if e.get("Atmosphere") is not None:
            body.atmosphere = e.get("Atmosphere")
        comp = e.get("AtmosphereComposition")
        if isinstance(comp, dict):
            body.atmosphere_composition = {k: float(v) for k, v in comp.items()}
        body.volcanism = e.get("Volcanism") or body.volcanism
        mats = e.get("Materials")
        if isinstance(mats, dict):
            body.materials = {k: float(v) for k, v in mats.items()}
        if e.get("Landable") is not None:
            body.landable = bool(e.get("Landable"))
        body.distance_ls = _f(e.get("DistanceFromArrivalLS")) or body.distance_ls
        body.semi_major_axis = _f(e.get("SemiMajorAxis")) or body.semi_major_axis
        parents = e.get("Parents")
        if isinstance(parents, list):
            ids: list[int] = []
            for parent in parents:
                if isinstance(parent, dict):
                    for value in parent.values():
                        if isinstance(value, int):
                            ids.append(value)
            body.parent_ids = ids
        body.terraform_state = e.get("TerraformState") or body.terraform_state
        if e.get("Rings") is not None:
            body.has_rings = bool(e.get("Rings"))
        if e.get("WasDiscovered") is not None:
            body.was_discovered = bool(e.get("WasDiscovered"))
        if e.get("WasMapped") is not None:
            body.was_mapped = bool(e.get("WasMapped"))
        if e.get("BodyCount") is not None:
            self.system.body_count = e.get("BodyCount")
        self._account_scan(body_id)

    def _account_scan(self, body_id: int | None = None, mapped: bool = False) -> None:
        """Считает стоимость тела: скан сразу, картографию — по факту DSS."""
        body = self.system.body(body_id)
        if body is None:
            return
        breakdown = body_values(body)
        if breakdown is None:
            return
        key = (self.system.address or 0, body.body_id)
        scan_done, map_done = self._valued_bodies.get(key, (0, 0))
        if breakdown.scan > scan_done:
            self.session_scan_value += breakdown.scan - scan_done
            scan_done = breakdown.scan
        if mapped:
            delta = max(0, (breakdown.mapped - breakdown.scan) - map_done)
            if delta:
                self.session_map_value += delta
                map_done += delta
        self._valued_bodies[key] = (scan_done, map_done)

    def _on_fssbodysignals(self, e: dict) -> None:
        body = self._ensure_body(e)
        if body is None:
            return
        for sig in e.get("Signals") or []:
            kind = (sig.get("Type") or "").lower()
            count = int(sig.get("Count") or 0)
            if "biological" in kind:
                body.bio_signals = count
            elif "geological" in kind:
                body.geo_signals = count
        body.signals_known = True

    def _on_saasignalsfound(self, e: dict) -> None:
        body = self._ensure_body(e)
        if body is None:
            return
        body.signals_known = True
        body.dss_scanned = True
        for sig in e.get("Signals") or []:
            kind = (sig.get("Type") or "").lower()
            count = int(sig.get("Count") or 0)
            if "biological" in kind:
                body.bio_signals = max(body.bio_signals or 0, count)
            elif "geological" in kind:
                body.geo_signals = count
        genuses = e.get("Genuses") or []
        if genuses:
            body.genuses = {}
            for item in genuses:
                genus = item.get("Genus")
                if genus:
                    body.genuses[str(genus)] = int(item.get("Count") or 1)
        self._account_scan(body.body_id, mapped=True)

    def _on_saascancomplete(self, e: dict) -> None:
        body = self._ensure_body(e)
        if body is not None:
            body.dss_scanned = True
            self._account_scan(body.body_id, mapped=True)

    def _on_sellexplorationdata(self, e: dict) -> None:
        try:
            self.session_sold += int(e.get("TotalEarnings") or 0)
        except (TypeError, ValueError):
            pass

    def _on_multisellexplorationdata(self, e: dict) -> None:
        for system in e.get("Systems") or []:
            try:
                self.session_sold += int(system.get("Earned") or system.get("Earnings") or 0)
            except (TypeError, ValueError):
                continue

    def _on_sellorganicdata(self, e: dict) -> None:
        total = 0
        for item in e.get("BioData") or []:
            try:
                total += int(item.get("Value") or 0) + int(item.get("Bonus") or 0)
            except (TypeError, ValueError):
                continue
        self.session_organic_sold += total

    def _on_scanorganic(self, e: dict) -> None:
        body = self._ensure_body(e)
        if body is None:
            return
        genus = e.get("Genus")
        species = e.get("Species")
        variant = e.get("Variant")
        key = species or genus or "unknown"
        organic = body.organisms.get(key)
        if organic is None:
            organic = Organic(key=key)
            body.organisms[key] = organic
        organic.genus = genus or organic.genus
        organic.species = species or organic.species
        organic.variant = variant or organic.variant
        organic.genus_local = e.get("Genus_Localised") or organic.genus_local
        organic.species_local = e.get("Species_Localised") or organic.species_local
        organic.variant_local = e.get("Variant_Localised") or organic.variant_local
        scan_type = (e.get("ScanType") or "").lower()
        lat, lon = self.status.lat, self.status.lon
        if scan_type == "log":
            organic.samples = max(organic.samples, 1)
            self._alert(f"Биология: {organic.genus_en} — первая проба")
        elif scan_type == "sample":
            organic.samples = max(organic.samples, 2)
            self._alert(f"Биология: {organic.genus_en} — вторая проба")
        elif scan_type in ("analyse", "analyze"):
            organic.samples = 3
            organic.analysed = True
            self.session_organic_estimate += organic.reward
            self._alert(f"Биология: {organic.genus_en} — анализ сдан")
        if lat is not None and lon is not None and scan_type in ("log", "sample"):
            organic.sample_pos.append((float(lat), float(lon)))
        organic.last_ts = time.time()

    def _on_died(self, _e: dict) -> None:
        # при смерти прогресс проб сбрасывается
        for organic in self._current_body_organisms():
            if not organic.analysed:
                organic.samples = 0
                organic.sample_pos.clear()

    _on_resurrect = _on_died

    # --- перемещения/режим
    def _on_supercruiseentry(self, _e: dict) -> None:
        self.mode = "Ship"

    def _on_supercruiseexit(self, e: dict) -> None:
        self.mode = "Ship"
        if e.get("Body"):
            self.current_body_name = e.get("Body")
            if e.get("BodyID") is not None:
                self.current_body_id = e.get("BodyID")

    def _on_approachbody(self, e: dict) -> None:
        if e.get("Body"):
            self.current_body_name = e.get("Body")
        if e.get("BodyID") is not None:
            self.current_body_id = e.get("BodyID")

    def _on_leavebody(self, _e: dict) -> None:
        self.current_body_id = None
        self.current_body_name = None

    def _on_touchdown(self, e: dict) -> None:
        self.mode = "Ship" if not e.get("OnFoot") else "OnFoot"
        self._on_approachbody(e)

    def _on_liftoff(self, _e: dict) -> None:
        self.mode = "Ship"

    def _on_disembark(self, _e: dict) -> None:
        self.mode = "OnFoot"

    def _on_embark(self, _e: dict) -> None:
        self.mode = "Ship"

    def _on_docked(self, _e: dict) -> None:
        self.mode = "Ship"

    # ------------------------------------------------------------- статус
    def apply_status(self, data: dict) -> None:
        self.status.update(data)
        if self.status.body_id is not None and self.status.body_id != self.current_body_id:
            if self.system.body(self.status.body_id):
                self.current_body_id = self.status.body_id
                self.current_body_name = self.status.body_name or self.current_body_name
        if self.status.body_name and not self.current_body_name:
            self.current_body_name = self.status.body_name

    # ------------------------------------------------------------- помощники
    def _ensure_body(self, e: dict) -> Body | None:
        body_id = e.get("BodyID")
        name = e.get("BodyName") or e.get("Body")
        if body_id is None:
            body_id = self.current_body_id
        if body_id is None and name and self.current_body_name == name:
            body_id = self.current_body_id
        if body_id is None:
            return None
        body = self.system.bodies.get(body_id)
        if body is None:
            body = Body(body_id=body_id, name=name or f"Body {body_id}")
            if self.current_body_id == body_id and self.current_body_name:
                body.name = self.current_body_name
            self.system.bodies[body_id] = body
        if name:
            body.name = name
        return body

    def _alert(self, text: str) -> None:
        self.organic_alert = text
        self.organic_alert_ts = time.time()

    def _current_body_organisms(self) -> list[Organic]:
        body = self.current_body()
        return list(body.organisms.values()) if body else []

    def current_body(self) -> Body | None:
        body = self.system.body(self.current_body_id)
        if body is not None:
            return body
        return self.system.body_by_name(self.current_body_name)

    def body_for_status(self) -> Body | None:
        return self.system.body(self.status.body_id) or self.current_body()

    def current_system_name(self) -> str | None:
        return self.system.name

    @property
    def position(self) -> tuple[float, float, float] | None:
        return self.system.star_pos

    @property
    def in_bio_range(self) -> bool:
        body = self.body_for_status()
        return bool(body and (body.bio_signals or 0) > 0)

    def active_organic(self) -> Organic | None:
        """Организм, который сейчас сканируется/сдан (для колониальной дистанции)."""
        body = self.body_for_status()
        if not body:
            return None
        active = [o for o in body.organisms.values() if not o.analysed and o.samples > 0]
        if not active:
            return None
        return max(active, key=lambda o: o.last_ts)

    def colony_distance(self) -> tuple[float, int] | None:
        """(расстояние от последней пробы, требуемый интервал) в метрах."""
        organic = self.active_organic()
        if not organic or not organic.sample_pos:
            return None
        lat, lon = self.status.lat, self.status.lon
        if lat is None or lon is None:
            return None
        body = self.body_for_status()
        radius = self.status.planet_radius or (body.radius if body else 0.0) or 0.0
        last_lat, last_lon = organic.sample_pos[-1]
        dist = surface_distance(float(lat), float(lon), last_lat, last_lon, radius)
        return dist, codex.sample_range(organic.genus)
