#!/usr/bin/env python3
"""Просмотр JSON-ответа EDSM (отладка формата)."""
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text())
bodies = data.get("bodies") or []
keys: set[str] = set()
for body in bodies:
    keys |= set(body.keys())
print("поля:", sorted(keys))
for body in bodies:
    if body.get("signals") or body.get("materials"):
        pick = {
            k: body.get(k)
            for k in ("bodyId", "name", "subType", "isLandable", "materials", "signals", "rings", "mapped", "discovery")
            if k in body
        }
        print(json.dumps(pick, ensure_ascii=False)[:1200])
        break
print("всего тел:", len(bodies))
