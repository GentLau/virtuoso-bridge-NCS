"""Global SSH connection-establishment gate.

Opening many SSH connections at once (one transport per registered user)
bursts past the remote sshd ``MaxStartups`` limit and the server starts
dropping handshakes with "Error reading SSH protocol banner".  This gate
spreads handshakes across a small bounded window; it is held only while a
connection is being established, never while a session/command runs.
"""

from __future__ import annotations

import threading
import time

_CONNECT_PERMITS = 16
_WAIT_SECONDS = 120.0

_gate = threading.BoundedSemaphore(_CONNECT_PERMITS)


class connect_slot:
    """Blocking context manager around SSH connection establishment."""

    def __enter__(self) -> "connect_slot":
        deadline = time.monotonic() + _WAIT_SECONDS
        while True:
            if _gate.acquire(blocking=False):
                return self
            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                raise TimeoutError("SSH connection gate exhausted")
            time.sleep(0.05)

    def __exit__(self, exc_type, exc, tb) -> None:
        _gate.release()


__all__ = ["connect_slot"]
