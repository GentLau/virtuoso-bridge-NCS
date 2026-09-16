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


__all__ = ["ParallelProbePackage", "ParallelProbeResult"]
