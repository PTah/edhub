# Edited by nc.ai 0.8.8.0 on macbook 2026-10-17 20:13:17
"""Конфигурация приложения и пути к данным/журналам.

Логика поиска каталога журналов повторяет то, что делает EDMarketConnector
(config/windows.py: FOLDERID_SavedGames / "Frontier Developments" / "Elite Dangerous"),
с добавлением macOS/Linux (Proton) вариантов.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

APP_NAME = "EDHUD"

DEFAULT_COLORS: dict[str, str] = {
    "bg": "#05070a",
    "panel": "#0b1018",
    "fg": "#ff7100",
    "dim": "#7a5220",
    "text": "#e6e6e6",
    "muted": "#8a94a6",
    "accent": "#54dfed",
    "ok": "#7ddb6a",
    "warn": "#ffd24a",
    "bad": "#ff5f56",
    "shadow": "#000000",
}


def app_dir() -> Path:
    """Каталог для настроек и кэша."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
        return base / "EliteDangerousHUD"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "EliteDangerousHUD"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "edhud"


def data_dir() -> Path:
    """Каталог с вендоренными данными (bio-criteria, регионы, кодекс)."""
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle) / "data"
    return Path(__file__).resolve().parent.parent / "data"


def config_path() -> Path:
    return app_dir() / "config.json"


def journal_dir_candidates() -> list[Path]:
    home = Path.home()
    saved = "Frontier Developments/Elite Dangerous"
    cands: list[Path] = []
    if sys.platform == "win32":
        base = os.environ.get("USERPROFILE")
        if base:
            cands.append(Path(base) / "Saved Games" / saved)
    cands.append(home / "Saved Games" / saved)
    cands.append(home / "Library/Application Support" / saved)
    # Steam / Proton
    steam_roots = [
        home / ".steam/steam",
        home / ".local/share/Steam",
        home / ".var/app/com.valvesoftware.Steam/data/Steam",
    ]
    for root in steam_roots:
        cands.append(
            root
            / "steamapps/compatdata/359320/pfx/drive_c/users/steamuser/Saved Games"
            / saved
        )
    return cands


def find_journal_dir() -> Path | None:
    for cand in journal_dir_candidates():
        try:
            if cand.is_dir() and any(cand.glob("Journal*.log")):
                return cand
        except OSError:
            continue
    for cand in journal_dir_candidates():
        if cand.is_dir():
            return cand
    return None


@dataclass
class Config:
    journal_dir: str | None = None
    # оверлей
    click_through: bool = True
    opacity: float = 0.90
    width: int = 1180
    top_offset: int = 6
    font_family: str = "Consolas"
    font_size: int = 11
    expanded: bool = False
    show_predictions: bool = True
    max_predictions: int = 6
    hide_delay_sec: float = 0.0
    overlay_x: int | None = None
    overlay_y: int | None = None
    copy_next_system: bool = False
    # поведение
    journal_poll_sec: float = 0.25
    status_poll_sec: float = 0.5
    allow_network: bool = True
    # догрузка тел от других командиров (EDSM + Spansh/EDDN)
    remote_enabled: bool = True
    remote_ttl_sec: int = 6 * 3600
    remote_timeout: float = 10.0
    # каталог туманностей для критериев биологии
    nebulae_enabled: bool = True
    # Windows: держать окно поверх всех и подсказывать про fullscreen
    keep_topmost: bool = True
    warn_fullscreen: bool = True
    locked_route: str | None = None
    colors: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_COLORS))

    # ---------------------------------------------------------------- пути
    def resolved_journal_dir(self) -> Path | None:
        if self.journal_dir:
            p = Path(self.journal_dir).expanduser()
            return p if p.is_dir() else None
        return find_journal_dir()

    # ---------------------------------------------------------------- IO
    def to_dict(self) -> dict:
        return asdict(self)

    def merged(self, data: dict) -> "Config":
        known = {f.name for f in fields(self)}
        for key, value in data.items():
            if key == "colors" and isinstance(value, dict):
                colors = dict(DEFAULT_COLORS)
                colors.update({k: str(v) for k, v in value.items()})
                self.colors = colors
            elif key in known:
                setattr(self, key, value)
        return self

    def save(self, path: Path | None = None) -> Path:
        path = path or config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        cfg = cls()
        path = path or config_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cfg
        if isinstance(data, dict):
            cfg.merged(data)
        return cfg

    # ---------------------------------------------------------------- цвета
    def color(self, key: str) -> str:
        return self.colors.get(key) or DEFAULT_COLORS.get(key, "#ffffff")
