"""Основное окно EDHUD (стиль EDEB): вкладки Route и Bodies."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from . import values
from .model import Body, GameState
from .route import Route


COLORS = {
    "bg": "#121212",
    "panel": "#1a1a1a",
    "fg": "#ff7100",
    "text": "#e8e8e8",
    "muted": "#8a8a8a",
    "ok": "#7ddb6a",
    "warn": "#ffd24a",
    "bad": "#ff5f56",
    "row": "#161616",
    "sel": "#2a1a0a",
    "ink": "#000000",
    "paper": "#f2f2f2",
}

# Колонки таблицы тел. Пояс — отдельная узкая ячейка со значком кольца.
BODY_COLUMNS = (
    ("belt", "", 28, "center"),
    ("name", "Имя", 200, "w"),
    ("type", "Тип", 140, "w"),
    ("atmos", "Атмосфера", 110, "w"),
    ("temp", "T", 70, "e"),
    ("bio", "Био", 50, "center"),
    ("geo", "Гео", 50, "center"),
    ("pml", "PML", 50, "center"),
    ("dss", "DSS", 50, "center"),
    ("value", "≈ Cr", 100, "e"),
    ("first", "1-е", 50, "center"),
    ("dist", "ls", 80, "e"),
    ("src", "Ист.", 70, "center"),
)


def _ls(value: float | None) -> str:
    if value is None:
        return "—"
    if value >= 10_000:
        return f"{value / 1000:,.0f} тыс".replace(",", " ")
    return f"{value:,.0f}".replace(",", " ")


def _temp(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f} K".replace(",", " ")


def signal_colors(column: str, count: int | None) -> tuple[str, str] | None:
    """Цвет ненулевого счётчика: био — зелёный, гео — красный, PML — чёрный.

    Чёрный текст на тёмной строке не виден, поэтому у PML светлый фон ячейки.
    Ноль и неизвестное значение остаются цветом таблицы.
    """
    if not count:
        return None
    if column == "bio":
        return COLORS["ok"], COLORS["row"]
    if column == "geo":
        return COLORS["bad"], COLORS["row"]
    if column == "pml":
        return COLORS["ink"], COLORS["paper"]
    return None


def _type_of(body: Body) -> str:
    if body.is_star or body.star_type:
        return f"{body.star_type or '?'} Star"
    return body.planet_class or "—"


def _ring_icon(master: tk.Misc) -> tk.PhotoImage:
    """Маленький Сатурн: так Exploration Buddy помечает тело с добываемым поясом."""
    w, h = 18, 14
    img = tk.PhotoImage(master=master, width=w, height=h)
    cx, cy = (w - 1) / 2, (h - 1) / 2
    ring = "#e6a23c"
    planet = "#e8e8e8"
    for y in range(h):
        for x in range(w):
            dx = x - cx
            dy = y - cy
            in_planet = dx * dx + dy * dy <= 9.0
            band = (dx / 8.0) ** 2 + (dy / 2.5) ** 2
            in_ring = 0.55 <= band <= 1.08
            # кольцо проходит перед нижней половиной планеты и за верхней
            if in_planet and not (in_ring and dy >= 0):
                img.put(planet, (x, y))
            elif in_ring:
                img.put(ring, (x, y))
    return img


def _value_of(body: Body, odyssey: bool) -> str:
    breakdown = values.body_values(body, odyssey=odyssey)
    if breakdown is None:
        return "—"
    amount = breakdown.mapped if body.dss_scanned else breakdown.scan
    return values.credits(amount)


class MainWindow:
    """Окно программы: скрытие = withdraw, выход только через App.request_quit."""

    def __init__(
        self,
        root: tk.Misc,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        self.on_close = on_close
        self.win = tk.Toplevel(root)
        self.win.title("EDHUD")
        self.win.geometry("980x520")
        self.win.minsize(720, 360)
        self.win.configure(bg=COLORS["bg"])
        self.win.protocol("WM_DELETE_WINDOW", self.hide)
        self._visible = True
        self._shown_tab = "bodies"
        self._ring_icon: tk.PhotoImage | None = None
        self._style()
        self._build()
        self._last_key: tuple | None = None

    def _style(self) -> None:
        style = ttk.Style(self.win)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("ED.TFrame", background=COLORS["bg"])
        style.configure("ED.TLabel", background=COLORS["bg"], foreground=COLORS["text"])
        style.configure("ED.Header.TLabel", background=COLORS["bg"], foreground=COLORS["fg"], font=("Segoe UI", 12, "bold"))
        style.configure("ED.Muted.TLabel", background=COLORS["bg"], foreground=COLORS["muted"])
        style.configure("ED.TNotebook", background=COLORS["bg"], borderwidth=0)
        style.configure("ED.TNotebook.Tab", background=COLORS["panel"], foreground=COLORS["muted"], padding=(14, 6))
        style.map(
            "ED.TNotebook.Tab",
            background=[("selected", COLORS["panel"])],
            foreground=[("selected", COLORS["fg"])],
        )
        style.configure(
            "ED.Treeview",
            background=COLORS["row"],
            foreground=COLORS["text"],
            fieldbackground=COLORS["row"],
            borderwidth=0,
            rowheight=24,
        )
        style.configure(
            "ED.Treeview.Heading",
            background=COLORS["panel"],
            foreground=COLORS["fg"],
            relief="flat",
        )
        style.map("ED.Treeview", background=[("selected", COLORS["sel"])], foreground=[("selected", COLORS["fg"])])

    def _build(self) -> None:
        top = ttk.Frame(self.win, style="ED.TFrame", padding=(12, 10))
        top.pack(fill="x")
        self.lbl_system = ttk.Label(top, text="Система: —", style="ED.Header.TLabel")
        self.lbl_system.pack(side="left")
        self.lbl_status = ttk.Label(top, text="", style="ED.Muted.TLabel")
        self.lbl_status.pack(side="left", padx=(16, 0))

        nb = ttk.Notebook(self.win, style="ED.TNotebook")
        nb.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.nb = nb

        self.tab_route = ttk.Frame(nb, style="ED.TFrame", padding=8)
        self.tab_bodies = ttk.Frame(nb, style="ED.TFrame", padding=8)
        nb.add(self.tab_route, text="Route")
        nb.add(self.tab_bodies, text="Bodies")
        nb.select(self.tab_bodies)

        self.route_info = ttk.Label(self.tab_route, text="Маршрут пуст", style="ED.TLabel")
        self.route_info.pack(anchor="w", pady=(0, 6))
        self.route_tree = ttk.Treeview(
            self.tab_route,
            columns=("idx", "system", "star", "ly"),
            show="headings",
            style="ED.Treeview",
        )
        for col, title, w, anchor in (
            ("idx", "#", 40, "center"),
            ("system", "Система", 320, "w"),
            ("star", "Класс", 80, "center"),
            ("ly", "До след., ly", 120, "e"),
        ):
            self.route_tree.heading(col, text=title)
            self.route_tree.column(col, width=w, anchor=anchor)
        route_scroll = ttk.Scrollbar(self.tab_route, orient="vertical", command=self.route_tree.yview)
        self.route_tree.configure(yscrollcommand=route_scroll.set)
        self.route_tree.pack(side="left", fill="both", expand=True)
        route_scroll.pack(side="right", fill="y")

        self._ring_icon = _ring_icon(self.win)
        self._build_bodies_table()

    def _build_bodies_table(self) -> None:
        """Таблица тел на метках: Treeview не умеет красить отдельные ячейки."""
        host = tk.Frame(self.tab_bodies, bg=COLORS["bg"])
        host.pack(fill="both", expand=True)
        host.grid_columnconfigure(0, weight=1)
        host.grid_rowconfigure(1, weight=1)

        header = tk.Frame(host, bg=COLORS["panel"])
        header.grid(row=0, column=0, sticky="ew")
        for index, (key, title, width, anchor) in enumerate(BODY_COLUMNS):
            weight = 1 if key == "name" else 0
            header.grid_columnconfigure(index, minsize=width, weight=weight)
            tk.Label(
                header,
                text=title,
                bg=COLORS["panel"],
                fg=COLORS["fg"],
                anchor=anchor,
                font=("Segoe UI", 9, "bold"),
                padx=4,
                pady=4,
            ).grid(row=0, column=index, sticky="ew")

        canvas = tk.Canvas(host, bg=COLORS["row"], highlightthickness=0, bd=0)
        scroll = ttk.Scrollbar(host, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.grid(row=1, column=0, sticky="nsew")
        scroll.grid(row=1, column=1, sticky="ns")
        tk.Frame(host, width=16, bg=COLORS["bg"]).grid(row=0, column=1)

        inner = tk.Frame(canvas, bg=COLORS["row"])
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        for index, (key, _title, width, _anchor) in enumerate(BODY_COLUMNS):
            inner.grid_columnconfigure(index, minsize=width, weight=(1 if key == "name" else 0))

        def _fit(event) -> None:
            canvas.itemconfigure(window, width=event.width)

        def _scrollregion(_event) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _wheel(event) -> None:
            canvas.yview_scroll(int(-event.delta / 120), "units")

        canvas.bind("<Configure>", _fit)
        inner.bind("<Configure>", _scrollregion)
        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _wheel))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))

        self._bodies_canvas = canvas
        self._bodies_inner = inner

    # ----------------------------------------------------------------- show
    def show(self) -> None:
        self._visible = True
        self.win.deiconify()
        self.win.lift()
        try:
            self.win.focus_force()
        except tk.TclError:
            pass

    def hide(self) -> None:
        self._visible = False
        self.win.withdraw()
        if self.on_close:
            self.on_close()

    def toggle(self) -> None:
        if self._visible and self.win.state() != "withdrawn":
            self.hide()
        else:
            self.show()

    def destroy(self) -> None:
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    # --------------------------------------------------------------- update
    def update_state(self, state: GameState) -> None:
        self._apply_tab(state)
        if not self._visible:
            # всё равно обновляем редко — но дешевле пропускать, если скрыто
            key = self._snapshot_key(state)
            if key == self._last_key:
                return
        key = self._snapshot_key(state)
        if key == self._last_key:
            return
        self._last_key = key
        self._update_header(state)
        self._update_route(state.route, state.system.name)
        self._update_bodies(state)

    def _snapshot_key(self, state: GameState) -> tuple:
        sys = state.system
        bodies = tuple(
            (
                b.body_id,
                b.bio_signals,
                b.geo_signals,
                b.mining_locations,
                b.dss_scanned,
                b.was_discovered,
                b.has_rings,
                b.source,
                round(b.distance_ls or 0, 1),
            )
            for b in sorted(sys.bodies.values(), key=lambda x: x.body_id)
        )
        route = tuple((h.system, h.star_class) for h in state.route.hops)
        dist = state.carrier_distance_ly()
        return (
            sys.address,
            sys.name,
            sys.body_count,
            sys.discovered_by_me,
            bodies,
            route,
            state.route.locked,
            state.carrier.callsign,
            state.carrier.system,
            None if dist is None else round(dist, 1),
        )

    def _apply_tab(self, state: GameState) -> None:
        tab = state.view_tab if state.view_tab in ("route", "bodies") else "bodies"
        if tab == self._shown_tab:
            return
        self._shown_tab = tab
        self.nb.select(self.tab_route if tab == "route" else self.tab_bodies)

    def _update_header(self, state: GameState) -> None:
        name = state.system.name or "—"
        known = len(state.system.bodies)
        total = state.system.body_count or known
        bio = sum(1 for b in state.system.bodies.values() if (b.bio_signals or 0) > 0)
        opened = " — открыта вами" if state.system.discovered_by_me else ""
        self.lbl_system.configure(text=f"Система: {name}{opened}")
        carrier = ""
        dist = state.carrier_distance_ly()
        if state.carrier.known and dist is not None:
            if dist < 0.05:
                carrier = " · карриер здесь"
            else:
                carrier = f" · карриер {dist:,.0f} ly".replace(",", " ")
        self.lbl_status.configure(
            text=f"тел {known}/{total} · био-тел {bio}{carrier}"
            + (" · маршрут залочен" if state.route.locked else "")
        )

    def _update_route(self, route: Route, current: str | None) -> None:
        self.route_tree.delete(*self.route_tree.get_children())
        if not route.hops:
            self.route_info.configure(text="Маршрут пуст (проложите в игре или plot/import)")
            return
        remaining = route.distance_remaining(current)
        src = route.source or "game"
        lock = " · залочен" if route.locked else ""
        extra = f" · осталось ~{remaining:,.1f} ly".replace(",", " ") if remaining else ""
        self.route_info.configure(text=f"Источник: {src}{lock}{extra}")
        current_item = None
        here = (current or "").lower()
        for i, hop in enumerate(route.hops, start=1):
            dist = hop.distance if hop.distance else None
            ly_text = f"{dist:,.1f}".replace(",", " ") if dist else "—"
            mark = "▶ " if here and hop.system.lower() == here else ""
            item = self.route_tree.insert(
                "",
                "end",
                values=(i, f"{mark}{hop.system}", hop.star_class or "—", ly_text),
            )
            if mark:
                current_item = item
        if current_item is not None:
            self.route_tree.see(current_item)

    def _update_bodies(self, state: GameState) -> None:
        for child in self._bodies_inner.winfo_children():
            child.destroy()
        bodies = sorted(
            state.system.bodies.values(),
            key=lambda b: (0 if b.is_star or b.star_type else 1, b.distance_ls or 0, b.body_id),
        )
        for row, body in enumerate(bodies):
            bio = "—" if body.bio_signals is None and not body.signals_known else str(body.bio_signals or 0)
            geo = "—" if body.geo_signals is None and not body.signals_known else str(body.geo_signals or 0)
            pml = "—" if body.mining_locations is None else str(body.mining_locations)
            dss = "✔" if body.dss_scanned else ("?" if body.dss_remote else "—")
            first = "✔" if not body.was_discovered and not body.remote else "—"
            src = body.source or ("своё" if not body.remote else "?")
            values = {
                "name": body.name or f"#{body.body_id}",
                "type": _type_of(body),
                "atmos": body.atmosphere_type or body.atmosphere or "—",
                "temp": _temp(body.surface_temp),
                "bio": bio,
                "geo": geo,
                "pml": pml,
                "dss": dss,
                "value": _value_of(body, state.odyssey),
                "first": first,
                "dist": _ls(body.distance_ls),
                "src": src,
            }
            counts = {
                "bio": body.bio_signals,
                "geo": body.geo_signals,
                "pml": body.mining_locations,
            }
            for col, (key, _title, _width, anchor) in enumerate(BODY_COLUMNS):
                if key == "belt":
                    icon = self._ring_icon if body.has_rings and self._ring_icon is not None else None
                    cell = tk.Label(self._bodies_inner, bg=COLORS["row"], image=icon)
                    if icon is not None:
                        cell.image = icon
                else:
                    paint = signal_colors(key, counts.get(key))
                    fg, bg = paint if paint else (COLORS["text"], COLORS["row"])
                    cell = tk.Label(
                        self._bodies_inner,
                        text=values[key],
                        bg=bg,
                        fg=fg,
                        anchor=anchor,
                        font=("Segoe UI", 9),
                        padx=4,
                        pady=2,
                    )
                cell.grid(row=row, column=col, sticky="ew")
