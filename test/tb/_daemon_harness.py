"""Fake-CIW harness for the bottom daemon's protocol state machine.

The daemon is normally launched by Virtuoso's ``ipcBeginProcess``; this harness
swaps its ``stdin``/``stdout`` for in-memory streams so a TB can script the CIW
side of the protocol byte-for-byte (frames, timeouts, rotation, truncation).

Frame grammar (spec: 日志返回设计标准):
    value frame : STX + "%L value" + RS
    error frame : NAK + error text   + RS
    log meta    : STX + path + US + start + US + end + RS
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

STX = b"\x02"
NAK = b"\x15"
RS = b"\x1e"
US = b"\x1f"

DAEMON_FILES = {
    "py3": SRC / "bridge" / "resources" / "ramic_bridge_daemon_3.py",
    "py27": SRC / "bridge" / "resources" / "ramic_bridge_daemon_27.py",
}
DAEMON_PATH = DAEMON_FILES["py3"]


class BytesBuffer:
    """Byte stream with a read cursor and a record of everything written.

    ``gate`` models the real ipc ordering: the CIW only writes a frame *after*
    it has received the directive, so the daemon's stale-data drain must see an
    empty pipe and the queued frames become readable right after the directive
    is written.
    """

    def __init__(self, data: bytes = b"", gate=None) -> None:
        self.data = bytearray(data)
        self.pos = 0
        self.written = bytearray()
        self.gate = gate

    def read(self, size: int = -1) -> bytes:
        if self.gate is not None and not self.gate():
            return b""
        if size < 0:
            size = len(self.data) - self.pos
        chunk = bytes(self.data[self.pos:self.pos + size])
        self.pos += len(chunk)
        return chunk

    def write(self, data) -> int:
        self.written.extend(data)
        return len(data)

    def flush(self) -> None:  # pragma: no cover - nothing buffered
        return None

    def remaining(self) -> bytes:
        """Bytes the CIW side queued but the daemon never consumed."""
        return bytes(self.data[self.pos:])


class FakeStream:
    """Stream stand-in for both daemon variants.

    ``ramic_bridge_daemon_3.py`` uses ``sys.stdin.buffer`` / ``sys.stdout.buffer``
    (bytes API); ``ramic_bridge_daemon_27.py`` uses the text-level
    ``sys.stdin.read(1)`` (whose result it feeds to ``ord``) and
    ``sys.stdout.write(bytes)``.  Providing both shapes keeps one harness for
    the whole log/protocol matrix.
    """

    def __init__(self, data: bytes = b"", gate=None) -> None:
        self.buffer = BytesBuffer(data, gate=gate)

    def read(self, size: int = -1) -> str:
        return self.buffer.read(size).decode("utf-8", "replace")

    def write(self, data) -> int:
        if isinstance(data, str):
            data = data.encode("utf-8")
        return self.buffer.write(data)

    def flush(self) -> None:  # pragma: no cover - nothing buffered
        return None


class FakeConn:
    """Socket stand-in: hands the request over once, records the response."""

    def __init__(self, request: bytes) -> None:
        self.request = request
        self.sent = bytearray()
        self.closed = False

    def recv(self, _size) -> bytes:
        data, self.request = self.request, b""
        return data

    def sendall(self, data) -> None:
        self.sent.extend(data)

    def shutdown(self, _how) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def load_daemon(name: str, token: str = "tok", path: Path | str | None = None):
    """Import one daemon variant as an isolated module.

    ``path`` selects the variant (``py3`` runs CPython 3, ``py27`` is the
    Python-2.7-compatible file); both share the same wire protocol.
    """
    spec = importlib.util.spec_from_file_location(name, path or DAEMON_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.DAEMON_TOKEN = token
    return module


def run_request(daemon, request: dict, ciw_bytes: bytes = b""):
    """Drive one connection end to end.

    Returns ``(ciw_stdin_seen, client_bytes, unread_ciw_bytes, response_json)``
    where ``ciw_stdin_seen`` is what the daemon sent toward the CIW, and
    ``unread_ciw_bytes`` are queued CIW bytes the daemon never consumed (used to
    prove that a request never reads a second frame when log is off).
    """
    payload = json.dumps(request, ensure_ascii=False).encode("utf-8")
    conn = FakeConn(payload)
    fake_stdout = FakeStream()
    fake_stdin = FakeStream(
        ciw_bytes, gate=lambda: bool(fake_stdout.buffer.written)
    )
    old_in, old_out = daemon.sys.stdin, daemon.sys.stdout
    try:
        daemon.sys.stdin, daemon.sys.stdout = fake_stdin, fake_stdout
        daemon.handle_connection(conn)
    finally:
        daemon.sys.stdin, daemon.sys.stdout = old_in, old_out
        daemon._timeout_flag = True
        if daemon._watchdog:
            daemon._watchdog.cancel()
    sent = bytes(conn.sent)
    parsed = None
    if sent[:1] in (STX, NAK) and sent.endswith(RS):
        try:
            parsed = json.loads(sent[1:-1].decode("utf-8"))
        except ValueError:
            parsed = None
    return (
        bytes(fake_stdout.buffer.written),
        sent,
        fake_stdin.buffer.remaining(),
        parsed,
    )


def value_frame(value: str) -> bytes:
    return STX + value.encode("utf-8") + RS


def error_frame(text: str) -> bytes:
    return NAK + text.encode("utf-8") + RS


def meta_frame(path: str | None, start: int, end: int) -> bytes:
    body = f"{path or ''}".encode("utf-8") + US + str(start).encode() + US + str(end).encode()
    return STX + body + RS


__all__ = [
    "BytesBuffer",
    "DAEMON_FILES",
    "DAEMON_PATH",
    "FakeConn",
    "FakeStream",
    "NAK",
    "RS",
    "STX",
    "US",
    "error_frame",
    "load_daemon",
    "meta_frame",
    "run_request",
    "value_frame",
]
