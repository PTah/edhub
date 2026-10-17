"""Голосовые оповещения через Windows SAPI (русский голос, без внешних пакетов)."""
from __future__ import annotations

import queue
import subprocess
import sys
import threading
from typing import Callable


def _escape_ps(text: str) -> str:
    return text.replace("'", "''")


def _speak_powershell(text: str, rate: int = 0) -> None:
    """Озвучка через SAPI.SpVoice; предпочитает голос с 'ru' в имени/Culture."""
    if sys.platform != "win32":
        return
    safe = _escape_ps(text)
    rate = max(-10, min(10, int(rate)))
    script = f"""
$ErrorActionPreference = 'SilentlyContinue'
$v = New-Object -ComObject SAPI.SpVoice
$voices = @($v.GetVoices())
$ru = $voices | Where-Object {{
  $_.GetDescription() -match 'ru|Russ|Елена|Ирина|Pavel|Mikhail|Dmitri|Katya'
}} | Select-Object -First 1
if (-not $ru) {{
  $ru = $voices | Where-Object {{
    try {{ $_.GetAttribute('Language') -match '0419|419|ru' }} catch {{ $false }}
  }} | Select-Object -First 1
}}
if ($ru) {{ $v.Voice = $ru }}
$v.Rate = {rate}
$v.Speak('{safe}')
"""
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        check=False,
        capture_output=True,
        creationflags=creation,
        timeout=60,
    )


class Voice:
    """Очередь фраз в фоновом потоке (не блокирует UI/журнал)."""

    def __init__(self, rate: int = 0, on_error: Callable[[str], None] | None = None) -> None:
        self.rate = rate
        self.on_error = on_error
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._thread = threading.Thread(target=self._worker, name="edhud-voice", daemon=True)
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread.start()

    def stop(self) -> None:
        if not self._started:
            return
        self._queue.put(None)

    def speak(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        if not self._started:
            self.start()
        try:
            self._queue.put_nowait(text)
        except queue.Full:
            pass

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            try:
                _speak_powershell(item, self.rate)
            except Exception as exc:
                if self.on_error:
                    try:
                        self.on_error(f"{type(exc).__name__}: {exc}")
                    except Exception:
                        pass
