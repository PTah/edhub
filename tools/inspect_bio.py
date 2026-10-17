#!/usr/bin/env python3
"""Отладка: свойства тела и предсказания биологии по журналу.

  python3 tools/inspect_bio.py [каталог_журналов] [BodyID]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud import bio, config, journal  # noqa: E402


def main() -> None:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else config.app_dir() / "demo"
    body_id = int(sys.argv[2]) if len(sys.argv) > 2 else None
    state = journal.load_snapshot(folder)
    print(f"система: {state.system.name} ({state.system.address})")
    for body in state.system.bodies.values():
        flags = []
        if body.is_star:
            flags.append("star")
        if body.landable:
            flags.append("landable")
        print(
            f"  [{body.body_id}] {body.name} · {body.planet_class or body.star_type} "
            f"({'/'.join(flags)}) · g={body.surface_gravity} K={body.surface_temp} "
            f"P={body.surface_pressure} atm={body.atmosphere!r} bio={body.bio_signals} "
            f"genuses={[k for k in body.genuses]}"
        )
    body = state.system.body(body_id) if body_id is not None else state.current_body()
    if body is None:
        print("тело не найдено")
        return
    props = bio.build_props(body, state.system)
    print(f"\nсвойства для предиктора ({body.name}):")
    for key, value in (props or {}).items():
        if isinstance(value, dict):
            value = dict(list(value.items())[:4])
        print(f"  {key} = {value!r}")
    if not props:
        print("  (нет свойств: тело не landable или нет родительской звезды)")
        return
    predictions = bio.predict(props)
    print(f"\nпредсказаний: {len(predictions)}")
    for prediction in predictions[:20]:
        print(f"  ≈ {prediction.label}  ({prediction.reward} cr)")
    known = {k for k in body.genuses}
    if known:
        print("\nс фильтром по известным родам (DSS):")
        for prediction in bio.predict(props, known_genuses=known)[:10]:
            print(f"  ≈ {prediction.label}")


if __name__ == "__main__":
    main()
