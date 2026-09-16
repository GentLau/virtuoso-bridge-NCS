"""Per-token concurrency budgets (spec: 并发设计 §2/§3, Draft v17).

The token-wide channel budget counts every open SSH channel.  The per-role
``max_sessions`` setting is configured on roles but enforced on the resolved
endpoint: multiple roles sharing one endpoint share one counter and the
effective limit is the minimum of their configured values.
"""
from __future__ import annotations

import threading


class CapacityExceeded(RuntimeError):
    """A token budget cannot accommodate the requested action."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


class _Lease:
    """Idempotent channel lease returned by TokenBudgets."""

    def __init__(self, budgets: "TokenBudgets", endpoint_key: str) -> None:
        self._budgets = budgets
        self.endpoint_key = endpoint_key
        self._lock = threading.Lock()
        self._released = False

    def release(self) -> None:
        with self._lock:
            if self._released:
                return
            self._released = True
        self._budgets._release_channel(self.endpoint_key)

    def __enter__(self) -> "_Lease":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


class TokenBudgets:
    """Thread, token-wide channel, and endpoint channel counters for one token."""

    def __init__(self, *, thread_pool_size: int, channel_budget: int) -> None:
        self.thread_pool_size = int(thread_pool_size)
        self.channel_budget = int(channel_budget)
        self._lock = threading.Lock()
        self._threads = 0
        self._channels = 0
        self._endpoint_limits: dict[str, int] = {}
        self._per_endpoint: dict[str, int] = {}

    # -- endpoint limits ----------------------------------------------------
    def set_endpoint_limit(self, endpoint_key: str, limit: int) -> int:
        with self._lock:
            value = max(1, int(limit))
            previous = self._endpoint_limits.get(endpoint_key)
            effective = value if previous is None else min(previous, value)
            self._endpoint_limits[endpoint_key] = effective
            return effective

    def endpoint_limit(self, endpoint_key: str) -> int:
        with self._lock:
            return self._endpoint_limits.get(endpoint_key, 10)

    # -- thread budget ------------------------------------------------------
    def try_acquire_thread(self) -> bool:
        with self._lock:
            if self._threads >= self.thread_pool_size:
                return False
            self._threads += 1
            return True

    def release_thread(self) -> None:
        with self._lock:
            if self._threads <= 0:
                raise RuntimeError("thread budget released without a lease")
            self._threads -= 1

    @property
    def threads_in_use(self) -> int:
        with self._lock:
            return self._threads

    # -- channel budgets ----------------------------------------------------
    def try_acquire_channel(
        self,
        *,
        endpoint_key: str,
        role_name: str | None = None,  # retained for diagnostics/tests
        role_max_sessions: int | None = None,
    ) -> _Lease | None:
        _ = role_name
        with self._lock:
            if role_max_sessions is not None:
                value = max(1, int(role_max_sessions))
                previous = self._endpoint_limits.get(endpoint_key)
                self._endpoint_limits[endpoint_key] = (
                    value if previous is None else min(previous, value)
                )
            if self._channels >= self.channel_budget:
                return None
            limit = self._endpoint_limits.get(endpoint_key, 10)
            if self._per_endpoint.get(endpoint_key, 0) >= limit:
                return None
            self._channels += 1
            self._per_endpoint[endpoint_key] = self._per_endpoint.get(endpoint_key, 0) + 1
        return _Lease(self, endpoint_key)

    def _release_channel(self, endpoint_key: str) -> None:
        with self._lock:
            if self._channels <= 0 or self._per_endpoint.get(endpoint_key, 0) <= 0:
                raise RuntimeError("channel budget released without a lease")
            self._channels -= 1
            left = self._per_endpoint[endpoint_key] - 1
            if left:
                self._per_endpoint[endpoint_key] = left
            else:
                self._per_endpoint.pop(endpoint_key, None)

    def denial_reason(self, endpoint_key: str) -> str:
        with self._lock:
            if self._channels >= self.channel_budget:
                return "channel budget exceeded"
            limit = self._endpoint_limits.get(endpoint_key, 10)
            if self._per_endpoint.get(endpoint_key, 0) >= limit:
                return "role max_sessions exceeded"
        return "channel budget exceeded"

    @property
    def channels_in_use(self) -> int:
        with self._lock:
            return self._channels

    def channels_in_use_for(self, endpoint_key: str) -> int:
        with self._lock:
            return self._per_endpoint.get(endpoint_key, 0)


__all__ = ["CapacityExceeded", "TokenBudgets"]
