# Created by nc.ai 1.2.11 on Papasha 2026-11-14 19:30:36
"""Canonn POI: чужие био-точки на поверхности (аналог «prior scans» из SRVSurvey).

SRVSurvey показывает не сами образцы (игра их координат не публикует), а
**точки, которые нанесли на карту другие командиры** — публичная база Canonn
(Codex POI). Запрос:

    GET https://us-central1-canonn-api-236217.cloudfunctions.net/query/getSystemPoi
        ?system=<имя>&odyssey=Y&cmdr=<ник>

Ответ содержит `codex` — записи вида
    {"body": "C 7", "english_name": "Stratum Tectonicas - Lime",
     "entryid": 2330304, "hud_category": "Biology",
     "latitude": "-31.0063", "longitude": "44.2323"}

Берём только `hud_category == "Biology"` с координатами: у геологии та же
структура, а `ScanOrganic` приходит без lat/lon (агрегат по телу).

Данные есть только там, где кто-то отметился: для случайной системы ответ
пустой — значит и показывать нечего.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import config

API = "https://us-central1-canonn-api-236217.cloudfunctions.net/query/getSystemPoi"
CACHE_TTL = 7 * 24 * 3600  # неделя: точки на планете не переезжают
MAX_POINTS = 200


def _cache_path(system_name: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", system_name)[:80]
    return config.app_dir() / "canonn" / f"{safe}.json"


def parse_bio_points(payload: dict | None) -> list[tuple[str, float, float, str]]:
    """codex-записи Canonn → [(короткое имя тела, lat, lon, подпись)]."""
    if not isinstance(payload, dict):
        return []
    out: list[tuple[str, float, float, str]] = []
    for entry in payload.get("codex") or []:
        if not isinstance(entry, dict):
            continue
        if (entry.get("hud_category") or "") != "Biology":
            continue
        body = (entry.get("body") or "").strip()
        name = (entry.get("english_name") or "").strip()
        lat, lon = entry.get("latitude"), entry.get("longitude")
        if not body or lat in (None, "") or lon in (None, ""):
            continue
        try:
            out.append((body, float(lat), float(lon), name))
        except (TypeError, ValueError):
            continue
        if len(out) >= MAX_POINTS:
            break
    return out


def fetch_system_poi(system_name: str, cmdr: str = "EDHUD", timeout: float = 15.0) -> dict | None:
    """Запрос к Canonn с дисковым кэшем (неделя). None — сеть недоступна."""
    if not system_name:
        return None
    path = _cache_path(system_name)
    try:
        stat = path.stat()
        if time.time() - stat.st_mtime < CACHE_TTL:
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    url = (
        f"{API}?system={urllib.parse.quote(system_name)}&odyssey=Y"
        f"&cmdr={urllib.parse.quote(cmdr or 'EDHUD')}"
    )
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return payload
