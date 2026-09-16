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
import ipaddress
import json
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path

try:  # POSIX: advisory file lock used across processes
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from transport.validation import validate_user_name

from transport.runtime_paths import registry_path


def canonical_host(value: str | None) -> str:
    """Canonical host form for endpoint keys and port scoping (配置一览 §6.5).

    ``strip`` -> lowercase -> drop trailing dots -> drop IPv6 brackets, so
    ``Server-A``, ``server-a.`` and ``server-a`` are the same value and
    ``[::1]`` becomes ``::1``.  Never resolves names (no DNS, no ssh config).
    """
    text = (value or "").strip().lower().rstrip(".")
    if len(text) >= 2 and text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    if ":" in text:
        try:
            text = str(ipaddress.ip_address(text))
        except ValueError:
            pass
    return text


@contextmanager
def file_lock(path: Path, *, timeout: float = 30.0):
    """Short-lived cross-process exclusive lock on ``path``.

    POSIX uses ``fcntl.flock``; Windows (no ``flock``) uses ``msvcrt.locking``
    on the first byte, which is the documented equivalent for "one writer at
    a time" semantics (配置一览 §6.4).

    Two details are load-bearing:

    * the sidecar ``*.lock`` file is created once and **never unlinked**.  A
      lock file removed while another process still holds it lets two later
      writers lock *different inodes*, which silently destroys mutual
      exclusion;
    * both backends acquire **non-blocking and retry** until ``timeout``, so a
      stuck holder surfaces as an ``OSError`` instead of hanging registration
      forever.  The lock byte is never written after creation (Windows refuses
      writes into a byte range another process has locked).
    """
    lock_path = Path(path).with_suffix(Path(path).suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                if fcntl is not None:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                else:  # pragma: no cover - Windows
                    import msvcrt
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise OSError(
                        f"timed out after {timeout:g}s waiting for lock {lock_path}"
                    ) from None
                time.sleep(0.02)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_UN)
            else:  # pragma: no cover - Windows
                import msvcrt as _m
                os.lseek(fd, 0, os.SEEK_SET)
                try:
                    _m.locking(fd, _m.LK_UNLCK, 1)
                except OSError:
                    pass
    finally:
        os.close(fd)


class RegistryError(Exception):
    """Base error for registry integrity/usage violations."""


class UserAlreadyRegisteredError(RegistryError):
    """Registering a user name that already exists without ``overwrite=True``."""


class TokenConflictError(RegistryError):
    """Registering a token that already belongs to another user."""


class RoleConfig(BaseModel):
    """Per-role configuration (spec: 配置一览 §2.3).

    ``mode`` is per role; ``None`` means "fall back to ``mode.default``".
    ``root`` is the role's file root; ``None`` means
    ``root.default/<role>``.  ``expected_*`` fields are probe-written
    verification baselines, not user configuration.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    mode: Literal["local", "remote"] | None = None
    host: str | None = None
    user: str | None = None
    jump_host: str | None = None
    jump_user: str | None = None
    proxy: str | None = None
    root: str | None = None
    expected_fingerprint: str | None = None
    max_sessions: int = Field(default=10, ge=1)


class DaemonRoleConfig(RoleConfig):
    """daemon role: Skill endpoint, deployment target, python environment."""

    daemon_port: int | None = Field(default=None, ge=1, le=65535)
    local_port: int | None = Field(default=None, ge=1, le=65535)
    python: str | None = None  # 环境：探测写入（或显式提供后校验）
    expected_hostname: str | None = None
    expected_user: str | None = None


class SpectreRoleConfig(RoleConfig):
    bin: str | None = None


class Roles(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    """The five role configurations; container key in registry.json is ``roles``."""

    gui: RoleConfig = Field(default_factory=RoleConfig)
    daemon: DaemonRoleConfig = Field(default_factory=DaemonRoleConfig)
    command: RoleConfig = Field(default_factory=RoleConfig)
    file: RoleConfig = Field(default_factory=RoleConfig)
    spectre: SpectreRoleConfig = Field(default_factory=SpectreRoleConfig)


class ModeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    """Global mode default (required, no default value)."""

    default: Literal["local", "remote"]


class RootConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    """Global file-root default; ``None`` means ``~/.virtuoso-bridge/<user>``."""

    default: str | None = None


class SshDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    """Global SSH fallback consumed by every remote role field left unset."""

    host: str | None = None
    user: str | None = None
    jump_host: str | None = None
    jump_user: str | None = None
    proxy: str | None = None


class Ssh(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    default: SshDefaults = Field(default_factory=SshDefaults)
    backend: Literal["openssh", "paramiko"] = "paramiko"
    control_master: Literal["auto", "force", "disable"] = "auto"
    tool_override: dict[str, str] = Field(default_factory=dict)


class Runtime(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    thread_pool_size: int = Field(default=32, ge=1)
    channel_budget: int = Field(default=10, ge=1)
    connect_timeout: float = Field(default=15.0, gt=0)


class CdsLog(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    log_level: Literal["off", "all", "warn", "error"] = "all"
    log_max_bytes: int = Field(default=65536, ge=1)


class UserEntry(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    token: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    # mode.default is required; a bare string is accepted as shorthand.
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    mode: ModeConfig | Literal["local", "remote"]
    ssh: Ssh = Field(default_factory=Ssh)
    root: RootConfig = Field(default_factory=RootConfig)
    roles: Roles = Field(default_factory=Roles)
    runtime: Runtime = Field(default_factory=Runtime)
    cdslog: CdsLog = Field(default_factory=CdsLog)
    registered_at: int | None = None  # unix seconds; set at the step-6 commit

    @model_validator(mode="before")
    @classmethod
    def _empty_to_none(cls, data):
        def normalize(value):
            if isinstance(value, dict):
                return {key: normalize(item) for key, item in value.items()}
            if isinstance(value, list):
                return [normalize(item) for item in value]
            if isinstance(value, str) and value.strip() == "":
                return None
            return value

        return normalize(data)

    @model_validator(mode="after")
    def _normalize_mode(self):
        if isinstance(self.mode, str):
            object.__setattr__(self, "mode", ModeConfig(default=self.mode))
        return self

    @model_validator(mode="after")
    def _validate_local_roles(self):
        for name in ("gui", "daemon", "command", "file", "spectre"):
            role = getattr(self.roles, name)
            if (role.mode or self.mode.default) == "local":
                if any((role.host, role.user, role.jump_host,
                        role.jump_user, role.proxy)):
                    raise ValueError(
                        f"role {name} is local: host/user/jump_host/jump_user/proxy must be empty"
                    )
        return self

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
            self._entries = self._read_disk_entries_locked()
            self._rebuild_token_index_locked()
            self._loaded = True
            return self

    def _read_disk_entries_locked(self) -> dict[str, UserEntry]:
        """Parse ``registry.json`` into entries (empty when absent).

        On-disk payloads for users whose configuration is unchanged keep the
        in-memory ``UserEntry`` object, so callers that hold a reference (and
        ``by_token`` identity checks) stay valid across a re-read.
        """
        if not self.path.is_file():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        users = raw if isinstance(raw, dict) else {}
        entries = {}
        for name, value in users.items():
            # a hand-edited registry must not smuggle path separators or other
            # unsafe keys into role roots / on-disk paths
            validate_user_name(str(name))
            entries[str(name)] = UserEntry.model_validate(value)
        for name, entry in entries.items():
            memory = self._entries.get(name)
            if memory is not None and memory.model_dump() == entry.model_dump():
                entries[name] = memory
        return entries

    @staticmethod
    def _lookup_name_in(entries: dict[str, UserEntry], user: str) -> str:
        """User key inside ``entries`` (case-insensitive on Windows)."""
        name = str(user)
        if os.name != "nt":
            return name
        folded = name.casefold()
        for existing in entries:
            if existing.casefold() == folded:
                return existing
        return name

    def _lookup_name_locked(self, user: str) -> str:
        return self._lookup_name_in(self._entries, user)

    @staticmethod
    def _index_of(entries: dict[str, UserEntry]) -> dict[str, str]:
        """Build the token index, refusing a duplicated token."""
        index: dict[str, str] = {}
        for name, entry in entries.items():
            holder = index.get(entry.token)
            if holder is not None:
                raise RegistryError(
                    f"registry is corrupt: token {entry.token!r} is shared by "
                    f"users {holder!r} and {name!r}"
                )
            index[entry.token] = name
        return index

    def _rebuild_token_index_locked(self) -> None:
        self._token_index = self._index_of(self._entries)

    def _save_payload_locked(self, payload: dict) -> None:
        """Write ``payload`` atomically.

        The caller **must** already hold :func:`file_lock` on ``self.path``:
        the lock spans the read-modify-write, not just this write.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        try:
            tmp.chmod(0o600)
        except OSError:
            pass  # Windows filesystems have no POSIX mode
        tmp.replace(self.path)

    def _mutate_locked(self, mutate) -> None:
        """Cross-process read-modify-write of the registry file.

        Each setup-phase mutation re-reads the file *inside* the OS lock, so a
        concurrent registration by another process cannot be overwritten with
        a stale in-memory snapshot (配置一览 §6.4, 多用户与注册).
        """
        with file_lock(self.path):
            entries = self._read_disk_entries_locked()
            mutate(entries)
            index = self._index_of(entries)
            self._save_payload_locked(
                {n: e.model_dump() for n, e in entries.items()}
            )
        self._entries = entries
        self._token_index = index

    def register(self, user: str, entry: UserEntry, *, overwrite: bool = False) -> None:
        """Verify and atomically commit one user entry (setup-phase write)."""
        with self._lock:
            if not self._loaded:
                raise RuntimeError("registry not loaded; call load() once at startup")
            if entry.registered_at is None:
                entry.registered_at = int(time.time())
            requested_name = validate_user_name(str(user))

            def mutate(entries: dict[str, UserEntry]) -> None:
                # On Windows user lookup is case-insensitive. Overwrite must
                # replace the existing key, not create a second case variant.
                name = self._lookup_name_in(entries, requested_name)
                previous = entries.get(name)
                if previous is not None and not overwrite:
                    raise UserAlreadyRegisteredError(
                        f"user {name!r} is already registered; "
                        f"use overwrite=True to replace it"
                    )
                index = self._index_of(entries)
                if previous is not None:
                    index.pop(previous.token, None)  # slot is being replaced
                holder = index.get(entry.token)
                if holder is not None and holder != name:
                    raise TokenConflictError(
                        f"token {entry.token!r} already belongs to user {holder!r}"
                    )
                entries[name] = entry

            self._mutate_locked(mutate)

    def remove(self, user: str) -> None:
        """Remove one user and its token mapping (setup-phase write)."""
        with self._lock:
            if not self._loaded:
                raise RuntimeError("registry not loaded; call load() once at startup")
            def mutate(entries: dict[str, UserEntry]) -> None:
                entries.pop(self._lookup_name_in(entries, user), None)

            self._mutate_locked(mutate)

    def get(self, user: str) -> UserEntry | None:
        return self._entries.get(self._lookup_name_locked(user))

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
    def _text(value: str | None) -> str:
        return (value or "").strip()

    canonical = json.dumps(
        [canonical_host(host), _text(user), canonical_host(jump_host), _text(jump_user), _text(proxy)],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return "v1:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_registry(path: str | Path | None = None) -> Registry:
    """Convenience loader used once at startup."""
    return Registry(path or registry_path()).load()


__all__ = [
    "CdsLog",
    "canonical_host",
    "file_lock",
    "DaemonRoleConfig",
    "ModeConfig",
    "RoleConfig",
    "Roles",
    "RootConfig",
    "Registry",
    "RegistryError",
    "Runtime",
    "SpectreRoleConfig",
    "Ssh",
    "SshDefaults",
    "TokenConflictError",
    "UserAlreadyRegisteredError",
    "UserEntry",
    "endpoint_key",
    "load_registry",
]
