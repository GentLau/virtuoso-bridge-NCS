# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-28 20:45
# 依赖: 无
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
#   ① 环境/前置：见正文的 require_environment 或首段只读探测（本节不适用时正文写明）；
#   ②③ 构建/校验被改对象：由用例内建前置保证；④ 只做被测动作；
#   ⑤ 打印期望 vs 实测（判据见正文）；⑥ 半真机不清理现场，留下状态便于复核。
"""Repro: capture the raw 8127 response for the symbol GEN same-view case.

The E2E suite's HttpTransport does not tolerate 4xx (urllib raises), so the
body of a 400 response never reaches the report.  This probe replays the
exact request the suite sends (symbol_e2e_tests.py, GEN-01/02/03, the
"same source/target view" assertion) and prints status + raw body.

Usage: python test/semi/probes/symbol_http_400_repro.py
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"


def call(payload: dict) -> tuple[int, str]:
    request = urllib.request.Request(
        API,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8")


def main() -> int:
    payload = {
        "operation": "virtuoso.symbol.generate",
        "token": TOKEN,
        "library": "schemtest",
        "cell": "gen_e2e",
        "schematic_view": "schematic",
        "symbol_view": "schematic",   # same as schematic_view -> suite expects ok=False
    }
    status, body = call(payload)
    print(f"request: {json.dumps(payload, ensure_ascii=False)}")
    print(f"status : {status}")
    print(f"body   : {body}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
