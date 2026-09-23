"""Fake-CIW harness for the bottom daemon (L0 layer).

The daemon is normally launched by Virtuoso's ``ipcBeginProcess``; this harness
swaps its ``stdin``/``stdout`` for in-memory streams so a test can script the
CIW side of the protocol byte-for-byte (frames, timeouts, rotation, truncation).

Frame grammar (spec: 日志返回设计标准):
    value frame : STX + value         + RS
    error frame : NAK + error text    + RS
    log meta    : STX + path + US + start + US + end + RS

This is the L0 twin of ``test/shared/fixtures/_daemon_harness.py``: unit tests must
not import from the TB tree, so the doubles live here as well.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
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

    def flush(self) -> None:
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

    def flush(self) -> None:
        return None


class FakeConn:
    """Socket stand-in: hands the request over once, records the response."""

    def __init__(self, request: bytes = b"", *, recv_error=None, chunk_size=None,
                 shutdown_error=None) -> None:
        self.request = request
        self.recv_error = recv_error
        self.chunk_size = chunk_size
        self.sent = bytearray()
        self.closed = False
        self.closed_raw = 0
        self.timeout = None
        self.shutdown_calls = 0
        #: raised by ``shutdown()`` when set - a peer that is already gone
        self.shutdown_error = shutdown_error

    def recv(self, size):
        if self.recv_error is not None:
            raise self.recv_error
        if not self.request:
            return b""
        take = size if self.chunk_size is None else min(size, self.chunk_size)
        data, self.request = self.request[:take], self.request[take:]
        return data

    def sendall(self, data) -> None:
        self.sent.extend(data)

    def shutdown(self, how) -> None:
        self.shutdown_calls += 1
        if self.shutdown_error is not None:
            raise self.shutdown_error

    def settimeout(self, timeout) -> None:
        self.timeout = timeout

    def close(self) -> None:
        self.closed_raw += 1


def load_daemon(name: str, token: str = "tok", path=None, argv=None):
    """Import one daemon variant as an isolated module."""
    from pathlib import Path as _Path

    spec = importlib.util.spec_from_file_location(name, _Path(path or DAEMON_PATH))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.DAEMON_TOKEN = token
    if argv is not None:
        module.sys.argv = list(argv)
    return module


class _StreamSwap:
    """Context manager that swaps stdin/stdout and restores daemon globals."""

    def __init__(self, daemon, ciw_bytes: bytes = b"", gate_mode: str = "write"):
        self.daemon = daemon
        self.stdout = FakeStream()
        if gate_mode == "write":
            gate = lambda: bool(self.stdout.buffer.written)  # noqa: E731
        elif gate_mode == "always":
            gate = None
        else:  # pragma: no cover - defensive
            raise ValueError(gate_mode)
        self.stdin = FakeStream(ciw_bytes, gate=gate)
        self._old_in = None
        self._old_out = None

    def __enter__(self):
        self._old_in, self._old_out = self.daemon.sys.stdin, self.daemon.sys.stdout
        self.daemon.sys.stdin, self.daemon.sys.stdout = self.stdin, self.stdout
        return self

    def __exit__(self, *exc):
        self.daemon.sys.stdin, self.daemon.sys.stdout = self._old_in, self._old_out
        self.daemon._timeout_flag = True
        if self.daemon._watchdog:
            self.daemon._watchdog.cancel()
        return False


def run_request(daemon, request, ciw_bytes: bytes = b"", *, conn=None,
                gate_mode: str = "write"):
    """Drive one connection end to end.

    Returns ``(ciw_stdin_seen, client_bytes, unread_ciw_bytes, response_json)``
    where ``ciw_stdin_seen`` is what the daemon sent toward the CIW, and
    ``unread_ciw_bytes`` are queued CIW bytes the daemon never consumed (used to
    prove that a request never reads a second frame when log is off).
    """
    payload = json.dumps(request, ensure_ascii=False).encode("utf-8")
    conn = conn or FakeConn(payload)
    with _StreamSwap(daemon, ciw_bytes, gate_mode=gate_mode) as swap:
        daemon.handle_connection(conn)
    sent = bytes(conn.sent)
    parsed = None
    if sent[:1] in (STX, NAK) and sent.endswith(RS):
        try:
            parsed = json.loads(sent[1:-1].decode("utf-8"))
        except ValueError:
            parsed = None
    return (bytes(swap.stdout.buffer.written), sent, swap.stdin.buffer.remaining(), parsed)


def value_frame(value: str) -> bytes:
    return STX + value.encode("utf-8") + RS


def error_frame(text: str) -> bytes:
    return NAK + text.encode("utf-8") + RS


def meta_frame(path, start: int, end: int) -> bytes:
    body = f"{path or ''}".encode("utf-8") + US + str(start).encode() + US + str(end).encode()
    return STX + body + RS


def request(**overrides) -> dict:
    payload = {"skill": "1+1", "timeout": 5.0, "token": "tok"}
    payload.update(overrides)
    return payload


__all__ = [
    "BytesBuffer",
    "DAEMON_FILES",
    "DAEMON_PATH",
    "FakeConn",
    "FakeStream",
    "NAK",
    "RS",
    "SRC",
    "STX",
    "US",
    "error_frame",
    "load_daemon",
    "meta_frame",
    "request",
    "run_request",
    "value_frame",
]
