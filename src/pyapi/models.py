"""Upper-facing API models and interface definitions.

Interface definitions belong to the upper layer (pyapi); the middle and bottom
layers implement them without importing upper business code.
"""

from __future__ import annotations

import dataclasses
import functools
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_serializer


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
    log: str = ""

    @field_serializer("execution_time", when_used="json")
    def _round_execution_time(self, value: float | None) -> float | None:
        return None if value is None else round(value, 3)

    @model_serializer(mode="wrap")
    def _json_key_names(self, handler, info):
        data = handler(self)
        if info.mode == "json":
            data["CDSlog"] = data.pop("log", "")
        return data

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


def skill_log_kwargs(
    log_level: str | None,
    log_max_bytes: int | None,
) -> dict[str, Any]:
    """Return only the explicitly supplied Skill log options.

    Upper-layer operations call this at the Skill boundary.  ``None`` means
    "not supplied" and must be omitted so the middle keeps the per-user
    registry default.
    """
    kwargs: dict[str, Any] = {}
    if log_level is not None:
        kwargs["log_level"] = log_level
    if log_max_bytes is not None:
        kwargs["log_max_bytes"] = log_max_bytes
    return kwargs


class ResultBase:
    """Common upper-layer Result contract.

    ``ok`` / ``steps`` / ``error`` stay owned by the package Result dataclass;
    ``step_details`` is a response-only switch (not a dataclass field so it
    cannot disturb existing positional constructors).

    The JSON serialization rule lives here so every package gets the same
    behavior: on success, ``steps`` is omitted unless ``step_details=true``;
    on failure, ``steps`` is always kept.
    """

    step_details = False

    def model_dump(self, mode: str | None = None, **_: Any) -> dict[str, Any]:
        data = {
            field.name: getattr(self, field.name)
            for field in dataclasses.fields(self)
            if field.name != "step_details"
        }
        if getattr(self, "ok", False) and not getattr(self, "step_details", False):
            data.pop("steps", None)
        return data


def _finalize_step_details(method):
    @functools.wraps(method)
    def wrapper(self, *args: Any, **kwargs: Any) -> Any:
        result = method(self, *args, **kwargs)
        if isinstance(result, ResultBase):
            request = args[0] if args else kwargs.get("request")
            result.step_details = bool(getattr(request, "step_details", False))
        return result

    return wrapper


class ResultPackage:
    """Set each operation's Result ``step_details`` from its Request."""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        for name, attr in list(cls.__dict__.items()):
            if name.startswith("_") or not callable(attr):
                continue
            if isinstance(attr, (staticmethod, classmethod)):
                continue
            setattr(cls, name, _finalize_step_details(attr))


class CommandResult(BaseModel):
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

    Deliberately limited to ``root``, the GUI execution fact ``display``,
    the Spectre ``bin`` fact, and raw per-role user groups: the upper layer
    must not be able to infer topology (mode/host/user/jump/proxy) from this
    query.  Unconfigured fixed fields serialize as omitted keys.
    """

    model_config = ConfigDict(extra="allow")

    root: str | None = None
    bin: str | None = None
    display: str | None = None

    @model_serializer(mode="wrap")
    def _omit_unconfigured(self, handler):
        return {
            key: value
            for key, value in handler(self).items()
            if value is not None
        }


class QueryResult(BaseModel):
    """Answer of ``middle.query(token=...)``.

    ``status`` is ``success``/``error``; an unknown token is a structured
    failure (``errors=["invalid token"]``) and never an exception.  返回 role 的
    ``root``、gui 的 ``display`` 与 spectre 的 ``bin``；本机路径不属于中层的
    查询范围（spec 总览 §4.2）。
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
    def execute_skill(
        self,
        skill_code: str,
        timeout: float | None = None,
        *,
        token: str,
        log_level: str | None = None,
        log_max_bytes: int | None = None,
    ) -> VirtuosoResult: ...

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
    def query(
        self,
        *,
        token: str,
        role: str | None = None,
        name: str | None = None,
    ) -> "QueryResult": ...


__all__ = [
    "CommandResult",
    "QueryResult",
    "ResultBase",
    "ResultPackage",
    "RoleQuery",
    "skill_log_kwargs",
    "ExecutionStatus",
    "Middle",
    "SimulationResult",
    "VirtuosoInterface",
    "VirtuosoResult",
]
