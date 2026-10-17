# Created by nc.ai 0.8.8.0 on macbook 2026-10-17 20:21:03
"""Минимальный ZMTP 3.1 SUB-клиент (без pyzmq).

EDDN раздаёт данные по ZeroMQ (PUB на tcp://eddn.edcd.io:9500). Чтобы не тащить
pyzmq в зависимости, здесь реализован только тот кусочек протокола, который нужен
подписчику: приветствие, команда READY (Socket-Type: SUB), подписка на всё, приём
кадров, ответ на PING. Если pyzmq установлен — edhud/eddn.py использует его.

Тело сообщения EDDN — zlib-сжатый JSON, распаковка в eddn.py.
"""
from __future__ import annotations

import socket
import struct
import time

GREETING = b"\xff" + b"\x00" * 8 + b"\x7f" + bytes([3, 1]) + b"NULL" + b"\x00" * 16 + b"\x00" + b"\x00" * 31

FLAG_MORE = 0x01
FLAG_LONG = 0x02
FLAG_COMMAND = 0x04


class ZmtpError(RuntimeError):
    pass


def _metadata(items: list[tuple[str, bytes]]) -> bytes:
    out = bytearray()
    for name, value in items:
        key = name.encode()
        out.append(len(key))
        out += key
        out += struct.pack(">I", len(value))
        out += value
    return bytes(out)


def encode_frame(body: bytes, command: bool = False, more: bool = False) -> bytes:
    """Кадр ZMTP: flags, длина (1 или 8 байт), тело."""
    flags = 0
    if command:
        flags |= FLAG_COMMAND
    if more:
        flags |= FLAG_MORE
    if len(body) > 255:
        flags |= FLAG_LONG
    out = bytearray([flags])
    if flags & FLAG_LONG:
        out += struct.pack(">Q", len(body))
    else:
        out.append(len(body))
    out += body
    return bytes(out)


def parse_endpoint(endpoint: str) -> tuple[str, int]:
    if "://" in endpoint:
        scheme, _, rest = endpoint.partition("://")
        if scheme not in ("tcp", "zmq"):
            raise ZmtpError(f"поддерживается только tcp://, получено {endpoint!r}")
    else:
        rest = endpoint
    host, _, port = rest.partition(":")
    if not host or not port:
        raise ZmtpError(f"не разобрать адрес {endpoint!r}")
    return host, int(port)


class ZmtpSubscriber:
    """Подписчик ZeroMQ PUB (одна подписка «на всё»)."""

    def __init__(self, endpoint: str, timeout: float = 20.0) -> None:
        self.endpoint = endpoint
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._buffer = bytearray()

    # ------------------------------------------------------------------ связь
    def connect(self, timeout: float | None = None) -> None:
        host, port = parse_endpoint(self.endpoint)
        sock = socket.create_connection((host, port), timeout=timeout or self.timeout)
        sock.settimeout(timeout or self.timeout)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._sock = sock
        self._buffer.clear()
        sock.sendall(GREETING)
        self._read_exact(64)  # приветствие сервера
        # READY с типом сокета SUB
        self._send_command(b"READY", _metadata([("Socket-Type", b"SUB"), ("Identity", b"")]))
        # ждём READY от сервера (перед этим он может прислать PING)
        self._await_peer_ready(min(5.0, timeout or self.timeout))
        # подписка «на всё»: 0x01 + пустая тема
        sock.sendall(encode_frame(b"\x01"))

    def _await_peer_ready(self, timeout: float) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            remaining = max(0.1, deadline - time.time())
            if self._sock is not None:
                self._sock.settimeout(remaining)
            try:
                flags, body = self._read_frame()
            except (socket.timeout, TimeoutError):
                return
            if flags & FLAG_COMMAND:
                if body[1:5] == b"READY":
                    return
                self._handle_command(body)

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    # ------------------------------------------------------------------ приём
    def recv(self) -> bytes | None:
        """Одно сообщение (склеенные части). None — таймаут/пусто."""
        while True:
            try:
                flags, body = self._read_frame()
            except (socket.timeout, TimeoutError):
                return None
            except OSError as exc:
                raise ZmtpError(str(exc)) from exc
            if flags & FLAG_COMMAND:
                self._handle_command(body)
                continue
            if flags & FLAG_MORE:
                parts = [body]
                while True:
                    more_flags, more_body = self._read_frame()
                    if more_flags & FLAG_COMMAND:
                        self._handle_command(more_body)
                        continue
                    parts.append(more_body)
                    if not more_flags & FLAG_MORE:
                        break
                return b"".join(parts)
            return body

    # --------------------------------------------------------------- служебное
    def _handle_command(self, body: bytes) -> None:
        if not body:
            return
        name = body[1 : 1 + body[0]]
        if name == b"PING":
            self._send_command(b"PONG", body[1 + body[0] :])

    def _send_command(self, name: bytes, data: bytes = b"") -> None:
        if self._sock is None:
            raise ZmtpError("нет соединения")
        body = bytes([len(name)]) + name + data
        self._sock.sendall(encode_frame(body, command=True))

    def _read_exact(self, size: int) -> bytes:
        if self._sock is None:
            raise ZmtpError("нет соединения")
        while len(self._buffer) < size:
            chunk = self._sock.recv(max(4096, size - len(self._buffer)))
            if not chunk:
                raise ZmtpError("соединение закрыто")
            self._buffer += chunk
        data = bytes(self._buffer[:size])
        del self._buffer[:size]
        return data

    def _read_frame(self) -> tuple[int, bytes]:
        flags = self._read_exact(1)[0]
        if flags & FLAG_LONG:
            size = struct.unpack(">Q", self._read_exact(8))[0]
        else:
            size = self._read_exact(1)[0]
        body = self._read_exact(size) if size else b""
        return flags, body


def poke(endpoint: str, seconds: float = 15.0) -> int:
    """Отладочная проверка: сколько сообщений пришло за N секунд."""
    subscriber = ZmtpSubscriber(endpoint)
    subscriber.connect()
    deadline = time.time() + seconds
    count = 0
    while time.time() < deadline:
        message = subscriber.recv()
        if message is None:
            break
        count += 1
    subscriber.close()
    return count
