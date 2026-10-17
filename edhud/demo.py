# Edited by nc.ai 0.8.8.0 on macbook 2026-10-17 20:13:51
"""Демо-режим: пишет настоящий журнал в отдельный каталог и «проигрывает» его.

Так проверяется весь путь данных (файлы -> watcher -> модель -> HUD) без игры.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path

DEMO_SYSTEM = "Synuefe EN-H d11-96"
DEMO_ADDRESS = 3932277477890
DEMO_POS = [-429.90625, -135.4375, -838.5]


@dataclass
class Step:
    delay: float
    kind: str  # event | status | navroute
    payload: dict


def _scan(body_id: int, name: str, **fields) -> dict:
    event = {
        "timestamp": "2026-01-01T00:00:00Z",
        "event": "Scan",
        "ScanType": "Detailed",
        "BodyName": name,
        "BodyID": body_id,
        "SystemAddress": DEMO_ADDRESS,
        "DistanceFromArrivalLS": fields.pop("distance", 0.0),
        "SemiMajorAxis": fields.pop("sma", 1.0e9),
        "Parents": fields.pop("parents", [{"Star": 0}]),
        "BodyCount": 12,
    }
    event.update(fields)
    return event


def _bodies() -> list[dict]:
    return [
        _scan(
            0,
            DEMO_SYSTEM + " A",
            StarType="K",
            Subclass=2,
            StellarMass=0.78,
            Radius=5.7e8,
            SurfaceTemperature=4790.0,
            distance=0.0,
            sma=0.0,
            parents=[],
        ),
        _scan(
            1,
            DEMO_SYSTEM + " 1",
            PlanetClass="Icy body",
            Radius=6.1e6,
            MassEM=0.9,
            SurfaceGravity=5.6,
            SurfaceTemperature=112.0,
            SurfacePressure=520.0,
            Atmosphere="thin neon atmosphere",
            AtmosphereComposition={"Neon": 100.0},
            Volcanism="None",
            Materials={"Iron": 19.4, "Sulphur": 15.2, "Carbon": 21.8, "Technetium": 0.62, "Phosphorus": 4.1},
            Landable=True,
            distance=1240.0,
            sma=1.3e10,
        ),
        _scan(
            2,
            DEMO_SYSTEM + " 2 a",
            PlanetClass="Rocky body",
            Radius=3.4e6,
            MassEM=0.21,
            SurfaceGravity=4.9,
            SurfaceTemperature=253.0,
            SurfacePressure=980.0,
            Atmosphere="thin carbon dioxide atmosphere",
            AtmosphereComposition={"CarbonDioxide": 100.0},
            Volcanism="minor water magma",
            Materials={"Iron": 14.1, "Nickel": 9.2, "Sulphur": 17.4, "Carbon": 16.2},
            Landable=True,
            distance=2410.0,
            sma=3.1e10,
            parents=[{"Star": 0}, {"Planet": 1}],
        ),
        _scan(
            3,
            DEMO_SYSTEM + " 3 c",
            PlanetClass="High metal content body",
            Radius=5.2e6,
            MassEM=0.71,
            SurfaceGravity=8.1,
            SurfaceTemperature=291.0,
            SurfacePressure=4100.0,
            Atmosphere="thin water atmosphere",
            AtmosphereComposition={"Water": 100.0},
            Volcanism="None",
            Materials={"Iron": 24.1, "Nickel": 16.4, "Sulphur": 12.7, "Carbon": 10.2, "Yttrium": 1.1},
            Landable=True,
            distance=3820.0,
            sma=6.4e10,
            parents=[{"Star": 0}, {"Planet": 1}],
            TerraformState="Terraformable",
        ),
    ]


def _navroute(progress: int) -> dict:
    route = [
        {"StarSystem": DEMO_SYSTEM, "SystemAddress": DEMO_ADDRESS, "StarPos": DEMO_POS, "StarClass": "K"},
        {"StarSystem": "Synuefe EN-H d11-97", "SystemAddress": 3932277477891, "StarPos": [-420.1, -128.2, -820.4], "StarClass": "K"},
        {"StarSystem": "Synuefe GG-O c22-4", "SystemAddress": 3932277477892, "StarPos": [-401.5, -110.0, -789.0], "StarClass": "M"},
        {"StarSystem": "HIP 36601", "SystemAddress": 8006664, "StarPos": [-380.2, -96.4, -745.9], "StarClass": "A"},
        {"StarSystem": "Outotz LS-K d8-3", "SystemAddress": 3344784, "StarPos": [-350.0, -60.1, -700.6], "StarClass": "K"},
    ]
    return {
        "timestamp": "2026-01-01T00:00:00Z",
        "event": "NavRoute",
        "Route": route[progress:],
    }


def _status(**fields) -> dict:
    base = {
        "timestamp": "2026-01-01T00:00:00Z",
        "Flags": 0,
        "Fuel": {"FuelMain": 30.2, "FuelReserve": 0.63},
        "Cargo": 4.0,
        "GuiFocus": 0,
        "BodyName": DEMO_SYSTEM + " 1",
        "BodyID": 1,
        "PlanetRadius": 6_100_000.0,
        "Latitude": 12.34,
        "Longitude": -45.67,
        "Heading": 180,
        "Altitude": 0.0,
        "Temperature": 112.0,
        "Gravity": 5.6,
    }
    base.update(fields)
    return base


def script() -> list[Step]:
    steps: list[Step] = []
    steps.append(Step(0.2, "event", {"event": "Fileheader", "part": 1, "language": "English/UK", "gameversion": "4.9.0.100"}))
    steps.append(
        Step(
            0.3,
            "event",
            {
                "event": "LoadGame",
                "Commander": "JAMESON",
                "FID": "F123456",
                "Ship": "Anaconda",
                "ShipName": "Пузырь",
                "GameMode": "Open",
                "Credits": 1_234_567_890,
                "Fuel": 32.0,
            },
        )
    )
    steps.append(
        Step(
            0.3,
            "event",
            {
                "event": "Location",
                "StarSystem": DEMO_SYSTEM,
                "SystemAddress": DEMO_ADDRESS,
                "StarPos": DEMO_POS,
                "Body": DEMO_SYSTEM + " A",
                "BodyID": 0,
                "BodyType": "Star",
                "Docked": False,
                "Population": 0,
            },
        )
    )
    steps.append(Step(0.4, "navroute", _navroute(0)))
    steps.append(Step(0.2, "event", _navroute(0)))
    steps.append(Step(0.3, "status", _status(Flags=1 << 4, Fuel={"FuelMain": 31.4, "FuelReserve": 0.63}, BodyName=None, BodyID=None, Latitude=None, Longitude=None)))
    steps.append(
        Step(
            0.4,
            "event",
            {
                "event": "FSDTarget",
                "Name": "Synuefe EN-H d11-97",
                "SystemAddress": 3932277477891,
                "StarClass": "K",
                "RemainingJumpsInRoute": 4,
            },
        )
    )

    for body in _bodies():
        steps.append(Step(0.5, "event", body))

    steps.append(
        Step(
            0.6,
            "event",
            {
                "event": "FSSBodySignals",
                "BodyName": DEMO_SYSTEM + " 1",
                "BodyID": 1,
                "SystemAddress": DEMO_ADDRESS,
                "Signals": [{"Type": "Biological", "Count": 3}],
            },
        )
    )
    steps.append(
        Step(
            0.6,
            "event",
            {
                "event": "SAASignalsFound",
                "BodyName": DEMO_SYSTEM + " 1",
                "BodyID": 1,
                "SystemAddress": DEMO_ADDRESS,
                "Signals": [{"Type": "Biological", "Count": 3}, {"Type": "Geological", "Count": 2}],
                "Genuses": [
                    {"Genus": "$Codex_Ent_Bacterial_Genus_Name;", "Genus_Localised": "Bacterium"},
                    {"Genus": "$Codex_Ent_Fungoids_Genus_Name;", "Genus_Localised": "Fungoida"},
                    {"Genus": "$Codex_Ent_Osseus_Genus_Name;", "Genus_Localised": "Osseus"},
                ],
            },
        )
    )
    steps.append(
        Step(
            0.5,
            "event",
            {
                "event": "FSSBodySignals",
                "BodyName": DEMO_SYSTEM + " 2 a",
                "BodyID": 2,
                "SystemAddress": DEMO_ADDRESS,
                "Signals": [{"Type": "Biological", "Count": 1}],
            },
        )
    )
    steps.append(
        Step(
            0.5,
            "event",
            {
                "event": "FSSBodySignals",
                "BodyName": "Synuefe GG-O c22-4 1",
                "BodyID": 1,
                "SystemAddress": 3932277477892,
                "Signals": [{"Type": "Biological", "Count": 2}],
            },
        )
    )
    steps.append(
        Step(
            0.5,
            "event",
            {
                "event": "FSDJump",
                "StarSystem": "Synuefe EN-H d11-97",
                "SystemAddress": 3932277477891,
                "StarPos": [-420.1, -128.2, -820.4],
                "JumpDist": 24.8,
                "FuelUsed": 3.1,
                "FuelLevel": 29.2,
            },
        )
    )
    steps.append(Step(0.3, "navroute", _navroute(1)))
    steps.append(
        Step(
            0.4,
            "event",
            {
                "event": "FSDJump",
                "StarSystem": "Synuefe GG-O c22-4",
                "SystemAddress": 3932277477892,
                "StarPos": [-401.5, -110.0, -789.0],
                "JumpDist": 27.3,
                "FuelUsed": 3.4,
                "FuelLevel": 25.8,
            },
        )
    )
    # --- целевая система: сканы тел, био-сигналы, посадка
    steps.append(
        Step(
            0.4,
            "event",
            _scan(
                0,
                "Synuefe GG-O c22-4 A",
                StarType="K",
                Radius=5.2e8,
                SurfaceTemperature=4510.0,
                distance=0.0,
                sma=0.0,
                parents=[],
            ),
        )
    )
    steps.append(
        Step(
            0.5,
            "event",
            _scan(
                1,
                "Synuefe GG-O c22-4 1",
                PlanetClass="Icy body",
                Radius=6.1e6,
                MassEM=0.94,
                SurfaceGravity=5.6,
                SurfaceTemperature=118.0,
                SurfacePressure=540.0,
                Atmosphere="thin neon atmosphere",
                AtmosphereComposition={"Neon": 100.0},
                Volcanism="None",
                Materials={
                    "Iron": 19.1,
                    "Sulphur": 15.6,
                    "Carbon": 21.2,
                    "Technetium": 0.71,
                    "Phosphorus": 4.4,
                },
                Landable=True,
                distance=1180.0,
                sma=1.2e10,
                WasDiscovered=False,
                WasMapped=False,
                WasFootfalled=False,
            ),
        )
    )
    steps.append(
        Step(
            0.6,
            "event",
            {
                "event": "ApproachBody",
                "StarSystem": "Synuefe GG-O c22-4",
                "SystemAddress": 3932277477892,
                "Body": "Synuefe GG-O c22-4 1",
                "BodyID": 1,
            },
        )
    )
    steps.append(
        Step(0.4, "event", {"event": "SupercruiseExit", "Body": "Synuefe GG-O c22-4 1", "BodyID": 1, "BodyType": "Planet"})
    )
    steps.append(
        Step(
            0.4,
            "event",
            {
                "event": "FSSBodySignals",
                "BodyName": "Synuefe GG-O c22-4 1",
                "BodyID": 1,
                "SystemAddress": 3932277477892,
                "Signals": [{"Type": "Biological", "Count": 2}],
            },
        )
    )
    steps.append(
        Step(
            0.5,
            "event",
            {
                "event": "SAASignalsFound",
                "BodyName": "Synuefe GG-O c22-4 1",
                "BodyID": 1,
                "SystemAddress": 3932277477892,
                "Signals": [{"Type": "Biological", "Count": 2}, {"Type": "Geological", "Count": 1}],
                "Genuses": [
                    {"Genus": "$Codex_Ent_Bacterial_Genus_Name;", "Genus_Localised": "Bacterium"},
                    {"Genus": "$Codex_Ent_Fungoids_Genus_Name;", "Genus_Localised": "Fungoida"},
                ],
            },
        )
    )
    steps.append(
        Step(
            0.5,
            "event",
            {
                "event": "SAAScanComplete",
                "BodyName": "Synuefe GG-O c22-4 1",
                "BodyID": 1,
                "SystemAddress": 3932277477892,
                "ProbesUsed": 6,
                "EfficiencyTarget": 6,
            },
        )
    )
    steps.append(
        Step(
            0.5,
            "event",
            {
                "event": "Touchdown",
                "Latitude": 12.34,
                "Longitude": -45.67,
                "OnPlanet": True,
                "Body": "Synuefe GG-O c22-4 1",
                "BodyID": 1,
            },
        )
    )
    steps.append(Step(0.3, "status", _status(Flags=(1 << 1), BodyName="Synuefe GG-O c22-4 1", BodyID=1, Latitude=12.34, Longitude=-45.67, PlanetRadius=6_100_000.0)))
    steps.append(
        Step(
            0.6,
            "event",
            {
                "event": "ScanOrganic",
                "ScanType": "Log",
                "Genus": "$Codex_Ent_Bacterial_Genus_Name;",
                "Genus_Localised": "Bacterium",
                "Species": "$Codex_Ent_Bacterial_07_Name;",
                "Species_Localised": "Bacterium Cerbrus",
                "Variant": "$Codex_Ent_Bacterial_07_K_Name;",
                "Variant_Localised": "Bacterium Cerbrus - Lime",
                "WasLogged": False,
                "Body": "Synuefe GG-O c22-4 1",
                "SystemAddress": 3932277477892,
            },
        )
    )
    steps.append(Step(0.3, "status", _status(Flags=(1 << 1) | (1 << 21), BodyName="Synuefe GG-O c22-4 1", BodyID=1, Latitude=12.36, Longitude=-45.70, PlanetRadius=6_100_000.0)))
    steps.append(
        Step(
            0.8,
            "event",
            {
                "event": "ScanOrganic",
                "ScanType": "Sample",
                "Genus": "$Codex_Ent_Bacterial_Genus_Name;",
                "Genus_Localised": "Bacterium",
                "Species": "$Codex_Ent_Bacterial_07_Name;",
                "Species_Localised": "Bacterium Cerbrus",
                "Variant": "$Codex_Ent_Bacterial_07_K_Name;",
                "Variant_Localised": "Bacterium Cerbrus - Lime",
                "Body": "Synuefe GG-O c22-4 1",
                "SystemAddress": 3932277477892,
            },
        )
    )
    steps.append(
        Step(
            0.6,
            "event",
            {
                "event": "ScanOrganic",
                "ScanType": "Analyse",
                "Genus": "$Codex_Ent_Fungoids_Genus_Name;",
                "Genus_Localised": "Fungoida",
                "Species": "$Codex_Ent_Fungoids_01_Name;",
                "Species_Localised": "Fungoida Setisis",
                "Variant": "$Codex_Ent_Fungoids_01_K_Name;",
                "Variant_Localised": "Fungoida Setisis - Gold",
                "WasLogged": True,
                "Body": "Synuefe GG-O c22-4 1",
                "SystemAddress": 3932277477892,
            },
        )
    )
    # продажа данных: реальные суммы с бонусами (First Logged ×5)
    steps.append(
        Step(
            0.6,
            "event",
            {
                "event": "SellOrganicData",
                "BioData": [
                    {
                        "Name": "$Codex_Ent_Fungoids_01_K_Name;",
                        "Name_Localised": "Fungoida Setisis - Gold",
                        "Value": 1671800,
                        "Bonus": 0,
                    },
                    {
                        "Name": "$Codex_Ent_Bacterial_07_K_Name;",
                        "Name_Localised": "Bacterium Cerbrus - Lime",
                        "Value": 1690000,
                        "Bonus": 6760000,
                    },
                ],
            },
        )
    )
    steps.append(
        Step(
            0.4,
            "event",
            {
                "event": "SellExplorationData",
                "Systems": ["Synuefe EN-H d11-97"],
                "Discovered": ["Synuefe GG-O c22-4 1"],
                "BaseValue": 120000,
                "Bonuses": 312000,
                "TotalEarnings": 432000,
            },
        )
    )
    return steps


def walking_steps(start_lat: float = 12.36, start_lon: float = -45.70, count: int = 40) -> list[Step]:
    """Игрок уезжает от точки первой пробы — видно colony-range индикатор."""
    steps = []
    for i in range(count):
        lat = start_lat + 0.0012 * i
        lon = start_lon - 0.0009 * i
        steps.append(
            Step(
                0.7,
                "status",
                _status(
                    Flags=(1 << 1) | (1 << 21),
                    BodyName="Synuefe GG-O c22-4 1",
                    BodyID=1,
                    Latitude=lat,
                    Longitude=lon,
                    PlanetRadius=6_100_000.0,
                ),
            )
        )
    return steps


def write_events(folder: Path, steps: list[Step], speed: float = 1.0, stop: threading.Event | None = None) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%dT%H%M%S", time.localtime())
    journal = folder / f"Journal.{stamp}.01.log"
    status_path = folder / "Status.json"
    navroute_path = folder / "NavRoute.json"
    with journal.open("w", encoding="utf-8") as handle:
        for step in steps:
            if stop is not None and stop.is_set():
                break
            time.sleep(max(0.0, step.delay / max(0.1, speed)))
            if step.kind == "event":
                handle.write(json.dumps(step.payload, ensure_ascii=False) + "\n")
                handle.flush()
            elif step.kind == "status":
                status_path.write_text(json.dumps(step.payload, ensure_ascii=False), encoding="utf-8")
            elif step.kind == "navroute":
                navroute_path.write_text(json.dumps(step.payload, ensure_ascii=False), encoding="utf-8")


def write_all(folder: Path) -> None:
    """Мгновенно записать весь демо-журнал (для тестов и режима dump)."""
    write_events(folder, script() + walking_steps(count=6), speed=1000.0)


class DemoPlayer(threading.Thread):
    def __init__(self, folder: Path, speed: float = 1.0) -> None:
        super().__init__(name="edhud-demo", daemon=True)
        self.folder = Path(folder)
        self.speed = speed
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        steps = script() + walking_steps()
        write_events(self.folder, steps, self.speed, self._stop)


def demo_folder() -> Path:
    from . import config

    return config.app_dir() / "demo"
