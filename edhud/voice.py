"""Голосовые оповещения через Windows SAPI (без внешних пакетов).

Голос выбирается по языку интерфейса: русский SAPI на русской Windows,
английский — во всех остальных случаях.
"""
from __future__ import annotations

import queue
import subprocess
import sys
import threading
from typing import Callable

from .i18n import language


def _escape_ps(text: str) -> str:
    return text.replace("'", "''")


def voice_script(text: str, rate: int = 0, lang: str | None = None) -> str:
    """Скрипт SAPI. Язык — ru или en; без -ExecutionPolicy Bypass и без .ps1 на диске."""
    safe = _escape_ps(text)
    rate = max(-10, min(10, int(rate)))
    lang = "ru" if (lang or language()) == "ru" else "en"
    if lang == "ru":
        name_match = "ru|Russ|Елена|Ирина|Pavel|Mikhail|Dmitri|Katya"
        lang_match = "0419|419"
    else:
        name_match = "English|David|Zira|Mark|Hazel|George|Susan|Hazel"
        lang_match = "0409|0809|0C09|1009|409"
    return f"""
$ErrorActionPreference = 'SilentlyContinue'
$v = New-Object -ComObject SAPI.SpVoice
$voices = @($v.GetVoices())
$pick = $voices | Where-Object {{
  $_.GetDescription() -match '{name_match}'
}} | Select-Object -First 1
if (-not $pick) {{
  $pick = $voices | Where-Object {{
    try {{ $_.GetAttribute('Language') -match '{lang_match}' }} catch {{ $false }}
  }} | Select-Object -First 1
}}
if ($pick) {{ $v.Voice = $pick }}
$v.Rate = {rate}
$v.Speak('{safe}')
"""


def _speak_powershell(text: str, rate: int = 0, lang: str | None = None) -> None:
    """Озвучка через SAPI.SpVoice выбранного языка."""
    if sys.platform != "win32":
        return
    script = voice_script(text, rate, lang)
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

    def __init__(
        self,
        rate: int = 0,
        on_error: Callable[[str], None] | None = None,
        lang: str | None = None,
    ) -> None:
        self.rate = rate
        self.lang = lang
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
                _speak_powershell(item, self.rate, self.lang or language())
            except Exception as exc:
                if self.on_error:
                    try:
                        self.on_error(f"{type(exc).__name__}: {exc}")
                    except Exception:
                        pass
