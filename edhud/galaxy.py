"""Галактические ориентиры: туманности и Guardian bubble.

Туманности нужны критериям биологии вида `nebulae [ ~ 160]` (расстояние до
ближайшей туманности). Каталог тянется один раз с edastro.com и кэшируется —
так же делает SrvSurvey (net/CodexRef.cs).

Guardian bubble — две больших сферы по 750 ly (Gamma Velorum, HEN 2-333) и шесть
малых по 100 ly (данные из SrvSurvey CodexRef.smallGuardianBubbles).
"""
from __future__ import annotations

import math
import time
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path

from . import config

NEBULA_URL = "https://edastro.com/mapcharts/files/nebulae-coordinates.csv"
USER_AGENT = "EDHUD/1.1 (+local overlay, python-urllib)"
MAX_CACHE_AGE = 60 * 60 * 24 * 30  # месяц

GUARDIAN_BUBBLES: tuple[tuple[float, float, float, float], ...] = (
    (1099.21875, -146.6875, -133.59375, 750.0),  # Synuefe / Gamma Velorum
    (-840.65625, -561.15625, 13361.8125, 750.0),  # HEN 2-333
    (-9298.6875, -419.40625, 7911.15625, 100.0),  # Prai Hypoo OK-I b0
    (-5479.28125, -574.84375, 10468.96875, 100.0),  # Prua Phoe US-B d58
    (1228.1875, -694.5625, 12341.65625, 100.0),  # Blaa Hypai EK-C c14-1
    (4961.1875, 158.09375, 20642.65625, 100.0),  # Eorl Auwsy SY-Z d13-3643
    (14602.75, -237.90625, 3561.875, 100.0),  # NGC 3199 Sector JH-V c2-0
    (8649.125, -154.71875, 2686.03125, 100.0),  # Eta Carina Sector EL-Y d1
)


def within_guardian_bubble(pos: tuple[float, float, float] | None) -> bool:
    if not pos:
        return False
    for x, y, z, radius in GUARDIAN_BUBBLES:
        if math.dist(pos, (x, y, z)) < radius:
            return True
    return False


def cache_dir() -> Path:
    return config.app_dir() / "cache"


def nebulae_cache() -> Path:
    return cache_dir() / "nebulae.csv"


def download_nebulae(timeout: float = 20.0) -> bool:
    """Скачивает каталог туманностей в кэш. False при любой проблеме с сетью."""
    path = nebulae_cache()
    try:
        if path.exists() and time.time() - path.stat().st_mtime < MAX_CACHE_AGE:
            return True
        path.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(NEBULA_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
        if len(payload) < 1000:
            return False
        path.write_bytes(payload)
        _positions.cache_clear()
        return True
    except (urllib.error.URLError, OSError, TimeoutError):
        return path.exists()


@lru_cache(maxsize=1)
def _positions() -> tuple[tuple[float, float, float], ...]:
    path = nebulae_cache()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ()
    points: list[tuple[float, float, float]] = []
    for line in text.splitlines()[1:]:
        parts = line.split(",")
        if len(parts) < 5:
            continue
        try:
            points.append((float(parts[2]), float(parts[3]), float(parts[4])))
        except ValueError:
            continue
    return tuple(points)


def nearest_nebula(pos: tuple[float, float, float] | None, max_distance: float | None = None) -> float | None:
    """Расстояние до ближайшей туманности (ly) или None, если каталога нет."""
    if not pos:
        return None
    points = _positions()
    if not points:
        return None
    best = min(math.dist(pos, p) for p in points)
    if max_distance is not None and best > max_distance:
        return best
    return best
