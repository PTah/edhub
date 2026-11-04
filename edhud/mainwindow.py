"""Основное окно EDHUD (стиль EDEB): вкладки Route и Bodies."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from . import bio, codex, values, winapi
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
    "accent": "#54dfed",
    "grid": "#3a3a3a",
}

# Колонки таблицы тел. Пояс — отдельная узкая ячейка со значком кольца.
BODY_COLUMNS = (
    ("belt", "", 28, "center"),
    ("name", "Имя", 200, "w"),
    ("type", "Тип", 140, "w"),
    ("atmos", "Атмосфера", 110, "w"),
    ("temp", "T", 70, "e"),
    ("bio", "Био", 50, "center"),
    ("guess", "Возможно", 220, "w"),
    ("geo", "Гео", 50, "center"),
    ("pml", "PML", 50, "center"),
    ("dss", "DSS", 50, "center"),
    ("value", "≈ Cr", 100, "e"),
    ("first", "1-е", 50, "center"),
    ("dist", "ls", 80, "e"),
    ("src", "Ист.", 70, "center"),
)

ROUTE_COLUMNS = (
    ("idx", "#", 48, "center"),
    ("system", "Система", 280, "w"),
    ("star", "Класс", 80, "center"),
    ("ly", "До след., ly", 110, "e"),
    ("opened", "Открыта", 140, "w"),
)

MIN_COL_WIDTH = 28
MIN_COL_WIDTHS = {
    "belt": 28,
    "name": 120,
    "type": 80,
    "atmos": 70,
    "guess": 100,
    "system": 140,
    "opened": 90,
}
RESIZE_EDGE = 6


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
        header = "DSS:" if body.genuses else "Предположительно:"
        return header + "\n" + "\n".join(rows)
    if body.genuses:
        names = [codex.display_name(key) for key in body.genuses]
        return "DSS (роды):\n" + "\n".join(f"• {name}" for name in names)
    if (body.bio_signals or 0) <= 0:
        return None
    missing: list[str] = []
    if not body.planet_class:
        missing.append("класс")
    if not body.atmosphere and not body.atmosphere_composition:
        missing.append("атмосфера")
    if body.surface_temp is None:
        missing.append("температура")
    if not body.materials:
        missing.append("материалы")
    if missing:
        return "Нет прогноза — нужен детальный скан\n(нет: " + ", ".join(missing) + ")"
    return "Нет совпадений в критериях био"


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
        on_copy_system: Callable[[str], None] | None = None,
        on_copy_carrier: Callable[[str], None] | None = None,
        on_plot_to_carrier: Callable[[], None] | None = None,
    ) -> None:
        self.on_close = on_close
        self.cfg = cfg
        self.on_copy_system = on_copy_system
        self.on_copy_carrier = on_copy_carrier
        self.on_plot_to_carrier = on_plot_to_carrier
        self._carrier_system: str | None = None
        self._system_name: str | None = None
        self._carrier_clicks = 0
        self._carrier_click_job: str | None = None
        self.win = tk.Toplevel(root)
        self.win.title("EDHUD")
        geometry = getattr(cfg, "main_geometry", None) if cfg is not None else None
        self.win.geometry(geometry or "980x520")
        self.win.minsize(720, 360)
        self.win.configure(bg=COLORS["bg"])
        self.win.protocol("WM_DELETE_WINDOW", self.hide)
        self._apply_saved_position()
        self.apply_opacity()
        self._visible = True
        self._shown_tab = "bodies"
        self._ring_icon: tk.PhotoImage | None = None
        self._ui_family = "Segoe UI"
        self._ui_size = 9
        self._state: GameState | None = None
        self._header_labels: list[tk.Label] = []
        self._route_header_labels: list[tk.Label] = []
        self._body_widths = {key: width for key, _title, width, _anchor in BODY_COLUMNS}
        self._route_widths = {key: width for key, _title, width, _anchor in ROUTE_COLUMNS}
        self._load_column_widths()
        self._col_drag: tuple[str, int, int, int] | None = None  # table, index, start_x, start_w
        self._save_after: str | None = None
        self._style()
        self._build()
        self._last_key: tuple | None = None
        self._layout_ready = False
        self.win.after(80, self._enable_layout_persist)
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

    def _build(self) -> None:
        top = ttk.Frame(self.win, style="ED.TFrame", padding=(12, 10))
        top.pack(fill="x")
        self.lbl_system = ttk.Label(top, text="Система: —", style="ED.Header.TLabel", cursor="hand2")
        self.lbl_system.pack(side="left")
        self.lbl_system.bind("<Double-Button-1>", self._on_system_double)
        self.lbl_status = ttk.Label(top, text="", style="ED.Muted.TLabel")
        self.lbl_status.pack(side="left", padx=(16, 0))
        # tk.Label: курсор-рука и подчёркивание — видно, что карриер кликабелен
        self.lbl_carrier = tk.Label(
            top,
            text="",
            bg=COLORS["bg"],
            fg=COLORS["accent"],
            font=(self._ui_family, self._ui_size, "underline"),
            cursor="hand2",
            padx=4,
        )
        self.lbl_carrier.pack(side="left", padx=(12, 0))
        # Double/Triple на Label в Windows часто срываются — считаем клики сами
        self.lbl_carrier.bind("<Button-1>", self._on_carrier_click)
        self.lbl_carrier_hint = ttk.Label(
            top, text="", style="ED.Muted.TLabel", font=(self._ui_family, max(7, self._ui_size - 1))
        )
        self.lbl_carrier_hint.pack(side="left", padx=(4, 0))
        self.lbl_carrier_hint.bind("<Button-1>", self._on_carrier_click)

        nb = ttk.Notebook(self.win, style="ED.TNotebook")
        nb.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.nb = nb
        nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self.tab_route = ttk.Frame(nb, style="ED.TFrame", padding=8)
        self.tab_bodies = ttk.Frame(nb, style="ED.TFrame", padding=8)
        nb.add(self.tab_route, text="Route")
        nb.add(self.tab_bodies, text="Bodies")
        nb.select(self.tab_bodies)

        self.route_info = ttk.Label(self.tab_route, text="Маршрут пуст", style="ED.TLabel")
        self.route_info.pack(anchor="w", pady=(0, 6))
        self._ring_icon = _ring_icon(self.win)
        self._build_route_table()
        self._build_bodies_table()

    def _load_column_widths(self) -> None:
        if self.cfg is None:
            return
        for key, width in (getattr(self.cfg, "bodies_columns", None) or {}).items():
            if key in self._body_widths:
                self._body_widths[key] = max(self._min_col_width(key), int(width))
        for key, width in (getattr(self.cfg, "route_columns", None) or {}).items():
            if key in self._route_widths:
                self._route_widths[key] = max(self._min_col_width(key), int(width))

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
        header.place(x=0, y=0, relheight=1)
        setattr(self, header_attr, header)

        pixel_widths = [
            max(self._min_col_width(key), int(widths.get(key, default)))
            for key, _t, default, _a in columns
        ]
        labels: list[tk.Label] = []
        head_h = _row_height(self._ui_size) + 8
        for index, (key, title, _default_w, anchor) in enumerate(columns):
            width = pixel_widths[index]
            header.grid_columnconfigure(index, minsize=width, weight=0)
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

        canvas = tk.Canvas(host, bg=COLORS["row"], highlightthickness=0, bd=0)
        scroll = ttk.Scrollbar(host, orient="vertical", command=canvas.yview)
        xscroll = ttk.Scrollbar(host, orient="horizontal", command=lambda *a: self._xview(table, *a))
        canvas.configure(yscrollcommand=scroll.set, xscrollcommand=xscroll.set)
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
            inner.grid_columnconfigure(index, minsize=width, weight=0)

        def _fit(event) -> None:
            widths_now = self._apply_column_geometry(table)
            total = sum(widths_now)
            # шире окна — пустое место справа, колонки не раздуваем
            canvas.itemconfigure(window, width=max(total, int(event.width) or total))
            header.configure(width=total)
            self._sync_header_x(table)

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
            header.place_configure(x=-canvas.canvasx(0), y=0)
        except tk.TclError:
            pass

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
            tip_text = tip or f"Двойной клик — копировать\n{copy_text}"
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
        self.apply_opacity()
        self._apply_saved_position()
        self._last_key = None
        if self._state is not None:
            self.update_state(self._state)

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
        if getattr(self, "lbl_carrier", None) is not None:
            self.lbl_carrier.configure(
                bg=COLORS["bg"],
                font=(self._ui_family, self._ui_size, "underline"),
            )
        if getattr(self, "lbl_carrier_hint", None) is not None:
            self.lbl_carrier_hint.configure(font=(self._ui_family, max(7, self._ui_size - 1)))

    def update_state(self, state: GameState) -> None:
        self._state = state
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
            (h.system, h.star_class, h.discovered_by, h.discovered_by_me) for h in state.route.hops
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
            None if dist is None else round(dist, 1),
            state.view_tab,
        )

    def _on_tab_changed(self, _event=None) -> None:
        """Показ Bodies заново рисует таблицу: скрытая вкладка могла остаться от прошлой системы."""
        if self._state is None:
            return
        try:
            current = self.nb.select()
        except tk.TclError:
            return
        if current == str(self.tab_bodies):
            self._update_header(self._state)
            self._update_bodies(self._state)

    def _apply_tab(self, state: GameState) -> None:
        tab = state.view_tab if state.view_tab in ("route", "bodies") else "bodies"
        if tab == self._shown_tab:
            return
        self._shown_tab = tab
        self.nb.select(self.tab_route if tab == "route" else self.tab_bodies)

    def _update_header(self, state: GameState) -> None:
        name = state.system.name or "—"
        self._system_name = state.system.name
        known = len(state.system.bodies)
        total = state.system.body_count or known
        bio = sum(1 for b in state.system.bodies.values() if (b.bio_signals or 0) > 0)
        opened = " — открыта вами" if state.system.discovered_by_me else ""
        self.lbl_system.configure(text=f"Система: {name}{opened}")
        self.lbl_status.configure(
            text=f"тел {known}/{total} · био-тел {bio}"
            + (" · маршрут залочен" if state.route.locked else "")
        )
        self._carrier_system = state.carrier.system if state.carrier.known else None
        if not state.carrier.known:
            self.lbl_carrier.configure(text="")
            self.lbl_carrier_hint.configure(text="")
            return
        from .hudmodel import _carrier_who

        who = _carrier_who(state.carrier)
        if state.carrier.jump_pending and state.carrier.jump_dest_system:
            frm = state.carrier.jump_from_system or self._carrier_system or "—"
            to = state.carrier.jump_dest_system
            text = f"Карриер готовится прыгать из {frm} в {to}"
            self.lbl_carrier.configure(text=text, fg=COLORS["warn"], bg=COLORS["bg"])
            self.lbl_carrier_hint.configure(text="· 2× копия · 3× маршрут Spansh")
            return
        if self._carrier_system:
            dist = state.carrier_distance_ly()
            if dist is None:
                text = f"{who}: {self._carrier_system}"
            elif dist < 0.05:
                text = f"{who}: {self._carrier_system} · здесь"
            else:
                ly = f"{dist:,.0f}".replace(",", " ")
                text = f"{who}: {self._carrier_system} · {ly} ly"
            self.lbl_carrier.configure(text=text, fg=COLORS["accent"], bg=COLORS["bg"])
            self.lbl_carrier_hint.configure(text="· 2× копия · 3× маршрут Spansh")
        else:
            self.lbl_carrier.configure(text="")
            self.lbl_carrier_hint.configure(text="")

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
        name = self._system_name
        if self.on_copy_system and name:
            self.on_copy_system(name)
        else:
            self._copy_text(name)

    def _on_carrier_click(self, _event=None) -> None:
        """2 клика — копия системы карриера, 3 — маршрут Spansh до него (не в игру)."""
        self._carrier_clicks += 1
        if self._carrier_click_job is not None:
            try:
                self.win.after_cancel(self._carrier_click_job)
            except (tk.TclError, ValueError):
                pass

        def flush() -> None:
            n = self._carrier_clicks
            self._carrier_clicks = 0
            self._carrier_click_job = None
            if n >= 3:
                self._on_carrier_triple()
            elif n == 2:
                self._on_carrier_double()

        self._carrier_click_job = self.win.after(320, flush)

    def _on_carrier_double(self, _event=None) -> None:
        name = self._carrier_system
        if self.on_copy_carrier and name:
            self.on_copy_carrier(name)
        else:
            self._copy_text(name)

    def _on_carrier_triple(self, _event=None) -> None:
        if self.on_plot_to_carrier and self._carrier_system:
            self.on_plot_to_carrier()

    def _update_route(self, route: Route, current: str | None) -> None:
        for child in self._route_inner.winfo_children():
            child.destroy()
        if not route.hops:
            self.route_info.configure(text="Маршрут пуст (проложите в игре или plot/import)")
            self._route_canvas.configure(scrollregion=(0, 0, 0, 0))
            return
        remaining = route.distance_remaining(current)
        src = route.source or "game"
        lock = " · залочен" if route.locked else ""
        extra = f" · осталось ~{remaining:,.1f} ly".replace(",", " ") if remaining else ""
        jumps = route.total_jumps
        jump_txt = f" · ~{jumps} прыж." if jumps else ""
        self.route_info.configure(
            text=(
                f"Источник: {src}{lock}{extra}{jump_txt}"
                " · 2× система — копия · маршрут до карриера — 3× по карриеру в шапке"
            )
        )
        here = route.index_of(current)
        here_row = None
        widths = self._apply_column_geometry("route")
        for row, hop in enumerate(route.hops):
            dist = hop.distance if hop.distance else None
            ly_text = f"{dist:,.1f}".replace(",", " ") if dist else "—"
            tag = route_tag(row, here)
            mark = "▶ " if tag == "here" else ""
            if tag == "done":
                fg = COLORS["muted"]
            elif tag == "here":
                fg = COLORS["ok"]
            else:
                fg = COLORS["text"]
            font = (self._ui_family, self._ui_size + (1 if tag == "here" else 0))
            opened = hop.opened_label()
            cells = {
                "idx": str(row + 1),
                "system": f"{mark}{hop.system}",
                "star": hop.star_class or "—",
                "ly": ly_text,
                "opened": opened,
            }
            for col, (key, _title, _width, anchor) in enumerate(ROUTE_COLUMNS):
                cell_fg = COLORS["ok"] if key == "opened" and hop.discovered_by_me else fg
                self._put_cell(
                    "route",
                    row,
                    col,
                    widths[col],
                    text=cells[key],
                    fg=cell_fg,
                    anchor=anchor,
                    font=font,
                    copy_text=hop.system if key == "system" else None,
                )
            if tag == "here":
                here_row = row
        self._route_inner.update_idletasks()
        total_w = sum(widths)
        self._route_canvas.itemconfigure(self._route_window, width=total_w)
        self._route_canvas.configure(scrollregion=self._route_canvas.bbox("all") or (0, 0, total_w, 0))
        self._sync_header_x("route")
        if here_row is not None:
            self._route_inner.update_idletasks()
            row_widgets = self._route_inner.grid_slaves(row=here_row)
            if row_widgets:
                y = row_widgets[0].winfo_y()
                total = max(1, self._route_inner.winfo_height())
                self._route_canvas.yview_moveto(max(0.0, y / total))

    def _update_bodies(self, state: GameState) -> None:
        for child in self._bodies_inner.winfo_children():
            child.destroy()
        jumped = state.system.address != getattr(self, "_bodies_address", None)
        bodies = sorted(
            state.system.bodies.values(),
            key=lambda b: (0 if b.is_star or b.star_type else 1, b.distance_ls or 0, b.body_id),
        )
        try:
            avail = int(self._bodies_canvas.winfo_width())
        except tk.TclError:
            avail = None
        widths = self._apply_column_geometry("bodies", avail if avail and avail > 1 else None)
        for row, body in enumerate(bodies):
            bio_text = "—" if body.bio_signals is None and not body.signals_known else str(body.bio_signals or 0)
            geo = "—" if body.geo_signals is None and not body.signals_known else str(body.geo_signals or 0)
            pml = "—" if body.mining_locations is None else str(body.mining_locations)
            guess, guess_color = _forecast(body, state)
            dss = "✔" if body.dss_scanned else ("?" if body.dss_remote else "—")
            first = "✔" if not body.was_discovered and not body.remote else "—"
            src = body.source or ("своё" if not body.remote else "?")
            cell_values = {
                "name": body.name or f"#{body.body_id}",
                "type": _type_of(body),
                "atmos": body.atmosphere_type or body.atmosphere or "—",
                "temp": _temp(body.surface_temp),
                "bio": bio_text,
                "guess": guess,
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
            tip = _forecast_tip(body, state)
            for col, (key, _title, _width, anchor) in enumerate(BODY_COLUMNS):
                if key == "belt":
                    icon = self._ring_icon if body.has_rings and self._ring_icon is not None else None
                    self._put_cell("bodies", row, col, widths[col], image=icon, anchor="center")
                    continue
                paint = signal_colors(key, counts.get(key))
                if key == "guess" and guess_color:
                    fg, bg = COLORS[guess_color], COLORS["row"]
                else:
                    fg, bg = paint if paint else (COLORS["text"], COLORS["row"])
                self._put_cell(
                    "bodies",
                    row,
                    col,
                    widths[col],
                    text=cell_values[key],
                    fg=fg,
                    bg=bg,
                    anchor=anchor,
                    tip=tip if key in ("bio", "guess") else None,
                )
        self._bodies_address = state.system.address
        self._bodies_inner.update_idletasks()
        total_w = sum(widths)
        self._bodies_canvas.itemconfigure(self._bodies_window, width=total_w)
        self._bodies_canvas.configure(scrollregion=self._bodies_canvas.bbox("all") or (0, 0, total_w, 0))
        self._sync_header_x("bodies")
        if jumped:
            self._bodies_canvas.yview_moveto(0)
