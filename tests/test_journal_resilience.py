# Created by nc.ai 1.2.11 on Papasha 2026-11-14 19:51:23
"""Тесты устойчивости чтения журнала: одно плохое событие не теряет остаток файла."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edhud.journal import JournalWatcher  # noqa: E402
from edhud.model import GameState  # noqa: E402


def _journal(tmp: str, systems: list[str]) -> Path:
    path = Path(tmp) / "Journal.2026-11-14T120000.01.log"
    lines = []
    for index, system in enumerate(systems):
        lines.append(
            json.dumps(
                {
                    "timestamp": f"2026-11-14T12:0{index}:00Z",
                    "event": "Location" if index == 0 else "FSDJump",
                    "StarSystem": system,
                    "SystemAddress": index + 1,
                }
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class JournalResilienceTests(unittest.TestCase):
    def test_failing_callback_does_not_skip_rest_of_file(self) -> None:
        """Именно этот баг показывал «застрявшую» систему: смещение уходило вперёд."""
        with tempfile.TemporaryDirectory() as tmp:
            _journal(tmp, ["Alpha", "Beta", "Gamma"])

            def on_event(event: dict) -> None:
                if event.get("StarSystem") == "Beta":
                    raise RuntimeError("boom")

            state = GameState()
            watcher = JournalWatcher(Path(tmp), state, on_event=on_event)
            watcher.read_journal()
            self.assertEqual(state.system.name, "Gamma")
            self.assertTrue(watcher.errors, "сбой колбэка должен попадать в errors")

    def test_apply_failure_does_not_skip_rest_of_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _journal(tmp, ["Alpha", "Beta", "Gamma"])
            state = GameState()
            original = state.apply
            calls = {"n": 0}

            def apply(event: dict) -> None:
                calls["n"] += 1
                if calls["n"] == 2:
                    raise ValueError("bad event")
                original(event)

            state.apply = apply  # type: ignore[method-assign]
            watcher = JournalWatcher(Path(tmp), state)
            watcher.read_journal()
            self.assertEqual(state.system.name, "Gamma")
            self.assertTrue(watcher.errors)


if __name__ == "__main__":
    unittest.main()
