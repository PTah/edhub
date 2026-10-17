#!/usr/bin/env python3
"""Трассировка предиктора: почему критерий не сработал (отладка)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud import bio, config, journal  # noqa: E402

GENUS = sys.argv[1] if len(sys.argv) > 1 else "Bacterium"


def failure(clause: bio.Clause, props: dict) -> str | None:
    ok = bio._clause_ok(clause, props)  # noqa: SLF001
    if ok:
        return None
    prop = bio.MAP_PROPS.get(clause.prop, clause.prop)
    return f"{clause.raw.strip()!r} (значение: {props.get(prop)!r})"


def walk(node: bio.Criteria, props: dict, depth: int = 0) -> None:
    if node.genus and node.genus != GENUS:
        return
    fails = [f for f in (failure(c, props) for c in node.query) if f]
    label = node.genus or node.species or node.variant or ""
    marker = "OK " if not fails else "FAIL"
    print(f"{'  ' * depth}{marker} {label}")
    for fail in fails:
        print(f"{'  ' * depth}   × {fail}")
    if fails:
        return
    for child in node.children:
        walk(child, props, depth + 1)


def main() -> None:
    folder = Path(sys.argv[2]) if len(sys.argv) > 2 else config.app_dir() / "demo"
    state = journal.load_snapshot(folder)
    body = state.current_body() or next(iter(state.system.bodies.values()))
    props = bio.build_props(body, state.system)
    if not props:
        print("нет свойств")
        return
    for criteria in bio.load_criteria():
        if criteria.genus == GENUS:
            walk(criteria, props)


if __name__ == "__main__":
    main()
