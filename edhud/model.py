# Edited by nc.ai 0.8.8.0 on macbook 2026-10-17 20:16:06
"""Состояние игры: система, тела, биология, статус, маршрут.

Модель собирается из событий журнала (как это делает EDMarketConnector в
monitor.py) плюс периодических снимков Status.json. Всё, что нужно оверлею,
доступно через GameState — рендер ничего не знает про журналы.
"""
from __future__ import annotations

import math
import time
from datetime import datetime
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
# Бит 17 — FsdCharging в Status.json (журнал Frontier). Бит 12 — ручник ТРП.
FLAG_FSD_CHARGING = 1 << 17
FLAG_HAS_LAT_LONG = 1 << 21
FLAG_FSD_JUMP = 1 << 30
FLAG_LOW_FUEL = 1 << 14
FLAG_IN_MAINSHIP = 1 << 19
FLAG_IN_FIGHTER = 1 << 20
FLAG_IN_SRV = 1 << 21
# Flags2: планирование / атмосфера
FLAG2_GLIDE = 1 << 12
# ниже этого (м) считаем, что ещё в атмосфере / у поверхности
ATMOSPHERE_ALT_M = 100_000.0

# Пояса, в которых можно добывать: ледяной, каменный, металлический, богатый металлами.
_MINEABLE_RING = {
    "eRingClass_Icy",
    "eRingClass_Rocky",
    "eRingClass_MetalRich",
    "eRingClass_Metallic",
}


def _apply_signal_counts(body: Body, signals: list, merge_bio: bool = False) -> None:
    """Био, гео и Planetary Mining Location из FSSBodySignals / SAASignalsFound."""
    for sig in signals:
        if not isinstance(sig, dict):
            continue
        kind = (sig.get("Type") or "").lower()
        local = (sig.get("Type_Localised") or "").lower()
        count = int(sig.get("Count") or 0)
        if "biological" in kind:
            if merge_bio:
                body.bio_signals = max(body.bio_signals or 0, count)
            else:
                body.bio_signals = count
        elif "geological" in kind:
            body.geo_signals = count
        elif "planetarymining" in kind or "mining location" in local:
            body.mining_locations = count


def _is_belt_body(name: str | None) -> bool:
    return "belt cluster" in (name or "").lower()


def _mineable_belt(rings: list, name: str | None = None) -> bool:
    """Кольцо или пояс астероидов, где есть добыча."""
    if _is_belt_body(name):
        return True
    for ring in rings:
        if not isinstance(ring, dict):
            continue
        kind = str(ring.get("RingClass") or "")
        if kind in _MINEABLE_RING or "belt" in str(ring.get("Name") or "").lower():
            return True
    return False

# Vista Genomics: бонус "First Logged" — пробу ещё никто не сдавал, платят ×5
FIRST_LOGGED_MULTIPLIER = 5

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


def surface_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Начальный курс от точки 1 к точке 2, градусы 0–360 (0 — север)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def turn_deg(bearing: float, heading: float | None) -> float | None:
    """Куда довернуть от текущего курса: вправо положительное, −180…180."""
    if heading is None:
        return None
    return (bearing - float(heading) + 540.0) % 360.0 - 180.0


@dataclass(frozen=True)
class SampleGuide:
    """Одна стрелка: к пробе, прочь от неё или к уже отмеченному образцу."""

    kind: str  # sample | away | spot
    title: str
    distance_m: float
    need_m: int
    bearing: float | None
    turn: float | None
    ready: bool


@dataclass(frozen=True)
class SamplePlan:
    name: str
    scans: str
    need_m: int
    ready: bool
    guides: tuple[SampleGuide, ...]


@dataclass(frozen=True)
class RadarBlip:
    """Точка на био-радаре относительно курса командира."""

    kind: str  # sample | spot | other | away
    label: str
    distance_m: float
    bearing: float
    turn: float | None
    ready: bool
    index: int = 0


@dataclass(frozen=True)
class RadarView:
    """Круговой радар под панелью биосигналов."""

    title: str
    range_m: float
    need_m: int
    heading: float | None
    ready: bool
    blips: tuple[RadarBlip, ...]


@dataclass
class Organic:
    key: str
    genus: str | None = None
    species: str | None = None
    variant: str | None = None
    genus_local: str | None = None
    species_local: str | None = None
    variant_local: str | None = None
    was_logged: bool | None = None
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
    def first_logged(self) -> bool:
        """First Logged: пробу ещё никто не сдавал — Vista Genomics платит ×5."""
        return self.was_logged is False

    @property
    def payout(self) -> int:
        base = self.reward
        if not base:
            return 0
        return base * FIRST_LOGGED_MULTIPLIER if self.first_logged else base

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
            "was_logged": self.was_logged,
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
            was_logged=data.get("was_logged"),
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
    has_rings: bool = False  # ледяной/каменный/металлический пояс — там можно добывать
    was_discovered: bool = False
    was_mapped: bool = False
    was_footfalled: bool = False
    bio_signals: int | None = None
    geo_signals: int | None = None
    mining_locations: int | None = None  # Planetary Mining Location, штук на теле
    genuses: dict[str, int] = field(default_factory=dict)
    dss_scanned: bool = False
    dss_remote: bool = False
    signals_known: bool = False
    signals_local: bool = False  # сигналы пришли из нашего журнала, не из EDSM/Spansh
    organisms: dict[str, Organic] = field(default_factory=dict)
    # точки биологии с координатами: кодекс и композиционный сканер (CodexEntry)
    bio_spots: list[dict] = field(default_factory=list)
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
class Carrier:
    """Свой флотоносец командира. Чужие носители из FSS сюда не попадают."""

    carrier_id: int | None = None
    callsign: str | None = None
    name: str | None = None
    system: str | None = None
    address: int | None = None
    body_id: int | None = None
    star_pos: tuple[float, float, float] | None = None
    # отложенный прыжок: после DepartureTime локация обновится сама
    jump_dest_system: str | None = None
    jump_dest_address: int | None = None
    jump_dest_body_id: int | None = None
    jump_departure: float | None = None

    @property
    def known(self) -> bool:
        return bool(self.carrier_id or self.callsign or self.system)


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
    # звезда системы не была открыта до нашего скана
    discovered_by_me: bool = False

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
    flags2: int = 0
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
    destination_name: str | None = None
    destination_body: int | None = None
    destination_system: int | None = None
    balance: int | None = None
    gui_focus: int = 0
    legal_state: str | None = None
    ts: float = 0.0

    def update(self, data: dict) -> None:
        self.raw = data
        self.flags = int(data.get("Flags") or 0)
        self.flags2 = int(data.get("Flags2") or 0)
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
        dest = data.get("Destination")
        if isinstance(dest, dict):
            self.destination_name = dest.get("Name")
            body = dest.get("Body")
            self.destination_body = int(body) if isinstance(body, int) else None
            system = dest.get("System")
            self.destination_system = int(system) if isinstance(system, int) else None
        else:
            self.destination_name = None
            self.destination_body = None
            self.destination_system = None
        self.balance = data.get("Balance")
        self.gui_focus = int(data.get("GuiFocus") or 0)
        self.legal_state = data.get("LegalState")
        self.ts = time.time()

    def flag(self, bit: int) -> bool:
        return bool(self.flags & bit)

    def flag2(self, bit: int) -> bool:
        return bool(self.flags2 & bit)

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
    def has_lat_long(self) -> bool:
        return self.flag(FLAG_HAS_LAT_LONG) or self.lat is not None

    @property
    def glide(self) -> bool:
        return self.flag2(FLAG2_GLIDE)

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


def _event_body_name(e: dict) -> str | None:
    """Имя тела из события. ScanOrganic пишет в Body числовой BodyID — это не имя."""
    for key in ("BodyName", "Body"):
        value = e.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _event_body_id(e: dict) -> int | None:
    """BodyID; в ScanOrganic тот же id иногда лежит в поле Body."""
    for key in ("BodyID", "Body"):
        value = e.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value == int(value):
            return int(value)
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            return int(value)
    return None


def _journal_ts(value: Any) -> float | None:
    """ISO-время журнала (…Z) → unix. Нужно для DepartureTime носителя."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def parse_materials(raw: Any) -> dict[str, float]:
    """Журнал отдаёт материалы списком {Name, Percent}, старые события — словарём."""
    rows: list = []
    if isinstance(raw, dict):
        rows = [{"Name": key, "Percent": value} for key, value in raw.items()]
    elif isinstance(raw, list):
        rows = raw
    found: dict[str, float] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        name = item.get("Name") if item.get("Name") is not None else item.get("name")
        percent = item.get("Percent") if "Percent" in item else item.get("percent")
        if not name:
            continue
        value = _f(percent)
        if value is None:
            continue
        found[str(name)] = value
    return found


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
    # тело, по которому только что пришли сигналы (FSS/DSS) — карточка слева
    last_fss_body_id: int | None = None
    status: Status = field(default_factory=Status)
    route: Route = field(default_factory=Route)
    carrier: Carrier = field(default_factory=Carrier)
    # какую вкладку окна показать: route на разгоне к прыжку, bodies в системе
    view_tab: str = "bodies"
    # носитель сменил систему, а координат в журнале нет — их доберёт сеть
    carrier_pos_pending: bool = False
    # корабль в атмосфере / у поверхности — верхний HUD приглушаем
    in_atmosphere: bool = False
    _jump_tab_latched: bool = False
    _was_in_supercruise: bool = False
    fsd_target: str | None = None
    fsd_target_class: str | None = None
    jumps_in_route: int | None = None
    # журнал прислал NavRoute без списка — надо перечитать NavRoute.json
    navroute_stale: bool = False
    jump_dist: float = 0.0
    session_jumps: int = 0
    session_new_systems: int = 0
    last_jump_ts: float = 0.0
    avg_jump_sec: float = 0.0
    session_started: float = field(default_factory=time.time)
    last_event_ts: float = 0.0
    last_event: str | None = None
    game_running: bool = False
    # Legacy (Elite Dangerous 3.8, Horizons/Beyond) — без Odyssey-бонусов и био-прогноза
    legacy: bool = False
    game_version: str | None = None
    build: str | None = None
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
    _new_systems: set[int] = field(default_factory=set)
    _star_pos: dict[int, tuple[float, float, float]] = field(default_factory=dict)
    _star_names: dict[str, tuple[float, float, float]] = field(default_factory=dict)
    # кто открыл систему (имя lower → командир; None = в базе нет имени)
    _discoverers: dict[str, str | None] = field(default_factory=dict)
    _systems_by_me: set[str] = field(default_factory=set)

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
    def _on_fileheader(self, e: dict) -> None:
        self._apply_version(e)

    def _on_loadgame(self, e: dict) -> None:
        self.cmdr = e.get("Commander")
        self.fid = e.get("FID")
        self.ship = e.get("Ship")
        self.ship_name = e.get("ShipName")
        self.game_mode = e.get("GameMode")
        self.game_running = True
        self._apply_version(e)
        if e.get("Fuel") is not None:
            self.status.fuel_main = float(e.get("Fuel") or 0.0)

    def _apply_version(self, e: dict) -> None:
        """Legacy (3.8) или Live/Odyssey (4.x) — по версии игры в Fileheader/LoadGame."""
        version = e.get("gameversion") or e.get("GameVersion")
        if version:
            self.game_version = str(version)
            self.legacy = str(version).startswith("3.")
        build = e.get("build")
        if build:
            self.build = str(build)

    @property
    def odyssey(self) -> bool:
        return not self.legacy

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
            self.last_fss_body_id = None
        self.system.address = address or self.system.address
        self.system.name = name or self.system.name
        if isinstance(pos, (list, tuple)) and len(pos) == 3:
            self.system.star_pos = (float(pos[0]), float(pos[1]), float(pos[2]))
            self._remember_star(self.system.address, self.system.name, self.system.star_pos)
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
        self.view_tab = "bodies"
        if e.get("Docked"):
            self.mode = "Ship"

    def _on_carrierjump(self, e: dict) -> None:
        """Прыжок носителя, на котором мы сидим: прибытие в систему и новая точка носителя."""
        self._on_location(e)
        cid = e.get("MarketID") or e.get("CarrierID")
        own = self.carrier.carrier_id
        callsign = (self.carrier.callsign or "").lower()
        station = (e.get("StationName") or "").lower()
        if own and cid and int(cid) != int(own) and station != callsign:
            return
        if not own and station != callsign and not e.get("CarrierID"):
            return
        self._clear_carrier_jump()
        self._move_carrier(e.get("StarSystem"), e.get("SystemAddress"), e.get("BodyID"), e.get("StarPos"))

    def _on_fsdjump(self, e: dict) -> None:
        self._set_system(e)
        self.view_tab = "bodies"
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

    def _on_startjump(self, e: dict) -> None:
        """Гиперпрыжок — смотрим маршрут. Разгон в суперкруиз вкладку не трогает."""
        if (e.get("JumpType") or "").lower() == "hyperspace":
            self.view_tab = "route"

    def _on_carrierlocation(self, e: dict) -> None:
        self.carrier.carrier_id = e.get("CarrierID") or self.carrier.carrier_id
        self._clear_carrier_jump()
        self._move_carrier(e.get("StarSystem"), e.get("SystemAddress"), e.get("BodyID"), e.get("StarPos"))

    def _on_carrierjumprequest(self, e: dict) -> None:
        """Носитель заложил прыжок. После DepartureTime локация обновится сама (без CarrierLocation)."""
        if not self._is_own_carrier(e):
            return
        self.carrier.jump_dest_system = e.get("SystemName") or e.get("StarSystem")
        address = e.get("SystemAddress")
        self.carrier.jump_dest_address = int(address) if address is not None else None
        body = e.get("BodyID")
        self.carrier.jump_dest_body_id = int(body) if body is not None else None
        self.carrier.jump_departure = _journal_ts(e.get("DepartureTime")) or time.time()
        self.apply_due_carrier_jump()

    def _on_carrierjumpcancelled(self, e: dict) -> None:
        if not self._is_own_carrier(e):
            return
        self._clear_carrier_jump()

    def _is_own_carrier(self, e: dict) -> bool:
        cid = e.get("CarrierID") or e.get("MarketID")
        own = self.carrier.carrier_id
        if own and cid is not None:
            try:
                return int(cid) == int(own)
            except (TypeError, ValueError):
                return False
        return bool(own) or cid is not None

    def _clear_carrier_jump(self) -> None:
        self.carrier.jump_dest_system = None
        self.carrier.jump_dest_address = None
        self.carrier.jump_dest_body_id = None
        self.carrier.jump_departure = None

    def apply_due_carrier_jump(self) -> bool:
        """Если время отбытия прошло — переносим носитель в целевую систему."""
        dep = self.carrier.jump_departure
        if dep is None:
            return False
        if time.time() + 1.0 < dep:
            return False
        system = self.carrier.jump_dest_system
        address = self.carrier.jump_dest_address
        body_id = self.carrier.jump_dest_body_id
        self._clear_carrier_jump()
        self._move_carrier(system, address, body_id, None)
        return True

    def _move_carrier(self, system: str | None, address, body_id, star_pos) -> None:
        """Новая система носителя. Старые координаты больше не годятся: в CarrierLocation их нет."""
        moved = False
        if address is not None and self.carrier.address is not None and int(address) != int(self.carrier.address):
            moved = True
        elif system and self.carrier.system and str(system).lower() != self.carrier.system.lower():
            moved = True
        if moved:
            self.carrier.star_pos = None
        if system:
            self.carrier.system = system
        if address is not None:
            self.carrier.address = int(address)
        if body_id is not None:
            self.carrier.body_id = body_id
        if isinstance(star_pos, (list, tuple)) and len(star_pos) == 3:
            self.carrier.star_pos = (float(star_pos[0]), float(star_pos[1]), float(star_pos[2]))
        self._adopt_carrier_pos()
        self.carrier_pos_pending = self.carrier.star_pos is None and bool(self.carrier.system or self.carrier.address is not None)

    def _on_carrierstats(self, e: dict) -> None:
        self.carrier.carrier_id = e.get("CarrierID") or self.carrier.carrier_id
        if e.get("Callsign"):
            self.carrier.callsign = e.get("Callsign")
        if e.get("Name"):
            self.carrier.name = e.get("Name")

    def _remember_star(
        self,
        address: int | None,
        name: str | None,
        pos: tuple[float, float, float] | None,
    ) -> None:
        if not pos:
            return
        if address is not None:
            self._star_pos[int(address)] = pos
        if name:
            self._star_names[name.lower()] = pos
        self._adopt_carrier_pos()

    def _adopt_carrier_pos(self) -> None:
        if self.carrier.star_pos:
            return
        pos = None
        if self.carrier.address is not None:
            pos = self._star_pos.get(int(self.carrier.address))
        if pos is None and self.carrier.system:
            pos = self._star_names.get(self.carrier.system.lower())
        if pos is None:
            for hop in self.route.hops:
                same_addr = self.carrier.address is not None and hop.address == self.carrier.address
                same_name = bool(self.carrier.system) and hop.system.lower() == self.carrier.system.lower()
                if (same_addr or same_name) and hop.star_pos:
                    pos = hop.star_pos
                    break
        if pos is not None:
            self.carrier.star_pos = pos
            self.carrier_pos_pending = False

    def carrier_star_pos(self) -> tuple[float, float, float] | None:
        self._adopt_carrier_pos()
        return self.carrier.star_pos

    def carrier_distance_ly(self) -> float | None:
        """None — носителя нет или нет координат. 0 — он в текущей системе."""
        if not self.carrier.known:
            return None
        here = self.system.address is not None and self.carrier.address is not None and int(
            self.system.address
        ) == int(self.carrier.address)
        if not here and self.carrier.system and self.system.name:
            here = self.carrier.system.lower() == self.system.name.lower()
        if here:
            return 0.0
        pos = self.carrier_star_pos()
        if not pos or not self.system.star_pos:
            return None
        return math.dist(pos, self.system.star_pos)

    def _on_navroute(self, e: dict) -> None:
        if self.route.locked:
            return
        # Игра часто пишет в журнал только {"event":"NavRoute"} без массива Route.
        # Полный список систем лежит в NavRoute.json — его перечитает журнал-вотчер.
        if e.get("Route"):
            self.route = Route.from_navroute(e)
            self.navroute_stale = False
            self.sync_route_discoverers()
        else:
            self.navroute_stale = True

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
        mats = parse_materials(e.get("Materials"))
        if mats:
            body.materials = mats
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
        rings = e.get("Rings")
        # Пояс у звезды в журнале висит на самой звезде, но добывают его в кластерах.
        # Значок пояса — у планет с кольцами и у тел «Belt Cluster», не у звезды.
        if body.is_star or body.star_type:
            body.has_rings = False
        elif isinstance(rings, list):
            body.has_rings = _mineable_belt(rings, body.name)
        elif _is_belt_body(body.name):
            body.has_rings = True
        if e.get("WasDiscovered") is not None:
            body.was_discovered = bool(e.get("WasDiscovered"))
        self._note_first_discovery(e)
        if e.get("WasMapped") is not None:
            body.was_mapped = bool(e.get("WasMapped"))
        if e.get("WasFootfalled") is not None:
            body.was_footfalled = bool(e.get("WasFootfalled"))
        if e.get("BodyCount") is not None:
            self.system.body_count = e.get("BodyCount")
        self._account_scan(body_id)

    def _note_first_discovery(self, e: dict) -> None:
        """Звезда с WasDiscovered=false — эту систему открыли мы."""
        if e.get("WasDiscovered") is not False or not e.get("StarType"):
            return
        address = e.get("SystemAddress") or self.system.address
        if address is None:
            return
        address = int(address)
        if self.system.address is not None and int(self.system.address) != address:
            return
        self.system.discovered_by_me = True
        if address not in self._new_systems:
            self._new_systems.add(address)
            self.session_new_systems = len(self._new_systems)
        name = e.get("StarSystem") or self.system.name
        if name:
            self.note_system_discoverer(str(name), None, by_me=True)

    def note_system_discoverer(
        self,
        system: str,
        commander: str | None,
        *,
        by_me: bool = False,
        cmdr: str | None = None,
    ) -> None:
        """Запомнить первооткрывателя системы и проставить на хопы маршрута."""
        key = system.strip().lower()
        if not key:
            return
        who = (commander or "").strip() or None
        me = (cmdr or self.cmdr or "").strip().lower()
        if by_me or (who and me and who.lower() == me):
            self._systems_by_me.add(key)
            self._discoverers[key] = who or self.cmdr
        elif key not in self._systems_by_me:
            self._discoverers[key] = who
        self.sync_route_discoverers()

    def sync_route_discoverers(self) -> None:
        for hop in self.route.hops:
            key = hop.system.lower()
            if key in self._systems_by_me:
                hop.discovered_by_me = True
                if not hop.discovered_by and self.cmdr:
                    hop.discovered_by = self.cmdr
                continue
            if key in self._discoverers:
                hop.discovered_by_me = False
                hop.discovered_by = self._discoverers[key]

    def _account_scan(self, body_id: int | None = None, mapped: bool = False) -> None:
        """Считает стоимость тела: скан сразу, картографию — по факту DSS."""
        body = self.system.body(body_id)
        if body is None:
            return
        breakdown = body_values(body, odyssey=self.odyssey)
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
        _apply_signal_counts(body, e.get("Signals") or [])
        body.signals_known = True
        body.signals_local = True
        self.last_fss_body_id = body.body_id

    def _on_saasignalsfound(self, e: dict) -> None:
        body = self._ensure_body(e)
        if body is None:
            return
        body.signals_known = True
        body.signals_local = True
        body.dss_scanned = True
        self.last_fss_body_id = body.body_id
        _apply_signal_counts(body, e.get("Signals") or [], merge_bio=True)
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
        if "WasLogged" in e:
            organic.was_logged = bool(e.get("WasLogged"))
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
            self.session_organic_estimate += organic.payout
            self._alert(f"Биология: {organic.genus_en} — анализ сдан")
        if lat is not None and lon is not None and scan_type in ("log", "sample"):
            organic.sample_pos.append((float(lat), float(lon)))
        organic.last_ts = time.time()

    def _on_codexentry(self, e: dict) -> None:
        """Координата организма: кодекс пишет её при скане на теле."""
        lat, lon = _f(e.get("Latitude")), _f(e.get("Longitude"))
        if lat is None or lon is None:
            return
        name = e.get("Name") or ""
        category = e.get("Category") or ""
        sub = e.get("SubCategory") or ""
        if "Codex_Ent_" not in name and "Biology" not in category and "Organic" not in sub:
            return
        address = e.get("SystemAddress")
        if address is not None and self.system.address is not None and int(address) != int(self.system.address):
            return
        body = self._ensure_body(
            {
                "BodyID": e.get("BodyID"),
                "BodyName": e.get("BodyName") or "",
                "SystemAddress": address,
            }
        )
        if body is None:
            return
        genus = codex.genus_key_from_name(name)
        if not genus:
            return
        label = e.get("Name_Localised") or codex.display_name(name)
        self._add_bio_spot(body, lat, lon, genus, label)

    def _add_bio_spot(self, body: Body, lat: float, lon: float, genus: str | None, label: str) -> None:
        radius = body.radius or self.status.planet_radius or 0.0
        for spot in body.bio_spots:
            if surface_distance(lat, lon, float(spot["lat"]), float(spot["lon"]), radius) < 30:
                return
        body.bio_spots.append(
            {"lat": float(lat), "lon": float(lon), "genus": genus, "name": label}
        )

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
        name = _event_body_name(e)
        body_id = _event_body_id(e)
        if name:
            self.current_body_name = name
        if body_id is not None:
            self.current_body_id = body_id

    def _on_approachbody(self, e: dict) -> None:
        name = _event_body_name(e)
        body_id = _event_body_id(e)
        if name:
            self.current_body_name = name
        if body_id is not None:
            self.current_body_id = body_id

    def _on_leavebody(self, _e: dict) -> None:
        self.current_body_id = None
        self.current_body_name = None
        self.in_atmosphere = False

    def _on_touchdown(self, e: dict) -> None:
        self.mode = "Ship" if not e.get("OnFoot") else "OnFoot"
        self.in_atmosphere = True
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
        self._sync_atmosphere()
        self._sync_travel_tab()
        if self.status.supercruise:
            self._was_in_supercruise = True
        elif not self.status.fsd_charging:
            self._was_in_supercruise = False

    def _sync_atmosphere(self) -> None:
        """Glide/посадка → в атмосфере; выход в SC / LeaveBody / высотный орбитальный круиз → нет."""
        st = self.status
        if st.supercruise or st.docked:
            self.in_atmosphere = False
            return
        if st.glide or st.landed:
            self.in_atmosphere = True
            return
        if st.has_lat_long and st.altitude is not None and st.altitude < ATMOSPHERE_ALT_M:
            self.in_atmosphere = True
            return
        if self.in_atmosphere and st.has_lat_long and st.altitude is not None:
            if st.altitude >= ATMOSPHERE_ALT_M:
                self.in_atmosphere = False
            return
        if self.in_atmosphere and not st.has_lat_long:
            self.in_atmosphere = False

    def _sync_travel_tab(self) -> None:
        """Route — в момент разгона к другой системе, не при входе в суперкруиз."""
        spool = self._hyperspace_spool()
        if spool and not self._jump_tab_latched:
            self.view_tab = "route"
            self._jump_tab_latched = True
        if not self.status.fsd_charging:
            self._jump_tab_latched = False

    def _hyperspace_spool(self) -> bool:
        """Charging FSD к другой системе → вкладка Route (и из обычного космоса)."""
        if not self.status.fsd_charging:
            return False
        dest = self.status.destination_system
        here = self.system.address
        if not isinstance(dest, int) or here is None:
            return False
        return int(dest) != int(here)

    # ------------------------------------------------------------- помощники
    def _ensure_body(self, e: dict) -> Body | None:
        body_id = _event_body_id(e)
        name = _event_body_name(e)
        if body_id is None:
            body_id = self.current_body_id
        if body_id is None and name and self.current_body_name == name:
            body_id = self.current_body_id
        if body_id is None:
            return None
        body = self.system.bodies.get(body_id)
        if body is None:
            body = Body(body_id=body_id, name=name or f"Body {body_id}")
            if self.current_body_id == body_id and isinstance(self.current_body_name, str):
                body.name = self.current_body_name
            self.system.bodies[body_id] = body
        if name:
            body.name = name
        elif not isinstance(body.name, str) or not body.name:
            if isinstance(self.current_body_name, str) and self.current_body_name:
                body.name = self.current_body_name
            else:
                body.name = f"Body {body_id}"
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

    def sample_plan(self) -> SamplePlan | None:
        """Курсы для второй и третьей пробы. Широта есть и пешком, и в SRV, и над планетой."""
        organic = self.active_organic()
        lat, lon = self.status.lat, self.status.lon
        if organic is None or lat is None or lon is None or not organic.sample_pos:
            return None
        body = self.body_for_status()
        radius = self.status.planet_radius or (body.radius if body else 0.0) or 0.0
        need = codex.sample_range(organic.genus)
        heading = self.status.heading
        guides: list[SampleGuide] = []
        closest_gap: tuple[float, float] | None = None  # (distance, bearing to sample)
        for index, (slat, slon) in enumerate(organic.sample_pos, start=1):
            dist = surface_distance(float(lat), float(lon), slat, slon, radius)
            bearing = surface_bearing(float(lat), float(lon), slat, slon) if dist >= 20 else None
            guides.append(
                SampleGuide(
                    kind="sample",
                    title=f"проба {index}",
                    distance_m=dist,
                    need_m=need,
                    bearing=bearing,
                    turn=turn_deg(bearing, heading) if bearing is not None else None,
                    ready=dist >= need,
                )
            )
            if dist < need and (closest_gap is None or dist < closest_gap[0]):
                closest_gap = (dist, bearing if bearing is not None else -1.0)
        ready = all(guide.ready for guide in guides)
        if closest_gap is not None and closest_gap[1] >= 0:
            away = (closest_gap[1] + 180.0) % 360.0
            guides.append(
                SampleGuide(
                    kind="away",
                    title="дальше",
                    distance_m=max(0.0, need - closest_gap[0]),
                    need_m=need,
                    bearing=away,
                    turn=turn_deg(away, heading),
                    ready=False,
                )
            )
        if body is not None:
            spots = self._valid_spots(body, organic, radius, need, float(lat), float(lon))
            for spot, dist, bearing in spots[:3]:
                guides.append(
                    SampleGuide(
                        kind="spot",
                        title=str(spot.get("name") or "образец"),
                        distance_m=dist,
                        need_m=need,
                        bearing=bearing,
                        turn=turn_deg(bearing, heading),
                        ready=True,
                    )
                )
        return SamplePlan(
            name=organic.genus_en or "био",
            scans=organic.scans_text,
            need_m=need,
            ready=ready,
            guides=tuple(guides),
        )

    def _valid_spots(
        self,
        body: Body,
        organic: Organic,
        radius: float,
        need: int,
        lat: float,
        lon: float,
    ) -> list[tuple[dict, float, float]]:
        """Отмеченные образцы того же рода, уже дальше колонии от всех проб."""
        genus = organic.genus
        found: list[tuple[dict, float, float]] = []
        for spot in body.bio_spots:
            spot_genus = spot.get("genus")
            if genus and spot_genus and spot_genus != genus:
                continue
            slat, slon = float(spot["lat"]), float(spot["lon"])
            if any(
                surface_distance(slat, slon, plat, plon, radius) < 30
                for plat, plon in organic.sample_pos
            ):
                continue
            if any(
                surface_distance(slat, slon, plat, plon, radius) < need
                for plat, plon in organic.sample_pos
            ):
                continue
            dist = surface_distance(lat, lon, slat, slon, radius)
            found.append((spot, dist, surface_bearing(lat, lon, slat, slon)))
        found.sort(key=lambda item: item[1])
        return found

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

    def near_surface(self) -> bool:
        """Пешком, в SRV или кораблём над поверхностью — есть широта/долгота."""
        return (
            self.status.lat is not None
            and self.status.lon is not None
            and not self.status.supercruise
            and not self.status.docked
        )

    def radar_view(self) -> RadarView | None:
        """Радар ближайших биоточек: свой род после первой пробы, иначе любые."""
        if not self.near_surface():
            return None
        body = self.body_for_status()
        if body is None or (body.bio_signals or 0) <= 0:
            return None
        lat, lon = float(self.status.lat), float(self.status.lon)
        radius = self.status.planet_radius or body.radius or 0.0
        heading = self.status.heading
        organic = self.active_organic()
        blips: list[RadarBlip] = []

        if organic is not None and organic.sample_pos:
            need = codex.sample_range(organic.genus)
            closest_gap: tuple[float, float] | None = None
            for index, (slat, slon) in enumerate(organic.sample_pos, start=1):
                dist = surface_distance(lat, lon, slat, slon, radius)
                bearing = surface_bearing(lat, lon, slat, slon)
                blips.append(
                    RadarBlip(
                        kind="sample",
                        label=f"проба {index}",
                        distance_m=dist,
                        bearing=bearing,
                        turn=turn_deg(bearing, heading),
                        ready=dist >= need,
                        index=index,
                    )
                )
                if dist < need and (closest_gap is None or dist < closest_gap[0]):
                    closest_gap = (dist, bearing)
            if closest_gap is not None:
                away = (closest_gap[1] + 180.0) % 360.0
                blips.append(
                    RadarBlip(
                        kind="away",
                        label="дальше",
                        distance_m=max(0.0, need - closest_gap[0]),
                        bearing=away,
                        turn=turn_deg(away, heading),
                        ready=False,
                    )
                )
            for spot, dist, bearing in self._valid_spots(body, organic, radius, need, lat, lon)[:6]:
                blips.append(
                    RadarBlip(
                        kind="spot",
                        label=str(spot.get("name") or "образец"),
                        distance_m=dist,
                        bearing=bearing,
                        turn=turn_deg(bearing, heading),
                        ready=True,
                    )
                )
            # те же роды внутри колонии — видно, но «мало»
            for spot in body.bio_spots:
                spot_genus = spot.get("genus")
                if organic.genus and spot_genus and spot_genus != organic.genus:
                    continue
                slat, slon = float(spot["lat"]), float(spot["lon"])
                if any(surface_distance(slat, slon, plat, plon, radius) < 30 for plat, plon in organic.sample_pos):
                    continue
                if all(surface_distance(slat, slon, plat, plon, radius) >= need for plat, plon in organic.sample_pos):
                    continue
                dist = surface_distance(lat, lon, slat, slon, radius)
                bearing = surface_bearing(lat, lon, slat, slon)
                if any(abs(b.distance_m - dist) < 15 and b.kind == "spot" for b in blips):
                    continue
                blips.append(
                    RadarBlip(
                        kind="other",
                        label=str(spot.get("name") or "близко"),
                        distance_m=dist,
                        bearing=bearing,
                        turn=turn_deg(bearing, heading),
                        ready=False,
                    )
                )
            ready = all(b.ready for b in blips if b.kind == "sample")
            span = max((b.distance_m for b in blips if b.kind != "away"), default=float(need))
            range_m = min(5000.0, max(float(need) * 1.35, span * 1.15, 250.0))
            return RadarView(
                title=f"{organic.genus_en} · интервал {need} м",
                range_m=range_m,
                need_m=need,
                heading=heading,
                ready=ready,
                blips=tuple(blips),
            )

        # ещё нет пробы — любые ближайшие отмеченные точки
        for spot in body.bio_spots:
            slat, slon = float(spot["lat"]), float(spot["lon"])
            dist = surface_distance(lat, lon, slat, slon, radius)
            bearing = surface_bearing(lat, lon, slat, slon)
            blips.append(
                RadarBlip(
                    kind="spot",
                    label=str(spot.get("name") or "био"),
                    distance_m=dist,
                    bearing=bearing,
                    turn=turn_deg(bearing, heading),
                    ready=True,
                )
            )
        blips.sort(key=lambda item: item.distance_m)
        blips = blips[:8]
        if not blips:
            return None
        span = blips[-1].distance_m if blips else 300.0
        range_m = min(5000.0, max(span * 1.2, 300.0))
        return RadarView(
            title="ближайшие био",
            range_m=range_m,
            need_m=0,
            heading=heading,
            ready=True,
            blips=tuple(blips),
        )
