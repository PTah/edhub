# Created by nc.ai 1.2.15 on Papasha 2026-11-15 16:59:44
"""База хотспотов из дампа Spansh: потоковый парсер, импорт, офлайн-поиск."""
from __future__ import annotations

import gzip
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("EDHUD_LANG", "ru")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud.spanshdb import SpanshIndex, iter_objects  # noqa: E402

SYSTEMS = [
    {
        "id64": 1,
        "name": "Alpha",
        "coords": {"x": 0.0, "y": 0.0, "z": 0.0},
        "bodies": [
            {
                "name": "Alpha 1",
                "reserveLevel": "eReserveLevel_Pristine",
                "rings": [
                    {
                        "name": "Alpha 1 A Ring",
                        "type": "Icy",
                        "mass": 4.4934e19,
                        "innerRadius": 108_800_000.0,
                        "outerRadius": 115_180_000.0,
                        "id64": 11,
                        "signals": {
                            "signals": {"Alexandrite": 2, "Tritium": 1},
                            "updateTime": "2026-01-01T00:00:00Z",
                        },
                    },
                    {
                        # без signals — в базу не попадает
                        "name": "Alpha 1 B Ring",
                        "type": "Icy",
                        "mass": 1000.0,
                        "innerRadius": 1000.0,
                        "outerRadius": 2000.0,
                        "id64": 12,
                    },
                ],
            }
        ],
    },
    {
        "id64": 2,
        "name": "Beta",
        "coords": {"x": 10.0, "y": 0.0, "z": 0.0},
        "bodies": [
            {
                "name": "Beta 3",
                "rings": [
                    {
                        "name": "Beta 3 A Ring",
                        "type": "Metallic",
                        "mass": 1e16,
                        "innerRadius": 1_000_000.0,
                        "outerRadius": 2_000_000.0,
                        "signals": {"signals": {"Painite": 1}},
                    }
                ],
            }
        ],
    },
    {
        "id64": 3,
        "name": "Far Away",
        "coords": {"x": 500.0, "y": 0.0, "z": 0.0},
        "bodies": [
            {
                "name": "Far Away 2",
                "rings": [
                    {
                        "name": "Far Away 2 A Ring",
                        "type": "Icy",
                        "mass": 1e14,
                        "innerRadius": 1_000_000.0,
                        "outerRadius": 3_000_000.0,
                        "signals": {"signals": {"Alexandrite": 4}},
                    }
                ],
            }
        ],
    },
]


def dump_file(path: Path, systems=SYSTEMS, as_array: bool = True) -> Path:
    """Мини-дамп в формате Spansh (gzip + JSON-массив)."""
    if as_array:
        payload = json.dumps(systems, ensure_ascii=False)
    else:
        payload = "\n".join(json.dumps(item, ensure_ascii=False) for item in systems)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        fh.write(payload)
    return path


class ParserTests(unittest.TestCase):
    def test_array_and_jsonl(self):
        array = '[\n {"a": 1},\n {"a": 2}\n]'
        jsonl = '{"a": 1}\n{"a": 2}\n'
        for text in (array, jsonl):
            objects = list(iter_objects(io.StringIO(text), chunk_size=3))
            self.assertEqual([item["a"] for item in objects], [1, 2])

    def test_truncated_tail_is_ignored(self):
        stream = io.StringIO('[{"a": 1}, {"a": ')
        self.assertEqual([item["a"] for item in iter_objects(stream, chunk_size=4)], [1])


class ImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.index = SpanshIndex(self.root / "spansh.db")

    def tearDown(self) -> None:
        self.index.close()
        self.tmp.cleanup()

    def test_import_keeps_only_rings_with_hotspots(self):
        source = dump_file(self.root / "d.json.gz")
        result = self.index.update(source=source)
        self.assertEqual(result["systems"], 3)
        self.assertEqual(result["rings"], 3)  # кольцо без signals не считается
        info = self.index.counts()
        self.assertEqual(info["rings"], 3)
        self.assertEqual(info["systems"], 3)
        self.assertEqual(info["dump"], str(source))

    def test_search_by_mineral_and_radius(self):
        self.index.update(source=dump_file(self.root / "d.json.gz"))
        near = self.index.search([0.0, 0.0, 0.0], radius_ly=50, mineral="Alexandrite")
        self.assertEqual(len(near), 1)
        self.assertEqual(near[0].system, "Alpha")
        self.assertEqual(near[0].hotspots["Alexandrite"], 2)
        self.assertAlmostEqual(near[0].density, 10.009, places=2)
        self.assertEqual(near[0].reserve, "Pristine")
        self.assertEqual(near[0].kind, "Icy")

        all_rings = self.index.search([0.0, 0.0, 0.0], radius_ly=900)
        self.assertEqual(len(all_rings), 3)
        self.assertEqual(all_rings[0].system, "Alpha")  # сначала близкие

        self.assertEqual(self.index.search([0.0, 0.0, 0.0], radius_ly=50, mineral="Musgravite"), [])

    def test_repeat_import_does_not_duplicate(self):
        source = dump_file(self.root / "d.json.gz")
        self.index.update(source=source)
        self.index.update(source=source)
        self.assertEqual(self.index.counts()["rings"], 3)

    def test_empty_index_searches_nothing(self):
        self.assertEqual(self.index.search([0, 0, 0], 10, "Alexandrite"), [])
        self.assertFalse(self.index.exists())

    def test_jsonl_dump_also_works(self):
        source = dump_file(self.root / "d.json", as_array=False)
        self.index.update(source=source)
        self.assertEqual(self.index.counts()["rings"], 3)


if __name__ == "__main__":
    unittest.main()
