"""Registration request / state models.

Six-step registration (spec: 多用户设计 §3.2).  Canonical request fields
follow 配置一览 §6: ``mode.default`` + ``ssh.default.*`` + ``root.default`` +
``roles.<gui|daemon|command|file|spectre>.*``.  Unknown fields are rejected.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    field_validator,
    model_validator,
)

from common.registry import UserEntry
from common.validation import validate_display, validate_token, validate_user_name


class RequestRole(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["local", "remote"] | None = None
    host: str | None = None
    user: str | None = None
    jump_host: str | None = None
    jump_user: str | None = None
    proxy: str | None = None
    root: str | None = None
    max_sessions: StrictInt | None = Field(default=None, ge=1)
    expected_fingerprint: str | None = None


class RequestDaemonRole(RequestRole):
    daemon_port: StrictInt | None = Field(default=None, ge=1, le=65535)
    local_port: StrictInt | None = Field(default=None, ge=1, le=65535)
    python: str | None = None
    expected_hostname: str | None = None
    expected_user: str | None = None


class RequestGuiRole(RequestRole):
    display: str | None = None

    @field_validator("display")
    @classmethod
    def _validate_display(cls, value):
        return validate_display(value)


class RequestSpectreRole(RequestRole):
    bin: str | None = None


class RequestRoles(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gui: RequestGuiRole = Field(default_factory=RequestGuiRole)
    daemon: RequestDaemonRole = Field(default_factory=RequestDaemonRole)
    command: RequestRole = Field(default_factory=RequestRole)
    file: RequestRole = Field(default_factory=RequestRole)
    spectre: RequestSpectreRole = Field(default_factory=RequestSpectreRole)


class RequestMode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default: Literal["local", "remote"]  # required, no default


class RequestRoot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default: str | None = None  # None -> ~/.virtuoso-bridge/<user>


class RequestEndpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str | None = None
    user: str | None = None
    jump_host: str | None = None
    jump_user: str | None = None
    proxy: str | None = None


class RequestSsh(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default: RequestEndpoint = Field(default_factory=RequestEndpoint)


class RegistrationRequest(BaseModel):
    """Step 1 application: required parameters submitted by the user."""

    model_config = ConfigDict(extra="forbid")

    user: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    token: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._-]{1,64}$")
    # mode.default is required; a bare "local"/"remote" is accepted as shorthand.
    mode: RequestMode | Literal["local", "remote"]
    ssh: RequestSsh = Field(default_factory=RequestSsh)
    root: RequestRoot = Field(default_factory=RequestRoot)
    roles: RequestRoles = Field(default_factory=RequestRoles)

    # runtime / transport / log policies (optional; defaults live in UserEntry)
    ssh_backend: Literal["openssh", "paramiko"] | None = None
    ssh_control_master: Literal["auto", "force", "disable"] | None = None
    ssh_tool_override: dict[str, str] | None = None
    thread_pool_size: StrictInt | None = Field(default=None, ge=1)
    channel_budget: StrictInt | None = Field(default=None, ge=1)
    connect_timeout: StrictFloat | None = Field(
        default=None, gt=0, allow_inf_nan=False
    )
    log_level: Literal["off", "all", "warn", "error"] | None = None
    log_max_bytes: StrictInt | None = Field(default=None, ge=1)

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
            object.__setattr__(self, "mode", RequestMode(default=self.mode))
        return self

    @model_validator(mode="after")
    def _check_roles(self):
        validate_user_name(self.user)
        if self.token is not None:
            validate_token(self.token)
        for name in ("gui", "daemon", "command", "file", "spectre"):
            role = getattr(self.roles, name)
            role_mode = role.mode or self.mode.default
            conn = (role.host, role.user, role.jump_host, role.jump_user, role.proxy)
            if role_mode == "local":
                if any(v for v in conn):
                    raise ValueError(
                        f"role {name} is local: host/user/jump/proxy must not be set"
                    )
            else:
                host = role.host or self.ssh.default.host
                account = role.user or self.ssh.default.user
                if not host:
                    raise ValueError(f"role {name} is remote: host is required")
                if not account:
                    raise ValueError(f"role {name} is remote: user is required")
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
