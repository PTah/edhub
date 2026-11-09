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


def _request(url: str, timeout: float, accept: str = "") -> bytes:
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


def helper_command(helper: Path, pid: int, source: Path, target: Path, log_path: Path) -> list[str]:
    return [
        str(helper),
        "--apply-update",
        "--wait-pid",
        str(int(pid)),
        "--source",
        str(source),
        "--target",
        str(target),
        "--log",
        str(log_path),
    ]


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

    kernel = ctypes.windll.kernel32
    handle = kernel.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return int(code.value) == STILL_ACTIVE
    finally:
        kernel.CloseHandle(handle)


def _terminate(pid: int) -> None:
    if pid <= 0 or sys.platform != "win32":
        return
    import ctypes

    kernel = ctypes.windll.kernel32
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


def apply_update(
    wait_pid: int,
    source: Path,
    target: Path,
    log_path: Path | None = None,
    *,
    restart: bool = True,
) -> int:
    """Подмена файлов. restart=False — для теста, без запуска exe."""
    source = Path(source)
    target = Path(target)
    _note(log_path, f"apply start waitPid={wait_pid} source={source} target={target}")
    if not source.exists() or not str(target):
        _note(log_path, "missing source or target")
        return 2
    deadline = time.time() + 45
    while process_alive(wait_pid) and time.time() < deadline:
        time.sleep(0.15)
    if process_alive(wait_pid):
        _note(log_path, "old process still alive, terminating")
        _terminate(wait_pid)
        time.sleep(0.8)
    try:
        if source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            _replace_file(source, target)
            restart_exe = target
        else:
            target.mkdir(parents=True, exist_ok=True)
            _copy_tree(source, target)
            restart_exe = target / "EDHUD.exe"
        _note(log_path, "files replaced")
    except OSError as exc:
        _note(log_path, f"copy failed: {exc}")
        return 1
    if not restart:
        return 0
    if not restart_exe.is_file():
        _note(log_path, "FATAL: restart exe missing")
        return 1
    started = _start_detached(restart_exe)
    _note(log_path, "relaunched" if started else "FATAL: could not relaunch")
    return 0 if started else 1


def _start_detached(exe: Path) -> bool:
    flags = SPAWN_FLAGS if sys.platform == "win32" else 0
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
    command = helper_command(helper, os.getpid(), payload, target, log_path)
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
                return
        except OSError:
            pass
        if proc.poll() is not None:
            raise RuntimeError("updater exited before it started")
        time.sleep(0.15)


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
    pid_text = _arg(argv, "--wait-pid")
    try:
        wait_pid = int(pid_text or "0")
    except ValueError:
        wait_pid = 0
    source = Path(_arg(argv, "--source"))
    target = Path(_arg(argv, "--target"))
    log_text = _arg(argv, "--log")
    log_path = Path(log_text) if log_text else None
    return apply_update(wait_pid, source, target, log_path, restart=True)
