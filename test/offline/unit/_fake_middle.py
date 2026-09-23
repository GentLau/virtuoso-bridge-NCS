"""Recording fake for the ``pyapi.models.Middle`` protocol (L0 contract tests).

Why this module exists
----------------------
Every upper-layer business package (``src/pyapi/packages/*``) talks to the
middle layer through the same seven duck-typed methods.  Offline contract
tests need a fake that

1. records the *exact* payload a package produced (SKILL text, shell command,
   uploaded/downloaded paths) so the test can assert on it,
2. can be scripted to return canned results, raise transport errors, or serve
   file contents for ``download_file``, and
3. never opens a socket, so the tests stay deterministic and CI-safe.

It is intentionally *not* a mock of the module under test: packages receive it
through their constructor, exactly like the production ``Middle``.

Usage::

    from _fake_middle import FakeMiddle

    middle = FakeMiddle()
    middle.skill_result = middle.fail_skill("ERROR: bad cell")
    pkg = SomePackage(middle)
    result = pkg.run(...)
    assert middle.calls_of("execute_skill")[0].kwargs["token"] == "tok"
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pyapi.models import CommandResult, ExecutionStatus, QueryResult, RoleQuery, VirtuosoResult


@dataclass(frozen=True)
class Call:
    """One recorded middle call."""

    method: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any]

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"Call({self.method}, args={self.args!r}, kwargs={self.kwargs!r})"


def ok_skill(output: str = "t") -> VirtuosoResult:
    return VirtuosoResult(status=ExecutionStatus.SUCCESS, output=output)


def fail_skill(*errors: str, output: str = "") -> VirtuosoResult:
    return VirtuosoResult(
        status=ExecutionStatus.FAILURE, output=output, errors=list(errors) or ["failed"]
    )


def ok_command(stdout: str = "", returncode: int = 0) -> CommandResult:
    return CommandResult(returncode, stdout, "")


def fail_command(returncode: int = 1, stderr: str = "boom") -> CommandResult:
    return CommandResult(returncode, "", stderr)


class FakeMiddle:
    """Records every call; results are scriptable per method."""

    def __init__(self, *, skill_output: str = "t") -> None:
        self.calls: list[Call] = []
        #: method names that must raise ``RuntimeError`` (transport failure)
        self.raise_on: set[str] = set()
        self.skill_result: VirtuosoResult = ok_skill(skill_output)
        self.command_result: CommandResult = ok_command()
        self.upload_result: CommandResult = ok_command()
        self.download_result: CommandResult = ok_command()
        self.gui_result: CommandResult = ok_command()
        self.spectre_result: CommandResult = ok_command()
        self.query_result: QueryResult = QueryResult(
            status=ExecutionStatus.SUCCESS,
            roles={"daemon": RoleQuery(root="/home/u/.virtuoso-bridge/u")},
        )
        #: remote path -> text content served to ``download_file`` (exact match,
        #: then "remote path ends with key" fallback).  Values may be a callable
        #: ``(remote_path, local_path) -> None`` for full control.
        self.remote_files: dict[str, Any] = {}
        #: remote path -> bytes/text captured by ``upload_file``
        self.uploaded: dict[str, Any] = {}
        self._queues: dict[str, list[Any]] = {}
        #: optional callables for command-driven flows
        self.command_handler: Callable[[str], CommandResult] | None = None

    # ------------------------------------------------------------------ setup
    def queue(self, method: str, *results: Any) -> "FakeMiddle":
        """Queue results consumed in order by ``method`` before the default."""
        self._queues.setdefault(method, []).extend(results)
        return self

    def fail_with(
        self, method: str, *, returncode: int = 1, stderr: str = "boom",
        kind: str = "command",
    ) -> "FakeMiddle":
        """Set the canned failure result for a command-like method."""
        self.queue(method, CommandResult(returncode, "", stderr, kind))
        return self

    def reset(self) -> None:
        self.calls.clear()
        self.uploaded.clear()
        self._queues.clear()

    # -------------------------------------------------------------- recording
    def _record(self, method: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append(Call(method, args, dict(kwargs)))
        if method in self.raise_on:
            raise RuntimeError(f"{method} boom")

    def _take(self, method: str, default: Any) -> Any:
        queued = self._queues.get(method)
        if queued:
            return queued.pop(0)
        return default

    # --------------------------------------------------------------- protocol
    def execute_skill(
        self, skill_code: str, timeout: float | None = None, *, token: str,
        log_level: str | None = None, log_max_bytes: int | None = None,
    ) -> VirtuosoResult:
        self._record(
            "execute_skill", skill_code, timeout, token=token,
            log_level=log_level, log_max_bytes=log_max_bytes,
        )
        return self._take("execute_skill", self.skill_result)

    def run_command(
        self, cmd: str, timeout: int | None = None, *, token: str, parallel: bool = False
    ) -> CommandResult:
        self._record("run_command", cmd, timeout, token=token, parallel=parallel)
        if self.command_handler is not None:
            return self.command_handler(cmd)
        return self._take("run_command", self.command_result)

    def upload_file(
        self, local_path: Path, remote_path: str, timeout: int | None = None, *,
        token: str, recursive: bool = False,
    ) -> CommandResult:
        self._record(
            "upload_file", local_path, remote_path, timeout, token=token,
            recursive=recursive,
        )
        try:
            self.uploaded[remote_path] = Path(local_path).read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            self.uploaded[remote_path] = None
        return self._take("upload_file", self.upload_result)

    def download_file(
        self, remote_path: str, local_path: Path, timeout: int | None = None, *,
        token: str, recursive: bool = False,
    ) -> CommandResult:
        self._record(
            "download_file", remote_path, local_path, timeout, token=token,
            recursive=recursive,
        )
        result = self._take("download_file", self.download_result)
        if result.returncode == 0:
            self._serve(remote_path, Path(local_path))
        return result

    def run_gui_command(
        self, cmd: str, timeout: int | None = None, *, token: str
    ) -> CommandResult:
        self._record("run_gui_command", cmd, timeout, token=token)
        return self._take("run_gui_command", self.gui_result)

    def run_spectre_command(
        self, cmd: str, timeout: int | None = None, *, token: str
    ) -> CommandResult:
        self._record("run_spectre_command", cmd, timeout, token=token)
        return self._take("run_spectre_command", self.spectre_result)

    def query(
        self, *, token: str, role: str | None = None, name: str | None = None
    ) -> QueryResult:
        self._record("query", token=token, role=role, name=name)
        return self._take("query", self.query_result)

    # -------------------------------------------------------------- file serve
    def _serve(self, remote_path: str, local_path: Path) -> None:
        payload: Any = None
        if remote_path in self.remote_files:
            payload = self.remote_files[remote_path]
        else:
            for key, value in self.remote_files.items():
                if remote_path.endswith(key):
                    payload = value
                    break
        if payload is None:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_text("", encoding="utf-8")
            return
        if callable(payload):
            payload(remote_path, local_path)
            return
        local_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, bytes):
            local_path.write_bytes(payload)
        else:
            local_path.write_text(str(payload), encoding="utf-8")

    # ------------------------------------------------------------- inspection
    @property
    def skill_codes(self) -> list[str]:
        return [c.args[0] for c in self.calls_of("execute_skill")]

    @property
    def commands(self) -> list[str]:
        return [c.args[0] for c in self.calls_of("run_command")]

    @property
    def skill_text(self) -> str:
        """All SKILL text concatenated - handy for "did we emit X" checks."""
        return "\n".join(self.skill_codes)

    def calls_of(self, method: str) -> list[Call]:
        return [c for c in self.calls if c.method == method]

    def last(self, method: str | None = None) -> Call:
        pool = self.calls if method is None else self.calls_of(method)
        assert pool, f"no call recorded for {method!r}"
        return pool[-1]

    def called(self, method: str) -> bool:
        return any(c.method == method for c in self.calls)


__all__ = [
    "Call",
    "FakeMiddle",
    "fail_command",
    "fail_skill",
    "ok_command",
    "ok_skill",
]
