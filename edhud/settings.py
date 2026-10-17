"""Окно настроек EDHUD (tkinter)."""
from __future__ import annotations

import webbrowser
from pathlib import Path
from tkinter import BooleanVar, DoubleVar, IntVar, StringVar, filedialog, messagebox, ttk
import tkinter as tk

from . import config


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
        frm = ttk.Frame(self.win, padding=12)
        frm.grid(row=0, column=0, sticky="nsew")

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
        row += 1

        btns = ttk.Frame(frm)
        btns.grid(row=row, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(btns, text="Отмена", command=self.win.destroy).pack(side="right", padx=4)
        ttk.Button(btns, text="Сохранить", command=self._save).pack(side="right", padx=4)

        self.win.update_idletasks()
        w, h = self.win.winfo_width(), self.win.winfo_height()
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        self.win.geometry(f"+{(sw - w) // 2}+{(sh - h) // 3}")

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
        try:
            self.cfg.save()
        except OSError as exc:
            messagebox.showerror("EDHUD", f"Не удалось сохранить:\n{exc}", parent=self.win)
            return
        if self.on_saved:
            self.on_saved(self.cfg)
        self.win.destroy()
