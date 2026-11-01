"""Окно настроек EDHUD (tkinter)."""
from __future__ import annotations

import webbrowser
from pathlib import Path
from tkinter import BooleanVar, DoubleVar, IntVar, StringVar, colorchooser, filedialog, messagebox, ttk
import tkinter as tk

from . import config

# Подписи цветов в разделе «Оформление». Первые — текст, дальше заливки.
COLOR_FIELDS = (
    ("fg", "Заголовок"),
    ("text", "Основной текст"),
    ("muted", "Приглушённый"),
    ("dim", "Линии"),
    ("accent", "Акцент"),
    ("ok", "Био / успех"),
    ("warn", "Предупреждение"),
    ("bad", "Ошибка"),
    ("bg", "Фон"),
    ("panel", "Панели"),
    ("row", "Строки таблицы"),
    ("sel", "Выделение"),
)


def _parse_color(value: str) -> str | None:
    text = (value or "").strip()
    if not text.startswith("#"):
        text = "#" + text
    if len(text) == 4 and all(ch in "0123456789abcdefABCDEF" for ch in text[1:]):
        text = "#" + "".join(ch * 2 for ch in text[1:])
    if len(text) == 7 and all(ch in "0123456789abcdefABCDEF" for ch in text[1:]):
        return text.lower()
    return None


class SettingsDialog:
    """Модальное окно настроек."""

    def __init__(self, root: tk.Misc, cfg: config.Config, on_saved=None) -> None:
        self.cfg = cfg
        self.on_saved = on_saved
        self.win = tk.Toplevel(root)
        self.win.title("EDHUD — настройки")
        self.win.attributes("-topmost", True)
        self.win.resizable(False, False)
        try:
            self.win.transient(root)
        except tk.TclError:
            pass
        self._build()
        self.win.grab_set()
        self.win.focus_force()
        self.win.protocol("WM_DELETE_WINDOW", self.win.destroy)

    def _build(self) -> None:
        pad = {"padx": 10, "pady": 4}
        outer = ttk.Frame(self.win, padding=(8, 8, 8, 4))
        outer.grid(row=0, column=0, sticky="nsew")
        nb = ttk.Notebook(outer)
        nb.grid(row=0, column=0, sticky="nsew")
        general = ttk.Frame(nb, padding=8)
        look = ttk.Frame(nb, padding=8)
        nb.add(general, text="Общее")
        nb.add(look, text="Оформление")
        self._build_general(general, pad)
        self._build_look(look)
        btns = ttk.Frame(outer)
        btns.grid(row=1, column=0, sticky="e", pady=(8, 4))
        ttk.Button(btns, text="Отмена", command=self.win.destroy).pack(side="right", padx=4)
        ttk.Button(btns, text="Сохранить", command=self._save).pack(side="right", padx=4)
        self.win.update_idletasks()
        w, h = self.win.winfo_width(), self.win.winfo_height()
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        self.win.geometry(f"+{(sw - w) // 2}+{max(0, (sh - h) // 3)}")

    def _build_general(self, frm: ttk.Frame, pad: dict) -> None:

        self.journal_dir = StringVar(value=self.cfg.journal_dir or "")
        self.opacity = DoubleVar(value=float(self.cfg.opacity))
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
        self.voice_rate = IntVar(value=int(self.cfg.voice_rate or 0))

        row = 0
        ttk.Label(frm, text="Журналы Elite Dangerous").grid(row=row, column=0, sticky="w", **pad)
        row += 1
        jrow = ttk.Frame(frm)
        jrow.grid(row=row, column=0, columnspan=2, sticky="ew", **pad)
        ttk.Entry(jrow, textvariable=self.journal_dir, width=56).pack(side="left", fill="x", expand=True)
        ttk.Button(jrow, text="…", width=3, command=self._browse_journal).pack(side="left", padx=(6, 0))
        row += 1
        ttk.Label(
            frm,
            text="Пусто = автопоиск Saved Games\\Frontier Developments\\Elite Dangerous",
            foreground="#666",
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=10)
        row += 1

        ttk.Separator(frm).grid(row=row, column=0, columnspan=2, sticky="ew", pady=8)
        row += 1
        ttk.Label(frm, text="Сеть и данные других командиров").grid(row=row, column=0, sticky="w", **pad)
        row += 1
        ttk.Checkbutton(frm, text="Разрешить сеть", variable=self.allow_network).grid(
            row=row, column=0, sticky="w", **pad
        )
        row += 1
        ttk.Checkbutton(
            frm, text="EDSM + Spansh (догрузка тел системы)", variable=self.remote_enabled
        ).grid(row=row, column=0, sticky="w", **pad)
        row += 1
        ttk.Checkbutton(frm, text="Живой фид EDDN", variable=self.eddn_enabled).grid(
            row=row, column=0, sticky="w", **pad
        )
        row += 1
        ttk.Checkbutton(
            frm, text="Каталог туманностей (для био-прогноза)", variable=self.nebulae_enabled
        ).grid(row=row, column=0, sticky="w", **pad)
        row += 1

        ttk.Label(frm, text="EDSM — Commander Name").grid(row=row, column=0, sticky="w", **pad)
        row += 1
        ttk.Entry(frm, textvariable=self.edsm_commander, width=40).grid(
            row=row, column=0, sticky="w", **pad
        )
        row += 1
        ttk.Label(frm, text="EDSM — API Key").grid(row=row, column=0, sticky="w", **pad)
        row += 1
        ttk.Entry(frm, textvariable=self.edsm_api_key, width=56, show="•").grid(
            row=row, column=0, columnspan=2, sticky="ew", **pad
        )
        row += 1
        ttk.Label(
            frm,
            text="Как на edsm.net → Settings → API: Commander Name + API Key.\n"
            "Нужны для личных данных командира. Публичные тела/стоимость — и без ключа.",
            foreground="#666",
            justify="left",
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=10)
        row += 1
        link = ttk.Frame(frm)
        link.grid(row=row, column=0, sticky="w", **pad)
        ttk.Button(
            link,
            text="Открыть EDSM API",
            command=lambda: webbrowser.open("https://www.edsm.net/en/settings/api"),
        ).pack(side="left")
        ttk.Button(link, text="Spansh", command=lambda: webbrowser.open("https://spansh.co.uk/")).pack(
            side="left", padx=6
        )
        row += 1

        ttk.Separator(frm).grid(row=row, column=0, columnspan=2, sticky="ew", pady=8)
        row += 1
        ttk.Label(frm, text="Голосовые оповещения (русский SAPI)").grid(
            row=row, column=0, sticky="w", **pad
        )
        row += 1
        ttk.Checkbutton(frm, text="Включить голос", variable=self.voice_enabled).grid(
            row=row, column=0, sticky="w", **pad
        )
        row += 1
        ttk.Checkbutton(
            frm, text="Биологический сигнал найден", variable=self.voice_bio
        ).grid(row=row, column=0, sticky="w", **pad)
        row += 1
        ttk.Checkbutton(
            frm, text="Система открыта вами", variable=self.voice_first_discovery
        ).grid(row=row, column=0, sticky="w", **pad)
        row += 1
        vrow = ttk.Frame(frm)
        vrow.grid(row=row, column=0, sticky="w", **pad)
        ttk.Label(vrow, text="Скорость речи (−10…10)").pack(side="left")
        ttk.Spinbox(vrow, from_=-10, to=10, textvariable=self.voice_rate, width=5).pack(
            side="left", padx=8
        )
        row += 1

        ttk.Separator(frm).grid(row=row, column=0, columnspan=2, sticky="ew", pady=8)
        row += 1
        ttk.Label(frm, text="Оверлей").grid(row=row, column=0, sticky="w", **pad)
        row += 1
        ttk.Checkbutton(
            frm, text="Сквозной режим мыши по умолчанию", variable=self.click_through
        ).grid(row=row, column=0, sticky="w", **pad)
        row += 1
        orow = ttk.Frame(frm)
        orow.grid(row=row, column=0, sticky="w", **pad)
        ttk.Label(orow, text="Прозрачность").pack(side="left")
        ttk.Spinbox(orow, from_=0.3, to=1.0, increment=0.05, textvariable=self.opacity, width=6).pack(
            side="left", padx=8
        )
        ttk.Label(orow, text="Ширина").pack(side="left", padx=(12, 0))
        ttk.Spinbox(orow, from_=600, to=2400, increment=20, textvariable=self.width, width=6).pack(
            side="left", padx=8
        )

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
        ttk.Label(frm, text="Тема").grid(row=row, column=0, sticky="w", padx=8, pady=4)
        theme = ttk.Combobox(
            frm,
            textvariable=self.theme,
            values=("dark", "light"),
            state="readonly",
            width=18,
        )
        theme.grid(row=row, column=1, sticky="w", padx=8, pady=4)
        theme.bind("<<ComboboxSelected>>", lambda _e: self._apply_theme_to_fields())
        ttk.Label(frm, text="dark — тёмная, light — светлая").grid(
            row=row, column=2, columnspan=2, sticky="w"
        )
        row += 1

        self._font_row(frm, row, "Шрифт оверлея", self.font_family, self.font_size, families, 8, 32)
        row += 1
        self._font_row(frm, row, "Шрифт окна", self.ui_font_family, self.ui_font_size, families, 8, 24)
        row += 1
        ttk.Label(
            frm,
            text="Смена темы подставляет палитру. Отдельные цвета можно поправить и сохранить.",
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
        ttk.Label(frm, text="размер").grid(row=row, column=2, sticky="e", padx=(8, 0))
        ttk.Spinbox(frm, from_=lo, to=hi, textvariable=size_var, width=5).grid(
            row=row, column=3, sticky="w", padx=8, pady=4
        )

    def _color_row(self, frm, row, col, key: str, title: str) -> None:
        var = StringVar(value=self.cfg.color(key))
        self.color_vars[key] = var
        ttk.Label(frm, text=title).grid(row=row, column=col, sticky="w", padx=8, pady=2)
        cell = ttk.Frame(frm)
        cell.grid(row=row, column=col + 1, sticky="w", padx=8, pady=2)
        ttk.Entry(cell, textvariable=var, width=10).pack(side="left")
        swatch = tk.Label(cell, text="    ", bg=self._safe_color(var.get()), relief="solid", bd=1)
        swatch.pack(side="left", padx=4)
        self._swatches[key] = swatch
        ttk.Button(cell, text="Цвет", width=6, command=lambda k=key: self._pick_color(k)).pack(side="left")
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
        chosen = colorchooser.askcolor(color=current, parent=self.win, title="Цвет")
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
            return "Тема: dark или light."
        family = self.font_family.get().strip()
        ui_family = self.ui_font_family.get().strip()
        if not family or not ui_family:
            return "Укажите шрифт оверлея и шрифт окна."
        try:
            size = int(self.font_size.get())
            ui_size = int(self.ui_font_size.get())
        except (tk.TclError, ValueError):
            return "Размер шрифта должен быть числом."
        colors = config.palette(theme)
        for key, title in COLOR_FIELDS:
            parsed = _parse_color(self.color_vars[key].get())
            if parsed is None:
                return f"Цвет «{title}» — это #RRGGBB."
            colors[key] = parsed
        self.cfg.theme = theme
        self.cfg.font_family = family
        self.cfg.font_size = max(8, min(32, size))
        self.cfg.ui_font_family = ui_family
        self.cfg.ui_font_size = max(8, min(24, ui_size))
        self.cfg.colors = colors
        return None

    def _browse_journal(self) -> None:
        path = filedialog.askdirectory(parent=self.win, title="Каталог журналов Elite Dangerous")
        if path:
            self.journal_dir.set(path)

    def _save(self) -> None:
        journal = self.journal_dir.get().strip()
        self.cfg.journal_dir = journal or None
        if self.cfg.journal_dir:
            p = Path(self.cfg.journal_dir)
            if not p.is_dir():
                messagebox.showerror("EDHUD", f"Каталог не найден:\n{p}", parent=self.win)
                return
        self.cfg.opacity = max(0.25, min(1.0, float(self.opacity.get())))
        self.cfg.width = max(400, min(3000, int(self.width.get())))
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
        self.cfg.voice_rate = max(-10, min(10, int(self.voice_rate.get())))
        look_error = self._read_look()
        if look_error:
            messagebox.showerror("EDHUD", look_error, parent=self.win)
            return
        try:
            self.cfg.save()
        except OSError as exc:
            messagebox.showerror("EDHUD", f"Не удалось сохранить:\n{exc}", parent=self.win)
            return
        if self.on_saved:
            self.on_saved(self.cfg)
        self.win.destroy()
