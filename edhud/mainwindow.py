# Edited by nc.ai 1.2.9 on new-admin-pc 2026-11-13 14:26:03
# Edited by nc.ai 1.2.11 on Papasha 2026-11-14 16:44:56
# Edited by nc.ai 1.2.15 on new-admin-pc 2026-11-17 16:25:52
"""Основное окно EDHUD (стиль EDEB): вкладки Route, Bodies и Пояса."""
from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import ttk
from typing import Callable

from . import bio, codex, icon, values, winapi
from .belts import BeltStore, SavedBelt
from .i18n import t
from .mining import format_hotspots, format_hotspots_tip, ring_kinds
from .model import Body, GameState, format_dss_range, is_belt_body, is_ring_body
from .route import Route
from .sphere import SphereHop, fetch_sphere, plan_tour


COLORS = {
    "bg": "#121212",
    "panel": "#1a1a1a",
    "fg": "#ff7100",
    "text": "#e8e8e8",
    "muted": "#8a8a8a",
    "ok": "#7ddb6a",
    "warn": "#ffd24a",
    "gold": "#ffd700",
    "bad": "#ff5f56",
    "row": "#161616",
    "sel": "#2a1a0a",
    "ink": "#000000",
    "paper": "#f2f2f2",
    "accent": "#54dfed",
    "grid": "#3a3a3a",
}

# Колонки таблицы тел. Пояс — отдельная узкая ячейка со значком кольца.
def _columns(spec: tuple[tuple[str, str, int, str], ...]) -> tuple:
    rows = []
    for key, title, width, anchor in spec:
        text = t(title) if title.startswith("col.") else title
        rows.append((key, text, width, anchor))
    return tuple(rows)


_BODY_SPEC = (
    ("belt", "", 28, "center"),
    ("name", "col.name", 200, "w"),
    ("type", "col.type", 140, "w"),
    ("atmos", "col.atmos", 110, "w"),
    ("temp", "col.temp", 110, "e"),
    ("bio", "col.bio", 50, "center"),
    ("guess", "col.guess", 220, "w"),
    ("geo", "col.geo", 50, "center"),
    ("pml", "PML", 50, "center"),
    ("minerals", "col.minerals", 180, "w"),
    ("dss", "DSS", 50, "center"),
    ("value", "col.value", 150, "e"),
    ("first", "col.first", 50, "center"),
    ("dist", "col.dist", 80, "e"),
    ("src", "col.src", 70, "center"),
)

_ROUTE_SPEC = (
    ("idx", "#", 48, "center"),
    ("system", "col.system", 240, "w"),
    ("star", "col.star", 70, "center"),
    ("ly", "col.ly", 110, "e"),
    ("bodies", "col.bodies", 160, "w"),
    ("opened", "col.opened", 140, "w"),
)

# Заголовки читаются при импорте — язык Windows уже известен.
BODY_COLUMNS = _columns(_BODY_SPEC)
ROUTE_COLUMNS = _columns(_ROUTE_SPEC)

MIN_COL_WIDTH = 28
MIN_COL_WIDTHS = {
    "belt": 28,
    "name": 120,
    "type": 80,
    "atmos": 70,
    "temp": 90,
    "guess": 100,
    "minerals": 120,
    "system": 140,
    "bodies": 100,
    "opened": 90,
    "idx": 40,
    "star": 60,
    "leg": 70,
    "center": 70,
}
RESIZE_EDGE = 6

# Колонки таблицы Sphere Route (Treeview): ключ → ширина по умолчанию.
SPHERE_COLUMN_DEFAULTS: dict[str, int] = {
    "idx": 48,
    "system": 220,
    "star": 90,
    "leg": 100,
    "center": 110,
}


def _ls(value: float | None) -> str:
    if value is None:
        return "—"
    if value >= 10_000:
        return f"{value / 1000:,.0f} {t('unit.thousand')}".replace(",", " ")
    return f"{value:,.0f}".replace(",", " ")


def _temp(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f} K".replace(",", " ")


def _route_bodies_cell(hop, *, here: bool, system) -> str:
    """Текст колонки «Тела»: для текущей системы — FSS/сканы, иначе EDSM."""
    if here and system is not None and system.body_count:
        local = sum(
            1
            for b in system.bodies.values()
            if not getattr(b, "remote", False)
            and not is_belt_body(b.name)
            and not is_ring_body(b.name)
        )
        text = f"{local}/{int(system.body_count)}"
        if system.nonbody_count:
            text += t("route.signals", n=int(system.nonbody_count))
        progress = system.fss_progress
        if isinstance(progress, (int, float)) and progress < 0.999:
            text += t("route.fss", n=f"{progress * 100:.0f}")
        return text
    return hop.bodies_label()


def _forecast(body: Body, state: GameState) -> tuple[str, str | None]:
    """Текст колонки «Возможно»: виды после DSS или прогноз до него."""
    if (body.bio_signals or 0) <= 0 and not body.genuses:
        return "—", None
    names = bio.forecast_names(body, state.system)
    if not names:
        return "—", None
    if body.genuses:
        return ", ".join(names), "ok"
    return "≈ " + ", ".join(names), "accent"


def _forecast_tip(body: Body, state: GameState) -> str | None:
    """Список био + цена при наведении на «Био» / «Возможно» (как в SrvSurvey)."""
    predictions = bio.predict_for_body(body, state.system, limit=64)
    if predictions:
        seen: set[str] = set()
        rows: list[str] = []
        for prediction in predictions:
            if prediction.label in seen:
                continue
            seen.add(prediction.label)
            price = values.credits(prediction.reward) if prediction.reward else ""
            rows.append(f"• {prediction.label}" + (f"  {price}" if price else ""))
        header = "DSS:" if body.genuses else t("tip.maybe")
        return header + "\n" + "\n".join(rows)
    if body.genuses:
        names = [codex.display_name(key) for key in body.genuses]
        return t("tip.dss_genera") + "\n" + "\n".join(f"• {name}" for name in names)
    if (body.bio_signals or 0) <= 0:
        return None
    missing: list[str] = []
    if not body.planet_class:
        missing.append(t("tip.miss_class"))
    if not body.atmosphere and not body.atmosphere_composition:
        missing.append(t("tip.miss_atmo"))
    if body.surface_temp is None:
        missing.append(t("tip.miss_temp"))
    if not body.materials:
        missing.append(t("tip.miss_mats"))
    if missing:
        return t("tip.no_forecast", missing=", ".join(missing))
    return t("tip.no_match")


class _CellTip:
    """Всплывающая подсказка у ячейки таблицы Bodies."""

    def __init__(self, *widgets: tk.Misc, text: str) -> None:
        self.widgets = [w for w in widgets if w is not None]
        self.widget = self.widgets[0]
        self.text = text
        self._tip: tk.Toplevel | None = None
        self._after: str | None = None
        for widget in self.widgets:
            widget.bind("<Enter>", self._schedule, add="+")
            widget.bind("<Leave>", self._on_leave, add="+")
            widget.bind("<Destroy>", self._hide, add="+")

    def _schedule(self, _event=None) -> None:
        if self._tip is not None or not self.text:
            return
        self._cancel_after()
        try:
            self._after = self.widget.after(280, self._show)
        except tk.TclError:
            self._show()

    def _on_leave(self, event=None) -> None:
        # уход на дочерний виджет той же ячейки — не прячем
        if event is not None:
            try:
                going = event.widget.winfo_containing(event.x_root, event.y_root)
            except tk.TclError:
                going = None
            if going is not None:
                for widget in self.widgets:
                    if going == widget or str(going).startswith(str(widget)):
                        return
                    try:
                        if going.master == widget or widget.master == going:
                            return
                    except tk.TclError:
                        pass
        self._hide()

    def _cancel_after(self) -> None:
        if self._after is None:
            return
        try:
            self.widget.after_cancel(self._after)
        except tk.TclError:
            pass
        self._after = None

    def _show(self) -> None:
        self._after = None
        if self._tip is not None or not self.text:
            return
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        try:
            tip.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        label = tk.Label(
            tip,
            text=self.text,
            justify="left",
            background=COLORS["panel"],
            foreground=COLORS["text"],
            relief="solid",
            borderwidth=1,
            font=("Segoe UI", 9),
            padx=8,
            pady=6,
        )
        label.pack()
        tip.update_idletasks()
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        tip.wm_geometry(f"+{x}+{y}")
        self._tip = tip

    def _hide(self, _event=None) -> None:
        self._cancel_after()
        tip = self._tip
        self._tip = None
        if tip is not None:
            try:
                tip.destroy()
            except tk.TclError:
                pass


def route_tag(hop_index: int, current_index: int | None) -> str:
    """Пройденные — серые, текущая (▶) — зелёная и чуть крупнее."""
    if current_index is None:
        return ""
    if hop_index < current_index:
        return "done"
    if hop_index == current_index:
        return "here"
    return ""


def route_jump_marks(
    hops,
    current_index: int | None,
    dest_name: str | None,
) -> dict[int, str]:
    """Квадратная стрелка прыжка: -< откуда, | промежуток, -> куда прыгает корабль."""
    dest = (dest_name or "").strip().lower()
    if not dest:
        return {}
    dest_index = None
    for index, hop in enumerate(hops):
        if hop.system.lower() == dest:
            dest_index = index
            break
    if dest_index is None:
        return {}
    marks: dict[int, str] = {dest_index: "-> "}
    if current_index is None or current_index == dest_index:
        return marks
    marks[current_index] = "-< "
    lo, hi = sorted((current_index, dest_index))
    for index in range(lo + 1, hi):
        marks[index] = "|  "
    return marks


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
    if column == "minerals":
        return COLORS["accent"], COLORS["row"]
    return None


def _type_of(body: Body) -> str:
    if body.is_star or body.star_type:
        return f"{body.star_type or '?'} Star"
    if body.planet_class:
        return body.planet_class
    name = (body.name or "").lower()
    if " ring" in name or name.endswith(" ring"):
        return "Ring"
    if is_belt_body(body.name):
        return "Belt Cluster"
    return "—"


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


_RING_KIND_KEYS = {
    "Icy": "ring.kind.icy",
    "Rocky": "ring.kind.rocky",
    "Metallic": "ring.kind.metallic",
    "Metal-Rich": "ring.kind.metal_rich",
}


def _rings_tip(body: Body) -> str | None:
    """Тултип символа кольца: какого типа кольцо — ледяное, металлическое и т. д."""
    if not body.has_rings or is_belt_body(body.name):
        return None
    kinds: list[str] = []
    for kind in ring_kinds(body.ring_types):
        key = _RING_KIND_KEYS.get(kind)
        text = t(key) if key else kind
        if text not in kinds:
            kinds.append(text)
    if not kinds:
        return t("tip.rings_unknown")
    return t("tip.rings_types", kinds=", ".join(kinds))


def _value_of(body: Body, odyssey: bool) -> str:
    breakdown = values.body_values(body, odyssey=odyssey)
    if breakdown is None:
        return "—"
    # Всегда оценка картографии (как в ED Buddy), не цена голого скана.
    return values.credits(breakdown.mapped)


def _paint_grid(widget: tk.Misc, bg: str | None = None) -> None:
    """Рамка ячейки — видимая табличная сетка."""
    opts = {
        "highlightthickness": 1,
        "highlightbackground": COLORS["grid"],
        "highlightcolor": COLORS["grid"],
        "bd": 0,
    }
    if bg is not None:
        opts["bg"] = bg
    widget.configure(**opts)


def _row_height(font_size: int) -> int:
    return max(22, int(font_size) + 14)


def _fmt_clock(seconds: float) -> str:
    """Секунды → «12:34» (или «1:02:03»)."""
    total = max(0, int(round(seconds)))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _geometry_xy(geometry: str) -> tuple[int, int]:
    """Разобрать X/Y из строки geometry tk («980x520+12+40», «800x600-10+20»)."""
    import re

    text = (geometry or "").strip()
    if not text:
        return 0, 0
    match = re.search(r"(?:^|\d)([+-]\d+)([+-]\d+)\s*$", text)
    if match:
        return int(match.group(1)), int(match.group(2))
    nums = re.findall(r"[+-]\d+", text)
    if len(nums) >= 2:
        return int(nums[-2]), int(nums[-1])
    if len(nums) == 1:
        return int(nums[0]), 0
    return 0, 0


class MainWindow:
    """Окно программы: скрытие = withdraw, выход только через App.request_quit."""

    def __init__(
        self,
        root: tk.Misc,
        on_close: Callable[[], None] | None = None,
        cfg=None,
        belt_store: BeltStore | None = None,
        hotspot_store=None,
        spansh_index=None,
        on_copy_system: Callable[[str], None] | None = None,
        on_copy_carrier: Callable[[str], None] | None = None,
        on_plot_to_carrier: Callable[[], None] | None = None,
        price_index=None,
        on_load_sphere_route: Callable[[list], int] | None = None,
    ) -> None:
        self.on_load_sphere_route = on_load_sphere_route
        self.on_close = on_close
        self.cfg = cfg
        self.belt_store = belt_store if belt_store is not None else BeltStore()
        self.hotspot_store = hotspot_store
        self.spansh_index = spansh_index
        self.price_index = price_index
        self.on_copy_system = on_copy_system
        self.on_copy_carrier = on_copy_carrier
        self.on_plot_to_carrier = on_plot_to_carrier
        self._carrier_system: str | None = None
        self._system_name: str | None = None
        self.win = tk.Toplevel(root)
        self.win.title(t("win.title"))
        icon.apply_icon(self.win)
        geometry = getattr(cfg, "main_geometry", None) if cfg is not None else None
        self.win.geometry(geometry or "980x520")
        self.win.minsize(720, 360)
        self.win.configure(bg=COLORS["bg"])
        self.win.protocol("WM_DELETE_WINDOW", self.hide)
        self._apply_saved_position()
        self.apply_opacity()
        self._visible = True
        self._shown_tab = "bodies"
        self._tab_address: int | None = None
        self._tab_view: str | None = None
        self._ring_icon: tk.PhotoImage | None = None
        self._ui_family = "Segoe UI"
        self._ui_size = 9
        self._state: GameState | None = None
        self._header_labels: list[tk.Label] = []
        self._route_header_labels: list[tk.Label] = []
        self._body_widths = {key: width for key, _title, width, _anchor in BODY_COLUMNS}
        self._route_widths = {key: width for key, _title, width, _anchor in ROUTE_COLUMNS}
        self._sphere_widths = dict(SPHERE_COLUMN_DEFAULTS)
        self._sphere_cursor = 0
        self._sphere_progress_sig: tuple | None = None
        self._load_column_widths()
        self._col_drag: tuple[str, int, int, int] | None = None  # table, index, start_x, start_w
        self._save_after: str | None = None
        self._style()
        self._build()
        self._last_key: tuple | None = None
        self._layout_ready = False
        # инкрементальная таблица Bodies: body_id → {cells, sig, row}
        self._body_rows: dict[int, dict] = {}
        self._bodies_order: list[int] = []
        self._bodies_address = None
        # инкрементальная + виртуализированная таблица Route: материализуем
        # только видимые строки, остальные держим разматериализованными.
        self._route_rows: dict[int, dict] = {}
        self._route_materialized: set[int] = set()
        self._route_hops_total = 0
        self._route_systems: tuple | None = None
        self._route_here: int | None = None
        self._route_col_px: list[int] = []
        self._route_hops: list = []
        self._route_jump_marks: dict = {}
        self._route_state: GameState | None = None
        self._last_route_key: tuple | None = None
        self.win.after(80, self._enable_layout_persist)
        self.win.after(1000, self._tick_carrier)
        self.win.bind("<Configure>", self._on_window_configure, add="+")

    def _style(self) -> None:
        style = ttk.Style(self.win)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("ED.TFrame", background=COLORS["bg"])
        style.configure("ED.TLabel", background=COLORS["bg"], foreground=COLORS["text"])
        style.configure(
            "ED.Header.TLabel",
            background=COLORS["bg"],
            foreground=COLORS["fg"],
            font=(self._ui_family, self._ui_size + 3, "bold"),
        )
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
            fieldbackground=COLORS["row"],
            foreground=COLORS["text"],
            borderwidth=0,
            rowheight=_row_height(self._ui_size),
            font=(self._ui_family, self._ui_size),
        )
        style.configure(
            "ED.Treeview.Heading",
            background=COLORS["panel"],
            foreground=COLORS["fg"],
            font=(self._ui_family, self._ui_size, "bold"),
        )
        style.map("ED.Treeview", background=[("selected", COLORS["sel"])], foreground=[("selected", COLORS["text"])])

    def _build(self) -> None:
        top = ttk.Frame(self.win, style="ED.TFrame", padding=(12, 10))
        top.pack(fill="x")
        self.lbl_system = ttk.Label(
            top, text=t("win.system", name="—", opened=""), style="ED.Header.TLabel", cursor="hand2"
        )
        self.lbl_system.pack(side="left")
        self.lbl_system.bind("<Double-Button-1>", self._on_system_double)
        self.lbl_status = ttk.Label(
            top,
            text="",
            style="ED.Muted.TLabel",
            font=(self._ui_family, self._ui_size),
        )
        self.lbl_status.pack(side="left", padx=(16, 0))
        # Несколько подписей: у прыжка «из A в B» каждая система копируется отдельно.
        self.frm_carrier = tk.Frame(top, bg=COLORS["bg"])
        self.frm_carrier.pack(side="left", padx=(12, 0))
        self.lbl_carrier = tk.Label(
            self.frm_carrier,
            text="",
            bg=COLORS["bg"],
            fg=COLORS["accent"],
            font=(self._ui_family, self._ui_size, "underline"),
            cursor="hand2",
            padx=4,
        )
        self.lbl_carrier.pack(side="left")
        self.lbl_carrier.bind("<Double-Button-1>", self._on_carrier_double)
        self._carrier_links: list[tk.Label] = []
        # «через 12:34 · тритий 512/1000 т» — обновляется раз в секунду
        self.lbl_carrier_info = tk.Label(
            self.frm_carrier,
            text="",
            bg=COLORS["bg"],
            fg=COLORS["warn"],
            font=(self._ui_family, self._ui_size),
            padx=4,
        )
        self.lbl_carrier_info.pack(side="left")
        self._carrier_snapshot = None
        self._carrier_jumping = False
        self.lbl_carrier_hint = ttk.Label(
            top, text="", style="ED.Muted.TLabel", font=(self._ui_family, max(7, self._ui_size - 1))
        )
        self.lbl_carrier_hint.pack(side="left", padx=(4, 0))

        nb = ttk.Notebook(self.win, style="ED.TNotebook")
        nb.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.nb = nb
        nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self.tab_route = ttk.Frame(nb, style="ED.TFrame", padding=8)
        self.tab_sphere = ttk.Frame(nb, style="ED.TFrame", padding=8)
        self.tab_bodies = ttk.Frame(nb, style="ED.TFrame", padding=8)
        self.tab_belts = ttk.Frame(nb, style="ED.TFrame", padding=8)
        self.tab_mining = ttk.Frame(nb, style="ED.TFrame", padding=0)
        nb.add(self.tab_route, text=t("win.tab_route"))
        nb.add(self.tab_sphere, text=t("win.tab_sphere"))
        nb.add(self.tab_bodies, text=t("win.tab_bodies"))
        nb.add(self.tab_belts, text=t("win.tab_belts"))
        nb.add(self.tab_mining, text=t("win.tab_mining"))
        nb.select(self.tab_bodies)

        self.route_info = ttk.Label(self.tab_route, text=t("win.route_empty"), style="ED.TLabel")
        self.route_info.pack(anchor="w", pady=(0, 6))
        self._ring_icon = _ring_icon(self.win)
        self._build_route_table()
        self._build_sphere_tab()
        self._build_bodies_table()
        self._build_belts_tab()
        self._build_mining_tab()
        self._bind_minerals_header_menu()
        self._refresh_belts_tab_title()

    def _build_mining_tab(self) -> None:
        """Вкладка «Добыча»: планетарные точки и кольца (см. edhud/miningui.py)."""
        from .miningui import MiningTab

        radius = 25.0
        if self.cfg is not None:
            radius = float(getattr(self.cfg, "mining_radius_ly", 25.0) or 25.0)
        self.mining_tab = MiningTab(
            self.tab_mining,
            colors=COLORS,
            ui_family=self._ui_family,
            ui_size=self._ui_size,
            price_index=self.price_index,
            belt_store=self.belt_store,
            hotspot_store=self.hotspot_store,
            on_target=self._set_mining_target,
            spansh_index=self.spansh_index,
            on_copy_system=self._copy_belt_system,
            on_status=self._flash_status,
            default_radius=radius,
            cfg=self.cfg,
            on_columns_changed=self._on_mining_columns_changed,
        )
        self.mining_tab.frame.pack(fill="both", expand=True)

    def _on_mining_columns_changed(self, widths: dict[str, int]) -> None:
        if self.cfg is None:
            return
        self.cfg.mining_columns = dict(widths)
        self._schedule_save()

    def _load_column_widths(self) -> None:
        if self.cfg is None:
            return
        for key, width in (getattr(self.cfg, "bodies_columns", None) or {}).items():
            if key in self._body_widths:
                self._body_widths[key] = max(self._min_col_width(key), int(width))
        for key, width in (getattr(self.cfg, "route_columns", None) or {}).items():
            if key in self._route_widths:
                self._route_widths[key] = max(self._min_col_width(key), int(width))
        for key, width in (getattr(self.cfg, "sphere_columns", None) or {}).items():
            if key in self._sphere_widths:
                self._sphere_widths[key] = max(self._min_col_width(key), int(width))

    def _enable_layout_persist(self) -> None:
        """После первой отрисовки: починить рамку и разрешить запись геометрии."""
        try:
            self.win.update_idletasks()
            winapi.detach_owner(winapi.hwnd_of(self.win))
        except Exception:
            pass
        self._layout_ready = True

    def _on_window_configure(self, event) -> None:
        if not self._layout_ready or event.widget is not self.win:
            return
        if self.win.state() != "normal":
            return
        geometry = self.win.geometry()
        if self.cfg is not None and getattr(self.cfg, "main_geometry", None) != geometry:
            self.cfg.main_geometry = geometry
            self._schedule_save()

    def _schedule_save(self) -> None:
        if self.cfg is None or not self._layout_ready:
            return
        if self._save_after is not None:
            try:
                self.win.after_cancel(self._save_after)
            except tk.TclError:
                pass
        self._save_after = self.win.after(400, lambda: self._persist_layout(write=True))

    def _persist_layout(self, write: bool = False) -> None:
        self._save_after = None
        if self.cfg is None:
            return
        self.cfg.bodies_columns = dict(self._body_widths)
        self.cfg.route_columns = dict(self._route_widths)
        self.cfg.sphere_columns = dict(self._sphere_widths)
        try:
            geom = self.win.geometry()
            self.cfg.main_geometry = geom
            x, y = _geometry_xy(geom)
            self.cfg.main_x = x
            self.cfg.main_y = y
        except tk.TclError:
            pass
        if not write:
            return
        try:
            self.cfg.save()
        except OSError:
            pass

    def _min_col_width(self, key: str) -> int:
        return max(MIN_COL_WIDTH, int(MIN_COL_WIDTHS.get(key, MIN_COL_WIDTH)))

    def _col_width(self, table: str, key: str, default: int) -> int:
        widths = self._body_widths if table == "bodies" else self._route_widths
        return max(self._min_col_width(key), int(widths.get(key, default)))

    def _table_spec(self, table: str) -> tuple[tuple, dict[str, int]]:
        if table == "bodies":
            return BODY_COLUMNS, self._body_widths
        return ROUTE_COLUMNS, self._route_widths

    def _canvas_avail(self, table: str) -> int | None:
        canvas = self._bodies_canvas if table == "bodies" else self._route_canvas
        try:
            avail = int(canvas.winfo_width())
        except tk.TclError:
            return None
        return avail if avail > 1 else None

    def _effective_widths(self, table: str) -> list[int]:
        """Ширины строго из настроек — без автодотяжки «Система» на всю ширину окна."""
        columns, widths_map = self._table_spec(table)
        return [
            max(self._min_col_width(key), int(widths_map[key]))
            for key, _title, _default, _anchor in columns
        ]

    def _apply_column_geometry(self, table: str, avail: int | None = None) -> list[int]:
        """Одинаковые пиксельные ширины у хедера и строк — иначе колонки разъезжаются."""
        del avail  # раньше сюда отдавали stretch; больше не раздуваем колонки
        widths = self._effective_widths(table)
        if table == "bodies":
            header, inner = self._bodies_header, self._bodies_inner
            clip = getattr(self, "_bodies_header_clip", None)
        else:
            header, inner = self._route_header, self._route_inner
            clip = getattr(self, "_route_header_clip", None)
        for index, width in enumerate(widths):
            header.grid_columnconfigure(index, minsize=width, weight=0, pad=0)
            inner.grid_columnconfigure(index, minsize=width, weight=0, pad=0)
        total = sum(widths)
        header.configure(width=total)
        try:
            header.place_configure(anchor="nw", width=total)
        except tk.TclError:
            pass
        for index, width in enumerate(widths):
            for box in header.grid_slaves(row=0, column=index):
                box.configure(width=width)
            for box in inner.grid_slaves(column=index):
                try:
                    box.configure(width=width)
                except tk.TclError:
                    pass
        if clip is not None:
            clip.configure(height=_row_height(self._ui_size) + 10)
        return widths

    def _set_col_width(self, table: str, index: int, width: int) -> None:
        columns, widths_map = self._table_spec(table)
        key = columns[index][0]
        widths_map[key] = max(self._min_col_width(key), int(width))
        canvas = self._bodies_canvas if table == "bodies" else self._route_canvas
        widths = self._apply_column_geometry(table)
        total = sum(widths)
        window = getattr(self, f"_{table}_window", None)
        if window is not None:
            canvas.itemconfigure(window, width=max(total, self._canvas_avail(table) or total))
        canvas.configure(scrollregion=canvas.bbox("all") or (0, 0, total, 0))
        self._sync_header_x(table)

    def _bind_col_resize(self, widget: tk.Misc, table: str, index: int) -> None:
        columns, _widths_map = self._table_spec(table)

        def on_motion(event) -> None:
            if self._col_drag is not None:
                return
            near = event.widget.winfo_width() - event.x <= RESIZE_EDGE
            event.widget.configure(cursor="sb_h_double_arrow" if near else "")

        def on_leave(_event) -> None:
            if self._col_drag is None:
                widget.configure(cursor="")

        def on_press(event) -> None:
            if event.widget.winfo_width() - event.x > RESIZE_EDGE:
                return
            key = columns[index][0]
            start_w = self._col_width(table, key, columns[index][2])
            self._col_drag = (table, index, event.x_root, start_w)
            widget.configure(cursor="sb_h_double_arrow")
            widget.grab_set()

        def on_drag(event) -> None:
            if self._col_drag is None:
                return
            drag_table, drag_index, start_x, start_w = self._col_drag
            if drag_table != table or drag_index != index:
                return
            self._set_col_width(table, index, start_w + (event.x_root - start_x))

        def on_release(_event) -> None:
            if self._col_drag is None:
                return
            self._col_drag = None
            try:
                widget.grab_release()
            except tk.TclError:
                pass
            widget.configure(cursor="")
            self._schedule_save()

        widget.bind("<Motion>", on_motion, add="+")
        widget.bind("<Leave>", on_leave, add="+")
        widget.bind("<ButtonPress-1>", on_press, add="+")
        widget.bind("<B1-Motion>", on_drag, add="+")
        widget.bind("<ButtonRelease-1>", on_release, add="+")

    def _make_box(
        self,
        parent: tk.Misc,
        width: int,
        height: int,
        bg: str,
        *,
        header: bool = False,
    ) -> tk.Frame:
        box = tk.Frame(parent, width=width, height=height, bg=bg)
        box.grid_propagate(False)
        box.pack_propagate(False)
        _paint_grid(box, bg)
        if header:
            box.configure(bg=COLORS["panel"])
            _paint_grid(box, COLORS["panel"])
        return box

    def _build_scroll_table(
        self,
        parent: tk.Misc,
        columns: tuple,
        widths: dict[str, int],
        header_attr: str,
        labels_attr: str,
        canvas_attr: str,
        inner_attr: str,
        gutter_attr: str,
        host_attr: str,
        table: str,
    ) -> None:
        host = tk.Frame(parent, bg=COLORS["bg"])
        host.pack(fill="both", expand=True)
        setattr(self, host_attr, host)
        host.grid_columnconfigure(0, weight=1)
        host.grid_rowconfigure(1, weight=1)

        clip = tk.Frame(host, bg=COLORS["panel"], height=_row_height(self._ui_size) + 10)
        clip.grid(row=0, column=0, sticky="ew")
        clip.grid_propagate(False)
        setattr(self, f"_{table}_header_clip", clip)

        header = tk.Frame(clip, bg=COLORS["panel"])
        setattr(self, header_attr, header)

        pixel_widths = [
            max(self._min_col_width(key), int(widths.get(key, default)))
            for key, _t, default, _a in columns
        ]
        labels: list[tk.Label] = []
        head_h = _row_height(self._ui_size) + 8
        for index, (key, title, _default_w, anchor) in enumerate(columns):
            width = pixel_widths[index]
            header.grid_columnconfigure(index, minsize=width, weight=0, pad=0)
            box = self._make_box(header, width, head_h, COLORS["panel"], header=True)
            label = tk.Label(
                box,
                text=title,
                bg=COLORS["panel"],
                fg=COLORS["fg"],
                anchor=anchor,
                font=(self._ui_family, self._ui_size, "bold"),
                padx=4,
                pady=2,
            )
            label.pack(fill="both", expand=True)
            box.grid(row=0, column=index, sticky="nsew")
            self._bind_col_resize(box, table, index)
            self._bind_col_resize(label, table, index)
            labels.append(label)
        setattr(self, labels_attr, labels)
        header.configure(width=sum(pixel_widths))
        # anchor=nw: у place по умолчанию center, и шапка съезжает на полширины относительно строк
        header.place(x=0, y=0, anchor="nw", relheight=1, width=sum(pixel_widths))

        canvas = tk.Canvas(host, bg=COLORS["row"], highlightthickness=0, bd=0)
        scroll = ttk.Scrollbar(host, orient="vertical", command=canvas.yview)
        xscroll = ttk.Scrollbar(host, orient="horizontal", command=lambda *a: self._xview(table, *a))
        if table == "route":
            # при прокрутке виртуализированной таблицы дозаполняем видимые строки
            canvas.configure(
                yscrollcommand=lambda *a: (scroll.set(*a), self._route_materialize())
            )
        else:
            canvas.configure(yscrollcommand=scroll.set)
        canvas.configure(xscrollcommand=xscroll.set)
        canvas.grid(row=1, column=0, sticky="nsew")
        scroll.grid(row=1, column=1, sticky="ns")
        xscroll.grid(row=2, column=0, sticky="ew")
        gutter = tk.Frame(host, width=16, bg=COLORS["bg"])
        gutter.grid(row=0, column=1)
        setattr(self, gutter_attr, gutter)

        inner = tk.Frame(canvas, bg=COLORS["row"])
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        setattr(self, f"_{table}_window", window)
        for index, width in enumerate(pixel_widths):
            inner.grid_columnconfigure(index, minsize=width, weight=0, pad=0)

        def _fit(event) -> None:
            widths_now = self._apply_column_geometry(table)
            total = sum(widths_now)
            # шире окна — пустое место справа, колонки не раздуваем
            canvas.itemconfigure(window, width=max(total, int(event.width) or total))
            header.configure(width=total)
            self._sync_header_x(table)
            if table == "route":
                self._route_materialize()

        def _scrollregion(_event) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))
            self._sync_header_x(table)

        def _wheel(event) -> None:
            canvas.yview_scroll(int(-event.delta / 120), "units")

        canvas.bind("<Configure>", _fit)
        inner.bind("<Configure>", _scrollregion)
        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _wheel))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))
        setattr(self, canvas_attr, canvas)
        setattr(self, inner_attr, inner)

    def _xview(self, table: str, *args) -> None:
        canvas = self._bodies_canvas if table == "bodies" else self._route_canvas
        canvas.xview(*args)
        self._sync_header_x(table)

    def _sync_header_x(self, table: str) -> None:
        canvas = self._bodies_canvas if table == "bodies" else self._route_canvas
        header = self._bodies_header if table == "bodies" else self._route_header
        try:
            header.place_configure(x=-int(canvas.canvasx(0)), y=0, anchor="nw")
        except tk.TclError:
            pass

    def _build_belts_tab(self) -> None:
        """Список сохранённых поясов с минералами."""
        self.belts_info = ttk.Label(
            self.tab_belts,
            text=t("win.belts_hint"),
            style="ED.Muted.TLabel",
        )
        self.belts_info.pack(anchor="w", pady=(0, 6))
        host = tk.Frame(self.tab_belts, bg=COLORS["bg"])
        host.pack(fill="both", expand=True)
        host.grid_columnconfigure(0, weight=1)
        host.grid_rowconfigure(0, weight=1)
        canvas = tk.Canvas(host, bg=COLORS["row"], highlightthickness=0, bd=0)
        scroll = ttk.Scrollbar(host, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        inner = tk.Frame(canvas, bg=COLORS["row"])
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        self._belts_canvas = canvas
        self._belts_inner = inner
        self._belts_window = window

        def _fit(event) -> None:
            canvas.itemconfigure(window, width=int(event.width) or 1)

        def _region(_event) -> None:
            canvas.configure(scrollregion=canvas.bbox("all") or (0, 0, 0, 0))

        def _wheel(event) -> None:
            canvas.yview_scroll(int(-event.delta / 120), "units")

        canvas.bind("<Configure>", _fit)
        inner.bind("<Configure>", _region)
        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _wheel))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))
        self._refresh_belts_list()

    def _refresh_belts_tab_title(self) -> None:
        count = len(self.belt_store)
        try:
            self.nb.tab(self.tab_belts, text=t("win.tab_belts_n", n=count) if count else t("win.tab_belts"))
        except tk.TclError:
            pass

    def _refresh_belts_list(self) -> None:
        if not hasattr(self, "_belts_inner"):
            return
        for child in self._belts_inner.winfo_children():
            child.destroy()
        belts = self.belt_store.list()
        if not belts:
            tk.Label(
                self._belts_inner,
                text=t("win.belts_empty"),
                bg=COLORS["row"],
                fg=COLORS["muted"],
                anchor="w",
                font=(self._ui_family, self._ui_size),
                padx=8,
                pady=10,
            ).pack(fill="x")
            self._refresh_belts_tab_title()
            return
        for belt in belts:
            self._add_belt_row(belt)
        self._refresh_belts_tab_title()

    def _add_belt_row(self, belt: SavedBelt) -> None:
        row = tk.Frame(self._belts_inner, bg=COLORS["row"])
        row.pack(fill="x", pady=1)
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(belt.saved_at)) if belt.saved_at else "—"
        estimate = values.credits(belt.estimate_cr())
        body_short = (belt.body_name or "").split()[-1] if belt.body_name else f"#{belt.body_id}"
        title = f"{belt.system} · {body_short}"
        if belt.planet_class:
            title += f" · {belt.planet_class}"
        left = tk.Label(
            row,
            text=title,
            bg=COLORS["row"],
            fg=COLORS["fg"],
            anchor="w",
            font=(self._ui_family, self._ui_size, "bold"),
            padx=8,
            cursor="hand2",
        )
        left.pack(fill="x", pady=(2, 0))
        minerals = tk.Label(
            row,
            text=t("win.belt_meta", minerals=belt.minerals_label(), estimate=estimate, when=when),
            bg=COLORS["row"],
            fg=COLORS["accent"],
            anchor="w",
            font=(self._ui_family, self._ui_size),
            padx=8,
            cursor="hand2",
        )
        minerals.pack(fill="x", pady=(0, 6))
        tip = format_hotspots_tip(belt.hotspots) or ""
        tip = (tip + "\n\n" + t("win.belt_copy_tip")).strip()
        for widget in (row, left, minerals):
            cell_tip = _CellTip(row, widget, text=tip)
            widget.tip = cell_tip
            widget.bind("<Double-Button-1>", lambda _e, name=belt.system: self._copy_belt_system(name), add="+")
            widget.bind("<Button-3>", lambda e, key=belt.key(): self._popup_belt_row_menu(e, key), add="+")

    def _copy_belt_system(self, name: str) -> None:
        if not name:
            return
        if self.on_copy_system:
            self.on_copy_system(name)
        else:
            self._copy_text(name)

    def _popup_belt_row_menu(self, event, key: str) -> None:
        menu = tk.Menu(self.win, tearoff=0)
        belt = next((b for b in self.belt_store.list() if b.key() == key), None)
        if belt is not None:
            menu.add_command(label=t("win.copy_system"), command=lambda: self._copy_belt_system(belt.system))
        menu.add_command(label=t("win.delete_belt"), command=lambda: self._delete_saved_belt(key))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _delete_saved_belt(self, key: str) -> None:
        if self.belt_store.remove(key):
            self._refresh_belts_list()
            self._flash_status(t("win.belt_deleted"))
            if self._state is not None:
                self._last_key = None
                self._update_bodies(self._state)

    def _bind_minerals_header_menu(self) -> None:
        for index, (key, _title, _w, _a) in enumerate(BODY_COLUMNS):
            if key != "minerals":
                continue
            if index >= len(self._header_labels):
                return
            label = self._header_labels[index]
            box = label.master
            for widget in (label, box):
                widget.bind("<Button-3>", self._popup_minerals_header_menu, add="+")
            return

    def _popup_minerals_header_menu(self, event) -> None:
        menu = tk.Menu(self.win, tearoff=0)
        menu.add_command(label=t("win.save_all"), command=self._save_all_system_belts)
        menu.add_command(label=t("win.open_belts"), command=self._show_belts_tab)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _show_belts_tab(self) -> None:
        try:
            self.nb.select(self.tab_belts)
        except tk.TclError:
            return
        self._shown_tab = "belts"
        self._refresh_belts_list()

    def _flash_status(self, text: str) -> None:
        if getattr(self, "lbl_status", None) is None:
            return
        prev = self.lbl_status.cget("text")
        self.lbl_status.configure(text=text)
        self.win.after(3500, lambda: self._restore_status(prev, text))

    def _restore_status(self, prev: str, expected: str) -> None:
        if getattr(self, "lbl_status", None) is None:
            return
        try:
            if self.lbl_status.cget("text") == expected:
                self.lbl_status.configure(text=prev)
        except tk.TclError:
            pass

    def _body_to_saved_belt(self, body: Body, state: GameState) -> SavedBelt | None:
        if not body.hotspots:
            return None
        pos = state.system.star_pos
        star_pos = [float(pos[0]), float(pos[1]), float(pos[2])] if pos and len(pos) == 3 else None
        return SavedBelt(
            system=state.system.name or "",
            address=int(state.system.address) if state.system.address is not None else None,
            body_id=int(body.body_id),
            body_name=body.name or f"Body {body.body_id}",
            hotspots={str(k): int(v or 0) for k, v in body.hotspots.items()},
            planet_class=body.planet_class,
            star_pos=star_pos,
            saved_at=time.time(),
            rings_mapped=bool(getattr(body, "rings_mapped", False) or body.has_rings),
        )

    def _save_body_belt(self, body_id: int) -> None:
        state = self._state
        if state is None:
            return
        body = state.system.body(body_id)
        if body is None or not body.hotspots:
            self._flash_status(t("win.no_minerals"))
            return
        belt = self._body_to_saved_belt(body, state)
        if belt is None or not belt.system:
            self._flash_status(t("win.belt_save_fail"))
            return
        self.belt_store.upsert(belt)
        self._refresh_belts_list()
        self._flash_status(
            t("win.belt_saved", system=belt.system, body=(belt.body_name or "").split()[-1])
        )
        self._last_key = None
        self._update_bodies(state)

    def _save_all_system_belts(self) -> None:
        state = self._state
        if state is None:
            return
        saved = 0
        for body in state.system.bodies.values():
            if is_ring_body(body.name) or not body.hotspots:
                continue
            belt = self._body_to_saved_belt(body, state)
            if belt is None or not belt.system:
                continue
            self.belt_store.upsert(belt)
            saved += 1
        self._refresh_belts_list()
        if saved:
            self._flash_status(t("win.belts_saved", n=saved))
            self._last_key = None
            self._update_bodies(state)
        else:
            self._flash_status(t("win.no_belts"))

    def _popup_minerals_cell_menu(self, event, body_id: int) -> None:
        state = self._state
        body = state.system.body(body_id) if state is not None else None
        menu = tk.Menu(self.win, tearoff=0)
        if body is not None and body.hotspots:
            already = self.belt_store.contains(
                state.system.address if state else None,
                body_id,
                state.system.name if state else "",
            )
            label = t("win.update_belt") if already else t("win.save_belt")
            menu.add_command(label=label, command=lambda: self._save_body_belt(body_id))
            if already:
                saved = self.belt_store.get(
                    state.system.address if state else None,
                    body_id,
                    state.system.name if state else "",
                )
                if saved is not None:
                    menu.add_command(
                        label=t("win.delete_belt"),
                        command=lambda k=saved.key(): self._delete_saved_belt(k),
                    )
        else:
            menu.add_command(label=t("win.no_belt_minerals"), state="disabled")
        menu.add_separator()
        menu.add_command(label=t("win.open_belts"), command=self._show_belts_tab)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _bind_minerals_cell(self, box: tk.Misc, label: tk.Misc, body_id: int) -> None:
        for widget in (box, label):
            widget._belt_body_id = body_id  # type: ignore[attr-defined]

            def _menu(event, bid=body_id) -> None:
                self._popup_minerals_cell_menu(event, bid)

            widget.bind("<Button-3>", _menu, add="+")

    def _build_bodies_table(self) -> None:
        """Таблица тел на метках: Treeview не умеет красить отдельные ячейки."""
        self._build_scroll_table(
            self.tab_bodies,
            BODY_COLUMNS,
            self._body_widths,
            "_bodies_header",
            "_header_labels",
            "_bodies_canvas",
            "_bodies_inner",
            "_bodies_gutter",
            "_bodies_host",
            "bodies",
        )

    def _build_route_table(self) -> None:
        self._build_scroll_table(
            self.tab_route,
            ROUTE_COLUMNS,
            self._route_widths,
            "_route_header",
            "_route_header_labels",
            "_route_canvas",
            "_route_inner",
            "_route_gutter",
            "_route_host",
            "route",
        )

    def _put_cell(
        self,
        table: str,
        row: int,
        col: int,
        width: int,
        *,
        text: str = "",
        image=None,
        fg: str | None = None,
        bg: str | None = None,
        anchor: str = "w",
        font=None,
        tip: str | None = None,
        copy_text: str | None = None,
    ):
        parent = self._bodies_inner if table == "bodies" else self._route_inner
        bg = bg or COLORS["row"]
        fg = fg or COLORS["text"]
        height = _row_height(self._ui_size)
        box = self._make_box(parent, width, height, bg)
        label = tk.Label(
            box,
            text=text,
            image=image,
            bg=bg,
            fg=fg,
            anchor=anchor,
            font=font or (self._ui_family, self._ui_size),
            padx=4,
            pady=1,
            cursor="hand2" if copy_text else "",
        )
        if image is not None:
            label.image = image
        label.pack(fill="both", expand=True)
        if tip:
            cell_tip = _CellTip(box, label, text=tip)
            label.tip = cell_tip
            box.tip = cell_tip
        if copy_text:
            tip_text = tip or t("tip.copy", name=copy_text)
            if not tip:
                cell_tip = _CellTip(box, label, text=tip_text)
                label.tip = cell_tip
                box.tip = cell_tip

            def _copy(_event=None, name=copy_text) -> None:
                if self.on_copy_system:
                    self.on_copy_system(name)
                else:
                    self._copy_text(name)

            label.bind("<Double-Button-1>", _copy, add="+")
            box.bind("<Double-Button-1>", _copy, add="+")
            box.configure(cursor="hand2")
        box.grid(row=row, column=col, sticky="nsew")
        return label

    def apply_opacity(self) -> None:
        if self.cfg is None:
            return
        try:
            alpha = max(0.25, min(1.0, float(getattr(self.cfg, "main_opacity", 1.0))))
            self.win.attributes("-alpha", alpha)
        except Exception:
            pass

    def _apply_saved_position(self) -> None:
        if self.cfg is None:
            return
        x = getattr(self.cfg, "main_x", None)
        y = getattr(self.cfg, "main_y", None)
        if x is None and y is None:
            return
        self.win.update_idletasks()
        geom = self.win.geometry()
        size = geom.split("+", 1)[0].split("-", 1)[0]
        cx, cy = _geometry_xy(geom)
        nx = int(x) if x is not None else cx
        ny = int(y) if y is not None else cy
        self.win.geometry(f"{size}+{nx}+{ny}")

    def move_to(self, x: int | None = None, y: int | None = None) -> None:
        self.win.update_idletasks()
        screen_w = self.win.winfo_screenwidth()
        screen_h = self.win.winfo_screenheight()
        w = max(1, self.win.winfo_width())
        h = max(1, self.win.winfo_height())
        cx, cy = _geometry_xy(self.win.geometry())
        nx = cx if x is None else max(0, min(int(x), max(0, screen_w - 120)))
        ny = cy if y is None else max(0, min(int(y), max(0, screen_h - 80)))
        self.win.geometry(f"{w}x{h}+{nx}+{ny}")
        if self.cfg is not None:
            self.cfg.main_x = nx
            self.cfg.main_y = ny
            self.cfg.main_geometry = self.win.geometry()

    def nudge(self, dx: int = 0, dy: int = 0) -> None:
        cx, cy = _geometry_xy(self.win.geometry())
        self.move_to(cx + int(dx), cy + int(dy))

    def current_xy(self) -> tuple[int, int]:
        return _geometry_xy(self.win.geometry())

    # ----------------------------------------------------------------- show
    def show(self) -> None:
        self._visible = True
        self.win.deiconify()
        self.win.lift()
        try:
            self.win.focus_force()
        except tk.TclError:
            pass
        self.win.after(30, self._enable_layout_persist)

    def hide(self) -> None:
        self._persist_layout(write=False)
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
            self._persist_layout(write=False)
        except Exception:
            pass
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    # --------------------------------------------------------------- update
    def apply_look(self, cfg) -> None:
        """Шрифт и палитра окна из настроек. Цвета таблицы живут в COLORS."""
        from .config import DARK_COLORS

        global BODY_COLUMNS, ROUTE_COLUMNS
        BODY_COLUMNS = _columns(_BODY_SPEC)
        ROUTE_COLUMNS = _columns(_ROUTE_SPEC)
        self.cfg = cfg
        for key in list(COLORS):
            if key == "grid":
                continue
            COLORS[key] = cfg.colors.get(key) or DARK_COLORS.get(key, COLORS[key])
        COLORS["grid"] = cfg.colors.get("grid") or "#3a3a3a"
        self._ui_family = cfg.ui_font_family or "Segoe UI"
        self._ui_size = max(8, min(24, int(cfg.ui_font_size or 9)))
        self._load_column_widths()
        for index, (key, _title, default_w, _anchor) in enumerate(BODY_COLUMNS):
            self._set_col_width("bodies", index, self._col_width("bodies", key, default_w))
        for index, (key, _title, default_w, _anchor) in enumerate(ROUTE_COLUMNS):
            self._set_col_width("route", index, self._col_width("route", key, default_w))
        self._style()
        self._paint_chrome()
        self._refresh_column_titles()
        self._refresh_tab_titles()
        self._refresh_sphere_headings()
        self._refresh_static_i18n()
        self.apply_opacity()
        self._apply_saved_position()
        self._last_key = None
        self._last_route_key = None
        self._clear_body_rows()
        if getattr(self, "mining_tab", None) is not None:
            self.mining_tab.refresh_i18n(self.cfg)
        if self._state is not None:
            self.update_state(self._state)
        else:
            try:
                self.route_info.configure(text=t("win.route_empty"))
            except tk.TclError:
                pass

    def _refresh_column_titles(self) -> None:
        """Переписать тексты шапок Bodies/Route после смены языка."""
        for labels_attr, columns in (
            ("_header_labels", BODY_COLUMNS),
            ("_route_header_labels", ROUTE_COLUMNS),
        ):
            labels = getattr(self, labels_attr, None)
            if not labels:
                continue
            for label, (_key, title, _w, _a) in zip(labels, columns):
                try:
                    label.configure(text=title)
                except tk.TclError:
                    pass

    def _refresh_static_i18n(self) -> None:
        """Подписи вкладок, которые не пересоздаются на каждый тик."""
        for widget, key in (
            (getattr(self, "belts_info", None), "win.belts_hint"),
        ):
            if widget is None:
                continue
            try:
                widget.configure(text=t(key))
            except tk.TclError:
                pass
        if getattr(self, "_belts_inner", None) is not None:
            self._refresh_belts_list()

    def _refresh_tab_titles(self) -> None:
        if not hasattr(self, "nb"):
            return
        try:
            self.nb.tab(self.tab_route, text=t("win.tab_route"))
            self.nb.tab(self.tab_sphere, text=t("win.tab_sphere"))
            self.nb.tab(self.tab_bodies, text=t("win.tab_bodies"))
            count = len(self.belt_store) if self.belt_store is not None else 0
            self.nb.tab(
                self.tab_belts,
                text=t("win.tab_belts_n", n=count) if count else t("win.tab_belts"),
            )
            self.nb.tab(self.tab_mining, text=t("win.tab_mining"))
        except tk.TclError:
            pass

    def _refresh_sphere_headings(self) -> None:
        tree = getattr(self, "sphere_tree", None)
        if tree is None:
            return
        headings = {
            "idx": (t("sphere.col_idx"), "center"),
            "system": (t("sphere.col_system"), "w"),
            "star": (t("sphere.col_star"), "center"),
            "leg": (t("sphere.col_leg"), "e"),
            "center": (t("sphere.col_center"), "e"),
        }
        try:
            for key, (title, anchor) in headings.items():
                tree.heading(key, text=title, anchor=anchor)
        except tk.TclError:
            pass
        for widget, key in (
            (getattr(self, "sphere_system_lbl", None), "sphere.system"),
            (getattr(self, "sphere_distance_lbl", None), "sphere.distance"),
            (getattr(self, "sphere_calc", None), "sphere.calc"),
            (getattr(self, "sphere_load", None), "sphere.load"),
            (getattr(self, "sphere_status", None), "sphere.hint"),
        ):
            if widget is None:
                continue
            try:
                widget.configure(text=t(key))
            except tk.TclError:
                pass
        tip = getattr(self, "_sphere_load_tip", None)
        if tip is not None:
            tip.text = t("sphere.load_tip")

    def _paint_chrome(self) -> None:
        font = (self._ui_family, self._ui_size, "bold")
        self.win.configure(bg=COLORS["bg"])
        for table, host_name, header_name, canvas_name, inner_name, gutter_name, labels in (
            (
                "bodies",
                "_bodies_host",
                "_bodies_header",
                "_bodies_canvas",
                "_bodies_inner",
                "_bodies_gutter",
                self._header_labels,
            ),
            (
                "route",
                "_route_host",
                "_route_header",
                "_route_canvas",
                "_route_inner",
                "_route_gutter",
                self._route_header_labels,
            ),
        ):
            host = getattr(self, host_name, None)
            if host is None:
                continue
            host.configure(bg=COLORS["bg"])
            getattr(self, header_name).configure(bg=COLORS["panel"])
            getattr(self, canvas_name).configure(bg=COLORS["row"])
            getattr(self, inner_name).configure(bg=COLORS["row"])
            getattr(self, gutter_name).configure(bg=COLORS["bg"])
            clip = getattr(self, f"_{table}_header_clip", None)
            if clip is not None:
                clip.configure(bg=COLORS["panel"], height=_row_height(self._ui_size) + 10)
            for label in labels:
                label.configure(bg=COLORS["panel"], fg=COLORS["fg"], font=font)
                parent = label.master
                if isinstance(parent, tk.Frame):
                    parent.configure(bg=COLORS["panel"], height=_row_height(self._ui_size) + 8)
                    _paint_grid(parent, COLORS["panel"])
            self._apply_column_geometry(table)
        if getattr(self, "frm_carrier", None) is not None:
            self.frm_carrier.configure(bg=COLORS["bg"])
            for child in self.frm_carrier.winfo_children():
                if isinstance(child, tk.Label):
                    child.configure(bg=COLORS["bg"])
        if getattr(self, "lbl_carrier_hint", None) is not None:
            self.lbl_carrier_hint.configure(font=(self._ui_family, max(7, self._ui_size - 1)))
        self._paint_sphere()

    def update_state(self, state: GameState) -> None:
        self._state = state
        self._apply_tab(state)
        if getattr(self, "mining_tab", None) is not None:
            self.mining_tab.set_state(state)
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
        route_key = self._route_key(state)
        if route_key != self._last_route_key:
            self._last_route_key = route_key
            self._update_route(state)
        self._update_bodies(state)
        self._sync_sphere_progress(state)

    def _route_key(self, state: GameState) -> tuple:
        route = tuple(
            (
                h.system,
                h.star_class,
                h.discovered_by,
                h.discovered_by_me,
                h.edsm_stars,
                h.edsm_planets,
                h.edsm_bodies,
                h.edsm_missing,
            )
            for h in state.route.hops
        )
        return (
            route,
            state.route.locked,
            state.system.name,
            state.system.address,
            state.fsd_target,
            state.jump_dest,
        )

    def _snapshot_key(self, state: GameState) -> tuple:
        sys = state.system
        bodies = tuple(
            (
                b.body_id,
                b.bio_signals,
                b.geo_signals,
                b.mining_locations,
                tuple(sorted((k, int(v)) for k, v in (b.hotspots or {}).items())),
                b.dss_scanned,
                getattr(b, "rings_mapped", False),
                b.was_discovered,
                b.has_rings,
                b.landable,
                b.planet_class,
                bool(b.materials),
                bool(b.genuses),
                b.source,
                round(b.distance_ls or 0, 1),
            )
            for b in sorted(sys.bodies.values(), key=lambda x: x.body_id)
        )
        route = tuple(
            (
                h.system,
                h.star_class,
                h.discovered_by,
                h.discovered_by_me,
                h.edsm_stars,
                h.edsm_planets,
                h.edsm_bodies,
                h.edsm_missing,
            )
            for h in state.route.hops
        )
        dist = state.carrier_distance_ly()
        names = tuple(
            (b.body_id, b.name)
            for b in sorted(sys.bodies.values(), key=lambda x: x.body_id)
        )
        return (
            sys.address,
            sys.name,
            sys.body_count,
            sys.nonbody_count,
            sys.fss_progress,
            sys.discovered_by_me,
            bodies,
            names,
            route,
            state.route.locked,
            state.carrier.callsign,
            state.carrier.name,
            state.carrier.system,
            state.carrier.address,
            state.carrier.jump_from_system,
            state.carrier.jump_dest_system,
            state.carrier.jump_departure,
            state.fsd_target,
            state.jump_dest,
            bool(state.jumping_away),
            None if dist is None else round(dist, 1),
            state.view_tab,
            bool(getattr(self.cfg, "show_belt_clusters", True)) if self.cfg is not None else True,
        )

    def _on_tab_changed(self, _event=None) -> None:
        """Ручной клик синхронизирует state — иначе автопереключение «залипает» на старой вкладке."""
        try:
            current = self.nb.select()
        except tk.TclError:
            return
        if current == str(self.tab_route):
            self._shown_tab = "route"
            self._tab_view = "route"
            if self._state is not None:
                self._state.view_tab = "route"
            return
        if current == str(self.tab_bodies):
            self._shown_tab = "bodies"
            self._tab_view = "bodies"
            if self._state is not None:
                self._state.view_tab = "bodies"
                self._update_header(self._state)
                self._update_bodies(self._state)
            return
        if current == str(self.tab_belts):
            self._shown_tab = "belts"
            self._refresh_belts_list()
            return
        if current == str(self.tab_sphere):
            self._shown_tab = "sphere"
            if self._state is not None:
                self._sync_sphere_progress(self._state, force=True)
            return
        if current == str(self.tab_mining):
            self._shown_tab = "mining"
            if self._state is not None:
                self.mining_tab.set_state(self._state)
            self.mining_tab.on_show()

    def _set_mining_target(self, name: str) -> None:
        """Целевой минерал выбран в «Добыче» — запоминаем и отдаём счётчикам."""
        target = (name or "").strip()
        if self.cfg is not None:
            self.cfg.mining_target = target
        if getattr(self, "_state", None) is not None:
            self._state.mining.target = target

    def set_spansh_index(self, index) -> None:
        """Включили/выключили базу Spansh в настройках — переключаем поиск на лету."""
        self.spansh_index = index
        tab = getattr(self, "mining_tab", None)
        if tab is not None:
            tab.spansh_index = index

    def _sticky_manual_tab(self) -> str | None:
        """Ручные вкладки, которые авто Route/Bodies не отбирает в той же системе."""
        if self._shown_tab in ("mining", "belts", "sphere"):
            return self._shown_tab
        try:
            current = self.nb.select()
        except tk.TclError:
            return None
        mapping = (
            (getattr(self, "tab_sphere", None), "sphere"),
            (getattr(self, "tab_mining", None), "mining"),
            (getattr(self, "tab_belts", None), "belts"),
        )
        for frame, name in mapping:
            if frame is not None and current == str(frame):
                self._shown_tab = name
                return name
        return None

    def _apply_tab(self, state: GameState) -> None:
        """Автопереключение Route/Bodies: срабатывает на смену системы и на смену маршрута.

        Ручной выбор вкладки (Добыча / Пояса / Sphere Route) живёт до прибытия
        в новую систему — зарядка и туннель гиперпрыжка её не отбирают.
        После FSDJump/Location окно снова следует за view_tab (обычно Bodies).
        """
        tab = state.view_tab if state.view_tab in ("route", "bodies") else "bodies"
        address = state.system.address
        sticky = self._sticky_manual_tab()
        if address == self._tab_address and tab == self._tab_view:
            return
        # та же система + ручная вкладка — не уводить на Route при старте прыжка
        if address == self._tab_address and sticky is not None:
            self._tab_view = tab
            return
        # во время прыжка Sphere Route не трогаем даже если адрес ещё не сменился в UI
        if sticky == "sphere" and state.jumping_away:
            self._tab_view = tab
            return
        self._tab_address = address
        self._tab_view = tab
        self._shown_tab = tab
        try:
            self.nb.select(self.tab_route if tab == "route" else self.tab_bodies)
        except tk.TclError:
            return

    def _update_header(self, state: GameState) -> None:
        name = state.system.name or "—"
        self._system_name = state.system.name
        # как FSS BodyCount: без Belt Cluster и колец (иначе бывает 13/12)
        known = state.system.fss_known_count()
        total = state.system.body_count or known
        bio = sum(
            1
            for b in state.system.bodies.values()
            if (b.bio_signals or 0) > 0
            and not is_belt_body(b.name)
            and not is_ring_body(b.name)
        )
        opened = t("win.opened") if state.system.discovered_by_me else ""
        if not opened and state.system.name:
            who = state.discoverer_of(state.system.name)
            if who and who.lower() != (self.cfg.edsm_commander or state.cmdr or "").lower():
                opened = t("win.discovered_by", name=who)
        self.lbl_system.configure(text=t("win.system", name=name, opened=opened))
        self.lbl_status.configure(
            text=t("win.status", known=known, total=total, bio=bio)
            + (t("win.locked") if state.route.locked else "")
        )
        self._carrier_system = state.carrier.system if state.carrier.known else None
        if not state.carrier.known:
            self._clear_carrier_links()
            self.lbl_carrier.configure(text="")
            self.lbl_carrier_hint.configure(text="")
            self._carrier_snapshot = None
            self.lbl_carrier_info.configure(text="")
            return
        from .hudmodel import _carrier_who

        who = _carrier_who(state.carrier)
        if state.carrier.jump_pending and state.carrier.jump_dest_system:
            frm = state.carrier.jump_from_system or self._carrier_system or "—"
            to = state.carrier.jump_dest_system
            self._show_carrier_jump(frm, to)
            self.lbl_carrier_hint.configure(text="")
            self._carrier_snapshot = state.carrier
            self._refresh_carrier_info()
            return
        self._clear_carrier_links()
        self._carrier_jumping = False
        self.lbl_carrier.configure(cursor="hand2", font=(self._ui_family, self._ui_size, "underline"))
        self._carrier_info_last()
        if self._carrier_system:
            # Всегда явно «Карриер …», иначе в шапке неочевидно, что за система
            generic = t("hud.carrier")
            prefix = generic if who.lower() == generic.lower() else f"{generic} {who}"
            dist = state.carrier_distance_ly()
            if dist is None:
                text = t("win.carrier_line", prefix=prefix, system=self._carrier_system)
            elif dist < 0.05:
                text = t("win.carrier_here", prefix=prefix, system=self._carrier_system)
            else:
                ly = f"{dist:,.0f}".replace(",", " ")
                key = "win.carrier_dist_approx" if state.carrier_distance_is_approx() else "win.carrier_dist"
                text = t(key, prefix=prefix, system=self._carrier_system, ly=ly)
            self.lbl_carrier.configure(text=text, fg=COLORS["accent"], bg=COLORS["bg"])
            self.lbl_carrier_hint.configure(text="")
            self._carrier_snapshot = state.carrier
            self._refresh_carrier_info()
        else:
            self.lbl_carrier.configure(text="")
            self.lbl_carrier_hint.configure(text="")
            self._carrier_snapshot = state.carrier if state.carrier.known else None
            self._refresh_carrier_info()

    def _refresh_carrier_info(self) -> None:
        """Остаток до прыжка и тритий — отдельной подписью, тикает раз в секунду."""
        carrier = self._carrier_snapshot
        if carrier is None:
            self.lbl_carrier_info.configure(text="")
            return
        parts: list[str] = []
        left = carrier.jump_remaining()
        jumping = bool(getattr(self, "_carrier_jumping", False))
        if left is not None:
            parts.append(
                t("win.carrier_jump_start", time=_fmt_clock(left))
                if jumping
                else t("win.carrier_countdown", time=_fmt_clock(left))
            )
        if carrier.fuel_level is not None:
            level = f"{carrier.fuel_level:,.0f}".replace(",", " ")
            if carrier.fuel_capacity:
                cap = f"{carrier.fuel_capacity:,.0f}".replace(",", " ")
                parts.append(
                    t("win.carrier_jump_fuel_cap", level=level, cap=cap)
                    if jumping
                    else t("win.carrier_fuel", level=level, cap=cap)
                )
            else:
                parts.append(
                    t("win.carrier_jump_fuel", fuel=level)
                    if jumping
                    else t("win.carrier_fuel_nocap", level=level)
                )
        self.lbl_carrier_info.configure(
            # при прыжке каждая часть уже начинается с запятой — клеим подряд
            text=("".join(parts) if jumping else " · ".join(parts)) if parts else "",
            fg=COLORS["warn"] if left is not None else COLORS["muted"],
        )

    def _tick_carrier(self) -> None:
        try:
            if self._carrier_snapshot is not None:
                self._refresh_carrier_info()
            self.win.after(1000, self._tick_carrier)
        except tk.TclError:
            return

    def _clear_carrier_links(self) -> None:
        for label in self._carrier_links:
            label.destroy()
        self._carrier_links.clear()

    def _carrier_link(self, text: str, copy: str | None, fg: str) -> None:
        label = tk.Label(
            self.frm_carrier,
            text=text,
            bg=COLORS["bg"],
            fg=fg,
            font=(self._ui_family, self._ui_size, "underline") if copy else (self._ui_family, self._ui_size),
            cursor="hand2" if copy else "",
        )
        label.pack(side="left")
        if copy:
            label.bind("<Double-Button-1>", lambda _e, name=copy: self._copy_carrier_name(name))
        self._carrier_links.append(label)

    def _show_carrier_jump(self, frm: str, to: str) -> None:
        self._clear_carrier_links()
        self._carrier_jumping = True
        self.lbl_carrier.configure(
            text=t("win.carrier_jump_prefix"),
            fg=COLORS["warn"],
            bg=COLORS["bg"],
            cursor="",
            font=(self._ui_family, self._ui_size),
        )
        self._carrier_link(frm, None if frm == "—" else frm, COLORS["warn"])
        self._carrier_link(t("win.carrier_jump_mid"), None, COLORS["warn"])
        self._carrier_link(to, to or None, COLORS["warn"])
        # «, старт через … , остаток трития: …» — только после систем назначения
        self._carrier_info_last()

    def _carrier_info_last(self) -> None:
        """Переставить подпись с отсчётом/тритием в конец строки носителя."""
        if getattr(self, "lbl_carrier_info", None) is None:
            return
        self.lbl_carrier_info.pack_forget()
        self.lbl_carrier_info.pack(side="left")

    def carrier_header_text(self) -> str:
        parts = [self.lbl_carrier.cget("text")]
        parts.extend(label.cget("text") for label in self._carrier_links)
        return "".join(parts)

    def _copy_carrier_name(self, name: str | None) -> None:
        if not name or name == "—":
            return
        if self.on_copy_carrier:
            self.on_copy_carrier(name)
        else:
            self._copy_text(name)

    def _copy_text(self, text: str | None) -> None:
        if not text:
            return
        try:
            self.win.clipboard_clear()
            self.win.clipboard_append(text)
            self.win.update_idletasks()
        except tk.TclError:
            pass

    def _on_system_double(self, _event=None) -> None:
        """Двойной клик по системе в шапке: имя в «Маршрут по шару» и в буфер."""
        name = self._system_name
        entry = getattr(self, "sphere_system", None)
        if name and entry is not None:
            entry.delete(0, "end")
            entry.insert(0, name)
        if self.on_copy_system and name:
            self.on_copy_system(name)
        else:
            self._copy_text(name)

    def _on_carrier_double(self, _event=None) -> None:
        """Двойной клик по карриеру в шапке — копия системы, где он стоит."""
        name = self._carrier_system
        if self.on_copy_carrier and name:
            self.on_copy_carrier(name)
        else:
            self._copy_text(name)

    def _on_carrier_triple(self, _event=None) -> None:
        """Оставлено для API/тестов: маршрут Spansh до карриера (из шапки убран)."""
        if self.on_plot_to_carrier and self._carrier_system:
            self.on_plot_to_carrier()

    def _build_sphere_tab(self) -> None:
        """Вкладка обхода всех систем в шаре заданного радиуса."""
        self._sphere_busy = False
        self._sphere_hops: list[SphereHop] = []
        bar = tk.Frame(self.tab_sphere, bg=COLORS["bg"])
        bar.pack(fill="x", pady=(0, 6))
        self._sphere_bar = bar
        font = (self._ui_family, self._ui_size)
        self.sphere_system_lbl = tk.Label(bar, text=t("sphere.system"), bg=COLORS["bg"], fg=COLORS["muted"], font=font)
        self.sphere_system_lbl.pack(side="left")
        self.sphere_system = tk.Entry(
            bar,
            width=28,
            bg=COLORS["row"],
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            relief="flat",
            font=font,
        )
        self.sphere_system.pack(side="left", padx=(6, 12))
        self.sphere_distance_lbl = tk.Label(
            bar, text=t("sphere.distance"), bg=COLORS["bg"], fg=COLORS["muted"], font=font
        )
        self.sphere_distance_lbl.pack(side="left")
        self.sphere_distance = tk.Entry(
            bar,
            width=8,
            bg=COLORS["row"],
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
            relief="flat",
            font=font,
        )
        self.sphere_distance.insert(0, "10")
        self.sphere_distance.pack(side="left", padx=(6, 12))
        self.sphere_calc = tk.Button(
            bar,
            text=t("sphere.calc"),
            command=self._calc_sphere,
            bg=COLORS["panel"],
            fg=COLORS["fg"],
            activebackground=COLORS["sel"],
            activeforeground=COLORS["fg"],
            relief="flat",
            font=font,
            padx=10,
        )
        self.sphere_calc.pack(side="left")
        self.sphere_load = tk.Button(
            bar,
            text=t("sphere.load"),
            command=self._load_sphere_route,
            state="disabled",
            bg=COLORS["panel"],
            fg=COLORS["fg"],
            activebackground=COLORS["sel"],
            activeforeground=COLORS["fg"],
            disabledforeground=COLORS["muted"],
            relief="flat",
            font=font,
            padx=10,
        )
        self.sphere_load.pack(side="left", padx=(8, 0))
        self._sphere_load_tip = _CellTip(self.sphere_load, text=t("sphere.load_tip"))
        self.sphere_system.bind("<Return>", lambda _e: self._calc_sphere())
        self.sphere_distance.bind("<Return>", lambda _e: self._calc_sphere())
        self.sphere_status = tk.Label(
            self.tab_sphere,
            text=t("sphere.hint"),
            bg=COLORS["bg"],
            fg=COLORS["muted"],
            anchor="w",
            font=font,
        )
        self.sphere_status.pack(fill="x", pady=(0, 6))

        host = tk.Frame(self.tab_sphere, bg=COLORS["bg"])
        host.pack(fill="both", expand=True)
        host.grid_columnconfigure(0, weight=1)
        host.grid_rowconfigure(0, weight=1)
        columns = ("idx", "system", "star", "leg", "center")
        self.sphere_tree = ttk.Treeview(host, columns=columns, show="headings", style="ED.Treeview")
        headings = {
            "idx": (t("sphere.col_idx"), "center"),
            "system": (t("sphere.col_system"), "w"),
            "star": (t("sphere.col_star"), "center"),
            "leg": (t("sphere.col_leg"), "e"),
            "center": (t("sphere.col_center"), "e"),
        }
        for key, (title, anchor) in headings.items():
            width = self._sphere_widths.get(key, SPHERE_COLUMN_DEFAULTS.get(key, 80))
            self.sphere_tree.heading(key, text=title, anchor=anchor)
            # stretch=False: иначе «Система» растягивается на остаток и сбрасывает ручную ширину
            self.sphere_tree.column(
                key,
                width=max(self._min_col_width(key), int(width)),
                minwidth=self._min_col_width(key),
                anchor=anchor,
                stretch=False,
            )
        scroll = ttk.Scrollbar(host, orient="vertical", command=self.sphere_tree.yview)
        xscroll = ttk.Scrollbar(host, orient="horizontal", command=self.sphere_tree.xview)
        self.sphere_tree.configure(yscrollcommand=scroll.set, xscrollcommand=xscroll.set)
        self.sphere_tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        host.grid_columnconfigure(0, weight=1)
        host.grid_rowconfigure(0, weight=1)
        self.sphere_tree.tag_configure("back", foreground=COLORS["gold"])
        self.sphere_tree.tag_configure("done", foreground=COLORS["muted"])
        self.sphere_tree.tag_configure("here", foreground=COLORS["ok"])
        self.sphere_tree.tag_configure("next", foreground=COLORS["accent"])
        self.sphere_tree.bind("<Double-Button-1>", self._on_sphere_double)
        self.sphere_tree.bind("<ButtonRelease-1>", self._on_sphere_column_release, add="+")

    def _paint_sphere(self) -> None:
        bar = getattr(self, "_sphere_bar", None)
        if bar is None:
            return
        font = (self._ui_family, self._ui_size)
        bar.configure(bg=COLORS["bg"])
        for label in (self.sphere_system_lbl, self.sphere_distance_lbl, self.sphere_status):
            label.configure(bg=COLORS["bg"], font=font)
        self.sphere_system_lbl.configure(fg=COLORS["muted"])
        self.sphere_distance_lbl.configure(fg=COLORS["muted"])
        self.sphere_status.configure(fg=COLORS["muted"])
        for entry in (self.sphere_system, self.sphere_distance):
            entry.configure(
                bg=COLORS["row"],
                fg=COLORS["text"],
                insertbackground=COLORS["text"],
                font=font,
            )
        self.sphere_calc.configure(
            bg=COLORS["panel"],
            fg=COLORS["fg"],
            activebackground=COLORS["sel"],
            activeforeground=COLORS["fg"],
            font=font,
        )
        self.sphere_load.configure(
            bg=COLORS["panel"],
            fg=COLORS["fg"],
            activebackground=COLORS["sel"],
            activeforeground=COLORS["fg"],
            disabledforeground=COLORS["muted"],
            font=font,
        )
        self.sphere_tree.tag_configure("back", foreground=COLORS["gold"])
        self.sphere_tree.tag_configure("done", foreground=COLORS["muted"])
        self.sphere_tree.tag_configure("here", foreground=COLORS["ok"])
        self.sphere_tree.tag_configure("next", foreground=COLORS["accent"])

    def _on_sphere_column_release(self, _event=None) -> None:
        """Сохранить ширины колонок Sphere после ручного ресайза разделителя."""
        tree = getattr(self, "sphere_tree", None)
        if tree is None:
            return
        changed = False
        for key in tree["columns"]:
            try:
                width = int(tree.column(key, "width"))
            except (tk.TclError, TypeError, ValueError):
                continue
            width = max(self._min_col_width(key), width)
            if self._sphere_widths.get(key) != width:
                self._sphere_widths[key] = width
                changed = True
        if changed:
            self._schedule_save()

    def _load_sphere_route(self) -> None:
        """Обход из таблицы → маршрут EDHUD (Route + HUD). В игру он не прокладывается."""
        hops = list(self._sphere_hops)
        if len(hops) < 2 or self.on_load_sphere_route is None:
            return
        count = self.on_load_sphere_route(hops)
        if count:
            self.sphere_status.configure(
                text=t("sphere.loaded", n=count), fg=COLORS["ok"]
            )

    def _calc_sphere(self) -> None:
        if self._sphere_busy:
            return
        system = (self.sphere_system.get() or "").strip()
        if not system:
            self.sphere_status.configure(text=t("sphere.need_system"), fg=COLORS["warn"])
            return
        try:
            radius = float((self.sphere_distance.get() or "").replace(",", "."))
        except ValueError:
            self.sphere_status.configure(text=t("sphere.bad_radius"), fg=COLORS["warn"])
            return
        center = None
        state = self._state
        if state is not None and (state.system.name or "").strip().lower() == system.lower():
            center = state.system.star_pos
        self._sphere_busy = True
        self.sphere_calc.configure(state="disabled")
        self.sphere_load.configure(state="disabled")
        self.sphere_status.configure(
            text=t("sphere.searching", radius=radius, system=system),
            fg=COLORS["muted"],
        )

        def work() -> None:
            try:
                hops = plan_tour(fetch_sphere(system, radius, center=center))
            except Exception as exc:  # noqa: BLE001 — текст ошибки в статус вкладки
                self._sphere_ui(lambda err=str(exc): self._show_sphere(None, err))
                return
            self._sphere_ui(lambda rows=hops: self._show_sphere(rows, None))

        threading.Thread(target=work, name="edhud-sphere", daemon=True).start()

    def _sphere_ui(self, callback) -> None:
        try:
            self.win.after(0, callback)
        except tk.TclError:
            pass

    def _show_sphere(self, hops: list[SphereHop] | None, error: str | None) -> None:
        self._sphere_busy = False
        try:
            self.sphere_calc.configure(state="normal")
            tree = self.sphere_tree
            tree.delete(*tree.get_children())
        except tk.TclError:
            return
        self._sphere_hops = list(hops or [])
        self._sphere_cursor = 0
        self._sphere_progress_sig = None
        if error:
            self.sphere_status.configure(text=t("sphere.error", error=error), fg=COLORS["bad"])
            return
        total = 0.0
        for hop in self._sphere_hops:
            total += hop.leg_ly or 0.0
        unique = sum(1 for hop in self._sphere_hops if not hop.returning)
        can_load = unique > 1 and self.on_load_sphere_route is not None
        self.sphere_load.configure(state="normal" if can_load else "disabled")
        if unique <= 1:
            text = t("sphere.alone", system=self._sphere_hops[0].name if self._sphere_hops else "—")
        else:
            ly = f"{total:,.1f}".replace(",", " ")
            text = t("sphere.done", n=unique, ly=ly)
            if unique > 250:
                text += t("sphere.approx")
            text += " · " + t("sphere.howto_short")
        self.sphere_status.configure(text=text, fg=COLORS["muted"])
        if self._state is not None:
            self._sync_sphere_progress(self._state, force=True)
        else:
            self._render_sphere_rows(here_idx=None, next_idx=None)

    def _sphere_index_of(self, system: str | None) -> int | None:
        if not system or not self._sphere_hops:
            return None
        key = system.lower()
        found = [i for i, hop in enumerate(self._sphere_hops) if hop.name.lower() == key]
        if not found:
            return None
        idx = next((i for i in found if i >= self._sphere_cursor), found[-1])
        self._sphere_cursor = idx
        return idx

    def _apply_star_to_sphere(self, system: str | None, star_class: str | None) -> bool:
        klass = (star_class or "").strip()
        name = (system or "").strip()
        if not klass or not name or not self._sphere_hops:
            return False
        key = name.lower()
        changed = False
        for hop in self._sphere_hops:
            if hop.name.lower() == key and hop.star_class != klass:
                hop.star_class = klass
                changed = True
        return changed

    def _sync_sphere_progress(self, state: GameState, *, force: bool = False) -> None:
        """Отметить посещённые/текущую/следующую и подтянуть класс звезды после прибытия."""
        if not self._sphere_hops or getattr(self, "sphere_tree", None) is None:
            return
        # класс звезды — только когда уже в системе (не во время туннеля)
        if not state.jumping_away:
            star = state.system.main_star()
            if star and star.star_type:
                self._apply_star_to_sphere(state.system.name, str(star.star_type))
            for hop in state.route.hops:
                if hop.star_class:
                    self._apply_star_to_sphere(hop.system, hop.star_class)

        here_idx = self._sphere_index_of(state.system.name)
        next_idx = here_idx + 1 if here_idx is not None and here_idx + 1 < len(self._sphere_hops) else None
        # во время прыжка «следующая» — цель Jump, если она в туре
        if state.jumping_away:
            dest = state.jump_arrow_system() or state.jump_dest or state.fsd_target
            if dest:
                dest_key = dest.lower()
                for i, hop in enumerate(self._sphere_hops):
                    if hop.name.lower() == dest_key:
                        next_idx = i
                        break

        classes = tuple(hop.star_class or "" for hop in self._sphere_hops)
        sig = (
            state.system.name,
            state.system.address,
            here_idx,
            next_idx,
            bool(state.jumping_away),
            classes,
        )
        if not force and sig == self._sphere_progress_sig:
            return
        self._sphere_progress_sig = sig
        self._render_sphere_rows(here_idx=here_idx, next_idx=next_idx)

    def _render_sphere_rows(self, *, here_idx: int | None, next_idx: int | None) -> None:
        tree = getattr(self, "sphere_tree", None)
        if tree is None:
            return
        try:
            tree.delete(*tree.get_children())
        except tk.TclError:
            return
        for index, hop in enumerate(self._sphere_hops):
            leg = "—" if index == 0 else f"{hop.leg_ly:,.2f}".replace(",", " ")
            center = f"{hop.from_center:,.2f}".replace(",", " ")
            mark = "↩" if hop.returning else str(index + 1)
            if hop.returning:
                tags: tuple[str, ...] = ("back",)
            elif here_idx is not None and index == here_idx:
                tags = ("here",)
            elif next_idx is not None and index == next_idx:
                tags = ("next",)
            elif here_idx is not None and index < here_idx:
                tags = ("done",)
            else:
                tags = ()
            tree.insert(
                "",
                "end",
                values=(mark, hop.name, hop.star_class or "—", leg, center),
                tags=tags,
            )
        # прокрутить к текущей / следующей
        focus = here_idx if here_idx is not None else next_idx
        if focus is not None:
            children = tree.get_children()
            if 0 <= focus < len(children):
                try:
                    tree.see(children[focus])
                except tk.TclError:
                    pass

    def _on_sphere_double(self, event) -> None:
        row = self.sphere_tree.identify_row(event.y)
        if not row:
            return
        values = self.sphere_tree.item(row, "values")
        if len(values) < 2:
            return
        name = str(values[1]).strip()
        if name:
            self._copy_text(name)

    def _update_route(self, state: GameState) -> None:
        route = state.route
        current = state.system.name
        self._route_state = state
        if not route.hops:
            self._clear_route_rows()
            self._route_hops_total = 0
            self._route_systems = None
            self._route_here = None
            self._route_col_px = []
            self._route_inner.configure(height=1)
            self.route_info.configure(text=t("win.route_empty"))
            self._route_canvas.configure(scrollregion=(0, 0, 0, 0))
            return
        remaining = route.distance_remaining(current)
        src = route.source or "game"
        lock = t("win.route_locked") if route.locked else ""
        extra = t("win.route_left", ly=f"{remaining:,.1f}".replace(",", " ")) if remaining else ""
        jumps = route.total_jumps
        jump_txt = t("win.route_jumps", n=jumps) if jumps else ""
        self.route_info.configure(
            text=t("win.route_info", src=src, lock=lock, extra=extra, jumps=jump_txt)
        )
        # Строки переиспользуем, пока не сменился набор систем маршрута.
        systems = tuple(h.system for h in route.hops)
        if self._route_systems != systems:
            self._clear_route_rows()
            self._route_systems = systems
        self._route_hops = route.hops
        self._route_here = route.index_of(current)
        self._route_hops_total = len(route.hops)
        self._route_jump_marks = route_jump_marks(
            route.hops, self._route_here, state.jump_arrow_system()
        )
        self._route_col_px = self._apply_column_geometry("route")
        row_h = _row_height(self._ui_size)
        total_w = sum(self._route_col_px)
        total_h = self._route_hops_total * row_h
        # Фиксированная высота внутреннего полотна = все строки маршрута;
        # реальные виджеты создаём только для видимого окна (виртуализация).
        self._route_inner.configure(height=max(1, total_h))
        self._route_inner.grid_propagate(False)
        self._route_canvas.itemconfigure(self._route_window, width=total_w)
        self._route_canvas.configure(scrollregion=(0, 0, total_w, total_h))
        self._sync_header_x("route")
        self._route_materialize()
        self._route_scroll_to_here()

    def _clear_route_rows(self) -> None:
        for child in self._route_inner.winfo_children():
            child.destroy()
        self._route_rows.clear()
        self._route_materialized.clear()

    def _make_route_row(self, row: int) -> dict:
        widths = self._route_col_px
        labels: list[tk.Label] = []
        for col, (key, _title, _width, anchor) in enumerate(ROUTE_COLUMNS):
            label = self._put_cell(
                "route",
                row,
                col,
                widths[col],
                anchor=anchor,
                copy_text=self._route_hops[row].system if key == "system" else None,
            )
            labels.append(label)
        data = {"labels": labels, "sig": None}
        self._route_rows[row] = data
        return data

    def _route_cell_data(self, row: int) -> tuple[list[str], list[str], tuple]:
        hop = self._route_hops[row]
        here = self._route_here
        state = self._route_state
        jump_marks = self._route_jump_marks
        dist = hop.distance if hop.distance else None
        ly_text = f"{dist:,.1f}".replace(",", " ") if dist else "—"
        tag = route_tag(row, here)
        jump = jump_marks.get(row)
        mark = jump if jump else ("▶ " if tag == "here" else "")
        if tag == "done" and jump is None:
            fg = COLORS["muted"]
        elif jump == "-> ":
            fg = COLORS["accent"]
        elif jump == "-< " or tag == "here":
            fg = COLORS["ok"]
        elif jump == "|  ":
            fg = COLORS["warn"]
        else:
            fg = COLORS["text"]
        font = (
            self._ui_family,
            self._ui_size + (1 if tag == "here" or jump in ("-< ", "-> ") else 0),
        )
        cells = [
            str(row + 1),
            f"{mark}{hop.system}",
            hop.star_class or "—",
            ly_text,
            _route_bodies_cell(hop, here=(tag == "here"), system=state.system),
            hop.opened_label(state.cmdr or getattr(self.cfg, "edsm_commander", None)),
        ]
        opened_fg = COLORS["gold"] if hop.discovered_by_me else fg
        fgs = [fg, fg, fg, fg, fg, opened_fg]
        return cells, fgs, font

    def _route_apply_row(self, row: int, data: dict) -> bool:
        cells, fgs, font = self._route_cell_data(row)
        sig = (tuple(cells), tuple(fgs), font)
        if sig == data["sig"]:
            return False
        for label, text, fg in zip(data["labels"], cells, fgs):
            label.configure(text=text, fg=fg, font=font)
        data["sig"] = sig
        return True

    def _route_materialize(self, _event=None) -> None:
        total = self._route_hops_total
        if total <= 0:
            return
        row_h = _row_height(self._ui_size)
        try:
            top = int(self._route_canvas.canvasy(0))
            view_h = max(1, int(self._route_canvas.winfo_height()))
        except tk.TclError:
            return
        margin = 12
        first = max(0, top // row_h - margin)
        last = min(total - 1, (top + view_h) // row_h + margin)
        wanted = set(range(first, last + 1))
        # Разматериализуем то, что ушло за пределы окна (виджеты остаются для reuse).
        for row in list(self._route_materialized):
            if row not in wanted:
                data = self._route_rows.get(row)
                if data:
                    for label in data["labels"]:
                        label.master.grid_forget()
                self._route_materialized.discard(row)
        widths = self._route_col_px
        for row in range(first, last + 1):
            data = self._route_rows.get(row)
            if data is None:
                data = self._make_route_row(row)
            self._route_apply_row(row, data)
            for col, label in enumerate(data["labels"]):
                box = label.master
                box.configure(width=widths[col])
                if not box.grid_info():
                    box.grid(row=row, column=col, sticky="nsew")
            self._route_materialized.add(row)

    def _route_scroll_to_here(self) -> None:
        here = self._route_here
        if here is None or self._route_hops_total <= 0:
            return
        row_h = _row_height(self._ui_size)
        total_h = self._route_hops_total * row_h
        self._route_canvas.yview_moveto(max(0.0, (here * row_h) / max(1, total_h)))

    def _body_row_data(self, body: Body, state: GameState) -> tuple[dict, dict, dict, tuple]:
        """Тексты/цвета/тултипы строки Bodies и сигнатура для пропуска лишних configure."""
        bio_text = "—" if body.bio_signals is None and not body.signals_known else str(body.bio_signals or 0)
        geo = "—" if body.geo_signals is None and not body.signals_known else str(body.geo_signals or 0)
        pml = "—" if body.mining_locations is None else str(body.mining_locations)
        minerals = format_hotspots(body.hotspots)
        guess, guess_color = _forecast(body, state)
        # Кольца/пояс: rings_mapped без dss_scanned — не ✔ (поверхность не сканировали).
        if body.dss_scanned:
            dss = "✔"
        elif body.dss_remote:
            dss = "?"
        else:
            dss = "—"
        first = "✔" if not body.was_discovered and not body.remote else "—"
        src = body.source or (t("src.own") if not body.remote else "?")
        values = {
            "name": body.name or f"#{body.body_id}",
            "type": _type_of(body),
            "atmos": body.atmosphere_type or body.atmosphere or "—",
            "temp": _temp(body.surface_temp),
            "bio": bio_text,
            "guess": guess,
            "geo": geo,
            "pml": pml,
            "minerals": minerals,
            "dss": dss,
            "value": _value_of(body, state.odyssey),
            "first": first,
            "dist": _ls(body.distance_ls),
            "src": src,
            "belt": bool(body.has_rings),
        }
        counts = {
            "bio": body.bio_signals,
            "geo": body.geo_signals,
            "pml": body.mining_locations,
            "minerals": sum(int(v or 0) for v in (body.hotspots or {}).values()) or None,
        }
        tip = _forecast_tip(body, state)
        minerals_tip = format_hotspots_tip(body.hotspots)
        if body.hotspots:
            saved = self.belt_store.contains(state.system.address, body.body_id, state.system.name or "")
            extra = t("tip.save_belt")
            if saved:
                extra = t("tip.saved_belt")
            minerals_tip = (minerals_tip + "\n\n" + extra) if minerals_tip else extra
        dss_tip = None
        if body.rings_mapped and not body.dss_scanned:
            dss_tip = t("tip.rings_only")
        elif not body.is_star and (body.radius or 0) > 0 and not body.dss_scanned:
            dss_tip = t("tip.dss_alt", rng=format_dss_range(body.radius))
        styles: dict[str, tuple[str, str]] = {}
        tips: dict[str, str | None] = {}
        rings_tip = _rings_tip(body)
        for key, _title, _width, _anchor in BODY_COLUMNS:
            if key == "belt":
                styles[key] = (COLORS["text"], COLORS["row"])
                tips[key] = rings_tip
                continue
            paint = signal_colors(key, counts.get(key))
            if key == "first" and first == "✔":
                styles[key] = (COLORS["gold"], COLORS["row"])
            elif key == "guess" and guess_color:
                styles[key] = (COLORS[guess_color], COLORS["row"])
            else:
                styles[key] = paint if paint else (COLORS["text"], COLORS["row"])
            if key in ("bio", "guess"):
                tips[key] = tip
            elif key == "minerals":
                tips[key] = minerals_tip
            elif key == "dss":
                tips[key] = dss_tip
            else:
                tips[key] = None
        sig = (
            values["name"],
            values["type"],
            values["atmos"],
            values["temp"],
            values["bio"],
            values["guess"],
            values["geo"],
            values["pml"],
            values["minerals"],
            values["dss"],
            values["value"],
            values["first"],
            values["dist"],
            values["src"],
            values["belt"],
            tip,
            minerals_tip,
            dss_tip,
            rings_tip,
            guess_color,
        )
        return values, styles, tips, sig

    def _clear_body_rows(self) -> None:
        for child in self._bodies_inner.winfo_children():
            child.destroy()
        self._body_rows.clear()
        self._bodies_order = []

    def _set_cell_tip(self, box, label, tip: str | None) -> None:
        existing = getattr(label, "tip", None)
        if tip:
            if existing is None:
                cell_tip = _CellTip(box, label, text=tip)
                label.tip = cell_tip
                box.tip = cell_tip
            else:
                existing.text = tip
        elif existing is not None:
            existing.text = ""

    def _update_bodies(self, state: GameState) -> None:
        jumped = state.system.address != getattr(self, "_bodies_address", None)
        if jumped:
            try:
                scroll = self._bodies_canvas.yview()
            except tk.TclError:
                scroll = (0.0, 1.0)
            self._clear_body_rows()
        else:
            try:
                scroll = self._bodies_canvas.yview()
            except tk.TclError:
                scroll = (0.0, 1.0)

        show_belts = True if self.cfg is None else bool(getattr(self.cfg, "show_belt_clusters", True))
        # Кольца не отдельной строкой: hotspot уже на планете-носителе.
        bodies = [
            b
            for b in state.system.bodies.values()
            if not is_ring_body(b.name) and (show_belts or not is_belt_body(b.name))
        ]
        bodies = sorted(
            bodies,
            key=lambda b: (0 if b.is_star or b.star_type else 1, b.distance_ls or 0, b.body_id),
        )
        order = [b.body_id for b in bodies]
        try:
            avail = int(self._bodies_canvas.winfo_width())
        except tk.TclError:
            avail = None
        widths = self._apply_column_geometry("bodies", avail if avail and avail > 1 else None)

        # убрать тела, которых больше нет в системе
        alive = set(order)
        for body_id in list(self._body_rows):
            if body_id not in alive:
                row = self._body_rows.pop(body_id)
                for box, _label in row["cells"].values():
                    try:
                        box.destroy()
                    except tk.TclError:
                        pass

        for row_idx, body in enumerate(bodies):
            values, styles, tips, sig = self._body_row_data(body, state)
            entry = self._body_rows.get(body.body_id)
            if entry is None:
                cells: dict[str, tuple] = {}
                for col, (key, _title, _width, anchor) in enumerate(BODY_COLUMNS):
                    if key == "belt":
                        icon = self._ring_icon if values["belt"] and self._ring_icon is not None else None
                        label = self._put_cell(
                            "bodies",
                            row_idx,
                            col,
                            widths[col],
                            image=icon,
                            anchor="center",
                            tip=tips.get(key) if icon is not None else None,
                        )
                    else:
                        fg, bg = styles[key]
                        label = self._put_cell(
                            "bodies",
                            row_idx,
                            col,
                            widths[col],
                            text=values[key],
                            fg=fg,
                            bg=bg,
                            anchor=anchor,
                            tip=tips.get(key),
                        )
                    box = label.master
                    cells[key] = (box, label)
                    if key == "minerals":
                        self._bind_minerals_cell(box, label, body.body_id)
                self._body_rows[body.body_id] = {"cells": cells, "sig": sig, "row": row_idx}
                continue

            # уже есть — обновить текст/цвет без destroy (FSS не мигает)
            if entry["sig"] != sig:
                for col, (key, _title, _width, anchor) in enumerate(BODY_COLUMNS):
                    box, label = entry["cells"][key]
                    fg, bg = styles[key]
                    if key == "belt":
                        icon = self._ring_icon if values["belt"] and self._ring_icon is not None else None
                        label.configure(image=icon or "", bg=bg)
                        if icon is not None:
                            label.image = icon
                        self._set_cell_tip(box, label, tips.get(key) if icon is not None else None)
                    else:
                        label.configure(text=values[key], fg=fg, bg=bg, anchor=anchor)
                        box.configure(bg=bg)
                        self._set_cell_tip(box, label, tips.get(key))
                    if key == "minerals":
                        self._bind_minerals_cell(box, label, body.body_id)
                entry["sig"] = sig

            if entry["row"] != row_idx:
                for col, (key, _title, _width, _anchor) in enumerate(BODY_COLUMNS):
                    box, _label = entry["cells"][key]
                    box.grid(row=row_idx, column=col, sticky="nsew")
                    try:
                        box.configure(width=widths[col])
                    except tk.TclError:
                        pass
                entry["row"] = row_idx

        self._bodies_order = order
        self._bodies_address = state.system.address
        self._bodies_inner.update_idletasks()
        total_w = sum(widths)
        self._bodies_canvas.itemconfigure(self._bodies_window, width=total_w)
        self._bodies_canvas.configure(scrollregion=self._bodies_canvas.bbox("all") or (0, 0, total_w, 0))
        self._sync_header_x("bodies")
        if jumped:
            self._bodies_canvas.yview_moveto(0)
        else:
            try:
                self._bodies_canvas.yview_moveto(scroll[0])
            except tk.TclError:
                pass
