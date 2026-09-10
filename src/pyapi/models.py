"""Upper-facing API models and interface definitions.

Interface definitions belong to the upper layer (pyapi); the middle and bottom
layers implement them without importing upper business code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Any, NamedTuple, Protocol

from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    ERROR = "error"


class VirtuosoResult(BaseModel):
    """Result of a Skill request.

    ``log`` is the CDS.log delta produced by this request, already filtered by
    level and length-limited by the bottom daemon (see the log-return standard).
    """

    status: ExecutionStatus
    output: str = ""
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    execution_time: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    log: str = ""

    @property
    def ok(self) -> bool:
        return self.status == ExecutionStatus.SUCCESS

    @property
    def is_nil(self) -> bool:
        return self.ok and (self.output or "").strip().strip('"') in ("nil", "")

    def save_json(self, path: Path, *, indent: int = 2, encoding: str = "utf-8") -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=indent), encoding=encoding)


class CommandResult(NamedTuple):
    """Result of a remote command / file transfer."""

    returncode: int
    stdout: str
    stderr: str


class SimulationResult(BaseModel):
    status: ExecutionStatus
    tool_version: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == ExecutionStatus.SUCCESS

    def save_json(self, path: Path, *, indent: int = 2, encoding: str = "utf-8") -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=indent), encoding=encoding)


class VirtuosoInterface(ABC):
    """Skill execution interface."""

    @abstractmethod
    def ensure_ready(self, timeout: int = 10) -> VirtuosoResult: ...

    @abstractmethod
    def execute_skill(self, skill_code: str, timeout: float | None = None, *, token: str) -> VirtuosoResult: ...

    @abstractmethod
    def test_connection(self, timeout: int = 10) -> bool: ...


class Middle(Protocol):
    """The three cross-layer capabilities (interface definition).

    ``token`` is a required per-call routing/authorization parameter;
    ``parallel`` is an explicit invocation mode of RunCommand, not a fourth
    interface.
    """

    def execute_skill(
        self, skill_code: str, timeout: float | None = None, *, token: str
    ) -> VirtuosoResult: ...

    def run_command(
        self, cmd: str, timeout: int | None = None, *, token: str, parallel: bool = False
    ) -> CommandResult: ...

    def upload_file(
        self, local_path: Path, remote_path: str, timeout: int | None = None, *, token: str, recursive: bool = False
    ) -> CommandResult: ...

    def download_file(
        self, remote_path: str, local_path: Path, timeout: int | None = None, *, token: str, recursive: bool = False
    ) -> CommandResult: ...


__all__ = [
    "CommandResult",
    "ExecutionStatus",
    "Middle",
    "SimulationResult",
    "VirtuosoInterface",
    "VirtuosoResult",
]
