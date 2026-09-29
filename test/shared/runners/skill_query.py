"""Run one SKILL expression through the business HTTP face (read-only helper).

Usage:
    python test/shared/runners/skill_query.py --token vb-vblog "1+2"
    python test/shared/runners/skill_query.py --token <t> --file expr.il

Prints the raw `output` on success; on failure prints status + errors and exits 1.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

API = "http://127.0.0.1:8127/api/operation"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("expr", nargs="?", help="SKILL expression")
    ap.add_argument("--file", type=Path, help="read expression from a file")
    ap.add_argument("--token", required=True)
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--url", default=API)
    args = ap.parse_args(argv)

    code = args.file.read_text(encoding="utf-8") if args.file else args.expr
    if not code:
        ap.error("give an expression or --file")

    body = json.dumps(
        {"operation": "basic.skill.execute", "token": args.token,
         "skill_code": code, "timeout": args.timeout}
    ).encode("utf-8")
    request = urllib.request.Request(
        args.url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=args.timeout + 60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    result = ((_c1_wrapper(payload)).get("result") or {})
    status = result.get("status")
    if status == "success":
        print(result.get("output", ""))
        return 0
    print(json.dumps({"ok": payload.get("ok"), "error": payload.get("error"),
                      "status": status, "errors": result.get("errors")},
                     ensure_ascii=False))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


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
