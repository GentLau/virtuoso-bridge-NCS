"""File -> Skill -> command -> file business package.

The package is upper-layer code: it only calls the five middle interfaces and
never imports SSH, sockets, registry internals, or daemon code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pyapi.models import CommandResult, Middle, VirtuosoResult


@dataclass
class BusinessStep:
    name: str
    ok: bool
    detail: Any = None


@dataclass
class BusinessResult:
    ok: bool
    steps: list[BusinessStep] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class Request:
    """Structural request model for ``demo.pipeline.run`` (顶层 §3)."""

    token: str
    local_input: str
    remote_input: str
    skill_code: str
    command: str
    remote_output: str
    local_output: str
    timeout: float | None = None
    recursive: bool = False


OPERATION_NAME = "demo.pipeline.run"


def _validate(request: Request) -> None:
    for name in ("token", "local_input", "remote_input", "skill_code",
                 "command", "remote_output", "local_output"):
        value = getattr(request, name)
        if not isinstance(value, str) or not value:
            raise ValueError(f"{name} must be a non-empty string")
    if request.timeout is not None and request.timeout <= 0:
        raise ValueError("timeout must be positive or None")


class FileSkillCommandFilePackage:
    def __init__(self, middle: Middle) -> None:
        self.middle = middle

    def run(
        self,
        *,
        token: str,
        local_input: str | Path,
        remote_input: str,
        skill_code: str,
        command: str,
        remote_output: str,
        local_output: str | Path,
        timeout: float | None = None,
        recursive: bool = False,
    ) -> BusinessResult:
        steps: list[BusinessStep] = []
        up: CommandResult = self.middle.upload_file(
            Path(local_input), remote_input, timeout=timeout, token=token,
            recursive=recursive,
        )
        steps.append(BusinessStep("upload", up.returncode == 0, up))
        if up.returncode != 0:
            return BusinessResult(False, steps, up.stderr or "upload failed")

        skill: VirtuosoResult = self.middle.execute_skill(
            skill_code, timeout=timeout, token=token
        )
        steps.append(BusinessStep("skill", skill.ok, skill))
        if not skill.ok:
            return BusinessResult(False, steps, "; ".join(skill.errors) or "skill failed")

        cmd: CommandResult = self.middle.run_command(command, timeout=timeout, token=token)
        steps.append(BusinessStep("command", cmd.returncode == 0, cmd))
        if cmd.returncode != 0:
            return BusinessResult(False, steps, cmd.stderr or "command failed")

        down: CommandResult = self.middle.download_file(
            remote_output, Path(local_output), timeout=timeout, token=token,
            recursive=recursive,
        )
        steps.append(BusinessStep("download", down.returncode == 0, down))
        if down.returncode != 0:
            return BusinessResult(False, steps, down.stderr or "download failed")
        return BusinessResult(True, steps)


    def run_request(self, request: Request) -> BusinessResult:
        """Spec-shaped entry point: ``method(request) -> Result`` (上层 §2.2)."""
        _validate(request)
        return self.run(
            token=request.token,
            local_input=request.local_input,
            remote_input=request.remote_input,
            skill_code=request.skill_code,
            command=request.command,
            remote_output=request.remote_output,
            local_output=request.local_output,
            timeout=request.timeout,
            recursive=request.recursive,
        )


__all__ = [
    "BusinessResult",
    "BusinessStep",
    "FileSkillCommandFilePackage",
    "OPERATION_NAME",
    "Request",
]
