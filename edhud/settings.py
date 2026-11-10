"""Окно настроек EDHUD (tkinter)."""
from __future__ import annotations

import webbrowser
from pathlib import Path
from tkinter import BooleanVar, DoubleVar, IntVar, StringVar, colorchooser, filedialog, messagebox, ttk
import tkinter as tk

from . import __version__, config
from .i18n import t
from .mainwindow import _geometry_xy

# Подписи цветов в разделе оформления. Значение — ключ перевода.
COLOR_FIELDS = (
    ("fg", "color.fg"),
    ("text", "color.text"),
    ("muted", "color.muted"),
    ("dim", "color.dim"),
    ("accent", "color.accent"),
    ("ok", "color.ok"),
    ("warn", "color.warn"),
    ("bad", "color.bad"),
    ("bg", "color.bg"),
    ("panel", "color.panel"),
    ("row", "color.row"),
    ("sel", "color.sel"),
)

NUDGE_STEP = 10


def _parse_color(value: str) -> str | None:
    text = (value or "").strip()
    if not text.startswith("#"):
        text = "#" + text
    if len(text) == 4 and all(ch in "0123456789abcdefABCDEF" for ch in text[1:]):
        text = "#" + "".join(ch * 2 for ch in text[1:])
    if len(text) == 7 and all(ch in "0123456789abcdefABCDEF" for ch in text[1:]):
        return text.lower()
    return None


def _clamp_alpha(value: float) -> float:
    return max(0.25, min(1.0, float(value)))


class SettingsDialog:
    """Модальное окно настроек."""

    def __init__(self, root: tk.Misc, cfg: config.Config, on_saved=None, on_live=None, on_check_updates=None) -> None:
        self.cfg = cfg
        self.on_saved = on_saved
        self.on_live = on_live
        self.on_check_updates = on_check_updates
        self.win = tk.Toplevel(root)
        self.win.title(t("set.title"))
        self.win.attributes("-topmost", True)
        self.win.resizable(True, True)
        try:
            self.win.transient(root)
        except tk.TclError:
            pass
        self._live_ready = False
        self._build()
        self.win.grab_set()
        self.win.focus_force()
        self.win.protocol("WM_DELETE_WINDOW", self.win.destroy)
        self.win.after(200, self._arm_live)

    def _arm_live(self) -> None:
        self._live_ready = True

    def _scrollable(self, parent: ttk.Frame) -> ttk.Frame:
        """Содержимое вкладки с вертикальной прокруткой. Кнопки Save снаружи."""
        host = ttk.Frame(parent)
        host.pack(fill="both", expand=True)
        canvas = tk.Canvas(host, highlightthickness=0, borderwidth=0)
        scroll = ttk.Scrollbar(host, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = ttk.Frame(canvas, padding=8)
        window = canvas.create_window((0, 0), window=inner, anchor="nw")

        def sync(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all") or (0, 0, 0, 0))
            width = max(1, canvas.winfo_width())
            canvas.itemconfigure(window, width=width)

        def wheel(event) -> None:
            if event.delta:
                canvas.yview_scroll(int(-event.delta / 120), "units")

        inner.bind("<Configure>", sync)
        canvas.bind("<Configure>", sync)
        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", wheel))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))
        return inner

    def _fit_to_screen(self) -> None:
        """На 1080p и с панелью задач окно не должно уезжать кнопкой Save за край."""
        self.win.update_idletasks()
        need_w = max(self.win.winfo_reqwidth(), 560)
        need_h = max(self.win.winfo_reqheight(), 360)
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        # запас под панель задач / верхнюю панель / DPI
        max_w = max(480, sw - 40)
        max_h = max(360, sh - 96)
        width = min(need_w, max_w)
        height = min(need_h, max_h)
        x = max(0, (sw - width) // 2)
        y = max(0, (sh - height) // 4)
        self.win.geometry(f"{width}x{height}+{x}+{y}")
        self.win.minsize(min(520, width), min(360, height))

    def _build(self) -> None:
        pad = {"padx": 10, "pady": 4}
        self.win.columnconfigure(0, weight=1)
        self.win.rowconfigure(0, weight=1)
        outer = ttk.Frame(self.win, padding=(8, 8, 8, 4))
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)
        nb = ttk.Notebook(outer)
        nb.grid(row=0, column=0, sticky="nsew")
        general_tab = ttk.Frame(nb)
        windows_tab = ttk.Frame(nb)
        look_tab = ttk.Frame(nb)
        nb.add(general_tab, text=t("set.tab_general"))
        nb.add(windows_tab, text=t("set.tab_windows"))
        nb.add(look_tab, text=t("set.tab_look"))
        general = self._scrollable(general_tab)
        windows = self._scrollable(windows_tab)
        look = self._scrollable(look_tab)
        self._build_general(general, pad)
        self._build_windows(windows, pad)
        self._build_look(look)
        btns = ttk.Frame(outer)
        btns.grid(row=1, column=0, sticky="ew", pady=(8, 4))
        ttk.Button(btns, text=t("set.cancel"), command=self.win.destroy).pack(side="right", padx=4)
        self._save_btn = ttk.Button(btns, text=t("set.save"), command=self._save)
        self._save_btn.pack(side="right", padx=4)
        self._fit_to_screen()

    def _build_general(self, frm: ttk.Frame, pad: dict) -> None:

        self.journal_dir = StringVar(value=self.cfg.journal_dir or "")
        self.width = IntVar(value=int(self.cfg.width))
        self.allow_network = BooleanVar(value=bool(self.cfg.allow_network))
        self.remote_enabled = BooleanVar(value=bool(self.cfg.remote_enabled))
        self.eddn_enabled = BooleanVar(value=bool(self.cfg.eddn_enabled))
        self.nebulae_enabled = BooleanVar(value=bool(self.cfg.nebulae_enabled))
        self.click_through = BooleanVar(value=bool(self.cfg.click_through))
        self.edsm_api_key = StringVar(value=self.cfg.edsm_api_key or "")
        self.edsm_commander = StringVar(value=self.cfg.edsm_commander or "")
        self.voice_enabled = BooleanVar(value=bool(self.cfg.voice_enabled))
        self.voice_bio = BooleanVar(value=bool(self.cfg.voice_bio))
        self.voice_first_discovery = BooleanVar(value=bool(self.cfg.voice_first_discovery))
        self.voice_dss_range = BooleanVar(value=bool(getattr(self.cfg, "voice_dss_range", True)))
        self.voice_expensive_planets = BooleanVar(
            value=bool(getattr(self.cfg, "voice_expensive_planets", True))
        )
        self.expensive_planet_credits = StringVar(
            value=str(int(getattr(self.cfg, "expensive_planet_credits", 2_500_000) or 2_500_000))
        )
        self.show_belt_clusters = BooleanVar(value=bool(getattr(self.cfg, "show_belt_clusters", True)))
        self.voice_rate = IntVar(value=int(self.cfg.voice_rate or 0))
        mode = str(getattr(self.cfg, "update_check", "auto") or "auto")
        self.update_check = StringVar(value=mode if mode in ("auto", "manual") else "auto")

        row = 0
        ttk.Label(frm, text=t("set.journals")).grid(row=row, column=0, sticky="w", **pad)
        row += 1
        jrow = ttk.Frame(frm)
        jrow.grid(row=row, column=0, columnspan=2, sticky="ew", **pad)
        ttk.Entry(jrow, textvariable=self.journal_dir, width=56).pack(side="left", fill="x", expand=True)
        ttk.Button(jrow, text="…", width=3, command=self._browse_journal).pack(side="left", padx=(6, 0))
        row += 1
        ttk.Label(
            frm,
            text=t("set.journals_hint"),
            foreground="#666",
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=10)
        row += 1

        ttk.Separator(frm).grid(row=row, column=0, columnspan=2, sticky="ew", pady=8)
        row += 1
        ttk.Label(frm, text=t("set.network")).grid(row=row, column=0, sticky="w", **pad)
        row += 1
        ttk.Checkbutton(frm, text=t("set.allow_net"), variable=self.allow_network).grid(
            row=row, column=0, sticky="w", **pad
        )
        row += 1
        ttk.Checkbutton(
            frm, text=t("set.remote"), variable=self.remote_enabled
        ).grid(row=row, column=0, sticky="w", **pad)
        row += 1
        ttk.Checkbutton(frm, text=t("set.eddn"), variable=self.eddn_enabled).grid(
            row=row, column=0, sticky="w", **pad
        )
        row += 1
        ttk.Checkbutton(
            frm, text=t("set.nebulae"), variable=self.nebulae_enabled
        ).grid(row=row, column=0, sticky="w", **pad)
        row += 1

        ttk.Label(frm, text=t("set.cmdr")).grid(row=row, column=0, sticky="w", **pad)
        row += 1
        ttk.Entry(frm, textvariable=self.edsm_commander, width=40).grid(
            row=row, column=0, sticky="w", **pad
        )
        row += 1
        ttk.Label(frm, text=t("set.api")).grid(row=row, column=0, sticky="w", **pad)
        row += 1
        ttk.Entry(frm, textvariable=self.edsm_api_key, width=56, show="•").grid(
            row=row, column=0, columnspan=2, sticky="ew", **pad
        )
        row += 1
        ttk.Label(
            frm,
            text=t("set.api_hint"),
            foreground="#666",
            justify="left",
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=10)
        row += 1
        link = ttk.Frame(frm)
        link.grid(row=row, column=0, sticky="w", **pad)
        ttk.Button(
            link,
            text=t("set.open_api"),
            command=lambda: webbrowser.open("https://www.edsm.net/en/settings/api"),
        ).pack(side="left")
        ttk.Button(link, text=t("set.spansh"), command=lambda: webbrowser.open("https://spansh.co.uk/")).pack(
            side="left", padx=6
        )
        row += 1

        ttk.Separator(frm).grid(row=row, column=0, columnspan=2, sticky="ew", pady=8)
        row += 1
        ttk.Label(frm, text=t("set.voice")).grid(
            row=row, column=0, sticky="w", **pad
        )
        row += 1
        ttk.Checkbutton(frm, text=t("set.voice_on"), variable=self.voice_enabled).grid(
            row=row, column=0, sticky="w", **pad
        )
        row += 1
        ttk.Checkbutton(
            frm, text=t("set.voice_bio"), variable=self.voice_bio
        ).grid(row=row, column=0, sticky="w", **pad)
        row += 1
        ttk.Checkbutton(
            frm, text=t("set.voice_disc"), variable=self.voice_first_discovery
        ).grid(row=row, column=0, sticky="w", **pad)
        row += 1
        ttk.Checkbutton(
            frm, text=t("set.voice_dss"), variable=self.voice_dss_range
        ).grid(row=row, column=0, sticky="w", **pad)
        row += 1
        ttk.Checkbutton(
            frm, text=t("set.voice_rich"), variable=self.voice_expensive_planets
        ).grid(row=row, column=0, sticky="w", **pad)
        row += 1
        erow = ttk.Frame(frm)
        erow.grid(row=row, column=0, sticky="w", **pad)
        ttk.Label(erow, text=t("set.rich_threshold")).pack(side="left")
        ttk.Entry(erow, textvariable=self.expensive_planet_credits, width=14).pack(
            side="left", padx=8
        )
        row += 1
        ttk.Label(
            frm,
            text=t("set.rich_hint"),
            foreground="#666",
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=10)
        row += 1
        vrow = ttk.Frame(frm)
        vrow.grid(row=row, column=0, sticky="w", **pad)
        ttk.Label(vrow, text=t("set.rate")).pack(side="left")
        ttk.Spinbox(vrow, from_=-10, to=10, textvariable=self.voice_rate, width=5).pack(
            side="left", padx=8
        )
        row += 1

        ttk.Separator(frm).grid(row=row, column=0, columnspan=2, sticky="ew", pady=8)
        row += 1
        ttk.Label(frm, text=t("set.overlay")).grid(row=row, column=0, sticky="w", **pad)
        row += 1
        ttk.Checkbutton(
            frm, text=t("set.click"), variable=self.click_through
        ).grid(row=row, column=0, sticky="w", **pad)
        row += 1
        ttk.Checkbutton(
            frm,
            text=t("set.belts"),
            variable=self.show_belt_clusters,
        ).grid(row=row, column=0, sticky="w", **pad)
        row += 1
        wrow = ttk.Frame(frm)
        wrow.grid(row=row, column=0, sticky="w", **pad)
        ttk.Label(wrow, text=t("set.width")).pack(side="left")
        ttk.Spinbox(wrow, from_=600, to=2400, increment=20, textvariable=self.width, width=6).pack(
            side="left", padx=8
        )
        row += 1

        ttk.Separator(frm).grid(row=row, column=0, columnspan=2, sticky="ew", pady=8)
        row += 1
        ttk.Label(frm, text=t("set.updates")).grid(row=row, column=0, sticky="w", **pad)
        row += 1
        ttk.Label(frm, text=t("set.version", version=__version__)).grid(
            row=row, column=0, sticky="w", **pad
        )
        row += 1
        ttk.Radiobutton(
            frm, text=t("set.update_auto"), value="auto", variable=self.update_check
        ).grid(row=row, column=0, sticky="w", **pad)
        row += 1
        ttk.Radiobutton(
            frm, text=t("set.update_manual"), value="manual", variable=self.update_check
        ).grid(row=row, column=0, sticky="w", **pad)
        row += 1
        ttk.Button(frm, text=t("set.update_now"), command=self._check_updates).grid(
            row=row, column=0, sticky="w", **pad
        )
        row += 1
        ttk.Label(frm, text=t("set.update_hint"), foreground="#666", justify="left").grid(
            row=row, column=0, columnspan=2, sticky="w", padx=10
        )

    def _check_updates(self) -> None:
        mode = self.update_check.get()
        self.cfg.update_check = mode if mode in ("auto", "manual") else "auto"
        if self.on_check_updates:
            self.on_check_updates(self.win)

    def _xy_defaults(self) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
        ox = self.cfg.overlay_x if self.cfg.overlay_x is not None else 0
        oy = self.cfg.overlay_y if self.cfg.overlay_y is not None else int(self.cfg.top_offset or 6)
        bx = self.cfg.bio_x if self.cfg.bio_x is not None else 16
        by = self.cfg.bio_y if self.cfg.bio_y is not None else 96
        if self.cfg.main_x is not None and self.cfg.main_y is not None:
            mx, my = int(self.cfg.main_x), int(self.cfg.main_y)
        else:
            mx, my = _geometry_xy(self.cfg.main_geometry or "980x520+80+80")
        return (int(ox), int(oy)), (int(mx), int(my)), (int(bx), int(by))

    def _build_windows(self, frm: ttk.Frame, pad: dict) -> None:
        (ox, oy), (mx, my), (bx, by) = self._xy_defaults()
        self.opacity = DoubleVar(value=_clamp_alpha(self.cfg.opacity))
        self.main_opacity = DoubleVar(value=_clamp_alpha(getattr(self.cfg, "main_opacity", 1.0)))
        self.bio_opacity = DoubleVar(
            value=_clamp_alpha(getattr(self.cfg, "bio_opacity", self.cfg.opacity))
        )
        self.overlay_x = IntVar(value=ox)
        self.overlay_y = IntVar(value=oy)
        self.main_x = IntVar(value=mx)
        self.main_y = IntVar(value=my)
        self.bio_x = IntVar(value=bx)
        self.bio_y = IntVar(value=by)

        ttk.Label(
            frm,
            text=t("set.windows_hint"),
            foreground="#666",
            wraplength=520,
            justify="left",
        ).grid(row=0, column=0, sticky="w", **pad)

        self._window_block(
            frm,
            1,
            t("set.hud_win"),
            self.overlay_x,
            self.overlay_y,
            self.opacity,
            "overlay",
            pad,
        )
        self._window_block(
            frm,
            2,
            t("set.main_win"),
            self.main_x,
            self.main_y,
            self.main_opacity,
            "main",
            pad,
        )
        self._window_block(
            frm,
            3,
            t("set.bio_win"),
            self.bio_x,
            self.bio_y,
            self.bio_opacity,
            "bio",
            pad,
        )

        for var in (
            self.opacity,
            self.main_opacity,
            self.bio_opacity,
            self.overlay_x,
            self.overlay_y,
            self.main_x,
            self.main_y,
            self.bio_x,
            self.bio_y,
        ):
            var.trace_add("write", lambda *_a: self._live_from_fields())

    def _window_block(
        self,
        frm: ttk.Frame,
        row: int,
        title: str,
        x_var: IntVar,
        y_var: IntVar,
        alpha_var: DoubleVar,
        kind: str,
        pad: dict,
    ) -> None:
        box = ttk.LabelFrame(frm, text=title, padding=8)
        box.grid(row=row, column=0, sticky="ew", padx=8, pady=6)
        line = ttk.Frame(box)
        line.pack(fill="x")
        ttk.Label(line, text="X").pack(side="left")
        ttk.Spinbox(line, from_=-200, to=8000, textvariable=x_var, width=7).pack(side="left", padx=(4, 10))
        ttk.Label(line, text="Y").pack(side="left")
        ttk.Spinbox(line, from_=-200, to=8000, textvariable=y_var, width=7).pack(side="left", padx=(4, 10))
        ttk.Label(line, text=t("set.opacity")).pack(side="left", padx=(8, 0))
        ttk.Spinbox(
            line, from_=0.25, to=1.0, increment=0.05, textvariable=alpha_var, width=6
        ).pack(side="left", padx=4)

        pad_fr = ttk.Frame(box)
        pad_fr.pack(pady=(8, 0))
        ttk.Button(pad_fr, text="↑", width=3, command=lambda: self._nudge(kind, 0, -NUDGE_STEP)).grid(
            row=0, column=1, padx=2, pady=2
        )
        ttk.Button(pad_fr, text="←", width=3, command=lambda: self._nudge(kind, -NUDGE_STEP, 0)).grid(
            row=1, column=0, padx=2, pady=2
        )
        ttk.Button(pad_fr, text="↓", width=3, command=lambda: self._nudge(kind, 0, NUDGE_STEP)).grid(
            row=1, column=1, padx=2, pady=2
        )
        ttk.Button(pad_fr, text="→", width=3, command=lambda: self._nudge(kind, NUDGE_STEP, 0)).grid(
            row=1, column=2, padx=2, pady=2
        )

    def _nudge(self, kind: str, dx: int, dy: int) -> None:
        if kind == "overlay":
            self.overlay_x.set(int(self.overlay_x.get()) + dx)
            self.overlay_y.set(int(self.overlay_y.get()) + dy)
        elif kind == "main":
            self.main_x.set(int(self.main_x.get()) + dx)
            self.main_y.set(int(self.main_y.get()) + dy)
        else:
            self.bio_x.set(int(self.bio_x.get()) + dx)
            self.bio_y.set(int(self.bio_y.get()) + dy)
        self._write_window_fields()
        self._emit_live()

    def _live_from_fields(self) -> None:
        if not self._live_ready:
            return
        try:
            self._write_window_fields()
        except (tk.TclError, ValueError, TypeError):
            return
        self._emit_live()

    def _write_window_fields(self) -> None:
        self.cfg.opacity = _clamp_alpha(self.opacity.get())
        self.cfg.main_opacity = _clamp_alpha(self.main_opacity.get())
        self.cfg.bio_opacity = _clamp_alpha(self.bio_opacity.get())
        self.cfg.overlay_x = int(self.overlay_x.get())
        self.cfg.overlay_y = int(self.overlay_y.get())
        self.cfg.main_x = int(self.main_x.get())
        self.cfg.main_y = int(self.main_y.get())
        self.cfg.bio_x = int(self.bio_x.get())
        self.cfg.bio_y = int(self.bio_y.get())

    def _emit_live(self) -> None:
        if self.on_live:
            try:
                self.on_live(self.cfg)
            except Exception:
                pass

    def _font_names(self) -> list[str]:
        from tkinter import font as tkfont

        names = sorted({name for name in tkfont.families(self.win) if name and not name.startswith("@")})
        return names or ["Consolas", "Segoe UI"]

    def _build_look(self, frm: ttk.Frame) -> None:
        families = self._font_names()
        self.theme = StringVar(value=self.cfg.theme if self.cfg.theme in config.THEMES else "dark")
        self.font_family = StringVar(value=self.cfg.font_family or "Consolas")
        self.font_size = IntVar(value=int(self.cfg.font_size or 11))
        self.ui_font_family = StringVar(value=self.cfg.ui_font_family or "Segoe UI")
        self.ui_font_size = IntVar(value=int(self.cfg.ui_font_size or 9))
        self.color_vars: dict[str, StringVar] = {}
        self._swatches: dict[str, tk.Label] = {}

        row = 0
        ttk.Label(frm, text=t("set.theme")).grid(row=row, column=0, sticky="w", padx=8, pady=4)
        theme = ttk.Combobox(
            frm,
            textvariable=self.theme,
            values=("dark", "light"),
            state="readonly",
            width=18,
        )
        theme.grid(row=row, column=1, sticky="w", padx=8, pady=4)
        theme.bind("<<ComboboxSelected>>", lambda _e: self._apply_theme_to_fields())
        ttk.Label(frm, text=t("set.theme_hint")).grid(
            row=row, column=2, columnspan=2, sticky="w"
        )
        row += 1

        self._font_row(frm, row, t("set.font_overlay"), self.font_family, self.font_size, families, 8, 32)
        row += 1
        self._font_row(frm, row, t("set.font_ui"), self.ui_font_family, self.ui_font_size, families, 8, 24)
        row += 1
        ttk.Label(
            frm,
            text=t("set.palette_hint"),
            foreground="#666",
        ).grid(row=row, column=0, columnspan=4, sticky="w", padx=8, pady=(0, 6))
        row += 1

        for index, (key, title) in enumerate(COLOR_FIELDS):
            grid_row = row + index // 2
            grid_col = (index % 2) * 2
            self._color_row(frm, grid_row, grid_col, key, title)

    def _font_row(self, frm, row, title, family_var, size_var, families, lo, hi) -> None:
        ttk.Label(frm, text=title).grid(row=row, column=0, sticky="w", padx=8, pady=4)
        box = ttk.Combobox(frm, textvariable=family_var, values=families, width=28)
        box.grid(row=row, column=1, sticky="w", padx=8, pady=4)
        ttk.Label(frm, text=t("set.size")).grid(row=row, column=2, sticky="e", padx=(8, 0))
        ttk.Spinbox(frm, from_=lo, to=hi, textvariable=size_var, width=5).grid(
            row=row, column=3, sticky="w", padx=8, pady=4
        )

    def _color_row(self, frm, row, col, key: str, title: str) -> None:
        var = StringVar(value=self.cfg.color(key))
        self.color_vars[key] = var
        ttk.Label(frm, text=t(title)).grid(row=row, column=col, sticky="w", padx=8, pady=2)
        cell = ttk.Frame(frm)
        cell.grid(row=row, column=col + 1, sticky="w", padx=8, pady=2)
        ttk.Entry(cell, textvariable=var, width=10).pack(side="left")
        swatch = tk.Label(cell, text="    ", bg=self._safe_color(var.get()), relief="solid", bd=1)
        swatch.pack(side="left", padx=4)
        self._swatches[key] = swatch
        ttk.Button(cell, text=t("set.pick"), width=8, command=lambda k=key: self._pick_color(k)).pack(side="left")
        var.trace_add("write", lambda *_a, k=key: self._paint_swatch(k))

    def _safe_color(self, value: str) -> str:
        parsed = _parse_color(value)
        return parsed or "#888888"

    def _paint_swatch(self, key: str) -> None:
        swatch = self._swatches.get(key)
        if swatch is None:
            return
        try:
            swatch.configure(bg=self._safe_color(self.color_vars[key].get()))
        except tk.TclError:
            pass

    def _pick_color(self, key: str) -> None:
        current = self._safe_color(self.color_vars[key].get())
        chosen = colorchooser.askcolor(color=current, parent=self.win, title=t("set.color_title"))
        if chosen and chosen[1]:
            self.color_vars[key].set(chosen[1])

    def _apply_theme_to_fields(self) -> None:
        colors = config.palette(self.theme.get())
        for key, var in self.color_vars.items():
            if key in colors:
                var.set(colors[key])

    def _read_look(self) -> str | None:
        theme = self.theme.get().strip()
        if theme not in config.THEMES:
            return t("set.err_theme")
        family = self.font_family.get().strip()
        ui_family = self.ui_font_family.get().strip()
        if not family or not ui_family:
            return t("set.err_font")
        try:
            size = int(self.font_size.get())
            ui_size = int(self.ui_font_size.get())
        except (tk.TclError, ValueError):
            return t("set.err_size")
        colors = config.palette(theme)
        for key, title in COLOR_FIELDS:
            parsed = _parse_color(self.color_vars[key].get())
            if parsed is None:
                return t("set.err_color", title=t(title))
            colors[key] = parsed
        self.cfg.theme = theme
        self.cfg.font_family = family
        self.cfg.font_size = max(8, min(32, size))
        self.cfg.ui_font_family = ui_family
        self.cfg.ui_font_size = max(8, min(24, ui_size))
        self.cfg.colors = colors
        return None

    def _browse_journal(self) -> None:
        path = filedialog.askdirectory(parent=self.win, title=t("set.browse"))
        if path:
            self.journal_dir.set(path)

    def _save(self) -> None:
        journal = self.journal_dir.get().strip()
        self.cfg.journal_dir = journal or None
        if self.cfg.journal_dir:
            p = Path(self.cfg.journal_dir)
            if not p.is_dir():
                messagebox.showerror("EDHUD", t("set.err_dir", path=p), parent=self.win)
                return
        try:
            self._write_window_fields()
            self.cfg.width = max(400, min(3000, int(self.width.get())))
        except (tk.TclError, ValueError, TypeError):
            messagebox.showerror("EDHUD", t("set.err_nums"), parent=self.win)
            return
        self.cfg.allow_network = bool(self.allow_network.get())
        self.cfg.remote_enabled = bool(self.remote_enabled.get())
        self.cfg.eddn_enabled = bool(self.eddn_enabled.get())
        self.cfg.nebulae_enabled = bool(self.nebulae_enabled.get())
        self.cfg.click_through = bool(self.click_through.get())
        self.cfg.edsm_api_key = self.edsm_api_key.get().strip()
        self.cfg.edsm_commander = self.edsm_commander.get().strip()
        self.cfg.voice_enabled = bool(self.voice_enabled.get())
        self.cfg.voice_bio = bool(self.voice_bio.get())
        self.cfg.voice_first_discovery = bool(self.voice_first_discovery.get())
        self.cfg.voice_dss_range = bool(self.voice_dss_range.get())
        self.cfg.voice_expensive_planets = bool(self.voice_expensive_planets.get())
        try:
            raw = self.expensive_planet_credits.get().replace(" ", "").replace(",", "")
            self.cfg.expensive_planet_credits = max(0, int(raw))
        except (TypeError, ValueError):
            messagebox.showerror(
                "EDHUD",
                t("set.err_credits"),
                parent=self.win,
            )
            return
        self.cfg.show_belt_clusters = bool(self.show_belt_clusters.get())
        mode = self.update_check.get()
        self.cfg.update_check = mode if mode in ("auto", "manual") else "auto"
        self.cfg.voice_rate = max(-10, min(10, int(self.voice_rate.get())))
        look_error = self._read_look()
        if look_error:
            messagebox.showerror("EDHUD", look_error, parent=self.win)
            return
        try:
            self.cfg.save()
        except OSError as exc:
            messagebox.showerror("EDHUD", t("set.err_save", error=exc), parent=self.win)
            return
        if self.on_saved:
            self.on_saved(self.cfg)
        self.win.destroy()
