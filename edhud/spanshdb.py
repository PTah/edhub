# Created by nc.ai 1.2.15 on Papasha 2026-11-15 16:58:12
"""База хотспотов из SQL-дампа Spansh: скачали один раз — ищем офлайн.

Дамп Spansh (`galaxy_1day` / `galaxy_populated`) — это gzip с массивом систем,
у каждой `id64`, `name`, `coords` и `bodies`, а у колец внутри `rings[].signals.signals`
лежат минералы с количеством хотспотов. Из 1–4 ГБ нам нужны только кольца с
хотспотами: получается компактная SQLite (`spansh.db`), по которой поиск
«александрит в 40 ly» идёт без сети.

Подкачка включается галочкой в настройках и по умолчанию выключена: качать
гигабайты без спроса нельзя.
"""
from __future__ import annotations

import gzip
import io
import json
import sqlite3
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Iterator

from . import config, mining

DUMP_URL = "https://downloads.spansh.co.uk/{name}.json.gz"
DUMPS = {
    "galaxy_1day": "суточная дельта (~1.1 ГБ)",
    "galaxy_7days": "недельная дельта (~2.7 ГБ)",
    "galaxy_1month": "месячная дельта (~5.4 ГБ)",
    "galaxy_populated": "полная база (~4.5 ГБ)",
}
DEFAULT_DUMP = "galaxy_1day"
USER_AGENT = "EDHUD/1.7.0 (Elite Dangerous HUD)"
SCHEMA = """
CREATE TABLE IF NOT EXISTS ring (
    id INTEGER PRIMARY KEY,          -- id64 кольца из дампа
    system TEXT NOT NULL,
    address INTEGER,
    x REAL, y REAL, z REAL,
    body TEXT NOT NULL,
    ring TEXT NOT NULL,
    kind TEXT,                        -- Icy / Metallic / Metal Rich / Rocky
    density REAL,
    reserve TEXT,
    hotspots TEXT NOT NULL,           -- JSON {"Painite": 2, ...}
    updated_at TEXT,
    imported REAL
);
CREATE INDEX IF NOT EXISTS ring_system ON ring(system);
CREATE INDEX IF NOT EXISTS ring_pos ON ring(x, y, z);
CREATE TABLE IF NOT EXISTS ring_mineral (
    ring_id INTEGER NOT NULL,
    mineral TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ring_mineral_name ON ring_mineral(mineral, ring_id);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


@dataclass
class RingHit:
    """Кольцо из базы Spansh в виде, понятном вкладке «Добыча»."""

    system: str
    body: str
    kind: str | None
    hotspots: dict[str, int]
    density: float | None = None
    reserve: str | None = None
    address: int | None = None
    star_pos: tuple[float, float, float] | None = None
    distance_ly: float | None = None

    def minerals_label(self) -> str:
        return mining.format_hotspots(self.hotspots)


def iter_objects(stream: Iterable[str], chunk_size: int = 1 << 20) -> Iterator[dict]:
    """Потоково разобрать JSON-массив (или JSONL) из `stream` без зависимостей.

    Дамп Spansh — один большой массив систем; держать его в памяти нельзя,
    поэтому читаем кусками и отдаём по объекту.
    """
    decoder = json.JSONDecoder()
    buffer = ""
    pos = 0
    while True:
        data = stream.read(chunk_size) if hasattr(stream, "read") else ""
        if data:
            buffer = buffer[pos:] + data
            pos = 0
        while pos < len(buffer) and buffer[pos] in " \t\r\n,[":
            pos += 1
        if pos >= len(buffer):
            if not data:
                return
            continue
        try:
            obj, end = decoder.raw_decode(buffer, pos)
        except ValueError:
            if not data:
                return
            continue
        pos = end
        yield obj
        if not data and pos >= len(buffer):
            return


class SpanshIndex:
    """SQLite с кольцами и их хотспотами + импорт из дампа Spansh."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else config.app_dir() / "spansh.db"
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------- база
    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.path))
            self._conn.executescript(SCHEMA)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def exists(self) -> bool:
        return self.path.exists() and self.path.stat().st_size > 0

    def counts(self) -> dict:
        """Сколько колец и по каким дампам — для настроек/статуса."""
        info = {"rings": 0, "systems": 0, "minerals": 0, "built_at": None, "dump": None, "size_mb": 0.0}
        if not self.exists():
            return info
        info["size_mb"] = round(self.path.stat().st_size / 1024 / 1024, 1)
        try:
            row = self.conn.execute("SELECT COUNT(*), COUNT(DISTINCT system) FROM ring").fetchone()
            info["rings"], info["systems"] = int(row[0] or 0), int(row[1] or 0)
            row = self.conn.execute("SELECT COUNT(DISTINCT mineral) FROM ring_mineral").fetchone()
            info["minerals"] = int(row[0] or 0)
            meta = dict(self.conn.execute("SELECT key, value FROM meta").fetchall())
            info["built_at"] = meta.get("built_at")
            info["dump"] = meta.get("dump")
        except sqlite3.DatabaseError:
            pass
        return info

    def clear(self) -> None:
        """Выбросить базу целиком (например, перед полной перекачкой)."""
        self.close()
        try:
            self.path.unlink()
        except OSError:
            pass

    # ---------------------------------------------------------- импорт
    def update(
        self,
        dump: str = DEFAULT_DUMP,
        *,
        source: str | Path | None = None,
        progress: Callable[[dict], None] | None = None,
        cancel: Callable[[], bool] | None = None,
        full_rebuild: bool = False,
    ) -> dict:
        """Скачать дамп и разложить кольца с хотспотами в SQLite.

        `source` — локальный файл (для тестов); по умолчанию тянем с Spansh.
        Возвращает статистику импорта.
        """
        if full_rebuild:
            self.clear()
        started = time.time()
        systems = 0
        rings = 0
        conn = self.conn
        stream = self._open_source(source, dump)
        try:
            for record in iter_objects(stream):
                if cancel is not None and cancel():
                    break
                systems += 1
                rings += self._import_record(conn, record)
                if systems % 200 == 0:
                    conn.commit()
                if progress is not None and systems % 200 == 0:
                    progress({"systems": systems, "rings": rings, "seconds": time.time() - started})
            conn.commit()
            self._set_meta(
                built_at=time.strftime("%Y-%m-%d %H:%M"),
                dump=str(source) if source else dump,
                seconds=f"{time.time() - started:.0f}",
            )
        finally:
            try:
                stream.close()  # type: ignore[union-attr]
            except (AttributeError, OSError, ValueError):
                pass
        return {"systems": systems, "rings": rings, "seconds": round(time.time() - started, 1)}

    @staticmethod
    def _open_source(source: str | Path | None, dump: str):
        """Поток UTF-8 поверх gzip: либо локальный файл, либо дамп Spansh."""
        import codecs

        if source:
            raw = gzip.open(str(source), "rb")
        else:  # pragma: no cover - сеть в тестах не дёргаем
            req = urllib.request.Request(DUMP_URL.format(name=dump), headers={"User-Agent": USER_AGENT})
            resp = urllib.request.urlopen(req, timeout=120)
            raw = gzip.GzipFile(fileobj=resp)
        return codecs.getreader("utf-8")(raw)

    def _import_record(self, conn: sqlite3.Connection, record: dict) -> int:
        """Разложить одну систему. Возвращает число импортированных колец."""
        system = str(record.get("name") or "").strip()
        if not system:
            return 0
        coords = record.get("coords") or {}
        try:
            x = float(coords.get("x") or 0.0)
            y = float(coords.get("y") or 0.0)
            z = float(coords.get("z") or 0.0)
        except (TypeError, ValueError):
            x = y = z = 0.0
        address = _as_int(record.get("id64"))
        imported = 0
        for body in record.get("bodies") or []:
            if not isinstance(body, dict):
                continue
            rings = body.get("rings") or []
            if not rings:
                continue
            body_name = str(body.get("name") or "")
            reserve = _clean_reserve(body.get("reserveLevel"))
            for ring in rings:
                if not isinstance(ring, dict):
                    continue
                hotspots = _ring_hotspots(ring)
                if not hotspots:
                    continue
                kind = _clean_kind(ring.get("type"))
                density = mining.ring_density(ring.get("mass"), ring.get("innerRadius"), ring.get("outerRadius"))
                ring_id = _as_int(ring.get("id64")) or _fallback_id(system, body_name, ring.get("name"))
                updated = ""
                signals = ring.get("signals")
                if isinstance(signals, dict):
                    updated = str(signals.get("updateTime") or "")
                conn.execute(
                    "INSERT OR REPLACE INTO ring (id, system, address, x, y, z, body, ring, kind, density,"
                    " reserve, hotspots, updated_at, imported) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        ring_id,
                        system,
                        address,
                        x,
                        y,
                        z,
                        body_name,
                        str(ring.get("name") or ""),
                        kind,
                        density,
                        reserve,
                        json.dumps(hotspots, ensure_ascii=False),
                        updated,
                        time.time(),
                    ),
                )
                conn.execute("DELETE FROM ring_mineral WHERE ring_id = ?", (ring_id,))
                conn.executemany(
                    "INSERT INTO ring_mineral (ring_id, mineral, count) VALUES (?,?,?)",
                    [(ring_id, name, int(count or 0)) for name, count in hotspots.items()],
                )
                imported += 1
        return imported

    def _set_meta(self, **values: str) -> None:
        self.conn.executemany(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)",
            [(key, str(value)) for key, value in values.items()],
        )
        self.conn.commit()

    # ----------------------------------------------------------- поиск
    def search(
        self,
        origin: Iterable[float] | None = None,
        radius_ly: float | None = None,
        mineral: str | None = None,
        limit: int = 200,
    ) -> list[RingHit]:
        """Кольца с минералом в радиусе от `origin` (по координатам систем)."""
        if not self.exists():
            return []
        want = (mineral or "").strip()
        sql = (
            "SELECT r.system, r.body, r.kind, r.density, r.reserve, r.hotspots, r.address, r.x, r.y, r.z"
            " FROM ring r"
        )
        params: list = []
        if want:
            sql += " WHERE EXISTS (SELECT 1 FROM ring_mineral m WHERE m.ring_id = r.id AND m.mineral = ?)"
            params.append(want)
        if origin is not None and radius_ly:
            try:
                ox, oy, oz = float(origin[0]), float(origin[1]), float(origin[2])
            except (TypeError, ValueError, IndexError):
                ox = oy = oz = None  # type: ignore[assignment]
            if ox is not None:
                # куб со стороной 2R гарантированно накрывает шар радиуса R
                sql += (" AND" if want else " WHERE") + " r.x BETWEEN ? AND ? AND r.y BETWEEN ? AND ? AND r.z BETWEEN ? AND ?"
                params.extend(
                    [
                        ox - radius_ly,
                        ox + radius_ly,
                        oy - radius_ly,
                        oy + radius_ly,
                        oz - radius_ly,
                        oz + radius_ly,
                    ]
                )
        sql += " LIMIT ?"
        params.append(max(50, int(limit) * 20))  # запас: часть отсеется по расстоянию
        try:
            rows = self.conn.execute(sql, params).fetchall()
        except sqlite3.DatabaseError:
            return []

        hits: list[RingHit] = []
        for system, body, kind, density, reserve, hotspots_json, address, x, y, z in rows:
            try:
                hotspots = json.loads(hotspots_json or "{}")
            except json.JSONDecodeError:
                continue
            if not isinstance(hotspots, dict) or not hotspots:
                continue
            distance = _distance(origin, (x, y, z))
            if radius_ly is not None and distance is not None and distance > float(radius_ly):
                continue
            hits.append(
                RingHit(
                    system=system,
                    body=body,
                    kind=kind,
                    hotspots={str(k): int(v or 0) for k, v in hotspots.items()},
                    density=density,
                    reserve=reserve,
                    address=address,
                    star_pos=(x, y, z),
                    distance_ly=distance,
                )
            )
        hits.sort(
            key=lambda hit: (
                hit.distance_ly if hit.distance_ly is not None else 9e9,
                -mining.hotspot_avg_price(_top_mineral(hit.hotspots, want)),
            )
        )
        return hits[: max(1, int(limit))]


def _top_mineral(hotspots: dict[str, int], want: str) -> str:
    if want:
        for name in hotspots:
            if name.lower() == want.lower():
                return name
    rows = mining.sorted_hotspots(hotspots)
    return rows[0][0] if rows else ""


def _ring_hotspots(ring: dict) -> dict[str, int]:
    """Хотспоты кольца из дампа: `signals.signals` — {минерал: количество}."""
    signals = ring.get("signals")
    if isinstance(signals, dict):
        inner = signals.get("signals")
        if isinstance(inner, dict):
            return {str(name): int(count or 0) for name, count in inner.items() if str(name).strip()}
    return {}


def _clean_kind(value) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.startswith("eRingClass_"):
        text = text[len("eRingClass_"):]
    return text


def _clean_reserve(value) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.startswith("eReserveLevel_"):
        text = text[len("eReserveLevel_"):]
    return text


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fallback_id(system: str, body: str, ring) -> int:
    """Стабильный ключ, если в дампе нет id64 кольца."""
    seed = f"{system}|{body}|{ring}".encode("utf-8")
    total = 0
    for byte in seed:
        total = (total * 131 + byte) % 2_000_000_000_000_000_000
    return total


def _distance(origin: Iterable[float] | None, pos: tuple[float, float, float] | None) -> float | None:
    if origin is None or pos is None:
        return None
    try:
        ox, oy, oz = float(origin[0]), float(origin[1]), float(origin[2])
        x, y, z = float(pos[0]), float(pos[1]), float(pos[2])
    except (TypeError, ValueError, IndexError):
        return None
    return ((ox - x) ** 2 + (oy - y) ** 2 + (oz - z) ** 2) ** 0.5
