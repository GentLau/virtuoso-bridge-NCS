"""User registry (profile → registry replacement).

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

import json
import threading
import time
from pathlib import Path

from typing import Literal

from pydantic import BaseModel, Field

from transport.runtime_paths import registry_path


class RegistryError(Exception):
    """Base error for registry integrity/usage violations."""


class UserAlreadyRegisteredError(RegistryError):
    """Registering a user name that already exists without ``overwrite=True``."""


class TokenConflictError(RegistryError):
    """Registering a token that already belongs to another user."""


class SkillRoute(BaseModel):
    local_port: int | None = Field(default=None, ge=1, le=65535)
    daemon_host: str | None = None
    daemon_port: int | None = Field(default=None, ge=1, le=65535)


class CommandRoute(BaseModel):
    host: str | None = None
    user: str | None = None


class FileRoute(BaseModel):
    host: str | None = None
    root: str | None = None


class SpectreRoute(BaseModel):
    host: str | None = None
    bin: str | None = None


class JumpRoute(BaseModel):
    host: str | None = None
    user: str | None = None


class Route(BaseModel):
    skill: SkillRoute = Field(default_factory=SkillRoute)
    command: CommandRoute = Field(default_factory=CommandRoute)
    file: FileRoute = Field(default_factory=FileRoute)
    spectre: SpectreRoute = Field(default_factory=SpectreRoute)
    jump: JumpRoute = Field(default_factory=JumpRoute)


class Expected(BaseModel):
    ssh_host_key_fingerprint: str | None = None
    daemon_endpoint_hostname: str | None = None
    daemon_user: str | None = None
    remote_python: str | None = None


class Deploy(BaseModel):
    scratch_root: str = "~/.virtuoso-bridge"


class Ssh(BaseModel):
    backend: Literal["openssh", "paramiko"] = "openssh"
    max_sessions: int = Field(default=10, ge=1)
    proxy: str | None = None
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
    token: str = Field(min_length=1, max_length=64)
    mode: Literal["local", "remote"]  # required, no default
    route: Route = Field(default_factory=Route)
    expected: Expected = Field(default_factory=Expected)
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
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

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

    def users(self) -> list[str]:
        return list(self._entries.keys())

    def entries(self) -> list[tuple[str, UserEntry]]:
        """Snapshot of ``(user, entry)`` pairs for validation/diagnostics."""
        return list(self._entries.items())


def load_registry(path: str | Path | None = None) -> Registry:
    """Convenience loader used once at startup."""
    return Registry(path or registry_path()).load()


__all__ = [
    "CdsLog",
    "CommandRoute",
    "Deploy",
    "Expected",
    "FileRoute",
    "JumpRoute",
    "Registry",
    "RegistryError",
    "Route",
    "Runtime",
    "SkillRoute",
    "SpectreRoute",
    "Ssh",
    "TokenConflictError",
    "UserAlreadyRegisteredError",
    "UserEntry",
    "load_registry",
]
