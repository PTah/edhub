# Created by nc.ai 1.2.15 on Papasha 2026-11-15 12:13:50
"""Вкладка «Добыча»: планетарные точки добычи и кольца с ценами.

Два источника строк:

* локальный — тела текущей системы из журнала (`geo_signals`, `hotspots`,
  `materials`), то есть то, что игра уже рассказала про эту систему;
* внешний — Spansh (`miningsearch`), поиск тел в радиусе от текущей системы
  по материалу поверхности.

Выручка считается по индексу цен (`prices.MarketIndex`), а если рынок ещё не
видели — по средней цене из `mining.HOTSPOT_AVG_PRICE_CR` (она помечается ≈).
"""
from __future__ import annotations

import threading
import time
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import ttk

from . import hotspots, mining, miningsearch, sellstations, values
from .i18n import t

COLUMNS: tuple[tuple[str, str, int, str], ...] = (
    ("system", "col.system", 150, "w"),
    ("body", "col.name", 190, "w"),
    ("subtype", "col.type", 130, "w"),
    ("sites", "col.sites", 170, "w"),
    ("material", "col.material", 120, "w"),
    ("share", "col.share", 70, "e"),
    ("ly", "col.ly_short", 70, "e"),
    ("ls", "col.dist", 80, "e"),
    ("minerals", "col.minerals", 200, "w"),
    ("density", "col.density", 80, "e"),
    ("price", "col.price", 110, "e"),
)


@dataclass
class MiningRow:
    """Строка таблицы: либо планетарная точка добычи, либо кольцо."""

    system: str
    body: str
    subtype: str = ""
    sites: str = ""
    material: str = ""
    share: float = 0.0
    distance_ly: float | None = None
    distance_ls: float | None = None
    rings: str = ""
    price: int = 0
    price_exact: bool = False
    density: float | None = None
    hotspots: dict[str, int] = field(default_factory=dict)
    body_id: int | None = None
    address: int | None = None
    planet_class: str | None = None
    origin: str = "here"  # here | db | spansh

    def sort_key(self, column: str):
        if column == "share":
            return self.share
        if column == "ly":
            return self.distance_ly if self.distance_ly is not None else 9e9
        if column == "ls":
            return self.distance_ls if self.distance_ls is not None else 9e9
        if column == "density":
            return self.density if self.density is not None else -1.0
        if column == "price":
            return self.price
        return str(self.cells()[COLUMNS_INDEX.get(column, 1)]).lower()

    def cells(self) -> tuple[str, ...]:
        share = f"{self.share:.1f}%" if self.share > 0 else "—"
        ly = f"{self.distance_ly:.1f}" if self.distance_ly else "—"
        ls = f"{int(self.distance_ls):,}".replace(",", " ") if self.distance_ls else "—"
        if self.price > 0:
            price = f"{'≈' if not self.price_exact else ''}{self.price:,}".replace(",", " ")
        else:
            price = "—"
        method = mining.mineral_method(self.material)
        material = f"{self.material} · {t('mining.method_core' if method == 'core' else 'mining.method_laser')}" if (self.material and method) else (self.material or "—")
        return (
            self.system,
            self.body,
            self.subtype or "—",
            self.sites or "—",
            material,
            share,
            ly,
            ls,
            self.rings or "—",
            f"{self.density:.2f}" if self.density else "—",
            price,
        )


COLUMNS_INDEX = {key: index for index, (key, _title, _w, _a) in enumerate(COLUMNS)}

# материалы для выпадающего списка: сначала редкие
MATERIAL_CHOICES: tuple[str, ...] = tuple(
    name
    for name, _grade in sorted(
        mining.RAW_MATERIAL_GRADE.items(),
        key=lambda item: (-item[1], item[0].lower()),
    )
)


def rows_from_spansh(
    hits: list,
    price_index=None,
    material: str | None = None,
) -> list[MiningRow]:
    """Строки из базы Spansh: кольца с известным составом и координатами системы."""
    rows: list[MiningRow] = []
    want = (material or "").strip()
    for hit in hits:
        if want and not any(name.lower() == want.lower() for name in hit.hotspots):
            continue
        name, price, exact = (
            _material_quote(want, price_index) if want else _best_hotspot(hit.hotspots, price_index)
        )
        rows.append(
            MiningRow(
                system=hit.system,
                body=hit.body,
                subtype=hit.kind or "",
                sites=_sites_label(sum(hit.hotspots.values()), hit.reserve),
                material=name,
                distance_ly=hit.distance_ly,
                rings=mining.format_hotspots(hit.hotspots),
                price=price,
                price_exact=exact,
                hotspots=dict(hit.hotspots),
                address=hit.address,
                density=hit.density,
                planet_class=hit.kind,
                origin="spansh",
            )
        )
    return rows


def _sites_label(count: int, reserve: str | None = None) -> str:
    """«хотспоты ×3 · Pristine» — сколько и насколько богатое кольцо."""
    label = t("mining.ring_sites", n=count)
    return f"{label} · {reserve}" if reserve else label


def ring_hint(ring_types, reserve: str | None = None, density: float | None = None) -> str:
    """«Icy · Pristine · плотн. 10.01 — ядро: …, лазер: …» — что копать в кольце."""
    kinds = mining.ring_kinds(ring_types)
    if not kinds:
        return ""
    parts = [" · ".join(kinds)]
    if reserve:
        parts.append(reserve)
    if density:
        parts.append(t("mining.density_short", value=f"{density:.2f}"))
    head = " · ".join(parts)
    table = mining.ring_minerals(ring_types)
    chunks: list[str] = []
    for method, key in ((mining.METHOD_CORE, "mining.method_core"), (mining.METHOD_LASER, "mining.method_laser")):
        names = [name for name in table.get(method, []) if mining.is_high_value(name)][:3]
        if not names:
            names = table.get(method, [])[:3]
        if names:
            chunks.append(f"{t(key)}: {', '.join(names)}")
    body = "; ".join(chunks)
    return f"{head} — {body}" if body else head


def best_sell_hint(price_index, material: str | None, origin=None, jump_range: float | None = None) -> str:
    """«лучший сбыт: <станция> (<система>) — 1 200 000 cr · 45 ly · 3 прыж.»."""
    if price_index is None or not material:
        return ""
    choice = sellstations.best_sell(price_index, material, origin, jump_range)
    if choice is None:
        return ""
    return t("mining.best_sell_full", where=f"{choice.station} ({choice.system})", price=values.credits(choice.price),
             distance=(f"{choice.distance_ly:.0f} ly" if choice.distance_ly is not None else "—"),
             jumps=(str(choice.jumps) if choice.jumps else "—"))


def rows_from_state(state, price_index=None, material: str | None = None) -> list[MiningRow]:
    """Тела текущей системы: точки добычи на поверхности и кольца с хотспотами."""
    rows: list[MiningRow] = []
    system = state.system.name or ""
    want = (material or "").strip()
    for body in (state.system.bodies or {}).values():
        if getattr(body, "is_star", False):
            continue
        share_of: dict[str, float] = dict(getattr(body, "materials", {}) or {})
        body_hotspots: dict[str, int] = dict(getattr(body, "hotspots", {}) or {})
        geo = getattr(body, "geo_signals", None)
        if geo and (not want or want in share_of):
            rows.append(
                MiningRow(
                    system=system,
                    body=body.name,
                    subtype=getattr(body, "planet_class", None) or "",
                    sites=f"{t('mining.geological')} ×{int(geo)}",
                    material=want or _best_material_name(share_of),
                    share=float(share_of.get(want) or 0.0) if want else _best_material_share(share_of),
                    distance_ls=getattr(body, "distance_ls", None),
                    body_id=getattr(body, "body_id", None),
                    planet_class=getattr(body, "planet_class", None),
                )
            )
        if body_hotspots and (not want or want in body_hotspots):
            top_name, top_price, exact = (
                _material_quote(want, price_index) if want else _best_hotspot(body_hotspots, price_index)
            )
            rows.append(
                MiningRow(
                    system=system,
                    body=body.name,
                    subtype=" · ".join(getattr(body, "ring_types", None) or [])
                    or (getattr(body, "planet_class", None) or ""),
                    sites=_sites_label(sum(body_hotspots.values()), getattr(body, "reserve_level", None)),
                    material=top_name,
                    distance_ls=getattr(body, "distance_ls", None),
                    rings=mining.format_hotspots(body_hotspots),
                    price=top_price,
                    price_exact=exact,
                    density=getattr(body, "ring_density", None),
                    hotspots=body_hotspots,
                    body_id=getattr(body, "body_id", None),
                    planet_class=getattr(body, "planet_class", None),
                )
            )
    rows.sort(key=lambda row: (row.system.lower(), row.body.lower()))
    return rows


def rows_from_hotspots(
    near: list[hotspots.NearRing],
    price_index=None,
    material: str | None = None,
) -> list[MiningRow]:
    """Строки из своей базы хотспотов: кольца с известным составом и расстоянием."""
    rows: list[MiningRow] = []
    want = (material or "").strip()
    for hit in near:
        ring = hit.ring
        if want and want not in ring.hotspots:
            continue
        name, price, exact = (
            _material_quote(want, price_index) if want else _best_hotspot(ring.hotspots, price_index)
        )
        rows.append(
            MiningRow(
                system=ring.system,
                body=ring.body_name,
                subtype=" · ".join(ring.ring_types) or (ring.planet_class or ""),
                sites=_sites_label(sum(ring.hotspots.values()), ring.reserve_level),
                material=name,
                distance_ly=hit.distance_ly,
                distance_ls=ring.distance_ls,
                rings=mining.format_hotspots(ring.hotspots),
                price=price,
                price_exact=exact,
                density=ring.density,
                hotspots=dict(ring.hotspots),
                body_id=ring.body_id,
                address=ring.address,
                planet_class=ring.planet_class,
                origin="db",
            )
        )
    return rows


def rows_from_remote(bodies: list[miningsearch.RemoteBody], material: str | None, price_index=None) -> list[MiningRow]:
    """Строки из ответа Spansh: поверхностные точки и кольца."""
    rows: list[MiningRow] = []
    for body in bodies:
        if body.has_surface_site():
            best_name, best_share = body.best_material() or ("", 0.0)
            rows.append(
                MiningRow(
                    system=body.system,
                    body=body.name,
                    subtype=body.subtype or "",
                    sites=body.signals_label(),
                    material=best_name,
                    share=best_share,
                    distance_ly=body.distance_ly,
                    distance_ls=body.distance_ls,
                    body_id=body.body_id,
                    address=body.address,
                )
            )
        if body.ring_types:
            name = material or ""
            price = 0
            exact = False
            if name:
                quote = price_index.best(name) if price_index is not None else None
                if quote is not None:
                    price, exact = int(quote.price), True
                else:
                    price = mining.hotspot_avg_price(name)
            rows.append(
                MiningRow(
                    system=body.system,
                    body=body.name,
                    subtype=" · ".join(body.ring_types),
                    sites=t("mining.rings_n", n=len(body.ring_types)),
                    material=name,
                    distance_ly=body.distance_ly,
                    distance_ls=body.distance_ls,
                    rings="—",  # Spansh состав колец не отдаёт
                    price=price,
                    price_exact=exact,
                    body_id=body.body_id,
                    address=body.address,
                    origin="spansh",
                )
            )
    return rows


def _best_material_name(materials: dict[str, float]) -> str:
    rows = mining.material_rows(materials)
    return rows[0][0] if rows else ""


def _best_material_share(materials: dict[str, float]) -> float:
    rows = mining.material_rows(materials)
    return float(rows[0][1]) if rows else 0.0


def _material_quote(name: str, price_index) -> tuple[str, int, bool]:
    """Цена конкретного минерала: живой индекс цен, иначе средняя (≈)."""
    quote = price_index.best(name) if price_index is not None else None
    if quote is not None and int(quote.price) > 0:
        return name, int(quote.price), True
    return name, mining.hotspot_avg_price(name), False


def _best_hotspot(hotspots: dict[str, int], price_index) -> tuple[str, int, bool]:
    """Самый дорогой горячий минерал: сначала живой индекс цен, потом средняя."""
    best_exact = ("", 0)
    best_average = ("", 0)
    for name in hotspots:
        quote = price_index.best(name) if price_index is not None else None
        if quote is not None and int(quote.price) > best_exact[1]:
            best_exact = (name, int(quote.price))
        average = mining.hotspot_avg_price(name)
        if average > best_average[1]:
            best_average = (name, average)
    if best_exact[1] > 0:
        return best_exact[0], best_exact[1], True
    return best_average[0], best_average[1], False


class MiningTab:
    """Вкладка целиком: панель фильтров + таблица."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        colors: dict,
        ui_family: str,
        ui_size: int,
        price_index=None,
        belt_store=None,
        hotspot_store=None,
        spansh_index=None,
        on_target=None,
        on_copy_system=None,
        on_status=None,
        default_radius: float = 25.0,
    ) -> None:
        self.colors = colors
        self.ui_family = ui_family
        self.ui_size = ui_size
        self.price_index = price_index
        self.belt_store = belt_store
        self.hotspot_store = hotspot_store
        self.spansh_index = spansh_index
        self.on_target = on_target or (lambda _name: None)
        self.on_copy_system = on_copy_system
        self.on_status = on_status or (lambda _text: None)
        self.frame = ttk.Frame(parent, style="ED.TFrame", padding=8)
        self._state = None
        self._rows: list[MiningRow] = []
        self._source = "here"  # here | db | spansh
        self._remote_bodies: list = []
        self._signature: tuple | None = None
        self._last_auto = 0.0
        self._sort_column = "ly"
        self._sort_desc = False
        self._searching = False
        self._radius = tk.StringVar(value=f"{int(default_radius)}")
        self._material = tk.StringVar(value="")
        self._status = tk.StringVar(value="")
        self._build()

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        bar = tk.Frame(self.frame, bg=self.colors["bg"])
        bar.pack(fill="x", pady=(0, 6))

        radius_box = tk.Frame(bar, bg=self.colors["bg"])
        radius_box.pack(side="left", padx=(0, 10))
        tk.Label(
            radius_box,
            text=t("mining.radius"),
            bg=self.colors["bg"],
            fg=self.colors["muted"],
            font=(self.ui_family, self.ui_size),
        ).pack(side="left")
        tk.Spinbox(
            radius_box,
            from_=1,
            to=100,
            width=4,
            textvariable=self._radius,
            bg=self.colors["panel"],
            fg=self.colors["fg"],
            buttonbackground=self.colors["panel"],
            insertbackground=self.colors["fg"],
            relief="flat",
        ).pack(side="left", padx=(4, 0))

        tk.Label(
            bar,
            text=t("mining.material"),
            bg=self.colors["bg"],
            fg=self.colors["muted"],
            font=(self.ui_family, self.ui_size),
        ).pack(side="left")
        self.material_combo = ttk.Combobox(
            bar,
            textvariable=self._material,
            values=("",) + MATERIAL_CHOICES,
            width=16,
            state="readonly",
        )
        self.material_combo.pack(side="left", padx=(4, 10))
        self.material_combo.bind("<<ComboboxSelected>>", self._on_material_change)

        self.search_button = tk.Button(
            bar,
            text=t("mining.search"),
            command=self.search,
            bg=self.colors["panel"],
            fg=self.colors["fg"],
            activebackground=self.colors["accent"],
            activeforeground=self.colors["bg"],
            relief="flat",
            padx=10,
            font=(self.ui_family, self.ui_size, "bold"),
        )
        self.search_button.pack(side="left", padx=(0, 6))
        self.local_button = tk.Button(
            bar,
            text=t("mining.here"),
            command=self.refresh,
            bg=self.colors["panel"],
            fg=self.colors["fg"],
            activebackground=self.colors["accent"],
            activeforeground=self.colors["bg"],
            relief="flat",
            padx=10,
            font=(self.ui_family, self.ui_size),
        )
        self.local_button.pack(side="left", padx=(0, 6))
        self.db_button = tk.Button(
            bar,
            text=t("mining.db_search"),
            command=self.search_db,
            bg=self.colors["panel"],
            fg=self.colors["fg"],
            activebackground=self.colors["accent"],
            activeforeground=self.colors["bg"],
            relief="flat",
            padx=10,
            font=(self.ui_family, self.ui_size),
        )
        self.db_button.pack(side="left", padx=(0, 6))
        self.save_button = tk.Button(
            bar,
            text=t("mining.save_belt"),
            command=self.save_selected,
            bg=self.colors["panel"],
            fg=self.colors["fg"],
            activebackground=self.colors["accent"],
            activeforeground=self.colors["bg"],
            relief="flat",
            padx=10,
            font=(self.ui_family, self.ui_size),
        )
        self.save_button.pack(side="left")

        tk.Label(
            self.frame,
            textvariable=self._status,
            bg=self.colors["bg"],
            fg=self.colors["muted"],
            anchor="w",
            font=(self.ui_family, self.ui_size),
        ).pack(fill="x", pady=(0, 4))

        host = tk.Frame(self.frame, bg=self.colors["bg"])
        host.pack(fill="both", expand=True)
        host.grid_columnconfigure(0, weight=1)
        host.grid_rowconfigure(0, weight=1)

        style = ttk.Style()
        style.configure(
            "Mining.Treeview",
            background=self.colors["row"],
            fieldbackground=self.colors["row"],
            foreground=self.colors["fg"],
            rowheight=max(18, self.ui_size * 2 + 6),
            borderwidth=0,
        )
        style.configure(
            "Mining.Treeview.Heading",
            background=self.colors["panel"],
            foreground=self.colors["fg"],
        )
        columns = tuple(key for key, _title, _w, _a in COLUMNS)
        self.tree = ttk.Treeview(
            host,
            columns=columns,
            show="headings",
            style="Mining.Treeview",
            selectmode="browse",
        )
        for key, title_key, width, anchor in COLUMNS:
            self.tree.heading(
                key,
                text=t(title_key),
                anchor=anchor,
                command=lambda col=key: self.sort_by(col),
            )
            self.tree.column(key, width=width, anchor=anchor, stretch=False)
        scroll = ttk.Scrollbar(host, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(host, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        self.tree.bind("<Double-Button-1>", self._on_double_click)

    # --------------------------------------------------------------- данные
    def set_state(self, state) -> None:
        """Каждый тик: если просканировали новое кольцо — таблица обновится сама."""
        self._state = state
        if self._source != "here":
            return
        signature = self._local_signature(state)
        if signature == self._signature:
            return
        now = time.monotonic()
        if now - self._last_auto < 0.5:
            return  # подождём следующего тика, чтобы не дёргать таблицу зря
        self._last_auto = now
        self._signature = signature
        self.refresh(quiet=True)

    def _local_signature(self, state) -> tuple:
        """Что показывает текущая система: тела, геология, минералы колец."""
        bodies = getattr(getattr(state, "system", None), "bodies", None) or {}
        return (
            getattr(getattr(state, "system", None), "name", "") or "",
            tuple(
                sorted(
                    (
                        int(getattr(body, "body_id", 0) or 0),
                        int(getattr(body, "geo_signals", 0) or 0),
                        tuple(sorted((getattr(body, "hotspots", None) or {}).items())),
                    )
                    for body in bodies.values()
                    if getattr(body, "geo_signals", None) or getattr(body, "hotspots", None)
                )
            ),
        )

    def on_show(self) -> None:
        """Вкладку выбрали — показываем локальные данные, если ещё пусто."""
        if not self._rows:
            self.refresh()

    def refresh(self, *, quiet: bool = False) -> None:
        """Перечитать текущую систему из журнала."""
        if self._state is None:
            return
        material = self._material_now()
        self._source = "here"
        self._rows = rows_from_state(self._state, self.price_index, material)
        self._render()
        if not quiet or not self._rows:
            self._status.set(self._local_status_text(material))

    def _local_status_text(self, material: str) -> str:
        parts = [
            t("mining.local_status", n=len(self._rows))
            if not material
            else t("mining.filter_status", n=len(self._rows), material=material)
        ]
        metrics = getattr(self._state, "mining", None)
        if metrics is not None:
            stats_text = metrics.hud_text()
            if stats_text:
                parts.append(stats_text)
        hint = self._ring_hint_text()
        if hint:
            parts.append(hint)
        sell = best_sell_hint(self.price_index, material, *self._sell_context())
        if sell:
            parts.append(sell)
        return " · ".join(parts)

    def _sell_context(self):
        """Координаты текущей системы и прыжковый радиус — для ранга сбыта."""
        state = self._state
        pos = getattr(getattr(state, "system", None), "star_pos", None)
        origin = (float(pos[0]), float(pos[1]), float(pos[2])) if pos and len(pos) == 3 else None
        return origin, float(getattr(state, "jump_range", 0.0) or 0.0)

    def _ring_hint_text(self) -> str:
        """Подсказка по самому дорогому кольцу текущей системы: тип, запас, что копать."""
        bodies = getattr(getattr(self._state, "system", None), "bodies", None) or {}
        candidates = [body for body in bodies.values() if getattr(body, "hotspots", None)]
        if not candidates:
            candidates = [body for body in bodies.values() if getattr(body, "has_rings", False)]
        if not candidates:
            return ""
        best = max(
            candidates,
            key=lambda body: sum(
                mining.hotspot_avg_price(name) * int(count or 0)
                for name, count in (getattr(body, "hotspots", None) or {}).items()
            ),
        )
        return ring_hint(
            getattr(best, "ring_types", None),
            getattr(best, "reserve_level", None),
            getattr(best, "ring_density", None),
        )

    def search_db(self) -> None:
        """Поиск по своей базе хотспотов: минерал + радиус от текущей системы."""
        if self.hotspot_store is None:
            return
        material = self._material_now()
        radius = self._radius_now()
        origin = getattr(getattr(self._state, "system", None), "star_pos", None)
        near = self.hotspot_store.search(origin, radius_ly=radius, mineral=material or None)
        self._source = "db"
        self._rows = rows_from_hotspots(near, self.price_index, material)
        from_base = 0
        if self.spansh_index is not None and self.spansh_index.exists():
            hits = self.spansh_index.search(origin, radius_ly=radius, mineral=material or None, limit=150)
            known = {(row.system.lower(), row.body.lower()) for row in self._rows}
            fresh = [hit for hit in hits if (hit.system.lower(), hit.body.lower()) not in known]
            from_base = len(fresh)
            self._rows += rows_from_spansh(fresh, self.price_index, material)
            self._rows.sort(
                key=lambda row: (
                    row.distance_ly if row.distance_ly is not None else 9e9,
                    -row.price,
                )
            )
        self._render()
        parts = [
            t(
                "mining.db_status",
                n=len(self._rows),
                total=len(self.hotspot_store),
                radius=int(radius),
                material=material or t("mining.any_material"),
            )
        ]
        if from_base:
            parts.append(t("mining.db_spansh", n=from_base))
        if near:
            first = near[0].ring
            hint = ring_hint(first.ring_types, first.reserve_level, first.density)
            if hint:
                parts.append(hint)
        sell = best_sell_hint(self.price_index, material, *self._sell_context())
        if sell:
            parts.append(sell)
        self._status.set(" · ".join(parts))

    def _on_material_change(self, _event=None) -> None:
        """Сменили минерал — перестраиваем то, что уже показано, и запоминаем цель."""
        material = self._material_now()
        self.on_target(material)
        if self._state is not None:
            self._state.mining.target = material
        if self._source == "db":
            self.search_db()
        elif self._source == "spansh":
            self._rows = rows_from_remote(self._remote_bodies, self._material_now() or None, self.price_index)
            self._render()
            self._status.set(t("mining.found", n=len(self._rows)))
        else:
            self.refresh()

    def _material_now(self) -> str:
        return (self._material.get() or "").strip()

    def _radius_now(self) -> float:
        try:
            return float(self._radius.get() or 25)
        except ValueError:
            return 25.0

    def search(self) -> None:
        """Поиск у Spansh в фоне: тела в радиусе с точками добычи."""
        if self._searching:
            return
        system = ""
        if self._state is not None:
            system = self._state.system.name or ""
        if not system:
            self._status.set(t("mining.no_system"))
            return
        radius = self._radius_now()
        material = self._material_now() or None
        self._searching = True
        self.search_button.configure(state="disabled")
        self._status.set(t("mining.searching", system=system, radius=int(radius)))

        def work() -> None:
            try:
                bodies = miningsearch.search_bodies(
                    system,
                    radius_ly=radius,
                    pages=4,
                    on_page=lambda page, total: self._status_from_thread(
                        t("mining.page", page=page, total=total)
                    ),
                )
                rows = rows_from_remote(bodies, material, self.price_index)
            except Exception as exc:  # noqa: BLE001 — показываем текст ошибки
                self._ui(lambda: self._finish_search(None, str(exc), bodies=None))
                return
            self._ui(lambda: self._finish_search(rows, None, bodies=bodies))

        threading.Thread(target=work, name="edhud-mining-search", daemon=True).start()

    def _status_from_thread(self, text: str) -> None:
        self._ui(lambda: self._status.set(text))

    def _finish_search(self, rows: list[MiningRow] | None, error: str | None, bodies=None) -> None:
        self._searching = False
        self.search_button.configure(state="normal")
        if error:
            self._status.set(t("mining.error", error=error))
            return
        self._source = "spansh"
        self._remote_bodies = list(bodies or [])
        self._rows = rows or []
        self._render()
        text = t("mining.found", n=len(self._rows)) + " " + t("mining.spansh_note")
        sell = best_sell_hint(self.price_index, self._material_now(), *self._sell_context())
        self._status.set(f"{text} · {sell}" if sell else text)

    def _ui(self, callback) -> None:
        try:
            self.frame.after(0, callback)
        except tk.TclError:
            pass

    # ------------------------------------------------------------- таблица
    def _render(self) -> None:
        self.tree.delete(*self.tree.get_children())
        rows = self._sorted_rows()
        for row in rows:
            self.tree.insert("", "end", values=row.cells())
        if not rows:
            self._status.set(self._status.get() or t("mining.empty"))

    def _sorted_rows(self) -> list[MiningRow]:
        rows = list(self._rows)
        try:
            rows.sort(key=lambda row: row.sort_key(self._sort_column), reverse=self._sort_desc)
        except TypeError:
            pass
        return rows

    def sort_by(self, column: str) -> None:
        if column == self._sort_column:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_column = column
            self._sort_desc = column in ("share", "price")
        self._render()

    def _selected_row(self) -> MiningRow | None:
        selection = self.tree.selection()
        if not selection:
            return None
        values = self.tree.item(selection[0], "values")
        if not values:
            return None
        for row in self._rows:
            if row.cells() == tuple(values):
                return row
        return None

    def _on_double_click(self, _event=None) -> None:
        row = self._selected_row()
        if row is not None and row.system and self.on_copy_system is not None:
            self.on_copy_system(row.system)

    def save_selected(self) -> None:
        """Сохранить кольцо выбранного тела в «Пояса»."""
        row = self._selected_row()
        if row is None or self.belt_store is None:
            return
        if not row.hotspots:
            self._status.set(t("mining.no_hotspots"))
            return
        from .belts import SavedBelt

        belt = SavedBelt(
            system=row.system,
            body_id=int(row.body_id or 0),
            body_name=row.body,
            hotspots=dict(row.hotspots),
            address=row.address,
            planet_class=row.planet_class,
        )
        self.belt_store.upsert(belt)
        self._status.set(t("mining.saved", body=row.body))
