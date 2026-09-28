"""Interruptible stream/pipe helpers for owned worker threads.

Owned pump threads must be able to observe a ``stop_event`` while a real pipe
or Paramiko channel is idle.  ``read_chunk`` does that by using channel
``recv_ready`` polling or a non-blocking ``os.read`` on the underlying fd.
Streams without a real fd (tests/fakes) keep the legacy blocking fallback.
"""
from __future__ import annotations

import errno
import os
import threading
from typing import Any, Iterator


def _channel_of(stream: Any) -> Any | None:
    channel = getattr(stream, "channel", None)
    if channel is None:
        return None
    if hasattr(channel, "recv_ready") and hasattr(channel, "recv"):
        return channel
    return None


def read_chunk(stream: Any, size: int,
               stop_event: threading.Event | None) -> bytes:
    """Read one chunk without an un-interruptible blocking read."""
    if stop_event is None:
        if hasattr(stream, "read"):
            return stream.read(size)
        if hasattr(stream, "__next__"):
            return next(stream, b"")
        return b""

    channel = _channel_of(stream)
    if channel is not None:
        while not stop_event.is_set():
            if channel.recv_ready():
                return channel.recv(size)
            if channel.exit_status_ready() and not channel.recv_ready():
                return b""
            stop_event.wait(0.01)
        return b""

    try:
        fd = stream.fileno()
    except (AttributeError, OSError, ValueError):
        if stop_event.is_set():
            return b""
        if hasattr(stream, "read"):
            return stream.read(size)
        if hasattr(stream, "__next__"):
            return next(stream, b"")
        return b""
    try:
        os.set_blocking(fd, False)
    except (AttributeError, OSError, ValueError):
        if stop_event.is_set():
            return b""
        if hasattr(stream, "read"):
            return stream.read(size)
        if hasattr(stream, "__next__"):
            return next(stream, b"")
        return b""
    while not stop_event.is_set():
        try:
            return os.read(fd, size)
        except BlockingIOError:
            stop_event.wait(0.01)
        except OSError as exc:
            if getattr(exc, "errno", None) in (errno.EAGAIN, errno.EWOULDBLOCK):
                stop_event.wait(0.01)
                continue
            raise
    return b""


def iter_lines(stream: Any, stop_event: threading.Event | None) -> Iterator[str]:
    """Yield decoded text lines until EOF or ``stop_event`` is set."""
    buffer = b""
    while stop_event is None or not stop_event.is_set():
        chunk = read_chunk(stream, 65536, stop_event)
        if not chunk:
            break
        buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            yield line.decode("utf-8", errors="replace") + "\n"
    if buffer:
        yield buffer.decode("utf-8", errors="replace")
