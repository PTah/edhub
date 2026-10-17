"""Прокладка маршрута через Galaxy Plotter (spansh.co.uk).

Как в EDEB: маршрут плоттера (нейтронки/экономичный) можно загрузить и держать
в оверлее отдельно от маршрута игры. API асинхронный: POST /api/route отдаёт
job-id, дальше GET /api/results/<job> до готовности.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from .route import Route

API = "https://spansh.co.uk/api/route"
RESULTS = "https://spansh.co.uk/api/results/"
USER_AGENT = "EDHUD/1.0 (+local overlay, python-urllib)"


def _post(url: str, payload: dict, timeout: float) -> dict:
    data = urllib.parse.urlencode(payload).encode()
    request = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def _get(url: str, timeout: float) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def plot_route(
    start: str,
    target: str,
    range_ly: float = 30.0,
    efficiency: float = 60.0,
    via: list[str] | None = None,
    timeout: float = 300.0,
    poll: float = 3.0,
    progress: Callable[[str], None] | None = None,
) -> Route:
    """Строит маршрут start -> target. Бросает RuntimeError при неудаче."""
    payload = {
        "from": start,
        "to": target,
        "range": f"{range_ly:g}",
        "efficiency": f"{efficiency:g}",
    }
    if via:
        payload["via"] = ",".join(via)
    try:
        reply = _post(API, payload, timeout=30)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"spansh недоступен: {exc}") from exc
    job = reply.get("job")
    if not job:
        raise RuntimeError(f"spansh: неожиданный ответ {reply}")

    deadline = time.time() + timeout
    last_state = ""
    while time.time() < deadline:
        time.sleep(poll)
        try:
            data = _get(RESULTS + job, timeout=30)
        except (urllib.error.URLError, TimeoutError):
            continue
        state = data.get("state") or data.get("status") or ""
        if state != last_state and progress:
            progress(f"spansh: {state}")
            last_state = state
        result = data.get("result")
        if isinstance(result, dict) and (result.get("system_jumps") or result.get("jumps")):
            route = Route.from_spansh(result)
            if route.hops:
                return route
        if state in ("failed", "error"):
            raise RuntimeError(f"spansh: маршрут не построен ({data.get('error')})")
    raise RuntimeError("spansh: время ожидания маршрута истекло")
