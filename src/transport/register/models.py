"""Registration request / state models.

These describe the six-step registration flow (see
``spec/design-concepts/底层与中层/多用户设计.md`` §3.2) and are consumed by
the registration HTTP page and the CLI.  They are setup-phase models only;
the runtime consumes ``UserEntry`` from the registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field, model_validator

from transport.registry import UserEntry

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_DEFAULT_SCRATCH = "~/.virtuoso-bridge"


class RegistrationRequest(BaseModel):
    """Step 1 application: required parameters submitted by the user."""

    user: str = Field(min_length=1, max_length=64)
    token: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._-]{1,64}$")
    host: str | None = None               # remote SSH host (command/file host)
    ssh_user: str | None = None           # remote SSH account
    daemon_host: str | None = None        # default: same as host
    daemon_user: str | None = None        # default: same as ssh_user
    daemon_port: int | None = Field(default=None, ge=1, le=65535)
    local_port: int | None = Field(default=None, ge=1, le=65535)
    scratch_root: str = _DEFAULT_SCRATCH  # deploy root
    jump_host: str | None = None
    jump_user: str | None = None
    local: bool = False                   # explicit local mode

    @property
    def mode(self) -> str:
        """local / remote, resolved per the registration spec."""
        if self.local:
            return "local"
        daemon = (self.daemon_host or self.host or "").strip().lower()
        if daemon in _LOCAL_HOSTS:
            return "local"
        if not self.host and not self.ssh_user and not self.jump_host:
            return "local"
        return "remote"

    @model_validator(mode="after")
    def _check_remote_required(self):
        if self.mode == "remote":
            if not self.host:
                raise ValueError("host is required in remote mode")
            if not self.ssh_user:
                raise ValueError("ssh_user is required in remote mode")
        return self

    @property
    def resolved_host(self) -> str:
        return (self.host or "").strip()

    @property
    def resolved_daemon_host(self) -> str:
        return (self.daemon_host or self.host or "127.0.0.1").strip()


@dataclass
class ProbeResult:
    """Step 3 output: candidate entry plus the daemon-file variant."""

    entry: UserEntry
    python_major: int


@dataclass
class ConnectivityReport:
    """Step 5 output; ``ok`` gates the step-6 registry write."""

    token: str
    command_ok: bool
    skill_ok: bool
    token_ok: bool
    banner_hostname: str | None = None
    expected_hostname: str | None = None
    detail: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.command_ok and self.skill_ok


@dataclass
class RegistrationState:
    """In-memory state of one in-progress registration (never persisted)."""

    user: str
    stage: str = "applied"                # validated/probed/deployed/verified/committed/failed
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
