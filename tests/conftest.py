# Created by nc.ai 1.2.11 on Papasha 2026-11-14 14:59:02
"""Общие настройки pytest.

Флак окружения (воспроизводился ~3 раза на 20 прогонов): `tkinter.Tk()`
изредка падает с `TclError: Can't find a usable tk.tcl` или
`invalid command name "tcl_findLibrary"`, хотя файлы Tk на месте.
Причина — не файлы: тесты создают/уничтожают десятки Tk-корней в одном
процессе, и если сборщик мусора освобождает старый Tcl-интерпретатор
(Tcl_Finalize) посреди инициализации нового, новый встаёт с битым
состоянием библиотеки Tcl. Проверено: в пробнике без pytest не
воспроизводится, а в сьюте стабильно ловится на повторных Tk().

Лечение:
  * gc.collect() перед созданием корня — мёртвые интерпретаторы
    финализируются в безопасной точке, а не во время init;
  * ретрай TclError — страховка, если сбой всё же случился.

Диагностика: EDHUD_TK_DEBUG=1 печатает факт сбоя и состояние файлов.
"""

from __future__ import annotations

import gc
import os
import time
import tkinter

_ATTEMPTS = 4
_PAUSE = 0.15
_DEBUG = os.environ.get("EDHUD_TK_DEBUG") == "1"
_orig_init = tkinter.Tk.__init__


def _diagnose(exc: BaseException) -> None:
    if not _DEBUG:
        return
    print(f"[tk-flake] {type(exc).__name__}: {str(exc).splitlines()[0][:160]}")
    try:
        import tkinter as _tk

        base = os.path.normpath(
            os.path.join(os.path.dirname(_tk.__file__), "..", "tcl", "tk8.6", "ttk")
        )
        target = os.path.join(base, "clamTheme.tcl")
        print(f"[tk-flake] exists({target})={os.path.exists(target)}")
    except Exception as diag_exc:  # noqa: BLE001 - диагностика не должна падать
        print(f"[tk-flake] diagnose failed: {diag_exc!r}")


def _retrying_init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
    last: BaseException | None = None
    for attempt in range(_ATTEMPTS):
        # финализируем уже уничтоженные интерпретаторы до создания нового
        gc.collect()
        try:
            return _orig_init(self, *args, **kwargs)
        except tkinter.TclError as exc:
            last = exc
            _diagnose(exc)
            time.sleep(_PAUSE * (attempt + 1))
    raise last  # type: ignore[misc]


tkinter.Tk.__init__ = _retrying_init  # type: ignore[method-assign]
