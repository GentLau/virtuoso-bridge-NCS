"""``basic`` business package: one operation per middle-layer interface.

六个业务操作就是中层六个方法的直通（Skill / 命令 / 文件上传 / 文件下载 /
GUI 命令 / Spectre 命令），不做任何编排、不做领域校验：参数结构校验由 Request
完成，运行结果原样放进 Result 的步骤痕迹里，让调用方拿到与中层一致的信息。

按 spec 上层 §2/§4 实现：包只接受一个 ``Middle``，方法同步无状态，
token 每次调用原样透传。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pyapi.models import Middle

#: spec 上层 §4.2：包级自描述（操作名, 方法名, Request, Result）
OPERATION_NAMES = (
    "basic.skill.execute",
    "basic.command.run",
    "basic.file.upload",
    "basic.file.download",
    "basic.gui.run",
    "basic.spectre.run",
)


@dataclass
class Result:
    """Uniform result for the six passthrough operations."""

    ok: bool
    steps: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    result: Any = None


@dataclass(frozen=True)
class SkillRequest:
    token: str
    skill_code: str
    timeout: float | None = None


@dataclass(frozen=True)
class CommandRequest:
    token: str
    cmd: str
    timeout: int | None = None
    parallel: bool = False


@dataclass(frozen=True)
class UploadRequest:
    token: str
    local_path: str
    remote_path: str
    timeout: int | None = None
    recursive: bool = False


@dataclass(frozen=True)
class DownloadRequest:
    token: str
    remote_path: str
    local_path: str
    timeout: int | None = None
    recursive: bool = False


@dataclass(frozen=True)
class GuiRequest:
    token: str
    cmd: str
    timeout: int | None = None


@dataclass(frozen=True)
class SpectreRequest:
    token: str
    cmd: str
    timeout: int | None = None


def _require_token(token: Any) -> str:
    if not isinstance(token, str) or not token:
        raise ValueError("token must be a non-empty string")
    return token


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_timeout(timeout: Any) -> None:
    if timeout is not None and (not isinstance(timeout, (int, float)) or timeout <= 0):
        raise ValueError("timeout must be a positive number or None")


class Package:
    """Direct passthrough of the six middle interfaces (no orchestration)."""

    def __init__(self, middle: Middle) -> None:
        self.middle = middle

    # -- one method per middle interface ---------------------------------------
    def execute_skill(self, request: SkillRequest) -> Result:
        token = _require_token(request.token)
        _require_text(request.skill_code, "skill_code")
        _require_timeout(request.timeout)
        skill = self.middle.execute_skill(
            request.skill_code, timeout=request.timeout, token=token
        )
        return Result(
            ok=bool(skill.ok),
            steps=[{"name": "skill", "ok": bool(skill.ok), "detail": skill}],
            error="; ".join(skill.errors) or None,
            result=skill,
        )

    def run_command(self, request: CommandRequest) -> Result:
        token = _require_token(request.token)
        _require_text(request.cmd, "cmd")
        _require_timeout(request.timeout)
        command = self.middle.run_command(
            request.cmd, timeout=request.timeout, token=token,
            parallel=bool(request.parallel),
        )
        return Result(
            ok=command.returncode == 0,
            steps=[{"name": "command", "ok": command.returncode == 0,
                    "detail": command}],
            error=command.stderr or None,
            result=command,
        )

    def upload_file(self, request: UploadRequest) -> Result:
        token = _require_token(request.token)
        _require_text(request.local_path, "local_path")
        _require_text(request.remote_path, "remote_path")
        _require_timeout(request.timeout)
        upload = self.middle.upload_file(
            Path(request.local_path), request.remote_path,
            timeout=request.timeout, token=token, recursive=bool(request.recursive),
        )
        return Result(
            ok=upload.returncode == 0,
            steps=[{"name": "upload", "ok": upload.returncode == 0, "detail": upload}],
            error=upload.stderr or None,
            result=upload,
        )

    def download_file(self, request: DownloadRequest) -> Result:
        token = _require_token(request.token)
        _require_text(request.remote_path, "remote_path")
        _require_text(request.local_path, "local_path")
        _require_timeout(request.timeout)
        download = self.middle.download_file(
            request.remote_path, Path(request.local_path),
            timeout=request.timeout, token=token, recursive=bool(request.recursive),
        )
        return Result(
            ok=download.returncode == 0,
            steps=[{"name": "download", "ok": download.returncode == 0,
                    "detail": download}],
            error=download.stderr or None,
            result=download,
        )

    def run_gui_command(self, request: GuiRequest) -> Result:
        token = _require_token(request.token)
        _require_text(request.cmd, "cmd")
        _require_timeout(request.timeout)
        gui = self.middle.run_gui_command(request.cmd, timeout=request.timeout, token=token)
        return Result(
            ok=gui.returncode == 0,
            steps=[{"name": "gui", "ok": gui.returncode == 0, "detail": gui}],
            error=gui.stderr or None,
            result=gui,
        )

    def run_spectre_command(self, request: SpectreRequest) -> Result:
        token = _require_token(request.token)
        _require_text(request.cmd, "cmd")
        _require_timeout(request.timeout)
        spectre = self.middle.run_spectre_command(
            request.cmd, timeout=request.timeout, token=token
        )
        return Result(
            ok=spectre.returncode == 0,
            steps=[{"name": "spectre", "ok": spectre.returncode == 0,
                    "detail": spectre}],
            error=spectre.stderr or None,
            result=spectre,
        )


#: 操作名 -> (方法名, Request 模型)
OPERATIONS = (
    ("basic.skill.execute", "execute_skill", SkillRequest, Result),
    ("basic.command.run", "run_command", CommandRequest, Result),
    ("basic.file.upload", "upload_file", UploadRequest, Result),
    ("basic.file.download", "download_file", DownloadRequest, Result),
    ("basic.gui.run", "run_gui_command", GuiRequest, Result),
    ("basic.spectre.run", "run_spectre_command", SpectreRequest, Result),
)

__all__ = [
    "CommandRequest",
    "DownloadRequest",
    "GuiRequest",
    "OPERATIONS",
    "OPERATION_NAMES",
    "Package",
    "Result",
    "SkillRequest",
    "SpectreRequest",
    "UploadRequest",
]
