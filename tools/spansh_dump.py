#!/usr/bin/env python3
"""Просмотр JSON-ответа Spansh /api/bodies/search (отладка формата)."""
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text())
results = data.get("results") or []
keys: set[str] = set()
for body in results:
    keys |= set(body.keys())
print("поля:", sorted(keys))
with_signals = [b for b in results if b.get("signals")]
print("с signals:", len(with_signals))
if with_signals:
    print(json.dumps(with_signals[0], ensure_ascii=False)[:1500])
else:
    print(json.dumps(results[0], ensure_ascii=False)[:1200])
