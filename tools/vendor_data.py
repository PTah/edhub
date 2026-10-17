#!/usr/bin/env python3
"""Переносит данные из референсных репозиториев (reference/) в data/.

Источники:
  * reference/SrvSurvey/SrvSurvey/bio-criteria/*.json  — правила биологии (SrvSurvey, GPLv3)
  * reference/SrvSurvey/SrvSurvey/EliteDangerousRegionMap/RegionMapData.cs
        — карта галактических регионов (klightspeed/EliteDangerousRegionMap, MIT)
  * reference/SrvSurvey/docs/codexRef.json — справочник кодекса (Canonn / SrvSurvey)

Запуск:  python3 tools/vendor_data.py [--ref reference] [--out data]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

BIO_NOTICE = """\
Файлы *.json в этом каталоге взяты из проекта SrvSurvey
(https://github.com/njthomson/SrvSurvey), каталог SrvSurvey/bio-criteria.
Автор: njthomson и участники проекта. Лицензия: GNU GPL v3.
Формат описан в readme.md исходного проекта; движок интерпретации
переписан на Python в edhud/bio.py.
"""


def vendor_bio_criteria(ref: Path, out: Path) -> int:
    src = ref / "SrvSurvey" / "SrvSurvey" / "bio-criteria"
    dst = out / "bio-criteria"
    dst.mkdir(parents=True, exist_ok=True)
    files = sorted(src.glob("*.json"))
    for f in files:
        shutil.copyfile(f, dst / f.name)
    readme = src / "readme.md"
    if readme.exists():
        shutil.copyfile(readme, dst / "readme.md")
    (dst / "NOTICE.txt").write_text(BIO_NOTICE, encoding="utf-8")
    return len(files)


def _csharp_string_array(text: str, marker: str) -> list[str | None]:
    start = text.index(marker)
    start = text.index("{", start) + 1
    end = text.index("};", start)
    body = text[start:end]
    out: list[str | None] = []
    for token in re.findall(r'"[^"]*"|null!', body):
        out.append(None if token == "null!" else token[1:-1])
    return out


def vendor_regions(ref: Path, out: Path) -> tuple[int, int]:
    src = ref / "SrvSurvey" / "SrvSurvey" / "EliteDangerousRegionMap" / "RegionMapData.cs"
    text = src.read_text(encoding="utf-8-sig")
    names = _csharp_string_array(text, "RegionNames = new string[]")

    start = text.index("RegionMapLines = new[]")
    body = text[text.index("{", start) + 1:]
    rows = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("new[]"):
            continue
        runs = [(int(a), int(b)) for a, b in re.findall(r"\((\d+),\s*(\d+)\)", line)]
        if runs:
            rows.append(runs)
        if line.startswith("};"):
            break

    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": "https://github.com/klightspeed/EliteDangerousRegionMap (через SrvSurvey), MIT",
        "x0": -49985,
        "z0": -24105,
        "scale": 83 / 4096,
        "names": names,
        "rows": rows,
    }
    (out / "galaxy_regions.json").write_text(
        json.dumps(payload, separators=(",", ":")), encoding="utf-8"
    )
    return len(names), len(rows)


def vendor_codex(ref: Path, out: Path) -> int:
    src = ref / "SrvSurvey" / "docs" / "codexRef.json"
    raw = json.loads(src.read_text(encoding="utf-8-sig"))
    trimmed: dict[str, dict] = {}
    for entry in raw.values():
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not name or not name.startswith("$"):
            continue
        label = entry.get("english_name") or ""
        if not label:
            continue
        item = {"en": label}
        reward = entry.get("reward")
        if reward:
            item["reward"] = reward
        cat = entry.get("hud_category")
        if cat:
            item["hud"] = cat
        trimmed[name] = item
    out.mkdir(parents=True, exist_ok=True)
    (out / "codex_ref.json").write_text(
        json.dumps(trimmed, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    return len(trimmed)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="reference")
    ap.add_argument("--out", default="data")
    args = ap.parse_args()

    ref = Path(args.ref)
    out = Path(args.out)
    if not ref.exists():
        raise SystemExit(f"нет каталога {ref}: клонируйте репозитории в reference/")

    n = vendor_bio_criteria(ref, out)
    print(f"bio-criteria: {n} файлов -> {out / 'bio-criteria'}")
    names, rows = vendor_regions(ref, out)
    print(f"galaxy_regions: {names} регионов, {rows} строк -> {out / 'galaxy_regions.json'}")
    n = vendor_codex(ref, out)
    print(f"codex_ref: {n} записей -> {out / 'codex_ref.json'}")


if __name__ == "__main__":
    main()
