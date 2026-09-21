"""Real-Virtuoso matrix for legal SKILL text through the public Skill API.

The bridge must be transparent to the caller: if the caller supplies legal
SKILL, the single-line vs multi-line packaging choice must not change the
result.  This TB deliberately keeps the cases small so failures point at the
daemon wrapping path, not at business logic.

Run with::

    PYTHONPATH=src python test/tb/skill_syntax_matrix_tb.py
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


CASES = [
    ("single_expression", "1+2", "3"),
    ("single_line_sequence", "a = 1 b = 2 a+b", "3"),
    ("single_line_trailing_comment", "a = 1 ; comment", "1"),
    ("single_line_progn", "progn(1 2 3)", "3"),
    ("single_line_let", "let((a b) a=1 b=2 a+b)", "3"),
    ("single_line_errset_progn", "errset(progn(1 2 3))", "(3)"),
    ("single_line_string_comment_char", 'strcat("a;b")', '"a;b"'),
    ("multi_line_sequence", "a = 1\nb = 2\na+b", "3"),
    ("multi_line_comment", "a = 1\n; comment\nb = 2\na+b", "3"),
    ("multi_line_errset_progn", "a = errset(progn(1\n2\n3))\ncar(a)", "3"),
]


def _call(base: str, token: str, skill: str, timeout: float) -> dict:
    body = json.dumps({
        "operation": "basic.skill.execute",
        "token": token,
        "timeout": timeout,
        "skill_code": skill,
    }).encode("utf-8")
    request = urllib.request.Request(
        base.rstrip("/") + "/api/operation",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout + 10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "error": f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')}",
        }


def _result(envelope: dict) -> dict:
    return ((envelope.get("data") or {}).get("result") or {})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8127")
    parser.add_argument("--token", default="vb-vblog")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--out",
        default=str(ROOT / "test" / "tb" / "artifacts" / "skill-syntax-matrix.json"),
    )
    args = parser.parse_args(argv)

    records = []
    failed = 0
    for name, skill, expected in CASES:
        envelope = _call(args.base, args.token, skill, args.timeout)
        result = _result(envelope)
        actual = result.get("output")
        passed = (
            bool(envelope.get("ok"))
            and result.get("status") == "success"
            and actual == expected
        )
        if not passed:
            failed += 1
        records.append({
            "name": name,
            "passed": passed,
            "skill": skill,
            "expected": expected,
            "actual": actual,
            "status": result.get("status"),
            "errors": result.get("errors") or [],
            "error": envelope.get("error"),
        })
        print(
            f"[{'PASS' if passed else 'FAIL'}] {name}: "
            f"expected={expected!r} actual={actual!r} "
            f"errors={result.get('errors') or []}",
            flush=True,
        )

    payload = {
        "base": args.base,
        "token": args.token,
        "passed": len(records) - failed,
        "failed": failed,
        "total": len(records),
        "records": records,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "passed": payload["passed"],
        "failed": payload["failed"],
        "total": payload["total"],
        "out": str(out),
    }, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
