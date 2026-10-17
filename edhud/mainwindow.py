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
    "row": "#161616",
    "sel": "#2a1a0a",
}


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


def _type_of(body: Body) -> str:
    if body.is_star or body.star_type:
        return f"{body.star_type or '?'} Star"
    return body.planet_class or "—"


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

        cols = (
            "name",
            "type",
            "atmos",
            "temp",
            "bio",
            "geo",
            "dss",
            "value",
            "first",
            "dist",
            "src",
        )
        self.bodies_tree = ttk.Treeview(
            self.tab_bodies, columns=cols, show="headings", style="ED.Treeview"
        )
        headings = {
            "name": ("Имя", 200, "w"),
            "type": ("Тип", 140, "w"),
            "atmos": ("Атмосфера", 110, "w"),
            "temp": ("T", 70, "e"),
            "bio": ("Био", 50, "center"),
            "geo": ("Гео", 50, "center"),
            "dss": ("DSS", 50, "center"),
            "value": ("≈ Cr", 100, "e"),
            "first": ("1-е", 50, "center"),
            "dist": ("ls", 80, "e"),
            "src": ("Ист.", 70, "center"),
        }
        for col in cols:
            title, w, anchor = headings[col]
            self.bodies_tree.heading(col, text=title)
            self.bodies_tree.column(col, width=w, anchor=anchor, stretch=(col == "name"))
        body_scroll = ttk.Scrollbar(self.tab_bodies, orient="vertical", command=self.bodies_tree.yview)
        self.bodies_tree.configure(yscrollcommand=body_scroll.set)
        self.bodies_tree.pack(side="left", fill="both", expand=True)
        body_scroll.pack(side="right", fill="y")

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
                b.dss_scanned,
                b.was_discovered,
                b.source,
                round(b.distance_ls or 0, 1),
            )
            for b in sorted(sys.bodies.values(), key=lambda x: x.body_id)
        )
        route = tuple((h.system, h.star_class) for h in state.route.hops)
        return (sys.address, sys.name, sys.body_count, bodies, route, state.route.locked)

    def _update_header(self, state: GameState) -> None:
        name = state.system.name or "—"
        known = len(state.system.bodies)
        total = state.system.body_count or known
        bio = sum(1 for b in state.system.bodies.values() if (b.bio_signals or 0) > 0)
        self.lbl_system.configure(text=f"Система: {name}")
        self.lbl_status.configure(
            text=f"тел {known}/{total} · био-тел {bio}"
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
        for i, hop in enumerate(route.hops, start=1):
            dist = hop.distance if hop.distance else None
            ly_text = f"{dist:,.1f}".replace(",", " ") if dist else "—"
            mark = "▶ " if current and hop.system == current else ""
            self.route_tree.insert(
                "",
                "end",
                values=(i, f"{mark}{hop.system}", hop.star_class or "—", ly_text),
            )

    def _update_bodies(self, state: GameState) -> None:
        self.bodies_tree.delete(*self.bodies_tree.get_children())
        bodies = sorted(
            state.system.bodies.values(),
            key=lambda b: (0 if b.is_star or b.star_type else 1, b.distance_ls or 0, b.body_id),
        )
        for body in bodies:
            bio = "—" if body.bio_signals is None and not body.signals_known else str(body.bio_signals or 0)
            geo = "—" if body.geo_signals is None and not body.signals_known else str(body.geo_signals or 0)
            dss = "✔" if body.dss_scanned else ("?" if body.dss_remote else "—")
            first = "✔" if not body.was_discovered and not body.remote else "—"
            src = body.source or ("своё" if not body.remote else "?")
            self.bodies_tree.insert(
                "",
                "end",
                values=(
                    body.name or f"#{body.body_id}",
                    _type_of(body),
                    body.atmosphere_type or body.atmosphere or "—",
                    _temp(body.surface_temp),
                    bio,
                    geo,
                    dss,
                    _value_of(body, state.odyssey),
                    first,
                    _ls(body.distance_ls),
                    src,
                ),
            )
