"""Parallel command/file probe package, used by stress and integration TBs."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from pyapi.models import Middle


@dataclass
class ParallelProbeResult:
    ok: bool
    results: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    steps: list[dict] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class Request:
    """Structural request model for ``demo.parallel.probe``."""

    token: str
    commands: list[str]
    uploads: list[tuple[str, str]] | None = None
    timeout: float | None = None
    parallel: bool = True
    max_workers: int | None = None


OPERATION_NAME = "demo.parallel.probe"


def _validate(request: Request) -> None:
    if not isinstance(request.token, str) or not request.token:
        raise ValueError("token must be a non-empty string")
    if not isinstance(request.commands, list) or not all(
        isinstance(item, str) for item in request.commands
    ):
        raise TypeError("commands must be a list of strings")
    if request.max_workers is not None and request.max_workers < 1:
        raise ValueError("max_workers must be >= 1")


class ParallelProbePackage:
    def __init__(self, middle: Middle) -> None:
        self.middle = middle

    def run(
        self,
        *,
        token: str,
        commands: list[str],
        uploads: list[tuple[str | Path, str]] | None = None,
        timeout: float | None = None,
        parallel: bool = True,
        max_workers: int | None = None,
    ) -> ParallelProbeResult:
        work: list[Callable[[], dict]] = []
        for command in commands:
            work.append(lambda c=command: {
                "kind": "command",
                "result": self.middle.run_command(
                    c, timeout=timeout, token=token, parallel=parallel
                ),
            })
        for local_path, remote_path in uploads or []:
            work.append(lambda lp=local_path, rp=remote_path: {
                "kind": "upload",
                "result": self.middle.upload_file(
                    Path(lp), rp, timeout=timeout, token=token
                ),
            })
        results: list[dict] = []
        errors: list[str] = []
        with ThreadPoolExecutor(max_workers=max_workers or max(1, len(work))) as pool:
            futures = [pool.submit(item) for item in work]
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as exc:  # noqa: BLE001 - report as package failure
                    errors.append(str(exc))
        success = not errors and all(
            getattr(item["result"], "returncode", 0) == 0 for item in results
        )
        return ParallelProbeResult(success, results, errors)


    def run_request(self, request: Request) -> ParallelProbeResult:
        """Spec-shaped entry point: ``method(request) -> Result`` (上层 §2.2)."""
        _validate(request)
        result = self.run(
            token=request.token,
            commands=request.commands,
            uploads=[(a, b) for a, b in (request.uploads or [])],
            timeout=request.timeout,
            parallel=request.parallel,
            max_workers=request.max_workers,
        )
        result.steps = list(result.results)
        result.error = "; ".join(result.errors) or None
        return result


#: spec 上层 §4.2: every package exports ``Package`` + its operation metadata
Package = ParallelProbePackage
OPERATIONS = ((OPERATION_NAME, "run_request", Request, ParallelProbeResult),)

__all__ = [
    "OPERATIONS",
    "OPERATION_NAME",
    "Package",
    "ParallelProbePackage",
    "ParallelProbeResult",
    "Request",
]
