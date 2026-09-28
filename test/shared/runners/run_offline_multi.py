"""Run offline pytest tests with a fresh process per work-root boundary.

The production contract is one work root per process.  Some legacy test files
contain several tests that each want their own root, so this runner first
tries a file as one process and, only if that fails, retries its collected
node ids one by one.  Each retry is a separate Python process and therefore a
fresh ``common.paths`` binding.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PATHS = (
    "test/offline/unit",
    "test/offline/integration",
    "test/offline/scenario",
)
_NODE_RE = re.compile(r"^(test/\S+::\S+)(?:\s|$)")


def _files(paths: list[str]) -> list[Path]:
    found: list[Path] = []
    for raw in paths:
        path = (ROOT / raw).resolve()
        if path.is_file():
            found.append(path)
        elif path.is_dir():
            found.extend(sorted(path.rglob("test_*.py")))
        else:
            raise FileNotFoundError(raw)
    return found


def _env() -> dict[str, str]:
    env = dict(os.environ)
    src = str(ROOT / "src")
    old = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src + (os.pathsep + old if old else "")
    env["VB_TEST_MULTIPROCESS"] = "1"
    return env


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *args],
        cwd=ROOT,
        env=_env(),
        text=True,
        capture_output=True,
    )


def _nodes(file: Path) -> list[str]:
    result = _run(["--collect-only", str(file.relative_to(ROOT))])
    if result.returncode != 0:
        return []
    return [
        match.group(1)
        for line in result.stdout.splitlines()
        if (match := _NODE_RE.match(line.strip()))
    ]


def _show(label: str, result: subprocess.CompletedProcess[str]) -> None:
    print(label, flush=True)
    if result.stdout.strip():
        print(result.stdout.rstrip(), flush=True)
    if result.stderr.strip():
        print(result.stderr.rstrip(), file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", default=list(DEFAULT_PATHS))
    parser.add_argument(
        "--node-isolation",
        choices=("auto", "always", "never"),
        default="auto",
        help="auto retries a failing file node-by-node in fresh processes",
    )
    parser.add_argument("--max-failures", type=int, default=0)
    args = parser.parse_args(argv)

    failures: list[str] = []
    total_files = 0
    for file in _files(args.paths):
        total_files += 1
        rel = str(file.relative_to(ROOT))
        first = _run(["-q", rel])
        if first.returncode == 0:
            print(f"[PASS] {rel}", flush=True)
            continue
        if args.node_isolation == "never":
            _show(f"[FAIL] {rel}", first)
            failures.append(rel)
            continue
        nodes = _nodes(file)
        if not nodes:
            _show(f"[FAIL] {rel} (collection failed)", first)
            failures.append(rel)
            continue
        print(
            f"[RETRY] {rel}: file-level run failed; isolating {len(nodes)} nodes",
            flush=True,
        )
        node_failures = []
        for node in nodes:
            result = _run(["-q", node])
            if result.returncode:
                node_failures.append(node)
                _show(f"[FAIL] {node}", result)
        if node_failures:
            failures.extend(node_failures)
            if args.max_failures and len(failures) >= args.max_failures:
                break
        else:
            print(f"[PASS-ISOLATED] {rel}", flush=True)

    print(f"\nfiles={total_files} failures={len(failures)}", flush=True)
    for failure in failures:
        print(f"FAILED {failure}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
