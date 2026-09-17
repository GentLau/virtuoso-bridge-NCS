"""In-memory registration reservation candidates (spec: 中层配置文档 §6.4).

Spec v24 changed reservation from a cross-process file lease to an
in-memory, process-local candidate set.  Registration is a low-concurrency
setup flow; the sixth commit is the first and only durable write.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Reservation:
    user: str
    token: str
    daemon_scope: str = "local"
    daemon_port: int | None = None
    local_port: int | None = None

    @classmethod
    def create(
        cls,
        *,
        user: str,
        token: str,
        daemon_scope: str,
        daemon_port: int | None,
        local_port: int | None,
    ) -> "Reservation":
        return cls(
            user=user,
            token=token,
            daemon_scope=daemon_scope or "local",
            daemon_port=daemon_port,
            local_port=local_port,
        )


class ReservationTable:
    """Thread-safe, in-memory candidate table owned by one registration server."""

    def __init__(self, path: str | Path | None = None) -> None:  # noqa: ARG002
        self._lock = threading.RLock()
        self._records: dict[str, Reservation] = {}
        # Kept only as a diagnostic compatibility attribute; never written.
        self.path = Path(path) if path is not None else None

    def _conflicts(self, record: Reservation, *, ignore_user: str | None = None) -> list[str]:
        conflicts: list[str] = []
        for other in self._records.values():
            if ignore_user is not None and other.user == ignore_user:
                continue
            if other.user == record.user:
                conflicts.append(f"user {record.user!r} already has a registration in progress")
            if other.token == record.token:
                conflicts.append(f"token already in use by registration {other.user!r}")
            if (
                record.daemon_port is not None
                and other.daemon_port == record.daemon_port
                and (other.daemon_scope or "local") == (record.daemon_scope or "local")
            ):
                conflicts.append(
                    f"daemon port {record.daemon_port} reserved on "
                    f"{record.daemon_scope} by {other.user!r}"
                )
            if record.local_port is not None and other.local_port == record.local_port:
                conflicts.append(
                    f"local port {record.local_port} reserved by {other.user!r}"
                )
        return conflicts

    def records(self) -> list[Reservation]:
        with self._lock:
            return [Reservation(**vars(record)) for record in self._records.values()]

    def reserve(self, record: Reservation) -> list[str]:
        with self._lock:
            conflicts = self._conflicts(record)
            if conflicts:
                return conflicts
            self._records[record.user] = Reservation(**vars(record))
            return []

    def update(self, record: Reservation) -> list[str]:
        with self._lock:
            conflicts = self._conflicts(record, ignore_user=record.user)
            if conflicts:
                return conflicts
            self._records[record.user] = Reservation(**vars(record))
            return []

    def release(self, user: str) -> bool:
        with self._lock:
            return self._records.pop(user, None) is not None

    def touch(self, user: str) -> None:  # noqa: ARG002
        """No-op: candidates live only for the lifetime of this process."""
        return None


__all__ = ["Reservation", "ReservationTable"]
