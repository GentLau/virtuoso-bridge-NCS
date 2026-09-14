"""Registration request / state models.

These describe the six-step registration flow (see
``spec/design-concepts/底层与中层/多用户设计.md`` §3.2) and are consumed by
the registration HTTP page and the CLI.  They are setup-phase models only;
the runtime consumes ``UserEntry`` from the registry.

Canonical request fields follow 配置一览 §6: ``ssh.default.*`` carries the
global fallback and ``role.<gui|daemon|command|file|spectre>.*`` carries the
per-role override.  Unknown fields are rejected (``extra="forbid"``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from transport.registry import UserEntry

_DEFAULT_SCRATCH = "~/.virtuoso-bridge"


class RequestEndpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str | None = None
    user: str | None = None
    jump_host: str | None = None
    jump_user: str | None = None
    proxy: str | None = None


class RequestDaemon(RequestEndpoint):
    daemon_port: int | None = Field(default=None, ge=1, le=65535)
    local_port: int | None = Field(default=None, ge=1, le=65535)


class RequestSpectre(RequestEndpoint):
    bin: str | None = None


class RequestSsh(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default: RequestEndpoint = Field(default_factory=RequestEndpoint)


class RequestRoles(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gui: RequestEndpoint = Field(default_factory=RequestEndpoint)
    daemon: RequestDaemon = Field(default_factory=RequestDaemon)
    command: RequestEndpoint = Field(default_factory=RequestEndpoint)
    file: RequestEndpoint = Field(default_factory=RequestEndpoint)
    spectre: RequestSpectre = Field(default_factory=RequestSpectre)


class RegistrationRequest(BaseModel):
    """Step 1 application: required parameters submitted by the user."""

    model_config = ConfigDict(extra="forbid")

    user: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    token: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._-]{1,64}$")
    mode: Literal["local", "remote"]      # mandatory; never inferred
    scratch_root: str = _DEFAULT_SCRATCH  # deploy root

    ssh: RequestSsh = Field(default_factory=RequestSsh)
    role: RequestRoles = Field(default_factory=RequestRoles)

    # runtime / transport / log policies (optional; defaults live in UserEntry)
    ssh_backend: Literal["openssh", "paramiko"] | None = None
    ssh_control_master: Literal["auto", "force", "disable"] | None = None
    ssh_tool_override: dict[str, str] | None = None
    thread_pool_size: int | None = Field(default=None, ge=1)
    channel_budget: int | None = Field(default=None, ge=1)
    connect_timeout: float | None = Field(default=None, gt=0)
    log_level: Literal["off", "all", "warn", "error"] | None = None
    log_max_bytes: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _check_remote_required(self):
        if self.mode == "remote":
            if not (self.ssh.default.host or "").strip():
                raise ValueError("ssh.default.host is required in remote mode")
            if not (self.ssh.default.user or "").strip():
                raise ValueError("ssh.default.user is required in remote mode")
        user = self.user or ""
        if user.startswith(("/", "\\")) or "/" in user or "\\" in user or ".." in user:
            raise ValueError("user must be a single path segment (no '/', '\', '..', absolute path)")
        return self


@dataclass
class ProbeResult:
    """Step 3 output: candidate entry plus the daemon-file variant."""

    entry: UserEntry
    python_major: int
    warnings: list[str] = field(default_factory=list)


@dataclass
class ConnectivityReport:
    """Step 5 output; ``ok`` gates the step-6 registry write."""

    token: str
    command_ok: bool
    skill_ok: bool
    token_ok: bool
    fingerprint_ok: bool = True
    banner_hostname: str | None = None
    expected_hostname: str | None = None
    detail: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.command_ok and self.skill_ok and self.token_ok and self.fingerprint_ok


@dataclass
class RegistrationState:
    """In-memory state of one in-progress registration (never persisted)."""

    user: str
    stage: str = "applied"                # validated/probed/deployed/verified/committed/failed
    step: int = 0                         # current six-step position (1..6)
    request: RegistrationRequest | None = None
    entry: UserEntry | None = None
    python_major: int | None = None
    setup_path: str | None = None
    token: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    report: ConnectivityReport | None = None


__all__ = [
    "ConnectivityReport",
    "ProbeResult",
    "RegistrationRequest",
    "RegistrationState",
]
