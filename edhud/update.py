"""Проверка и установка обновлений EDHUD с GitHub.

Как в nc.ai: никакого PowerShell, cmd и временных .ps1 — на эту связку
реагирует эвристика антивируса. Новая сборка сама запускается с
--apply-update, дожидается выхода текущей, подменяет файлы и перезапускает
программу.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

REPO = "PTah/edhub"
RELEASE_PAGE = f"https://github.com/{REPO}/releases/latest"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
USER_AGENT = "EDHUD-updater/1.3"
MAX_ASSET_BYTES = 400 << 20
API_ATTEMPTS = 3

# Те же флаги, что у NotCursor: тихий процесс, своя группа, не умирает вместе
# с Job родительского процесса.
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_TERMINATE = 0x0001
STILL_ACTIVE = 259
SPAWN_FLAGS = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB


@dataclass
class Asset:
    name: str
    url: str
    size: int = 0


@dataclass
class UpdateInfo:
    current: str
    latest: str = ""
    available: bool = False
    notes: str = ""
    url: str = RELEASE_PAGE
    asset_name: str = ""
    asset_url: str = ""
    asset_size: int = 0
    error: str = ""
    kind: str = ""
    assets: list[Asset] = field(default_factory=list)


def parse_version(value: str) -> list[int]:
    text = (value or "").strip()
    if text.lower().startswith("v"):
        text = text[1:]
    for sep in ("-", "+"):
        if sep in text:
            text = text.split(sep, 1)[0]
    parts: list[int] = []
    for piece in text.split("."):
        piece = piece.strip()
        if not piece.isdigit():
            break
        parts.append(int(piece))
    return parts


def compare_versions(left: str, right: str) -> int:
    """-1 если left < right, 0 если равны, 1 если left > right."""
    a, b = parse_version(left), parse_version(right)
    width = max(len(a), len(b))
    for index in range(width):
        x = a[index] if index < len(a) else 0
        y = b[index] if index < len(b) else 0
        if x < y:
            return -1
        if x > y:
            return 1
    return 0


def current_version() -> str:
    from . import __version__

    return str(__version__)


def install_kind() -> str:
    """onefile — portable exe, onedir — установка, source — запуск из Python."""
    if not getattr(sys, "frozen", False):
        return "source"
    exe = Path(sys.executable).resolve()
    if (exe.parent / "_internal").is_dir():
        return "onedir"
    return "onefile"


def pick_asset(assets: list[Asset], kind: str) -> Asset | None:
    if kind == "source":
        kind = "onedir"
    zips = [asset for asset in assets if asset.name.lower().endswith(".zip") and asset.url]
    if kind == "onefile":
        portable = [asset for asset in zips if "portable" in asset.name.lower()]
        versioned = [asset for asset in portable if any(ch.isdigit() for ch in asset.name)]
        pool = versioned or portable
        return pool[0] if pool else None
    windows = [
        asset
        for asset in zips
        if "portable" not in asset.name.lower() and "setup" not in asset.name.lower()
    ]
    versioned = [asset for asset in windows if any(ch.isdigit() for ch in asset.name)]
    pool = versioned or windows
    return pool[0] if pool else None


def _updates_dir() -> Path:
    from .config import app_dir

    path = app_dir() / "updates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cleanup_staging() -> None:
    """Старая распаковка после успешного перезапуска. Ошибки не важны."""
    staging = _updates_dir() / "staging"
    if staging.is_dir() and _is_under(Path(sys.executable), staging):
        return
    shutil.rmtree(staging, ignore_errors=True)


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _winhttp_get(
    url: str,
    timeout: float,
    accept: str = "",
    *,
    follow: bool = True,
    on_chunk=None,
) -> tuple[int, str, int]:
    """GET через WinHTTP (хранилище сертификатов Windows, без PowerShell).

    urllib на этой машине не доверяет цепочке GitHub. WinHTTP использует
    те же корни, что браузер и системные программы.
    """
    import ctypes
    from ctypes import wintypes
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    host = parts.hostname or ""
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    port = int(parts.port or (443 if parts.scheme == "https" else 80))
    secure = parts.scheme == "https"

    wh = ctypes.WinDLL("winhttp")
    wh.WinHttpOpen.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
    wh.WinHttpOpen.restype = ctypes.c_void_p
    wh.WinHttpConnect.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, wintypes.WORD, wintypes.DWORD]
    wh.WinHttpConnect.restype = ctypes.c_void_p
    wh.WinHttpOpenRequest.argtypes = [
        ctypes.c_void_p,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    wh.WinHttpOpenRequest.restype = ctypes.c_void_p
    wh.WinHttpSetTimeouts.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    wh.WinHttpSetTimeouts.restype = wintypes.BOOL
    wh.WinHttpSetOption.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    wh.WinHttpSetOption.restype = wintypes.BOOL
    wh.WinHttpSendRequest.argtypes = [
        ctypes.c_void_p,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_size_t,
    ]
    wh.WinHttpSendRequest.restype = wintypes.BOOL
    wh.WinHttpReceiveResponse.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    wh.WinHttpReceiveResponse.restype = wintypes.BOOL
    wh.WinHttpQueryHeaders.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
    ]
    wh.WinHttpQueryHeaders.restype = wintypes.BOOL
    wh.WinHttpQueryDataAvailable.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
    wh.WinHttpQueryDataAvailable.restype = wintypes.BOOL
    wh.WinHttpReadData.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    wh.WinHttpReadData.restype = wintypes.BOOL
    wh.WinHttpCloseHandle.argtypes = [ctypes.c_void_p]
    wh.WinHttpCloseHandle.restype = wintypes.BOOL

    access = 4  # WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY
    session = wh.WinHttpOpen(USER_AGENT, access, None, None, 0)
    if not session:
        session = wh.WinHttpOpen(USER_AGENT, 0, None, None, 0)
    if not session:
        raise OSError("WinHttpOpen failed")
    connect = request = None
    try:
        ms = max(1000, int(timeout * 1000))
        wh.WinHttpSetTimeouts(session, ms, ms, ms, ms)
        connect = wh.WinHttpConnect(session, host, port, 0)
        if not connect:
            raise OSError(f"WinHttpConnect {host}")
        flags = 0x00800000 if secure else 0
        request = wh.WinHttpOpenRequest(connect, "GET", path, None, None, None, flags)
        if not request:
            raise OSError("WinHttpOpenRequest failed")
        if not follow:
            policy = wintypes.DWORD(0)  # WINHTTP_OPTION_REDIRECT_POLICY_NEVER
            wh.WinHttpSetOption(request, 88, ctypes.byref(policy), ctypes.sizeof(policy))
        extra = f"Accept: {accept}\r\n" if accept else None
        sent = wh.WinHttpSendRequest(request, extra, -1 if extra else 0, None, 0, 0, 0)
        if not sent or not wh.WinHttpReceiveResponse(request, None):
            raise OSError(f"WinHTTP GET failed ({ctypes.get_last_error()})")
        status_code = wintypes.DWORD()
        status_len = wintypes.DWORD(ctypes.sizeof(status_code))
        status_idx = wintypes.DWORD(0)
        if not wh.WinHttpQueryHeaders(
            request,
            19 | 0x20000000,  # STATUS_CODE | FLAG_NUMBER
            None,
            ctypes.byref(status_code),
            ctypes.byref(status_len),
            ctypes.byref(status_idx),
        ):
            raise OSError("WinHTTP status missing")
        location = _winhttp_header(wh, request, "Location")
        length_text = _winhttp_header(wh, request, "Content-Length")
        try:
            total_hint = int(length_text or "0")
        except ValueError:
            total_hint = 0
        done = 0
        while True:
            avail = wintypes.DWORD(0)
            if not wh.WinHttpQueryDataAvailable(request, ctypes.byref(avail)) or not avail.value:
                break
            n = min(int(avail.value), 256 * 1024)
            block = ctypes.create_string_buffer(n)
            read = wintypes.DWORD(0)
            if not wh.WinHttpReadData(request, block, n, ctypes.byref(read)) or not read.value:
                break
            piece = block.raw[: int(read.value)]
            done += len(piece)
            if done > MAX_ASSET_BYTES:
                raise OSError("update file is too large")
            if on_chunk is not None:
                on_chunk(piece, total_hint)
        return int(status_code.value), location, total_hint or done
    finally:
        if request:
            wh.WinHttpCloseHandle(request)
        if connect:
            wh.WinHttpCloseHandle(connect)
        wh.WinHttpCloseHandle(session)


def _winhttp_header(wh, request, name: str) -> str:
    import ctypes
    from ctypes import wintypes

    size = wintypes.DWORD(0)
    index = wintypes.DWORD(0)
    wh.WinHttpQueryHeaders(request, 65535, name, None, ctypes.byref(size), ctypes.byref(index))
    if not size.value:
        return ""
    buf = ctypes.create_unicode_buffer(max(1, size.value // 2 + 1))
    index = wintypes.DWORD(0)
    if not wh.WinHttpQueryHeaders(request, 65535, name, buf, ctypes.byref(size), ctypes.byref(index)):
        return ""
    return buf.value or ""


def _request(url: str, timeout: float, accept: str = "") -> bytes:
    if sys.platform == "win32":
        chunks: list[bytes] = []

        def take(piece: bytes, _total: int) -> None:
            chunks.append(piece)

        status, _location, _done = _winhttp_get(url, timeout, accept, on_chunk=take)
        if status >= 300:
            raise urllib.error.HTTPError(url, status, f"HTTP {status}", hdrs=None, fp=None)
        return b"".join(chunks)
    headers = {"User-Agent": USER_AGENT}
    if accept:
        headers["Accept"] = accept
    last_error: Exception | None = None
    for attempt in range(API_ATTEMPTS):
        if attempt:
            time.sleep(0.7 * attempt)
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                status = getattr(response, "status", 200) or 200
                if status >= 500:
                    last_error = urllib.error.URLError(f"HTTP {status}")
                    continue
                return response.read(1 << 20)
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                raise
            last_error = exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
    if last_error is None:
        last_error = urllib.error.URLError("no response")
    raise last_error


def _latest_tag_from_redirect() -> str:
    if sys.platform == "win32":
        status, location, _done = _winhttp_get(RELEASE_PAGE, 20, follow=False)
        if status < 300 or status >= 400 or not location:
            raise urllib.error.URLError(f"HTTP {status}")
        tag = location.rstrip("/").rsplit("/", 1)[-1]
        if not tag.lower().startswith("v") or not parse_version(tag):
            raise urllib.error.URLError(f"bad release tag {tag!r}")
        return tag

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(RELEASE_PAGE, headers={"User-Agent": USER_AGENT})
    try:
        with opener.open(req, timeout=20) as response:
            status = getattr(response, "status", 200)
            location = response.headers.get("Location") or ""
            if status < 300:
                raise urllib.error.URLError(f"HTTP {status}")
    except urllib.error.HTTPError as exc:
        location = exc.headers.get("Location") if exc.headers else ""
        if exc.code < 300 or exc.code >= 400 or not location:
            raise
    tag = location.rstrip("/").rsplit("/", 1)[-1]
    if not tag.lower().startswith("v") or not parse_version(tag):
        raise urllib.error.URLError(f"bad release tag {tag!r}")
    return tag


def _synthetic_release(tag: str) -> tuple[str, str, list[Asset]]:
    version = tag[1:] if tag.lower().startswith("v") else tag
    base = f"https://github.com/{REPO}/releases/download/{tag}"
    assets = [
        Asset(f"EDHUD-portable-{version}.zip", f"{base}/EDHUD-portable-{version}.zip"),
        Asset(f"EDHUD-{version}-windows.zip", f"{base}/EDHUD-{version}-windows.zip"),
    ]
    return version, f"https://github.com/{REPO}/releases/tag/{tag}", assets


def fetch_release() -> tuple[str, str, str, list[Asset]]:
    """(latest, notes, url, assets). Бросает исключение, если GitHub недоступен."""
    try:
        raw = _request(API_LATEST, timeout=45, accept="application/vnd.github+json")
        data = json.loads(raw.decode("utf-8"))
        tag = str(data.get("tag_name") or "")
        if not tag:
            raise ValueError("empty tag_name")
        latest = tag[1:] if tag.lower().startswith("v") else tag
        notes = str(data.get("body") or "").strip()
        url = str(data.get("html_url") or RELEASE_PAGE)
        assets = [
            Asset(
                name=str(item.get("name") or ""),
                url=str(item.get("browser_download_url") or ""),
                size=int(item.get("size") or 0),
            )
            for item in (data.get("assets") or [])
            if isinstance(item, dict)
        ]
        return latest, notes, url, assets
    except Exception as api_error:
        try:
            tag = _latest_tag_from_redirect()
        except Exception as redirect_error:
            raise redirect_error from api_error
        latest, url, assets = _synthetic_release(tag)
        return latest, "", url, assets


def check(current: str | None = None) -> UpdateInfo:
    current = current if current is not None else current_version()
    kind = install_kind()
    info = UpdateInfo(current=current, kind=kind)
    try:
        latest, notes, url, assets = fetch_release()
    except Exception as exc:
        info.error = str(exc)
        return info
    info.latest = latest
    info.notes = notes
    info.url = url or RELEASE_PAGE
    info.assets = assets
    asset = pick_asset(assets, "onefile" if kind == "onefile" else "onedir")
    if asset is not None:
        info.asset_name = asset.name
        info.asset_url = asset.url
        info.asset_size = asset.size
    info.available = compare_versions(latest, current) > 0
    return info


def format_bytes(value: int) -> str:
    if value >= 1_048_576:
        return f"{value / 1_048_576:.1f} MB"
    if value >= 1024:
        return f"{value / 1024:.0f} KB"
    return f"{value} B"


def download(url: str, dest: Path, progress=None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    if sys.platform == "win32":
        done = 0

        def take(piece: bytes, total: int) -> None:
            nonlocal done
            handle.write(piece)
            done += len(piece)
            if progress is not None:
                progress(done, total)

        with tmp.open("wb") as handle:
            status, _location, total = _winhttp_get(url, 120, on_chunk=take)
        if status >= 300:
            tmp.unlink(missing_ok=True)
            raise OSError(f"download HTTP {status}")
        if total and done < total:
            tmp.unlink(missing_ok=True)
            raise OSError(f"downloaded {done} of {total} bytes")
        tmp.replace(dest)
        return
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as response:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        with tmp.open("wb") as handle:
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                done += len(chunk)
                if done > MAX_ASSET_BYTES:
                    raise OSError("update file is too large")
                if progress is not None:
                    progress(done, total)
    if total and done < total:
        tmp.unlink(missing_ok=True)
        raise OSError(f"downloaded {done} of {total} bytes")
    tmp.replace(dest)


def _extract(archive: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(dest)


def find_payload(root: Path, kind: str) -> Path:
    exes = [path for path in root.rglob("EDHUD.exe") if path.is_file()]
    if not exes:
        raise FileNotFoundError("EDHUD.exe")
    if kind == "onefile":
        return exes[0]
    for exe in exes:
        if (exe.parent / "_internal").is_dir():
            return exe.parent
    return exes[0].parent


def stage_update(info: UpdateInfo, progress=None) -> Path:
    if not info.asset_url:
        raise FileNotFoundError(info.asset_name or "asset")
    incoming = _updates_dir() / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    archive = incoming / (info.asset_name or "EDHUD-update.zip")
    download(info.asset_url, archive, progress=progress)
    staging = _updates_dir() / "staging"
    _extract(archive, staging)
    kind = "onefile" if install_kind() == "onefile" else "onedir"
    return find_payload(staging, kind)


def current_target() -> Path:
    exe = Path(sys.executable).resolve()
    if install_kind() == "onefile":
        return exe
    return exe.parent


def helper_command(
    helper: Path,
    pid: int,
    source: Path,
    target: Path,
    log_path: Path,
    extra_pids: tuple[int, ...] | list[int] = (),
) -> list[str]:
    command = [str(helper), "--apply-update"]
    seen: list[int] = []
    raw = list(pid) if isinstance(pid, (list, tuple)) else [pid]
    raw.extend(extra_pids)
    for item in raw:
        try:
            number = int(item)
        except (TypeError, ValueError):
            continue
        if number > 0 and number not in seen:
            seen.append(number)
            command.extend(["--wait-pid", str(number)])
    command.extend(
        [
            "--source",
            str(source),
            "--target",
            str(target),
            "--log",
            str(log_path),
        ]
    )
    return command


def wait_pids_from_argv(argv: list[str]) -> list[int]:
    found: list[int] = []
    index = 0
    while index < len(argv):
        if argv[index] == "--wait-pid" and index + 1 < len(argv):
            try:
                number = int(argv[index + 1])
            except ValueError:
                number = 0
            if number > 0 and number not in found:
                found.append(number)
            index += 2
            continue
        index += 1
    return found


def _same_path(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return os.path.normcase(os.path.normpath(left)) == os.path.normcase(os.path.normpath(right))


def _kernel32():
    import ctypes

    return ctypes.WinDLL("kernel32", use_last_error=True)


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    import ctypes
    from ctypes import wintypes

    kernel = _kernel32()
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        # Процесс есть, но открыть его нельзя (антивирус, чужой integrity).
        # Считать его мёртвым нельзя: подмена тогда бьётся в занятый exe и выходит.
        return ctypes.get_last_error() == 5
    try:
        code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return int(code.value) == STILL_ACTIVE
    finally:
        kernel.CloseHandle(handle)


def _process_image(pid: int) -> str:
    if pid <= 0 or sys.platform != "win32":
        return ""
    import ctypes
    from ctypes import wintypes

    kernel = _kernel32()
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if not kernel.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ""
        return buf.value
    finally:
        kernel.CloseHandle(handle)


def _parent_pid(pid: int) -> int:
    """Родитель процесса. 0, если снимок процессов недоступен."""
    if pid <= 0 or sys.platform != "win32":
        return 0
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_void_p),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel = _kernel32()
    TH32CS_SNAPPROCESS = 0x00000002
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel.Process32FirstW.restype = wintypes.BOOL
    kernel.Process32NextW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    snap = kernel.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    invalid = ctypes.c_void_p(-1).value
    if not snap or snap == invalid:
        return 0
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = kernel.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            if int(entry.th32ProcessID) == int(pid):
                return int(entry.th32ParentProcessID)
            ok = kernel.Process32NextW(snap, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snap)
    return 0


def same_exe_parent(pid: int) -> int:
    """PID загрузчика onefile, если он держит тот же exe.

    Родителя вроде explorer не возвращаем: его нельзя ни ждать, ни завершать.
    """
    parent = _parent_pid(pid)
    if parent <= 0 or parent == pid:
        return 0
    if _same_path(_process_image(pid), _process_image(parent)):
        return parent
    return 0


def _terminate(pid: int) -> None:
    if pid <= 0 or sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    kernel = _kernel32()
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(PROCESS_TERMINATE, False, int(pid))
    if not handle:
        return
    try:
        kernel.TerminateProcess(handle, 1)
    finally:
        kernel.CloseHandle(handle)


def _note(log_path: Path | None, message: str) -> None:
    if log_path is None:
        return
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {message}\n")
    except OSError:
        pass


def _copy_tree(source: Path, target: Path) -> None:
    for dirpath, _dirnames, filenames in os.walk(source):
        rel = Path(dirpath).relative_to(source)
        dest_dir = target / rel
        dest_dir.mkdir(parents=True, exist_ok=True)
        for name in filenames:
            shutil.copy2(Path(dirpath) / name, dest_dir / name)


def _replace_file(source: Path, target: Path) -> None:
    old = Path(str(target) + ".old")
    old.unlink(missing_ok=True)
    renamed = False
    try:
        os.replace(target, old)
        renamed = True
    except OSError:
        renamed = False
    try:
        shutil.copy2(source, target)
    except OSError:
        if renamed and old.exists() and not target.exists():
            os.replace(old, target)
        raise
    else:
        old.unlink(missing_ok=True)


def _install_tree(source: Path, target: Path, *, attempts: int = 30, pause: float = 0.4) -> None:
    """Копирует сборку. Повторяет, пока Windows держит exe после выхода процесса."""
    last: OSError | None = None
    for _attempt in range(max(1, attempts)):
        try:
            if source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                _replace_file(source, target)
            else:
                target.mkdir(parents=True, exist_ok=True)
                _copy_tree(source, target)
            return
        except OSError as exc:
            last = exc
            if pause:
                time.sleep(pause)
    if last is not None:
        raise last


def _wait_until_dead(pids: list[int], log_path: Path | None) -> None:
    pending = [pid for pid in pids if pid > 0]
    if not pending:
        return
    _note(log_path, "waiting for " + ",".join(str(pid) for pid in pending))
    deadline = time.time() + 45
    while pending and time.time() < deadline:
        pending = [pid for pid in pending if process_alive(pid)]
        if pending:
            time.sleep(0.15)
    for pid in pending:
        _note(log_path, f"old process still alive, terminating {pid}")
        _terminate(pid)
    # Файл exe ещё мгновение отображён в процессе, который уже завершился.
    time.sleep(0.4)


def apply_update(
    wait_pid: int,
    source: Path,
    target: Path,
    log_path: Path | None = None,
    *,
    restart: bool = True,
    wait_pids: list[int] | None = None,
) -> int:
    """Подмена файлов. restart=False — для теста, без запуска exe."""
    source = Path(source)
    target = Path(target)
    pids: list[int] = []
    for item in [wait_pid, *(wait_pids or [])]:
        try:
            number = int(item)
        except (TypeError, ValueError):
            continue
        if number > 0 and number not in pids:
            pids.append(number)
    _note(log_path, f"apply start waitPid={pids} source={source} target={target}")
    if not source.exists() or not str(target):
        _note(log_path, "missing source or target")
        return 2
    _wait_until_dead(pids, log_path)
    restart_exe = target if source.is_file() else target / "EDHUD.exe"
    replaced = False
    try:
        _install_tree(source, target)
        replaced = True
        _note(log_path, "files replaced")
    except OSError as exc:
        _note(log_path, f"copy failed: {exc}")
        if not restart:
            return 1
    if not restart:
        return 0
    if not restart_exe.is_file():
        _note(log_path, "FATAL: restart exe missing")
        return 1
    if not replaced:
        # Старую сборку всё равно поднимаем, но без немедленной повторной проверки:
        # иначе неудачная подмена зациклится.
        os.environ["EDHUD_SKIP_UPDATE"] = "1"
        _note(log_path, "relaunching previous build")
    started = _start_detached(restart_exe)
    _note(log_path, "relaunched" if started else "FATAL: could not relaunch")
    return 0 if started else 1


def _shell_execute(exe: Path) -> bool:
    """Обычный запуск, как двойной щелчок. Без CREATE_NO_WINDOW, чтобы окно появилось."""
    if sys.platform != "win32":
        return False
    import ctypes

    shell = ctypes.WinDLL("shell32", use_last_error=True)
    shell.ShellExecuteW.restype = ctypes.c_void_p
    shell.ShellExecuteW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_int,
    ]
    rc = shell.ShellExecuteW(None, "open", str(exe), None, str(exe.parent), 1)
    return int(rc or 0) > 32


def _start_detached(exe: Path) -> bool:
    if _shell_execute(exe):
        return True
    # Перезапуск GUI не прячем: CREATE_NO_WINDOW оставляет процесс без окна.
    flags = 0
    if sys.platform == "win32":
        flags = CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB
    for _attempt in range(3):
        try:
            proc = subprocess.Popen(  # noqa: S603
                [str(exe)],
                cwd=str(exe.parent),
                creationflags=flags,
                close_fds=True,
            )
            proc.poll()
            return True
        except OSError:
            if flags & CREATE_BREAKAWAY_FROM_JOB:
                flags = flags & ~CREATE_BREAKAWAY_FROM_JOB
                continue
            time.sleep(0.4)
    return False


def spawn_helper(payload: Path, target: Path | None = None) -> None:
    """Запускает новую сборку в режиме подмены и ждёт первую строку лога."""
    payload = Path(payload)
    target = Path(target) if target is not None else current_target()
    helper = payload if payload.is_file() else payload / "EDHUD.exe"
    if not helper.is_file():
        raise FileNotFoundError(str(helper))
    log_path = _updates_dir() / "apply.log"
    try:
        log_path.unlink()
    except OSError:
        pass
    pid = os.getpid()
    parent = same_exe_parent(pid)
    command = helper_command(
        helper,
        pid,
        payload,
        target,
        log_path,
        extra_pids=(parent,) if parent else (),
    )
    flags = SPAWN_FLAGS if sys.platform == "win32" else 0
    try:
        proc = subprocess.Popen(  # noqa: S603
            command,
            cwd=str(helper.parent),
            creationflags=flags,
            close_fds=True,
        )
    except OSError:
        if not (flags & CREATE_BREAKAWAY_FROM_JOB):
            raise
        proc = subprocess.Popen(  # noqa: S603
            command,
            cwd=str(helper.parent),
            creationflags=flags & ~CREATE_BREAKAWAY_FROM_JOB,
            close_fds=True,
        )
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            if log_path.is_file() and log_path.stat().st_size > 0:
                if proc.poll() is not None:
                    raise RuntimeError("updater exited before the app quit")
                return
        except OSError:
            pass
        if proc.poll() is not None:
            raise RuntimeError("updater exited before it started")
        time.sleep(0.15)
    if proc.poll() is not None:
        raise RuntimeError("updater exited before it started")


def _arg(argv: list[str], name: str) -> str:
    if name not in argv:
        return ""
    index = argv.index(name)
    if index + 1 >= len(argv):
        return ""
    return argv[index + 1]


def apply_from_argv(argv: list[str]) -> int:
    if "--apply-update" not in argv:
        return 0
    pids = wait_pids_from_argv(argv)
    wait_pid = pids[0] if pids else 0
    source = Path(_arg(argv, "--source"))
    target = Path(_arg(argv, "--target"))
    log_text = _arg(argv, "--log")
    log_path = Path(log_text) if log_text else None
    return apply_update(wait_pid, source, target, log_path, restart=True, wait_pids=pids[1:])
