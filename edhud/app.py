# Edited by nc.ai 0.8.8.0 on macbook 2026-10-17 20:13:24
"""Связка: журналы -> состояние -> HUD (tkinter-оверлей или терминал)."""
from __future__ import annotations

import queue
import threading
import time
from pathlib import Path

from . import demo, galaxy, hudmodel, remote
from .config import Config
from .hotkeys import Hotkeys
from .journal import JournalWatcher
from .model import GameState
from .route import Route
from .store import SystemStore
from .tui import run_tui

SAVE_INTERVAL = 20.0
FULLSCREEN_HINT = "полноэкранный режим: если оверлея не видно — Alt+Enter (Borderless)"


class App:
    def __init__(
        self,
        cfg: Config,
        ui: str = "overlay",
        expanded: bool | None = None,
        journal_dir: str | Path | None = None,
        demo_speed: float | None = None,
    ) -> None:
        self.cfg = cfg
        self.ui = ui
        self.expanded = cfg.expanded if expanded is None else expanded
        self.journal_dir = Path(journal_dir) if journal_dir else cfg.resolved_journal_dir()
        self.state = GameState()
        self.store = SystemStore()
        self.remote_client = (
            remote.RemoteClient(ttl=float(cfg.remote_ttl_sec), timeout=float(cfg.remote_timeout))
            if cfg.remote_enabled
            else None
        )
        self.watcher: JournalWatcher | None = None
        self.overlay = None
        self.hotkeys: Hotkeys | None = None
        self.demo_player: demo.DemoPlayer | None = None
        self.demo_speed = demo_speed
        self._cached_for: int | None = None
        self._remote_for: int | None = None
        self._remote_results: queue.Queue = queue.Queue()
        self._last_save = 0.0
        self._stop = threading.Event()

    # ------------------------------------------------------------------ setup
    def prepare(self) -> bool:
        if self.journal_dir is None:
            return False
        try:
            self.journal_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False
        return True

    def load_locked_route(self) -> None:
        path = self.cfg.locked_route
        if not path:
            return
        route_path = Path(path).expanduser()
        if not route_path.exists():
            return
        try:
            self.state.route = Route.load(route_path)
            self.state.route.locked = True
        except (OSError, ValueError, KeyError):
            pass

    def start(self) -> None:
        assert self.journal_dir is not None
        self.load_locked_route()
        if self.demo_speed is not None:
            self.demo_player = demo.DemoPlayer(self.journal_dir, self.demo_speed)
            self.demo_player.start()
        self.watcher = JournalWatcher(
            self.journal_dir,
            self.state,
            poll_journal=self.cfg.journal_poll_sec,
            poll_status=self.cfg.status_poll_sec,
            on_event=self._on_event,
        )
        self.watcher.start()
        self._warm_nebulae()

    def _warm_nebulae(self) -> None:
        """Каталог туманностей нужен критериям `nebulae [...]` — качаем в фоне."""
        if not (self.cfg.nebulae_enabled and self.cfg.allow_network):
            return

        def work() -> None:
            try:
                galaxy.download_nebulae()
            except Exception:
                pass

        threading.Thread(target=work, name="edhud-nebulae", daemon=True).start()

    def _on_event(self, event: dict) -> None:
        if event.get("event") != "FSDJump":
            return
        if not self.cfg.copy_next_system or self.overlay is None:
            return
        if self.state.route.source == "game":
            return
        hop = self.state.route.next_hop(self.state.system.name)
        if hop is not None:
            self.overlay.copy_to_clipboard(hop.system)

    # ------------------------------------------------------------------- loop
    def tick(self) -> None:
        self.sync_system()
        self.collect_remote()
        self.autosave()
        if self.overlay is not None:
            view = hudmodel.build_view(
                self.state, self.cfg, expanded=self.expanded, hint=self.hint()
            )
            self.overlay.set_view(view)

    def hint(self) -> str | None:
        if self.overlay is None or not self.cfg.warn_fullscreen:
            return None
        if getattr(self.overlay, "fullscreen", None) is True:
            return FULLSCREEN_HINT
        return None

    def sync_system(self) -> None:
        """Кэш своих систем + запуск догрузки от других командиров."""
        address = self.state.system.address
        if not address or address == self._cached_for:
            return
        cached = self.store.load(address, self.state.system.name)
        if cached is not None:
            for body_id, body in cached.bodies.items():
                self.state.system.bodies.setdefault(body_id, body)
            if cached.remote_sources:
                self.state.system.remote_sources = list(cached.remote_sources)
            self.state.system.remote_scan_value = self.state.system.remote_scan_value or cached.remote_scan_value
            self.state.system.remote_mapped_value = (
                self.state.system.remote_mapped_value or cached.remote_mapped_value
            )
        self._cached_for = address
        self._start_remote(address, self.state.system.name)

    def _start_remote(self, address: int, name: str | None) -> None:
        if self.remote_client is None or not name:
            return
        if self._remote_for == address:
            return
        self._remote_for = address

        def work() -> None:
            try:
                result = self.remote_client.fetch(name, address)
            except Exception:
                result = None
            if result is not None:
                self._remote_results.put(result)

        threading.Thread(target=work, name="edhud-remote", daemon=True).start()

    def collect_remote(self) -> None:
        while True:
            try:
                result = self._remote_results.get_nowait()
            except queue.Empty:
                return
            current = self.state.system.address
            if current and result.address and result.address != current:
                continue  # система уже сменилась
            added = remote.merge_into_system(self.state.system, result)
            if added:
                self.store.save(self.state.system)

    def autosave(self) -> None:
        now = time.time()
        if now - self._last_save < SAVE_INTERVAL:
            return
        self._last_save = now
        if self.state.system.address and self.state.system.bodies:
            self.store.save(self.state.system)

    # -------------------------------------------------------------------- UI
    def _start_overlay(self) -> None:
        from .overlay import Overlay

        self.overlay = Overlay(
            self.cfg,
            on_expanded=self.toggle_expanded,
            on_click_through=self.toggle_click_through,
            on_visible=self.toggle_visible,
        )
        bindings = {
            0x77: self.toggle_expanded,  # F8
            0x78: self.toggle_click_through,  # F9
            0x79: self.toggle_visible,  # F10
        }
        self.hotkeys = Hotkeys(bindings)
        self.hotkeys.start()

    def toggle_expanded(self) -> None:
        self.expanded = not self.expanded
        self.cfg.expanded = self.expanded

    def toggle_click_through(self) -> None:
        self.cfg.click_through = not self.cfg.click_through
        if self.overlay is not None:
            self.overlay.cfg.click_through = self.cfg.click_through
            self.overlay._apply_click_through()

    def toggle_visible(self) -> None:
        if self.overlay is not None:
            self.overlay.toggle_visible()

    def run(self) -> int:
        if not self.prepare():
            print("Не найден каталог журналов Elite Dangerous.")
            print('Укажите его: run.py run --journal-dir "..."')
            return 2
        if self.ui == "tui":
            self.start()
            try:
                run_tui(self.state, self.cfg, expanded=self.expanded)
            finally:
                self.shutdown()
            return 0

        self._start_overlay()
        self.start()
        assert self.overlay is not None

        def loop() -> None:
            if self._stop.is_set():
                return
            self.tick()
            self.overlay.root.after(200, loop)

        loop()
        try:
            self.overlay.run()
        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown()
        return 0

    def shutdown(self) -> None:
        self._stop.set()
        if self.watcher is not None:
            self.watcher.stop()
        if self.demo_player is not None:
            self.demo_player.stop()
        if self.hotkeys is not None:
            self.hotkeys.stop()
        if self.state.system.address and self.state.system.bodies:
            self.store.save(self.state.system)
        try:
            self.cfg.save()
        except OSError:
            pass


def dump(journal_dir: str | Path) -> list[str]:
    """Печатает текущее состояние HUD по журналам (без окна)."""
    from .journal import load_snapshot

    state = load_snapshot(Path(journal_dir))
    cfg = Config()
    view = hudmodel.build_view(state, cfg, expanded=True)
    lines = [
        f"командир: {state.cmdr or '—'} · корабль: {state.ship or '—'}",
        f"система: {state.system.name or '—'} ({state.system.address or '—'}), тел: {len(state.system.bodies)}",
        "",
    ]
    return lines + view.plain()
