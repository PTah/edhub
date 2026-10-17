#!/usr/bin/env python3
# Edited by nc.ai 0.8.8.0 on macbook 2026-10-17 20:14:17
"""Поиск неиспользуемых импортов (простая проверка, без внешних зависимостей)."""
from __future__ import annotations

import ast
import pathlib
import sys


def unused_imports(path: pathlib.Path) -> list[str]:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported[(alias.asname or alias.name).split(".")[0]] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.module == "__future__":
                continue
            for alias in node.names:
                if alias.name != "*":
                    imported[alias.asname or alias.name] = node.lineno
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    return [f"{name}:{line}" for name, line in imported.items() if name not in names and f'"{name}"' not in src]


def main() -> int:
    root = pathlib.Path(__file__).resolve().parent.parent
    found = False
    patterns = ["*.py", "edhud/*.py", "tools/*.py", "tests/*.py"]
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            unused = unused_imports(path)
            if unused:
                found = True
                print(f"{path.relative_to(root)}: {', '.join(unused)}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
