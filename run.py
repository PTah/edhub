#!/usr/bin/env python3
# Edited by nc.ai 0.8.8.0 on macbook 2026-10-17 20:13:30
"""EDHUD — оверлей исследователя Elite Dangerous (маршрут + биология).

Примеры:
  python3 run.py                      # оверлей сверху экрана (ищет журналы сам)
  python3 run.py run --demo           # демо на синтетическом журнале
  python3 run.py run --tui            # тот же HUD в терминале
  python3 run.py dump                 # один кадр HUD в консоль
  python3 run.py plot "Sol" "Colonia" --range 60
  python3 run.py import-route route.txt
  python3 run.py lock | unlock | export-route route.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from edhud import config, demo, eddn, remote, spansh, values, winapi
from edhud.app import App, dump
from edhud.route import Route, parse_route_text


def locked_path() -> Path:
    return config.app_dir() / "route_locked.json"


def _set_locked(route: Route) -> Path:
    path = route.save(locked_path())
    cfg = config.Config.load()
    cfg.locked_route = str(path)
    cfg.save()
    return path


def _route_summary(route: Route) -> str:
    if not route.hops:
        return "маршрут пуст"
    first = route.hops[0]
    last = route.hops[-1]
    total_ly = route.distance_remaining(None)
    return (
        f"{first.system} -> {last.system}: точек {len(route.hops)}, "
        f"прыжков ~{route.total_jumps}, ~{total_ly:,.0f} ly".replace(",", " ")
    )


# --------------------------------------------------------------------- команды
def cmd_run(args) -> int:
    cfg = config.Config.load()
    if args.journal_dir:
        cfg.journal_dir = args.journal_dir
    if args.no_click_through:
        cfg.click_through = False
    if args.width:
        cfg.width = args.width
    if args.offline:
        cfg.allow_network = False
        cfg.remote_enabled = False
        cfg.nebulae_enabled = False
        cfg.eddn_enabled = False
    if args.no_remote:
        cfg.remote_enabled = False
    if args.no_eddn:
        cfg.eddn_enabled = False

    journal_dir = None
    demo_speed = None
    if args.demo:
        journal_dir = demo.demo_folder()
        demo_speed = args.speed
    app = App(
        cfg,
        ui="tui" if args.tui else "overlay",
        expanded=True if args.expanded else None,
        journal_dir=journal_dir,
        demo_speed=demo_speed,
    )
    return app.run()


def cmd_eddn(args) -> int:
    """Проверка живой подписки EDDN: сколько сообщений и что пришло по системе."""
    listener_filter = eddn.SetFilter()
    if args.system:
        listener_filter.update(names={args.system}, addresses={args.address} if args.address else set())

    def on_message(message: dict) -> None:
        print(
            f"{message.get('event')}: {message.get('StarSystem') or message.get('SystemName') or '—'} "
            f"{message.get('BodyName') or ''}"
        )

    listener = eddn.EddnListener(
        endpoint=args.endpoint,
        on_message=on_message if args.system else None,
        system_filter=listener_filter if args.system else None,
    )
    print(f"EDDN {args.endpoint}, backend={listener.stats['backend']}, слушаю {args.seconds:.0f} с")
    listener.start()
    try:
        deadline = time.time() + args.seconds
        while time.time() < deadline:
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        listener.stop()
        listener.join(timeout=5)
    stats = listener.stats
    print(
        f"получено {stats['received']}, подошло по фильтру {stats['matched']}, "
        f"ошибок {stats['errors']}" + (f" ({stats['last_error']})" if stats["last_error"] else "")
    )
    return 0 if stats["received"] else 1


def cmd_remote(args) -> int:
    """Проверка догрузки тел: что EDSM/Spansh знают о системе."""
    cfg = config.Config.load()
    client = remote.RemoteClient(ttl=0.0, timeout=max(5.0, cfg.remote_timeout))
    system = client.fetch(args.system, getattr(args, "address", None), force=True)
    if system is None or not system.bodies:
        print(f"нет данных по системе {args.system!r} (EDSM/Spansh недоступны или систему не сканировали)")
        return 1
    print(f"{system.name}: тел {len(system.bodies)}, источники: {', '.join(system.sources) or '—'}")
    if system.estimated_scan_value:
        print(
            f"EDSM: скан ≈{values.credits(system.estimated_scan_value)}"
            f", с картами ≈{values.credits(system.estimated_mapped_value or 0)}"
        )
    bio = [b for b in system.bodies.values() if b.bio_signals]
    print(f"тел с биологией: {len(bio)}")
    for body in sorted(system.bodies.values(), key=lambda b: b.distance_ls)[: args.limit]:
        parts = [f"{body.body_id:>3} {body.name}"]
        parts.append(body.planet_class or body.star_type or "?")
        if body.bio_signals:
            parts.append(f"БИО {body.bio_signals}")
        if body.geo_signals:
            parts.append(f"гео {body.geo_signals}")
        if body.scan_value:
            parts.append(f"скан ≈{values.credits(body.scan_value)}")
        if body.discovered_by:
            parts.append(f"открыл {body.discovered_by}")
        print("  " + " · ".join(parts))
    return 0


def cmd_dump(args) -> int:
    if args.journal_dir:
        folder = Path(args.journal_dir)
    else:
        folder = demo.demo_folder()
        if not any(folder.glob("Journal*.log")):
            demo.write_all(folder)
    if not folder.exists():
        print(f"нет каталога журналов: {folder}")
        return 2
    for line in dump(folder):
        print(line)
    return 0


def cmd_plot(args) -> int:
    def progress(message: str) -> None:
        print(message, file=sys.stderr)

    try:
        route = spansh.plot_route(
            args.start,
            args.target,
            range_ly=args.range,
            efficiency=args.efficiency,
            via=args.via or None,
            progress=progress,
        )
    except RuntimeError as exc:
        print(f"не удалось построить маршрут: {exc}")
        return 1
    path = _set_locked(route)
    print(_route_summary(route))
    print(f"сохранено: {path} (загрузится при старте, маршрут залочен)")
    return 0


def cmd_import(args) -> int:
    text = Path(args.file).read_text(encoding="utf-8")
    names = parse_route_text(text)
    if not names:
        print("в файле не найдено имён систем")
        return 1
    route = Route.from_names(names)
    path = _set_locked(route)
    print(_route_summary(route))
    print(f"сохранено: {path}")
    return 0


def cmd_lock(args) -> int:
    cfg = config.Config.load()
    folder = Path(args.journal_dir) if args.journal_dir else cfg.resolved_journal_dir()
    if folder is None:
        print("не найден каталог журналов")
        return 2
    nav = folder / "NavRoute.json"
    if not nav.exists():
        print(f"нет {nav} — задайте маршрут в игре")
        return 1
    route = Route.from_navroute(json.loads(nav.read_text(encoding="utf-8-sig")))
    if not route.hops:
        print("маршрут в игре пуст")
        return 1
    route.locked = True
    route.source = "locked"
    path = _set_locked(route)
    print(_route_summary(route))
    print(f"залочен: {path}")
    return 0


def cmd_unlock(_args) -> int:
    cfg = config.Config.load()
    cfg.locked_route = None
    cfg.save()
    path = locked_path()
    if path.exists():
        path.unlink()
    print("маршрут разлочен, снова используется маршрут игры")
    return 0


def cmd_export(args) -> int:
    path = locked_path()
    if not path.exists():
        print("нет залоченного маршрута")
        return 1
    if args.file == "-":
        print(path.read_text(encoding="utf-8"))
        return 0
    target = Path(args.file)
    target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"экспортировано: {target}")
    return 0


# ----------------------------------------------------------------------- CLI
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="edhud", description="Оверлей исследователя Elite Dangerous")
    subs = parser.add_subparsers(dest="cmd")

    run = subs.add_parser("run", help="запустить оверлей (по умолчанию)")
    run.add_argument("--tui", action="store_true", help="HUD в терминале вместо окна")
    run.add_argument("--demo", action="store_true", help="демо на синтетическом журнале")
    run.add_argument("--speed", type=float, default=1.0, help="скорость демо")
    run.add_argument("--journal-dir", help="каталог журналов Elite Dangerous")
    run.add_argument("--expanded", action="store_true", help="сразу с панелью подробностей")
    run.add_argument("--no-click-through", action="store_true", help="окно ловит клики мыши")
    run.add_argument("--width", type=int, help="ширина оверлея, px")
    run.add_argument("--offline", action="store_true", help="без сети: без EDSM/Spansh и каталога туманностей")
    run.add_argument("--no-remote", action="store_true", help="не догружать тела от других командиров")
    run.add_argument("--no-eddn", action="store_true", help="не подключаться к живой шине EDDN")
    run.set_defaults(func=cmd_run)

    dump_cmd = subs.add_parser("dump", help="напечатать один кадр HUD")
    dump_cmd.add_argument("--journal-dir")
    dump_cmd.set_defaults(func=cmd_dump)

    remote_cmd = subs.add_parser("remote", help="показать, что EDSM/Spansh знают о системе")
    remote_cmd.add_argument("system")
    remote_cmd.add_argument("--address", type=int, help="SystemAddress (id64), если известен")
    remote_cmd.add_argument("--limit", type=int, default=12)
    remote_cmd.set_defaults(func=cmd_remote)

    eddn_cmd = subs.add_parser("eddn", help="проверить живую подписку EDDN")
    eddn_cmd.add_argument("--system", help="фильтр по системе")
    eddn_cmd.add_argument("--address", type=int, help="SystemAddress (id64)")
    eddn_cmd.add_argument("--endpoint", default=eddn.DEFAULT_ENDPOINT)
    eddn_cmd.add_argument("--seconds", type=float, default=20.0)
    eddn_cmd.set_defaults(func=cmd_eddn)

    plot = subs.add_parser("plot", help="построить маршрут через Spansh Galaxy Plotter")
    plot.add_argument("start")
    plot.add_argument("target")
    plot.add_argument("--range", type=float, default=30.0, help="дальность прыжка, ly")
    plot.add_argument("--efficiency", type=float, default=60.0)
    plot.add_argument("--via", action="append", help="промежуточная система (можно несколько)")
    plot.set_defaults(func=cmd_plot)

    imp = subs.add_parser("import-route", help="импортировать маршрут из текста/CSV")
    imp.add_argument("file")
    imp.set_defaults(func=cmd_import)

    lock = subs.add_parser("lock", help="залочить текущий маршрут игры")
    lock.add_argument("--journal-dir")
    lock.set_defaults(func=cmd_lock)

    unlock = subs.add_parser("unlock", help="вернуться к маршруту игры")
    unlock.set_defaults(func=cmd_unlock)

    export = subs.add_parser("export-route", help="экспортировать залоченный маршрут")
    export.add_argument("file")
    export.set_defaults(func=cmd_export)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    winapi.enable_dpi_awareness()  # до создания окна: иначе шрифт мылится на 125/150 %
    parser = build_parser()
    if not argv or argv[0].startswith("-"):
        argv = ["run"] + argv
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
