"""Per-SSH-endpoint connection-establishment budget.

Bursting many handshakes at once trips the remote sshd ``MaxStartups``
limit.  Each endpoint (host/user/jump identity) gets its own bounded budget
so one user never queues behind another user's handshakes, and every wait
inherits the caller's end-to-end deadline.  No module-level mutable
semaphore is shared across endpoints beyond a keyed registry.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager

from typing import Iterator

_registry: dict[str, tuple[int, threading.BoundedSemaphore]] = {}
_registry_lock = threading.Lock()


def _get(endpoint_key: str, budget: int) -> threading.BoundedSemaphore:
    with _registry_lock:
        item = _registry.get(endpoint_key)
        if item is None or item[0] != budget:
            item = (budget, threading.BoundedSemaphore(max(1, int(budget))))
            _registry[endpoint_key] = item
        return item[1]


@contextmanager
def connect_slot(
    endpoint_key: str,
    budget: int = 16,
    deadline: float | None = None,
) -> Iterator[None]:
    """Hold one endpoint connect permit until the handshake completes."""
    sem = _get(endpoint_key, budget)
    acquired = False
    if deadline is None:
        sem.acquire()
        acquired = True
    else:
        while True:
            acquired = sem.acquire(blocking=False)
            if acquired:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError(f"SSH connection budget exhausted for {endpoint_key}")
            time.sleep(0.02)
    try:
        yield
    finally:
        sem.release()


__all__ = ["connect_slot"]
