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
    """Result of a remote command / file transfer.

    ``kind`` classifies the failure mode (see the architecture §4.4): only
    ``command`` means the returncode is the real command exit code; the bridge
    reserved codes 124/255 are only meaningful when ``kind != "command"``.
    """

    returncode: int
    stdout: str
    stderr: str
    kind: str = "command"


class RoleQuery(BaseModel):
    """Parameter facts of one role (spec §4.2).

    Deliberately limited to ``root``/``bin``: the upper layer must not be able
    to infer topology (mode/host/user/jump/proxy) from this query.
    """

    root: str | None = None
    bin: str | None = None


class QueryResult(BaseModel):
    """Answer of ``middle.query(token=...)``.

    ``status`` is ``success``/``error``; an unknown token is a structured
    failure (``errors=["invalid token"]``) and never an exception.  只返回 role 的
    ``root``/``bin``：本机路径不属于中层的查询范围（spec 总览 §4.2）。
    """

    status: ExecutionStatus
    roles: dict[str, RoleQuery] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


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
    """The five cross-layer interfaces (spec: 三层架构 §4.1).

    Interfaces: Skill / 命令 / 文件（上传+下载）/ GUI 命令 / Spectre 命令。
    GUI 与 Spectre 命令是一次性命令（等价 ``parallel=True`` 语义，无持久
    shell），同样占用该 token 的 channel 预算。``token`` 每次调用必填。
    """

    def execute_skill(
        self,
        skill_code: str,
        timeout: float | None = None,
        *,
        token: str,
        log_level: str | None = None,
        log_max_bytes: int | None = None,
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

    def run_gui_command(
        self, cmd: str, timeout: int | None = None, *, token: str
    ) -> CommandResult: ...

    def run_spectre_command(
        self, cmd: str, timeout: int | None = None, *, token: str
    ) -> CommandResult: ...

    #: Companion read-only query (spec §4.2) — not a sixth business interface:
    #: it never sends, executes or transfers anything, and never consumes the
    #: three budgets or a queue slot.
    def query(self, *, token: str) -> "QueryResult": ...


__all__ = [
    "CommandResult",
    "QueryResult",
    "RoleQuery",
    "ExecutionStatus",
    "Middle",
    "SimulationResult",
    "VirtuosoInterface",
    "VirtuosoResult",
]
