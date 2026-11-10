# Edited by nc.ai 0.8.8.0 on macbook 2026-10-17 20:13:24
"""Связка: журналы -> состояние -> HUD (tkinter-оверлей или терминал)."""
from __future__ import annotations

import os
import queue
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import quote

from . import config as config_mod
from . import demo, eddn, edsm_upload, galaxy, hudmodel, remote, spansh, tray
from .alerts import Alert, AlertEngine
from .config import Config
from .hotkeys import Hotkeys
from .journal import JournalWatcher
from .model import GameState
from .route import Route
from .belts import BeltStore
from .store import SystemStore
from .tui import run_tui
from .i18n import t
from .voice import Voice

SAVE_INTERVAL = 20.0


def _system_discoverer_from_remote(result) -> str | None:
    """Первооткрыватель системы: сначала главная звезда, иначе любое тело с discovery."""
    bodies = getattr(result, "bodies", None) or {}
    rows = list(bodies.values()) if isinstance(bodies, dict) else list(bodies)
    for body in rows:
        if (getattr(body, "star_type", None) or getattr(body, "is_star", False)) and getattr(
            body, "discovered_by", None
        ):
            return str(body.discovered_by)
    for body in rows:
        who = getattr(body, "discovered_by", None)
        if who:
            return str(who)
    return None


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
        self.belt_store = BeltStore()
        self.remote_client = self._make_remote_client()
        self.watcher: JournalWatcher | None = None
        self.overlay = None
        self.mainwindow = None
        self.hotkeys: Hotkeys | None = None
        self.tray: tray.TrayIcon | None = None
        self.demo_player: demo.DemoPlayer | None = None
        self.demo_speed = demo_speed
        self.eddn: eddn.EddnListener | None = None
        self.voice = Voice(rate=int(cfg.voice_rate or 0))
        self._update_busy = False
        self.alerts = AlertEngine(on_alert=self._on_alert)
        self.alerts.configure(cfg)
        from . import __version__

        self.edsm = edsm_upload.EdsmUploader(lambda: self.cfg, __version__)
        self._eddn_filter = eddn.SetFilter()
        self._eddn_messages: queue.Queue = queue.Queue(maxsize=512)
        self._cached_for: int | None = None
        self._remote_for: int | None = None
        self._remote_results: queue.Queue = queue.Queue()
        self._last_save = 0.0
        self._stop = threading.Event()
        self._settings_open = False
        self._voice_alert: str | None = None
        self._carrier_lookup: str | None = None
        self._carrier_lookup_at = 0.0
        self._route_disc_busy = False
        self._route_disc_key: tuple | None = None

    def _make_remote_client(self) -> remote.RemoteClient | None:
        if not self.cfg.remote_enabled:
            return None
        return remote.RemoteClient(
            ttl=float(self.cfg.remote_ttl_sec),
            timeout=float(self.cfg.remote_timeout),
            edsm_api_key=self.cfg.edsm_api_key or "",
            edsm_commander=self.cfg.edsm_commander or "",
        )

    # ------------------------------------------------------------------ setup
    def prepare(self) -> bool:
        if self.journal_dir is None:
            # всё равно стартуем: трей + настройки позволят указать каталог
            candidates = config_mod.journal_dir_candidates()
            self.journal_dir = candidates[0] if candidates else config_mod.app_dir() / "journals"
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
            self.state.sync_route_discoverers()
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
            on_status=self._on_status,
            on_catchup_done=self._on_journal_catchup,
        )
        self.watcher.start()
        if self.cfg.voice_enabled:
            self.voice.start()
        self._warm_nebulae()
        self._start_eddn()

    def _start_eddn(self) -> None:
        """Подписка на живой EDDN (нужен только текущий прыжок/система)."""
        if not (self.cfg.eddn_enabled and self.cfg.allow_network):
            return
        self.eddn = eddn.EddnListener(
            endpoint=self.cfg.eddn_endpoint,
            on_message=self._on_eddn_message,
            system_filter=self._eddn_filter,
        )
        self.eddn.start()

    def _on_eddn_message(self, message: dict) -> None:
        try:
            self._eddn_messages.put_nowait(message)
        except queue.Full:
            pass

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

    def _on_journal_catchup(self) -> None:
        """После replay: голос, кэш проб с координатами, снимок на диск, выгрузка на EDSM."""
        self.alerts.arm()
        self._cached_for = None
        self.sync_system()
        self.state.persist_needed = False
        self._save_system_now()
        self.edsm.enable_live(self.journal_dir)

    def _on_alert(self, alert: Alert) -> None:
        if alert.overlay:
            self._voice_alert = alert.overlay
        if self.cfg.voice_enabled:
            self.voice.speak(alert.text)

    def _save_system_now(self) -> None:
        if not self.state.system.address or not self.state.system.bodies:
            return
        if self.watcher is not None and self.watcher.catchup_pending:
            return
        self.store.save(self.state.system)
        self._last_save = time.time()

    def _on_event(self, event: dict) -> None:
        self.alerts.handle(event, self.state)
        self.edsm.note(event, self.state)
        if self.state.persist_needed:
            self.state.persist_needed = False
            self._save_system_now()
        if event.get("event") != "FSDJump":
            return
        if not self.cfg.copy_next_system or self.overlay is None:
            return
        if self.state.route.source == "game":
            return
        hop = self.state.route.next_hop(self.state.system.name)
        if hop is not None:
            self.overlay.copy_to_clipboard(hop.system)

    def _on_status(self) -> None:
        self.alerts.handle_status(self.state)

    # ------------------------------------------------------------------- loop
    def tick(self) -> None:
        try:
            self.sync_system()
            self.collect_remote()
            self.collect_eddn()
            self._lookup_carrier_pos()
            self._lookup_route_discoverers()
            self.autosave()
            if self.overlay is not None:
                view = hudmodel.build_view(
                    self.state, self.cfg, expanded=self.expanded, hint=self.hint()
                )
                if self._voice_alert and not view.alert:
                    view.alert = self._voice_alert
                    self._voice_alert = None
                self.overlay.set_view(view)
                self.overlay.set_bio(hudmodel.build_bio_board(self.state))
                self.overlay.set_planet_dim(self.state.in_atmosphere)
            if self.mainwindow is not None:
                self.mainwindow.update_state(self.state)
        except Exception:
            self._note_tick_error()

    def _note_tick_error(self) -> None:
        """Ошибка кадра не должна останавливать окно: иначе нет ни трея, ни выхода."""
        now = time.time()
        if now - getattr(self, "_tick_error_at", 0.0) < 30:
            return
        self._tick_error_at = now
        try:
            import traceback

            path = config_mod.app_dir() / "error.log"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(traceback.format_exc() + "\n")
        except OSError:
            pass

    def _lookup_route_discoverers(self) -> None:
        """Для хопов маршрута без первооткрывателя — спросить EDSM (пакетами)."""
        if not self.cfg.allow_network or not self.cfg.remote_enabled:
            return
        if self._route_disc_busy:
            return
        pending: list[str] = []
        for hop in self.state.route.hops:
            key = hop.system.lower()
            need_disc = key not in self.state._systems_by_me and key not in self.state._discoverers
            need_stats = key not in self.state._body_stats
            if not need_disc and not need_stats:
                continue
            pending.append(hop.system)
        route_key = tuple(h.system.lower() for h in self.state.route.hops)
        if not pending:
            self._route_disc_key = route_key
            return
        if route_key == self._route_disc_key and not pending:
            return
        batch = pending[:5]
        self._route_disc_busy = True

        def work() -> None:
            results: list[tuple[str, str | None | bool, object | None]] = []
            for name in batch:
                try:
                    who, stats = remote.system_route_info(name)
                    results.append((name, who, stats))
                except Exception:
                    results.append((name, None, None))

            def apply() -> None:
                self._route_disc_busy = False
                me = self.cfg.edsm_commander or self.state.cmdr
                for name, who, stats in results:
                    if who is False:
                        self.state.note_system_discoverer(name, None, cmdr=me)
                    elif isinstance(who, str):
                        self.state.note_system_discoverer(name, who, cmdr=me)
                    if stats is not None:
                        self.state.note_system_body_stats(
                            name,
                            stars=stats.stars if not stats.missing else None,
                            planets=stats.planets if not stats.missing else None,
                            bodies=stats.bodies if not stats.missing else None,
                            missing=bool(stats.missing),
                        )
                self.state.sync_route_discoverers()
                if len(pending) <= len(batch):
                    self._route_disc_key = route_key

            self._ui(apply)

        threading.Thread(target=work, name="edhud-route-disc", daemon=True).start()

    def _lookup_carrier_pos(self) -> None:
        """CarrierLocation/прыжок носителя без StarPos — координаты с EDSM/Spansh."""
        self.state.apply_due_carrier_jump()
        if not self.state.carrier_pos_pending or not self.cfg.allow_network:
            return
        name = self.state.carrier.system
        address = self.state.carrier.address
        if not name and address is None:
            return
        key = (name or "").lower() or str(address)
        now = time.time()
        if key == self._carrier_lookup and now - self._carrier_lookup_at < 45:
            return
        self._carrier_lookup = key
        self._carrier_lookup_at = now

        def work() -> None:
            pos = remote.system_coordinates(name, address=address)

            def apply() -> None:
                current = (self.state.carrier.system or "").lower()
                same_name = bool(name) and current == name.lower()
                same_addr = (
                    address is not None
                    and self.state.carrier.address is not None
                    and int(address) == int(self.state.carrier.address)
                )
                if not (same_name or same_addr):
                    self._carrier_lookup = None
                    return
                if not pos:
                    # сброс ключа — повторим поиск позже
                    self._carrier_lookup = None
                    return
                self.state.carrier.star_pos = pos
                self.state.carrier_pos_pending = False
                self.state._remember_star(self.state.carrier.address, self.state.carrier.system, pos)

            self._ui(apply)

        threading.Thread(target=work, name="edhud-carrier-pos", daemon=True).start()

    def hint(self) -> str | None:
        hints: list[str] = []
        if self.state.legacy:
            hints.append(t("hint.legacy"))
        if (
            self.overlay is not None
            and self.cfg.warn_fullscreen
            and getattr(self.overlay, "fullscreen", None) is True
        ):
            hints.append(t("hint.fullscreen"))
        return " · ".join(hints) if hints else None

    def sync_system(self) -> None:
        """Кэш своих систем + запуск догрузки от других командиров."""
        address = self.state.system.address
        if not address or address == self._cached_for:
            return
        cached = self.store.load(address, self.state.system.name)
        if cached is not None:
            # merge, не setdefault: журнал уже создал тело без sample_pos
            self.state.system.merge_from(cached)
        self._cached_for = address
        self._eddn_filter.update(
            names={self.state.system.name} if self.state.system.name else set(),
            addresses={address},
        )
        self._start_remote(address, self.state.system.name)

    def _start_remote(self, address: int, name: str | None) -> None:
        if self.remote_client is None or not name:
            return
        if self.state.legacy and not self.cfg.remote_in_legacy:
            return  # EDSM — только Live; в Legacy догрузка отключена
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
            who = _system_discoverer_from_remote(result)
            if who and self.state.system.name:
                self.state.note_system_discoverer(
                    self.state.system.name,
                    who,
                    cmdr=self.cfg.edsm_commander or self.state.cmdr,
                )
            if added:
                self.store.save(self.state.system)

    def collect_eddn(self) -> None:
        """Применяет сообщения EDDN к текущей системе (только в главном потоке)."""
        changed = False
        while True:
            try:
                message = self._eddn_messages.get_nowait()
            except queue.Empty:
                break
            if remote.apply_eddn(self.state.system, message):
                changed = True
        if changed:
            self.store.save(self.state.system)

    def autosave(self) -> None:
        if self.watcher is not None and self.watcher.catchup_pending:
            return
        now = time.time()
        if now - self._last_save < SAVE_INTERVAL:
            return
        if self.state.system.address and self.state.system.bodies:
            self.store.save(self.state.system)
            self._last_save = now

    # -------------------------------------------------------------------- UI
    def _ui(self, fn) -> None:
        """Выполнить действие в потоке tkinter."""
        if self.overlay is None:
            return
        try:
            self.overlay.root.after(0, fn)
        except Exception:
            fn()

    def _start_overlay(self) -> None:
        from .overlay import Overlay

        self.overlay = Overlay(
            self.cfg,
            on_expanded=self.toggle_expanded,
            on_click_through=self.toggle_click_through,
            on_visible=self.toggle_visible,
            on_quit=self.request_quit,
            on_settings=self.open_settings,
            system_name_provider=lambda: self.state.system.name,
            system_address_provider=lambda: self.state.system.address,
            carrier_system_provider=lambda: self.state.carrier.system,
            on_copy_carrier=self.copy_system_name,
        )
        bindings = {
            0x77: lambda: self._ui(self.toggle_expanded),  # F8
            0x78: lambda: self._ui(self.toggle_click_through),  # F9
            0x79: lambda: self._ui(self.toggle_visible),  # F10
            0x7B: lambda: self._ui(self.request_quit),  # F12
        }
        self.hotkeys = Hotkeys(bindings)
        self.hotkeys.start()
        from .mainwindow import MainWindow

        self.mainwindow = MainWindow(
            self.overlay.root,
            cfg=self.cfg,
            belt_store=self.belt_store,
            on_copy_system=self.copy_system_name,
            on_copy_carrier=self.copy_system_name,
            on_plot_to_carrier=self.plot_route_to_carrier,
        )
        self.mainwindow.apply_look(self.cfg)
        self.mainwindow.show()
        self._start_tray()

    def _start_tray(self) -> None:
        from . import __version__

        self.tray = tray.TrayIcon(
            on_command=self._on_tray_command,
            tip=t("tray.tip", version=__version__),
            state_provider=self._tray_state,
        )
        self.tray.start()

    def _tray_state(self) -> dict:
        visible = True
        if self.overlay is not None:
            visible = bool(getattr(self.overlay, "_visible", True))
        main_visible = bool(
            self.mainwindow is not None and getattr(self.mainwindow, "_visible", False)
        )
        return {
            "visible": visible,
            "main_visible": main_visible,
            "expanded": self.expanded,
            "click_through": bool(self.cfg.click_through),
        }

    def _on_tray_command(self, command_id: int) -> None:
        # из потока трея — в UI
        mapping = {
            tray.ID_TOGGLE_VISIBLE: self.toggle_visible,
            tray.ID_TOGGLE_MAIN: self.toggle_mainwindow,
            tray.ID_TOGGLE_EXPANDED: self.toggle_expanded,
            tray.ID_TOGGLE_CLICK: self.toggle_click_through,
            tray.ID_OPEN_SPANSH: self.open_spansh_system,
            tray.ID_OPEN_EDSM: self.open_edsm_system,
            tray.ID_OPEN_MAP: self.open_spansh_map,
            tray.ID_SETTINGS: self.open_settings,
            tray.ID_CHECK_UPDATE: lambda: self.check_updates(interactive=True),
            tray.ID_OPEN_CONFIG: self.open_config_folder,
            tray.ID_QUIT: self.request_quit,
        }
        action = mapping.get(command_id)
        if action:
            self._ui(action)

    def toggle_mainwindow(self) -> None:
        if self.mainwindow is not None:
            self.mainwindow.toggle()

    def toggle_expanded(self) -> None:
        self.expanded = not self.expanded
        self.cfg.expanded = self.expanded

    def toggle_click_through(self) -> None:
        self.cfg.click_through = not self.cfg.click_through
        if self.overlay is not None:
            self.overlay.cfg.click_through = self.cfg.click_through
            self.overlay._apply_click_through()
            if self.overlay._view is not None:
                self.overlay._draw(self.overlay._view)

    def toggle_visible(self) -> None:
        if self.overlay is not None:
            self.overlay.toggle_visible()

    def open_spansh_system(self) -> None:
        address = self.state.system.address
        name = self.state.system.name
        if address:
            url = f"https://spansh.co.uk/system/{int(address)}"
        elif name:
            url = f"https://spansh.co.uk/system/{quote(str(name))}"
        else:
            url = "https://spansh.co.uk/"
        webbrowser.open(url)

    def open_edsm_system(self) -> None:
        name = self.state.system.name
        if name:
            url = f"https://www.edsm.net/en/system?systemName={quote(str(name))}"
        else:
            url = "https://www.edsm.net/"
        webbrowser.open(url)

    def open_spansh_map(self) -> None:
        webbrowser.open("https://spansh.co.uk/plotter")

    def copy_system_name(self, name: str | None = None) -> None:
        """Скопировать имя системы в буфер (двойной клик по заголовку / карриеру)."""
        text = (name or "").strip()
        if not text:
            return
        if self.overlay is not None:
            self.overlay.copy_to_clipboard(text)
        elif self.mainwindow is not None:
            self.mainwindow._copy_text(text)

    def plot_route_to_carrier(self) -> None:
        """Маршрут Spansh до карриера в EDHUD (не прокладка в игре; из шапки убран)."""
        start = self.state.system.name
        target = self.state.carrier.system
        if not start or not target:
            self._voice_alert = t("voice.no_route")
            return
        if start.lower() == target.lower():
            self._voice_alert = t("voice.carrier_here")
            return
        if not self.cfg.allow_network:
            self._voice_alert = t("voice.offline")
            return
        if getattr(self, "_plot_busy", False):
            return
        self._plot_busy = True
        self._voice_alert = t("voice.plotting", target=target)
        if self.mainwindow is not None:
            try:
                self.mainwindow.route_info.configure(text=t("win.plotting", target=target))
                self.mainwindow.nb.select(self.mainwindow.tab_route)
            except Exception:
                pass

        def work() -> None:
            error = None
            route = None
            try:
                # 50 ly — типичный исследовательский прыжок; длинные «ноги» = нейтронки Spansh
                route = spansh.plot_route(start, target, range_ly=50.0, efficiency=60.0)
            except Exception as exc:
                error = str(exc)

            def apply() -> None:
                self._plot_busy = False
                if route is not None and route.hops:
                    self.state.route = route
                    self.state.route.locked = True
                    self.state.sync_route_discoverers()
                    self.state.view_tab = "route"
                    jumps = route.total_jumps
                    self._voice_alert = t(
                        "voice.plotted", count=len(route.hops), jumps=jumps
                    )
                else:
                    self._voice_alert = t("voice.plot_fail", error=error or t("voice.empty"))
                    if self.mainwindow is not None:
                        try:
                            self.mainwindow.route_info.configure(
                                text=t("win.plot_fail", error=error or t("voice.empty"))
                            )
                        except Exception:
                            pass

            self._ui(apply)

        threading.Thread(target=work, name="edhud-plot-carrier", daemon=True).start()

    def open_config_folder(self) -> None:
        path = config_mod.app_dir()
        path.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except OSError:
            webbrowser.open(path.as_uri())

    def open_settings(self) -> None:
        if self._settings_open or self.overlay is None:
            return
        from .settings import SettingsDialog

        self._settings_open = True

        def on_saved(cfg: Config) -> None:
            self.cfg = cfg
            self._apply_settings()

        def on_close() -> None:
            self._settings_open = False

        dlg = SettingsDialog(
            self.overlay.root,
            self.cfg,
            on_saved=on_saved,
            on_live=self._apply_window_layout,
            on_check_updates=lambda parent: self.check_updates(interactive=True, parent=parent),
        )
        dlg.win.bind("<Destroy>", lambda e: on_close() if e.widget is dlg.win else None)

    def _apply_window_layout(self, cfg: Config | None = None) -> None:
        """Позиции и прозрачность окон — сразу из настроек / стрелок."""
        if cfg is not None:
            self.cfg = cfg
        if self.overlay is not None:
            self.overlay.cfg = self.cfg
            try:
                self.overlay.move_to(self.cfg.overlay_x, self.cfg.overlay_y)
                self.overlay.apply_opacity()
                self.overlay.bio.cfg = self.cfg
                self.overlay.bio.move_to(self.cfg.bio_x, self.cfg.bio_y)
                self.overlay.bio.apply_opacity()
            except Exception:
                pass
        if self.mainwindow is not None:
            self.mainwindow.cfg = self.cfg
            try:
                self.mainwindow.move_to(self.cfg.main_x, self.cfg.main_y)
                self.mainwindow.apply_opacity()
            except Exception:
                pass

    def _apply_settings(self) -> None:
        """Применить сохранённые настройки на лету."""
        self.remote_client = self._make_remote_client()
        new_journal = self.cfg.resolved_journal_dir()
        if new_journal and new_journal != self.journal_dir:
            self.journal_dir = new_journal
            if self.watcher is not None:
                self.watcher.stop()
                self.alerts.armed = False
                self.watcher = JournalWatcher(
                    self.journal_dir,
                    self.state,
                    poll_journal=self.cfg.journal_poll_sec,
                    poll_status=self.cfg.status_poll_sec,
                    on_event=self._on_event,
                    on_catchup_done=self._on_journal_catchup,
                )
                self.watcher.start()
        self.alerts.configure(self.cfg)
        self.voice.rate = int(self.cfg.voice_rate or 0)
        if self.cfg.voice_enabled:
            self.voice.start()
        if self.overlay is not None:
            self.overlay.cfg = self.cfg
            try:
                self.overlay.apply_opacity()
                self.overlay.bio.cfg = self.cfg
                self.overlay.bio.apply_opacity()
            except Exception:
                pass
            self.overlay._apply_click_through()
            self.overlay._place_window()
            if self.cfg.bio_x is not None or self.cfg.bio_y is not None:
                self.overlay.bio.move_to(self.cfg.bio_x, self.cfg.bio_y)
            self.overlay.refresh_look()
        if self.mainwindow is not None:
            self.mainwindow.apply_look(self.cfg)
        self._apply_window_layout()
        # EDDN: перезапуск при смене флага
        want_eddn = bool(self.cfg.eddn_enabled and self.cfg.allow_network)
        if want_eddn and self.eddn is None:
            self._start_eddn()
        elif not want_eddn and self.eddn is not None:
            self.eddn.stop()
            self.eddn = None

    def check_updates(self, interactive: bool = False, parent=None) -> None:
        """Проверка релиза GitHub. В авторежиме молчит, если новой версии нет."""
        if self._update_busy or self.overlay is None:
            return
        self._update_busy = True
        owner = parent

        def work() -> None:
            from . import update as upd

            try:
                info = upd.check()
            except Exception as exc:
                info = upd.UpdateInfo(current=upd.current_version(), error=str(exc))

            def show() -> None:
                self._update_busy = False
                self._present_update(info, interactive, owner)

            self._ui(show)

        threading.Thread(target=work, name="edhud-update-check", daemon=True).start()

    def _present_update(self, info, interactive: bool, parent) -> None:
        from tkinter import messagebox

        from . import update as upd

        host = parent if parent is not None else (self.overlay.root if self.overlay else None)
        if info.error:
            if interactive:
                messagebox.showerror("EDHUD", t("update.error", error=info.error), parent=host)
            return
        if not info.available:
            if interactive:
                messagebox.showinfo("EDHUD", t("update.none", current=info.current), parent=host)
            return
        notes = (info.notes or "").strip()
        if len(notes) > 700:
            notes = notes[:700].rstrip() + "…"
        if not messagebox.askyesno(
            t("update.title"),
            t("update.available", latest=info.latest, current=info.current, notes=notes or "—"),
            parent=host,
        ):
            return
        if upd.install_kind() == "source":
            if messagebox.askyesno("EDHUD", t("update.source"), parent=host):
                webbrowser.open(info.url or upd.RELEASE_PAGE)
            return
        if not info.asset_url:
            messagebox.showerror("EDHUD", t("update.no_asset", latest=info.latest), parent=host)
            return
        self._download_update(info, host)

    def _download_update(self, info, parent) -> None:
        import tkinter as tk
        from tkinter import messagebox, ttk

        from . import update as upd

        win = tk.Toplevel(parent)
        win.title(t("update.title"))
        win.attributes("-topmost", True)
        win.resizable(False, False)
        label = ttk.Label(win, text=t("update.downloading", name=info.asset_name), padding=16)
        label.pack()

        def progress(done: int, total: int) -> None:
            if total:
                text = t(
                    "update.progress_total",
                    done=upd.format_bytes(done),
                    total=upd.format_bytes(total),
                )
            else:
                text = t("update.progress", done=upd.format_bytes(done))

            def paint() -> None:
                try:
                    label.configure(text=text)
                except tk.TclError:
                    pass

            self._ui(paint)

        def work() -> None:
            try:
                payload = upd.stage_update(info, progress=progress)
                upd.spawn_helper(payload)
            except Exception as exc:
                def fail() -> None:
                    try:
                        win.destroy()
                    except tk.TclError:
                        pass
                    messagebox.showerror("EDHUD", t("update.failed", error=exc), parent=parent)

                self._ui(fail)
                return

            def restart() -> None:
                # Подменщик уже ждёт наш выход. Диалог «Ок» держал процесс
                # живым, а после кнопки окно закрывалось и никто его не поднимал.
                try:
                    label.configure(text=t("update.restarting"))
                    win.update_idletasks()
                except tk.TclError:
                    pass
                self._exit_for_update()

            self._ui(restart)

        threading.Thread(target=work, name="edhud-update-download", daemon=True).start()

    def _exit_for_update(self) -> None:
        """Отпустить exe сразу. Подменщик сам подменит файлы и запустит EDHUD."""
        self._stop.set()
        if self.tray is not None:
            try:
                self.tray.stop()
            except Exception:
                pass
        try:
            self.voice.stop()
        except Exception:
            pass
        os._exit(0)

    def request_quit(self) -> None:
        """Корректный выход: остановить потоки и закрыть окно tkinter."""
        self._stop.set()
        if self.tray is not None:
            self.tray.stop()
        self.voice.stop()
        if self.mainwindow is not None:
            try:
                self.mainwindow.destroy()
            except Exception:
                pass
        if self.overlay is not None:
            try:
                self.overlay.root.after(0, self.overlay.destroy)
            except Exception:
                self.overlay.destroy()

    def run(self) -> int:
        if not self.prepare():
            print(t("app.no_journal"))
            print(t("app.no_journal_2"))
            print(t("app.no_journal_3"))
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
            if self.overlay is not None and not self._stop.is_set():
                self.overlay.root.after(200, loop)

        loop()
        try:
            from .update import cleanup_staging

            cleanup_staging()
        except Exception:
            pass
        if (
            str(getattr(self.cfg, "update_check", "auto") or "auto") != "manual"
            and os.environ.get("EDHUD_SKIP_UPDATE") != "1"
        ):
            self.overlay.root.after(4000, lambda: self.check_updates(interactive=False))
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
        if self.eddn is not None:
            self.eddn.stop()
        if self.hotkeys is not None:
            self.hotkeys.stop()
        if self.tray is not None:
            self.tray.stop()
        self.voice.stop()
        if self.mainwindow is not None:
            try:
                self.mainwindow.destroy()
            except Exception:
                pass
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
