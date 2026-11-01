"""Справочник кодекса: имена родов/видов и «ценность» в Vista Genomics.

GENUS_NAMES / GENUS_RANGE повторяют таблицы SrvSurvey
(BioScanning.genusNames и BioGenus.getRange): ключ — имя из журнала
(`$Codex_Ent_Bacterial_Genus_Name;`), значение — английское имя и минимальная
дистанция между пробами (clonal colony range), метры.

data/codex_ref.json — выжимка из SrvSurvey/docs/codexRef.json (Canonn):
codex-имя -> английское имя + базовая награда.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache

from . import config

GENUS_NAMES: dict[str, str] = {
    "$Codex_Ent_Aleoids_Genus_Name;": "Aleoida",
    "$Codex_Ent_Bacterial_Genus_Name;": "Bacterium",
    "$Codex_Ent_Cactoid_Genus_Name;": "Cactoida",
    "$Codex_Ent_Clypeus_Genus_Name;": "Clypeus",
    "$Codex_Ent_Conchas_Genus_Name;": "Concha",
    "$Codex_Ent_Electricae_Genus_Name;": "Electricae",
    "$Codex_Ent_Fonticulus_Genus_Name;": "Fonticulua",
    "$Codex_Ent_Shrubs_Genus_Name;": "Frutexa",
    "$Codex_Ent_Fumerolas_Genus_Name;": "Fumerola",
    "$Codex_Ent_Fungoids_Genus_Name;": "Fungoida",
    "$Codex_Ent_Osseus_Genus_Name;": "Osseus",
    "$Codex_Ent_Recepta_Genus_Name;": "Recepta",
    "$Codex_Ent_Stratum_Genus_Name;": "Stratum",
    "$Codex_Ent_Tubus_Genus_Name;": "Tubus",
    "$Codex_Ent_Tussocks_Genus_Name;": "Tussock",
    # Horizons
    "$Codex_Ent_Vents_Name;": "Amphora Plant",
    "$Codex_Ent_Sphere_Name;": "Anemone",
    "$Codex_Ent_Cone_Name;": "Bark Mounds",
    "$Codex_Ent_Brancae_Name;": "Brain Tree",
    "$Codex_Ent_Ground_Struct_Ice_Name;": "Crystalline Shards",
    "$Codex_Ent_Tube_Name;": "Sinuous Tubers",
    # новое
    "$Codex_Ent_Ingensradices_Unicus_Name;": "Radicoida",
    "$Codex_Ent_Ingensradices_Genus_Name;": "Radicoida",
    # таргоиды
    "$Codex_Ent_Barnacles_Name;": "Mega Barnacles",
    "$Codex_Ent_Thargoid_Coral_Name;": "Coral Roots",
    "$Codex_Ent_Thargoid_Tower_Name;": "Spire Towers",
}

GENUS_RANGE: dict[str, int] = {
    "$Codex_Ent_Fumerolas_Genus_Name;": 100,
    "$Codex_Ent_Aleoids_Genus_Name;": 150,
    "$Codex_Ent_Clypeus_Genus_Name;": 150,
    "$Codex_Ent_Conchas_Genus_Name;": 150,
    "$Codex_Ent_Shrubs_Genus_Name;": 150,
    "$Codex_Ent_Recepta_Genus_Name;": 150,
    "$Codex_Ent_Tussocks_Genus_Name;": 200,
    "$Codex_Ent_Cactoid_Genus_Name;": 300,
    "$Codex_Ent_Fungoids_Genus_Name;": 300,
    "$Codex_Ent_Bacterial_Genus_Name;": 500,
    "$Codex_Ent_Fonticulus_Genus_Name;": 500,
    "$Codex_Ent_Stratum_Genus_Name;": 500,
    "$Codex_Ent_Osseus_Genus_Name;": 800,
    "$Codex_Ent_Tubus_Genus_Name;": 800,
    "$Codex_Ent_Electricae_Genus_Name;": 1000,
    # Horizons
    "$Codex_Ent_Vents_Name;": 100,
    "$Codex_Ent_Sphere_Name;": 100,
    "$Codex_Ent_Cone_Name;": 100,
    "$Codex_Ent_Brancae_Name;": 100,
    "$Codex_Ent_Ground_Struct_Ice_Name;": 100,
    "$Codex_Ent_Tube_Name;": 100,
    # таргоиды
    "$Codex_Ent_Barnacles_Name;": 85,
    "$Codex_Ent_Thargoid_Coral_Name;": 85,
    "$Codex_Ent_Thargoid_Tower_Name;": 85,
    "$Codex_Ent_Ingensradices_Genus_Name;": 15,
    "$Codex_Ent_Ingensradices_Unicus_Name;": 15,
}

DEFAULT_RANGE = 50

_CODEX_RE = re.compile(r"^\$(?:Codex_Ent_)?(.+?)(?:_Name;)?$")
_SPECIES_RE = re.compile(r"^\$Codex_Ent_(?P<base>.+?)_(?P<num>\d{1,2})_Name;$")
_VARIANT_RE = re.compile(r"^\$Codex_Ent_(?P<base>.+?)_(?P<num>\d{1,2})_(?P<variant>[A-Za-z]{1,4})_Name;$")


@lru_cache(maxsize=1)
def _ref() -> dict:
    try:
        return json.loads((config.data_dir() / "codex_ref.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


@lru_cache(maxsize=1)
def _species_index() -> dict[tuple[str, int], str]:
    """(база имени, номер вида) -> английское имя вида.

    В справочнике есть только записи вариантов (`$Codex_Ent_Bacterial_07_K_Name;`
    -> "Bacterium Cerbrus - Lime"), из них и восстанавливаем имя вида.
    """
    index: dict[tuple[str, int], str] = {}
    for name, item in _ref().items():
        match = _VARIANT_RE.match(name)
        english = item.get("en") or ""
        if not match or not english:
            continue
        species = english.split(" - ")[0].strip()
        key = (match.group("base").lower(), int(match.group("num")))
        index.setdefault(key, species)
    return index


@lru_cache(maxsize=1)
def _by_english() -> dict[str, int]:
    out: dict[str, int] = {}
    for item in _ref().values():
        name = item.get("en")
        if not name:
            continue
        reward = int(item.get("reward") or 0)
        if reward > out.get(name, 0):
            out[name] = reward
    return out


def english(codex_name: str | None) -> str | None:
    if not codex_name:
        return None
    if codex_name in GENUS_NAMES:
        return GENUS_NAMES[codex_name]
    item = _ref().get(codex_name)
    if item and item.get("en"):
        return item["en"]
    match = _SPECIES_RE.match(codex_name)
    if match:
        species = _species_index().get((match.group("base").lower(), int(match.group("num"))))
        if species:
            return species
    return None


def display_name(codex_name: str | None) -> str:
    """Человекочитаемое имя: из справочника, иначе из codex-строки."""
    if not codex_name:
        return ""
    name = english(codex_name)
    if name:
        return name
    m = _CODEX_RE.match(codex_name)
    if m:
        return m.group(1).replace("_", " ")
    return codex_name


def sample_range(codex_name: str | None) -> int:
    if not codex_name:
        return DEFAULT_RANGE
    return GENUS_RANGE.get(codex_name, DEFAULT_RANGE)


def genus_key_from_name(name: str | None) -> str | None:
    """Род по строке кодекса: и у «…_Genus_Name», и у вида «Fonticulus_01_M»."""
    if not name:
        return None
    best: str | None = None
    best_len = 0
    for key in GENUS_RANGE:
        stem = key.split("_Ent_")[-1].replace("_Genus_Name;", "").replace("_Name;", "")
        if stem and stem in name and len(stem) > best_len:
            best = key
            best_len = len(stem)
    return best


def reward_for(genus_en: str | None, species_en: str | None, variant_en: str | None) -> int:
    """Базовая награда Vista Genomics за анализ (без множителей)."""
    if not genus_en or not species_en:
        return 0
    index = _by_english()
    # локализованное имя вида уже содержит род: "Fungoida Setisis"
    if species_en.lower().startswith(genus_en.lower()):
        base = species_en
    else:
        base = f"{genus_en} {species_en}"
    if variant_en:
        short = variant_en.split(" - ")[-1]
        value = index.get(f"{base} - {short}")
        if value:
            return value
    candidates = [r for name, r in index.items() if name == base or name.startswith(base + " -")]
    return min(candidates) if candidates else 0
