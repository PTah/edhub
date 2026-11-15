# Created by nc.ai 1.2.15 on Papasha 2026-11-15 12:12:18
"""Индекс рыночных цен на то, что добывают: журнал `Market` + поток EDDN.

Зачем свой индекс, а не запрос к сайту: публичных API с ценами без ключа почти
не осталось (EDDB закрыт, Inara требует ключ), а Spansh цен не отдаёт. Зато у
нас уже есть два источника даром:

* событие журнала `Market` (и Market.json) — полный снимок рынка станции,
  где командир только что пристыковался;
* поток EDDN `commodity` — те же снимки от EDMC других игроков, когда сессия
  EDDN включена.

Индекс хранит только добываемые товары (см. `mining.HOTSPOT_AVG_PRICE_CR`),
по одной лучшей станции на товар и с датой: иначе файл растёт неограниченно.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import config
from .mining import HOTSPOT_AVG_PRICE_CR

# нормализованные имена добываемых товаров (нижний регистр)
MINING_COMMODITIES: frozenset[str] = frozenset(name.lower() for name in HOTSPOT_AVG_PRICE_CR)

MAX_QUOTES = 4000
DEFAULT_MAX_AGE_DAYS = 14.0
EDDN_COMMODITY_SCHEMA = "commodity"


def is_mining_commodity(name: str | None) -> bool:
    return bool(name) and str(name).lower() in MINING_COMMODITIES


@dataclass
class Quote:
    """Лучшая известная цена продажи товара и где она."""

    commodity: str
    station: str
    system: str
    price: int
    updated: float = 0.0

    def age_days(self, now: float | None = None) -> float:
        if not self.updated:
            return 999.0
        return max(0.0, ((now or time.time()) - float(self.updated)) / 86400.0)


class MarketIndex:
    """JSON-индекс цен: %LOCALAPPDATA%/EliteDangerousHUD/prices.json."""

    def __init__(self, path: Path | None = None, max_age_days: float = DEFAULT_MAX_AGE_DAYS) -> None:
        self.path = Path(path) if path else config.app_dir() / "prices.json"
        self.max_age_days = float(max_age_days)
        self._quotes: dict[str, Quote] = {}
        self._lock = threading.Lock()
        self.load()

    # ------------------------------------------------------------ хранилище
    def load(self) -> None:
        quotes: dict[str, Quote] = {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._quotes = {}
            return
        rows = raw.get("quotes") if isinstance(raw, dict) else raw
        if not isinstance(rows, list):
            self._quotes = {}
            return
        for item in rows:
            if not isinstance(item, dict):
                continue
            commodity = item.get("commodity")
            if not is_mining_commodity(commodity):
                continue
            try:
                quote = Quote(
                    commodity=str(commodity),
                    station=str(item.get("station") or ""),
                    system=str(item.get("system") or ""),
                    price=int(item.get("price") or 0),
                    updated=float(item.get("updated") or 0.0),
                )
            except (TypeError, ValueError):
                continue
            if quote.price > 0:
                quotes[quote.commodity.lower()] = quote
        self._quotes = quotes

    def save(self) -> bool:
        self.prune()
        with self._lock:
            payload = {
                "version": 1,
                "quotes": [asdict(quote) for quote in self._quotes.values()],
            }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
        except OSError:
            return False

    # ------------------------------------------------------------- наполнение
    def add(self, commodity: str, station: str, system: str, price: int, updated: float | None = None) -> bool:
        """Добавить цену, если она лучше известной. True — индекс изменился."""
        if not is_mining_commodity(commodity):
            return False
        price = int(price or 0)
        if price <= 0:
            return False
        key = str(commodity).lower()
        when = float(updated or time.time())
        with self._lock:
            current = self._quotes.get(key)
            if current is not None and current.price >= price and current.updated >= when:
                return False
            self._quotes[key] = Quote(
                commodity=str(commodity),
                station=str(station or ""),
                system=str(system or ""),
                price=price,
                updated=when,
            )
            return True

    def ingest_market_event(self, event: dict) -> int:
        """Снимок рынка из журнала: {"StationName","StarSystem","Items":[...]}."""
        if not isinstance(event, dict):
            return 0
        station = str(event.get("StationName") or "")
        system = str(event.get("StarSystem") or "")
        items = event.get("Items")
        if not isinstance(items, list):
            return 0
        stamp = _event_time(event)
        changed = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("Name") or item.get("name")
            price = item.get("SellPrice", item.get("sellPrice"))
            if not is_mining_commodity(name):
                continue
            try:
                price = int(price or 0)
            except (TypeError, ValueError):
                continue
            if self.add(str(name), station, system, price, stamp):
                changed += 1
        return changed

    def ingest_commodity(self, message: dict) -> int:
        """Сообщение EDDN commodity/3 (строка fields в нижнем регистре)."""
        if not isinstance(message, dict):
            return 0
        station = str(message.get("stationName") or message.get("station_name") or "")
        system = str(message.get("systemName") or message.get("starSystem") or "")
        rows = message.get("commodities")
        if not isinstance(rows, list):
            return 0
        stamp = _parse_stamp(message.get("timestamp"))
        changed = 0
        for item in rows:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("Name")
            if not is_mining_commodity(name):
                continue
            try:
                price = int(item.get("sellPrice", item.get("SellPrice", 0)) or 0)
            except (TypeError, ValueError):
                continue
            if self.add(str(name), station, system, price, stamp):
                changed += 1
        return changed

    # -------------------------------------------------------------- выборки
    def best(self, commodity: str) -> Quote | None:
        with self._lock:
            return self._quotes.get(str(commodity or "").lower())

    def quotes(self) -> list[Quote]:
        """Все известные товары: сначала самые дорогие."""
        with self._lock:
            rows = list(self._quotes.values())
        rows.sort(key=lambda quote: (-quote.price, quote.commodity.lower()))
        return rows

    def prune(self, now: float | None = None) -> int:
        """Выкинуть устаревшее и лишнее (старше max_age_days)."""
        limit = (now or time.time()) - self.max_age_days * 86400.0
        with self._lock:
            fresh = {key: quote for key, quote in self._quotes.items() if quote.updated >= limit}
            if len(fresh) > MAX_QUOTES:
                keep = sorted(fresh.items(), key=lambda item: -item[1].updated)[:MAX_QUOTES]
                fresh = dict(keep)
            removed = len(self._quotes) - len(fresh)
            self._quotes = fresh
        return removed

    def __len__(self) -> int:
        return len(self._quotes)


def _parse_stamp(value) -> float | None:
    """ISO-время из EDDN → epoch."""
    if not isinstance(value, str) or not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        from datetime import datetime

        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def _event_time(event: dict) -> float:
    return _parse_stamp(event.get("timestamp")) or time.time()


class PriceFeed(threading.Thread):
    """Фоновый поток EDDN: только сообщения commodity по добываемым товарам."""

    def __init__(self, index: MarketIndex, *, save_every: float = 120.0, **listener_kwargs) -> None:
        super().__init__(name="edhud-prices", daemon=True)
        from .eddn import EddnListener

        self.index = index
        self._listener = EddnListener(
            on_message=self._on_message,
            system_filter=self._accept,
            **listener_kwargs,
        )
        self.save_every = float(save_every)
        self._last_save = time.time()
        self.changed = 0
        self.stats = self._listener.stats

    # ---------------------------------------------------------------- фильтр
    @staticmethod
    def _accept(message: dict) -> bool:
        """Пускаем только commodity-сообщения с добываемыми товарами."""
        if not isinstance(message, dict) or message.get("event") != "commodity":
            return False
        rows = message.get("commodities")
        if not isinstance(rows, list):
            return False
        for item in rows:
            if isinstance(item, dict) and is_mining_commodity(item.get("name")):
                return True
        return False

    def _on_message(self, message: dict) -> None:
        self.changed += self.index.ingest_commodity(message)
        now = time.time()
        if self.changed and now - self._last_save >= self.save_every:
            self.index.save()
            self._last_save = now

    # ------------------------------------------------------------------- API
    def stop(self) -> None:
        self._listener.stop()
        try:
            self.index.save()
        except Exception:  # noqa: BLE001 — на выходе падать некуда
            pass

    def run(self) -> None:
        self._listener.run()
