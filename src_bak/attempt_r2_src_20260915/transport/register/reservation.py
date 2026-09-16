"""Cross-step registration reservations (配置一览 §6.4).

A registration in progress (steps 2..6) holds one record in
``<working dir>/registry.reservation`` so that two concurrent registrations
cannot pick the same user / token / daemon port / local port.

Contract (frozen in the spec):

- the file holds a *set* of records — concurrent registrations are not
  serialised by one long-lived lock;
- the lock around it is short: it is held only while reading/modifying the
  file ("read-modify-write + atomic replace"), never while waiting for the
  user to load the setup in the CIW;
- a record carries ``pid`` + ``created_at``/``updated_at``, so a crashed
  registration is reclaimed by the next reader (missing pid or stale
  timestamp), which keeps the mechanism crash-safe on both POSIX and Windows;
- uniqueness scope: ``token``/``user`` globally, ``daemon_port`` per daemon
  target host, ``local_port`` on the local machine.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from transport.registry import file_lock
from transport.runtime_paths import registry_path

STALE_AFTER_SECONDS = 900.0


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _pid_alive(pid: int) -> bool:
    """Best-effort liveness probe (never kills anything)."""
    if pid <= 0:
        return False
    if os.name == "nt":  # pragma: no cover - Windows
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            try:
                code = ctypes.c_ulong()
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                    return False
                return code.value == STILL_ACTIVE
            finally:
                kernel32.CloseHandle(handle)
        except Exception:  # noqa: BLE001 - never fail a registration on this
            return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


@dataclass
class Reservation:
    user: str
    token: str
    daemon_scope: str = "local"
    daemon_port: int | None = None
    local_port: int | None = None
    pid: int = 0
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def create(cls, *, user: str, token: str, daemon_scope: str,
               daemon_port: int | None, local_port: int | None) -> "Reservation":
        stamp = _now()
        return cls(
            user=user, token=token, daemon_scope=daemon_scope,
            daemon_port=daemon_port, local_port=local_port,
            pid=os.getpid(), created_at=stamp, updated_at=stamp,
        )

    @classmethod
    def from_dict(cls, raw: dict) -> "Reservation":
        return cls(
            user=str(raw.get("user", "")),
            token=str(raw.get("token", "")),
            daemon_scope=str(raw.get("daemon_scope", "local") or "local"),
            daemon_port=raw.get("daemon_port"),
            local_port=raw.get("local_port"),
            pid=int(raw.get("pid") or 0),
            created_at=str(raw.get("created_at", "")),
            updated_at=str(raw.get("updated_at", "")),
        )

    def to_dict(self) -> dict:
        return {
            "user": self.user, "token": self.token,
            "daemon_scope": self.daemon_scope, "daemon_port": self.daemon_port,
            "local_port": self.local_port, "pid": self.pid,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }


class ReservationTable:
    """Record set backed by one JSON file, guarded by a short file lock."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else registry_path().with_name("registry.reservation")

    # -- file plumbing -----------------------------------------------------
    @contextmanager
    def _locked(self):
        with file_lock(self.path):
            yield

    def _read_locked(self) -> list[dict]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if not isinstance(raw, list):
            return []
        return [r for r in raw if isinstance(r, dict)]

    def _write_locked(self, records: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            tmp.chmod(0o600)
        except OSError:
            pass  # Windows filesystems have no POSIX mode
        tmp.replace(self.path)

    @staticmethod
    def _is_stale(record: dict) -> bool:
        try:
            updated = float(record.get("updated_at_epoch") or 0)
        except (TypeError, ValueError):
            updated = 0.0
        if updated and (time.time() - updated) > STALE_AFTER_SECONDS:
            return True
        pid = int(record.get("pid") or 0)
        if pid and not _pid_alive(pid):
            return True
        return False

    def _prune(self, records: list[dict]) -> tuple[list[dict], list[str]]:
        live = [r for r in records if not self._is_stale(r)]
        removed = [str(r.get("user", "")) for r in records if self._is_stale(r)]
        return live, removed

    # -- public API --------------------------------------------------------
    def records(self) -> list[Reservation]:
        """Live records; stale ones are reclaimed as a side effect."""
        with self._locked():
            raw = self._read_locked()
            live, removed = self._prune(raw)
            if removed:
                self._write_locked(live)
            return [Reservation.from_dict(r) for r in live]

    def reserve(self, record: Reservation) -> list[str]:
        """Add ``record``; returns a list of conflict reasons (empty = ok)."""
        conflicts: list[str] = []
        with self._locked():
            raw = self._read_locked()
            live, removed = self._prune(raw)
            for other in live:
                if other.get("user") == record.user:
                    conflicts.append(f"user {record.user!r} already has a registration in progress")
                if other.get("token") == record.token:
                    conflicts.append(f"token already in use by registration {other.get('user')!r}")
                if (record.daemon_port is not None
                        and other.get("daemon_port") == record.daemon_port
                        and (other.get("daemon_scope") or "local") == (record.daemon_scope or "local")):
                    conflicts.append(
                        f"daemon port {record.daemon_port} reserved on "
                        f"{record.daemon_scope} by {other.get('user')!r}"
                    )
                if (record.local_port is not None
                        and other.get("local_port") == record.local_port):
                    conflicts.append(
                        f"local port {record.local_port} reserved by {other.get('user')!r}"
                    )
            if conflicts:
                if removed:
                    self._write_locked(live)
                return conflicts
            payload = record.to_dict()
            payload["updated_at_epoch"] = time.time()
            live.append(payload)
            self._write_locked(live)
            return []

    def update(self, record: Reservation) -> list[str]:
        """Replace ``record.user``'s entry with fresh ports (one atomic step)."""
        with self._locked():
            raw = self._read_locked()
            live, removed = self._prune(raw)
            others = [r for r in live if r.get("user") != record.user]
            conflicts: list[str] = []
            for other in others:
                if other.get("token") == record.token:
                    conflicts.append(f"token already in use by registration {other.get('user')!r}")
                if (record.daemon_port is not None
                        and other.get("daemon_port") == record.daemon_port
                        and (other.get("daemon_scope") or "local") == (record.daemon_scope or "local")):
                    conflicts.append(
                        f"daemon port {record.daemon_port} reserved on "
                        f"{record.daemon_scope} by {other.get('user')!r}"
                    )
                if (record.local_port is not None
                        and other.get("local_port") == record.local_port):
                    conflicts.append(
                        f"local port {record.local_port} reserved by {other.get('user')!r}"
                    )
            if conflicts:
                if removed:
                    self._write_locked(live)
                return conflicts
            payload = record.to_dict()
            payload["updated_at_epoch"] = time.time()
            others.append(payload)
            self._write_locked(others)
            return []

    def release(self, user: str) -> bool:
        """Drop ``user``'s record; returns True when something was removed."""
        with self._locked():
            raw = self._read_locked()
            live, removed = self._prune(raw)
            kept = [r for r in live if r.get("user") != user]
            found = len(kept) != len(live)
            if found or removed:
                self._write_locked(kept)
            return found

    def touch(self, user: str) -> None:
        """Refresh ``updated_at`` (long-running step, avoids stale reclaim)."""
        with self._locked():
            raw = self._read_locked()
            live, removed = self._prune(raw)
            for record in live:
                if record.get("user") == user:
                    record["updated_at"] = _now()
                    record["updated_at_epoch"] = time.time()
            if live or removed:
                self._write_locked(live)


__all__ = ["Reservation", "ReservationTable", "STALE_AFTER_SECONDS", "_pid_alive"]
