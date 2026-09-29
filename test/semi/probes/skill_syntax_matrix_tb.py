# === TB 注释头（规范见 test/docs/写TB规范.md §0）=====================
# 作者: 设计/Codex
# 最后改动: 2026-09-28 12:04
# 依赖: 无
# =====================================================================
# 六步流程（按 test/docs/写TB规范.md §1–§6）：
# §1 环境检查：已调用 require_environment(base, token)。
# §2 构建：确定 HTTP /api/operation 入口和合法 SKILL case 列表。
# §3 最终检查：环境检查通过后逐 case 构造请求，无额外持久对象。
# §4 执行：单行/多行/注释/progn/let 等合法 SKILL。
# §5 比对：expected / actual / status 逐项比对并写入 JSON。
# §6 重复/收尾：10 个 case 全量重复；证据写 --out，不改远端现场。
"""Real-Virtuoso matrix for legal SKILL text through the public Skill API.

The bridge must be transparent to the caller: if the caller supplies legal
SKILL, the single-line vs multi-line packaging choice must not change the
result.  This TB deliberately keeps the cases small so failures point at the
daemon wrapping path, not at business logic.

Run with::

    PYTHONPATH=src python test/semi/probes/skill_syntax_matrix_tb.py
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_RUNNERS = ROOT / "test" / "shared" / "runners"
if str(_RUNNERS) not in sys.path:
    sys.path.insert(0, str(_RUNNERS))
from env_check import require_environment  # noqa: E402


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
    return ((_c1_wrapper(envelope)).get("result") or {})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8127")
    parser.add_argument("--token", default="vb-vblog")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--out",
        default=str(ROOT / "test" / "artifacts" / "evidence" / "skill-syntax-matrix.json"),
    )
    args = parser.parse_args(argv)

    # 六步 §1：确认 HTTP 业务面和 token 对应的环境可用。
    base = args.base.rstrip("/")
    if not base.endswith("/api/operation"):
        base += "/api/operation"
    environment = require_environment(base=base, token=args.token)
    # 六步 §2–§5：逐 case 执行合法 SKILL，并记录 expected / actual / 判定。
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
        "environment": environment,
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


# --- C1 兼容垫片（2026-09-29，C3）------------------------------------------------
# C1（2f88853）起：业务载荷直返顶层（值型 `value`、命令/skill 型 `result`）、
# 成功默认省略 `steps`、失败壳去掉 `data`。历史 TB 按 `response["data"]` 解析，
# 本垫片把新契约响应合成为旧 `data` 壳，让既有解析零改动继续工作。
def _c1_wrapper(body):
    if not isinstance(body, dict):
        return {}
    if isinstance(body.get("data"), dict):
        return body["data"]
    wrapped = {"ok": body.get("ok"), "error": body.get("error")}
    for key in ("value", "result", "steps"):
        if key in body:
            wrapped[key] = body[key]
    return wrapped
