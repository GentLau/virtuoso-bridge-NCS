"""Run offline core TBs with one process per work-root-owning case."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT = (
    "test/offline/core/semantics_tb.py",
    "test/offline/core/fault_injection_tb.py",
    "test/offline/core/api_server_tb.py",
    "test/offline/core/daemon_log_protocol_tb.py",
    "test/offline/core/p076_tar_completion_tb.py",
    "test/offline/core/thread_lifecycle_tb.py",
)


def _load_cases(script: Path) -> list[str]:
    spec = importlib.util.spec_from_file_location(
        f"_vb_core_{script.stem}", script
    )
    if spec is None or spec.loader is None:
        return []
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cases = getattr(module, "CASES", None)
    return sorted(cases) if isinstance(cases, dict) else []


def _env() -> dict[str, str]:
    env = dict(os.environ)
    src = str(ROOT / "src")
    old = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src + (os.pathsep + old if old else "")
    return env


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scripts", nargs="*", default=list(DEFAULT))
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    merged: dict[str, object] = {}
    failed = 0
    with tempfile.TemporaryDirectory(prefix="vb-core-multi-") as tmp:
        tmpdir = Path(tmp)
        for raw in args.scripts:
            script = (ROOT / raw).resolve()
            cases = _load_cases(script)
            jobs = cases or [""]
            for case in jobs:
                out = tmpdir / f"{script.stem}-{case or 'all'}.json"
                cmd = [sys.executable, str(script)]
                if case:
                    cmd += ["--case", case]
                cmd += ["--out", str(out)]
                result = subprocess.run(
                    cmd, cwd=ROOT, env=_env(), text=True, capture_output=True
                )
                key = f"{script.name}:{case or 'all'}"
                if result.returncode:
                    failed += 1
                    merged[key] = {
                        "status": "fail",
                        "stderr": result.stderr[-2000:],
                        "stdout": result.stdout[-2000:],
                    }
                    print(f"[FAIL] {key}", flush=True)
                else:
                    payload = json.loads(out.read_text(encoding="utf-8"))
                    merged[key] = {"status": "pass", "detail": payload}
                    print(f"[PASS] {key}", flush=True)

    text = json.dumps(
        {"ok": failed == 0, "failed": failed, "results": merged},
        ensure_ascii=False,
        indent=2,
    )
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
