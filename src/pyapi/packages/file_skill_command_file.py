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


__all__ = ["BusinessResult", "BusinessStep", "FileSkillCommandFilePackage"]
