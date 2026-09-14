"""User registry (single source of per-user configuration).

The registry is the single source of truth for every runtime configuration
item: one verified ``registry.json`` under the local working directory.

Lifecycle contract:

- **Load once**: ``load()`` (or ``load_registry``) reads the file into memory
  a single time; every later lookup is an in-memory access.  The business
  path must never touch the filesystem.
- **Rare writes only from registration/removal**: ``register()`` / ``remove()``
  are the only writers and atomically replace the file (tmp + replace).
  They are setup-phase operations, not runtime operations.
- **Verified registry**: duplicate users are refused by default, tokens are
  unique across users, and loading a file with duplicate tokens fails fast.

严禁高频文件 IO：业务路径只能调用一次 ``load()``，之后全部走内存缓存。
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path

try:  # POSIX: advisory file lock used across processes
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None

from typing import Literal

from pydantic import BaseModel, Field

from transport.runtime_paths import registry_path


class RegistryError(Exception):
    """Base error for registry integrity/usage violations."""


class UserAlreadyRegisteredError(RegistryError):
    """Registering a user name that already exists without ``overwrite=True``."""


class TokenConflictError(RegistryError):
    """Registering a token that already belongs to another user."""


class EndpointConfig(BaseModel):
    """Per-role endpoint policy: each field falls back to ``ssh.default.*``."""

    host: str | None = None
    user: str | None = None
    jump_host: str | None = None
    jump_user: str | None = None
    proxy: str | None = None


class DaemonConfig(EndpointConfig):
    """The only role with ports (daemon listen port + local tunnel port)."""

    daemon_port: int | None = Field(default=None, ge=1, le=65535)
    local_port: int | None = Field(default=None, ge=1, le=65535)


class SpectreConfig(EndpointConfig):
    """Spectre role is recorded this version, never consumed by business calls."""

    bin: str | None = None


class SshDefaults(EndpointConfig):
    """Global SSH fallback consumed by every role field left unset."""


class Route(BaseModel):
    gui: EndpointConfig = Field(default_factory=EndpointConfig)
    daemon: DaemonConfig = Field(default_factory=DaemonConfig)
    command: EndpointConfig = Field(default_factory=EndpointConfig)
    file: EndpointConfig = Field(default_factory=EndpointConfig)
    spectre: SpectreConfig = Field(default_factory=SpectreConfig)


class Expected(BaseModel):
    ssh_endpoints: dict[str, str] = Field(default_factory=dict)  # per business SSH endpoint
    daemon_endpoint_hostname: str | None = None
    daemon_user: str | None = None


class Environment(BaseModel):
    remote_python: str | None = None  # detected on the remote side, consumed there


class Deploy(BaseModel):
    scratch_root: str = "~/.virtuoso-bridge"


class Ssh(BaseModel):
    default: SshDefaults = Field(default_factory=SshDefaults)
    backend: Literal["openssh", "paramiko"] = "openssh"
    control_master: str = "auto"
    tool_override: dict[str, str] = Field(default_factory=dict)


class Runtime(BaseModel):
    thread_pool_size: int = Field(default=32, ge=1)
    channel_budget: int = Field(default=10, ge=1)
    connect_timeout: float = Field(default=15.0, gt=0)


class CdsLog(BaseModel):
    log_level: Literal["off", "all", "warn", "error"] = "all"
    log_max_bytes: int = Field(default=65536, ge=1)


class UserEntry(BaseModel):
    token: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    mode: Literal["local", "remote"]  # required, no default
    route: Route = Field(default_factory=Route)
    expected: Expected = Field(default_factory=Expected)
    environment: Environment = Field(default_factory=Environment)
    deploy: Deploy = Field(default_factory=Deploy)
    ssh: Ssh = Field(default_factory=Ssh)
    runtime: Runtime = Field(default_factory=Runtime)
    cdslog: CdsLog = Field(default_factory=CdsLog)
    registered_at: int | None = None # unix seconds; set at the step-6 commit


class Registry:
    """Load-once, in-memory, verified user registry."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._entries: dict[str, UserEntry] = {}
        self._token_index: dict[str, str] = {}
        self._lock = threading.Lock()
        self._loaded = False

    def load(self) -> "Registry":
        """Read registry.json once into memory.  Subsequent calls are no-ops."""
        with self._lock:
            if self._loaded:
                return self
            if self.path.is_file():
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                users = raw.get("users", {}) if isinstance(raw, dict) else {}
                self._entries = {
                    str(name): UserEntry.model_validate(value)
                    for name, value in users.items()
                }
                self._rebuild_token_index_locked()
            self._loaded = True
            return self

    def _rebuild_token_index_locked(self) -> None:
        self._token_index = {}
        for name, entry in self._entries.items():
            if entry.token in self._token_index:
                other = self._token_index[entry.token]
                raise RegistryError(
                    f"registry is corrupt: token {entry.token!r} is shared by "
                    f"users {other!r} and {name!r}"
                )
            self._token_index[entry.token] = name

    def _save_payload_locked(self, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_suffix(".json.lock")
        tmp = self.path.with_suffix(".json.tmp")
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            os.write(fd, b"0")  # keep a byte so msvcrt can lock a real region
            os.lseek(fd, 0, os.SEEK_SET)
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_EX)
            else:
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
            try:
                tmp.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                try:
                    tmp.chmod(0o600)
                except OSError:
                    pass  # Windows filesystems have no POSIX mode
                tmp.replace(self.path)
            finally:
                if fcntl is not None:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                else:
                    import msvcrt as _m
                    os.lseek(fd, 0, os.SEEK_SET)
                    _m.locking(fd, _m.LK_UNLCK, 1)
        finally:
            os.close(fd)

    def register(self, user: str, entry: UserEntry, *, overwrite: bool = False) -> None:
        """Verify and atomically commit one user entry (setup-phase write)."""
        with self._lock:
            if not self._loaded:
                raise RuntimeError("registry not loaded; call load() once at startup")
            if entry.registered_at is None:
                entry.registered_at = int(time.time())
            name = str(user)
            previous = self._entries.get(name)
            if previous is not None and not overwrite:
                raise UserAlreadyRegisteredError(
                    f"user {name!r} is already registered; "
                    f"use overwrite=True to replace it"
                )
            holder = self._token_index.get(entry.token)
            if holder is not None and holder != name:
                raise TokenConflictError(
                    f"token {entry.token!r} already belongs to user {holder!r}"
                )
            if previous is not None and previous.token != entry.token:
                # persist first; only commit memory after the replace succeeds
                new_entries = dict(self._entries)
                new_entries[name] = entry
                new_index = dict(self._token_index)
                new_index.pop(previous.token, None)
                new_index[entry.token] = name
                self._save_payload_locked(
                    {"users": {n: e.model_dump() for n, e in new_entries.items()}}
                )
                self._entries = new_entries
                self._token_index = new_index
                return
            new_entries = dict(self._entries)
            new_entries[name] = entry
            new_index = dict(self._token_index)
            new_index[entry.token] = name
            self._save_payload_locked(
                {"users": {n: e.model_dump() for n, e in new_entries.items()}}
            )
            self._entries = new_entries
            self._token_index = new_index

    def remove(self, user: str) -> None:
        """Remove one user and its token mapping (setup-phase write)."""
        with self._lock:
            if not self._loaded:
                raise RuntimeError("registry not loaded; call load() once at startup")
            name = str(user)
            previous = self._entries.get(name)
            if previous is not None:
                new_entries = dict(self._entries)
                new_entries.pop(name, None)
                new_index = dict(self._token_index)
                new_index.pop(previous.token, None)
                self._save_payload_locked(
                    {"users": {n: e.model_dump() for n, e in new_entries.items()}}
                )
                self._entries = new_entries
                self._token_index = new_index

    def get(self, user: str) -> UserEntry | None:
        return self._entries.get(str(user))

    def by_token(self, token: str) -> UserEntry | None:
        """O(1) token lookup against the in-memory index."""
        name = self._token_index.get(token)
        return self._entries.get(name) if name is not None else None

    def user_of(self, token: str) -> str | None:
        """Human-readable username owning a token (for user-visible paths)."""
        return self._token_index.get(token)

    def users(self) -> list[str]:
        return list(self._entries.keys())

    def entries(self) -> list[tuple[str, UserEntry]]:
        """Snapshot of ``(user, entry)`` pairs for validation/diagnostics."""
        return list(self._entries.items())


def endpoint_key(
    host: str,
    user: str | None = None,
    jump_host: str | None = None,
    jump_user: str | None = None,
    proxy: str | None = None,
) -> str:
    """Versioned, unambiguous SSH endpoint identity (配置一览 §6.5).

    ``v1:`` + SHA256 of the canonical JSON array
    ``[host, user, jump_host, jump_user, proxy]``.  Hosts are lowercased and
    stripped of trailing dots; empty values become ``""``.
    """
    def _host(value: str | None) -> str:
        return (value or "").strip().rstrip(".").lower()

    def _text(value: str | None) -> str:
        return (value or "").strip()

    canonical = json.dumps(
        [_host(host), _text(user), _host(jump_host), _text(jump_user), _text(proxy)],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return "v1:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_registry(path: str | Path | None = None) -> Registry:
    """Convenience loader used once at startup."""
    return Registry(path or registry_path()).load()


__all__ = [
    "CdsLog",
    "EndpointConfig",
    "Deploy",
    "Expected",
    "SpectreConfig",
    "SshDefaults",
    "Registry",
    "RegistryError",
    "Route",
    "Runtime",
    "DaemonConfig",

    "Ssh",
    "TokenConflictError",
    "endpoint_key",
    "UserAlreadyRegisteredError",
    "UserEntry",
    "load_registry",
]
