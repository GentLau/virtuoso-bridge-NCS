# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-28 20:45
# 依赖: 无
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
#   ① 环境/前置：见正文的 require_environment 或首段只读探测（本节不适用时正文写明）；
#   ②③ 构建/校验被改对象：由用例内建前置保证；④ 只做被测动作；
#   ⑤ 打印期望 vs 实测（判据见正文）；⑥ 半真机不清理现场，留下状态便于复核。
"""symbol.generate 句柄/幂等探针（第五轮新增，真机）。

现象：同一 CIW 会话里对同一个 cell 第二次 ``virtuoso.symbol.generate`` 会直接报
``*Error* target symbol is open``（``src/pyapi/packages/_symbol_generate.py:143-144``
的守卫），而第一次生成**成功后并没有把目标 symbol view 关掉**。

真实设计迭代（改原理图 → 重新生成 symbol）在第二次就断，属于幂等性/句柄泄漏问题。
探针把三步都测出来：

1. 首次 generate → 看 ``dbFindOpenCellViewByName(<lib> <cell> symbol)`` 是否非空；
2. 再次 generate（overwrite=True）→ 期望成功，实测是否报 "target symbol is open"；
3. 手工 ``dbClose`` 后再 generate → 确认"关掉就能过"，从而把根因钉在"没关"。

verdict ∈ {clean, leaks-open-view, other}
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
DEFAULT_TOKEN = "d6af595b342647b58ec63ca6"
LIB, CELL = "SRX65", "sym_probe"


def call(token: str, operation: str, **fields: Any) -> dict:
    body = json.dumps({"operation": operation, "token": token, **fields},
                      ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        API, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return json.loads(error.read().decode("utf-8"))


def skill(token: str, code: str) -> str:
    response = call(token, "basic.skill.execute", skill_code=code, timeout=300)
    result = ((response.get("data") or {}).get("result") or {})
    if result.get("status") != "success":
        raise AssertionError(json.dumps(result, ensure_ascii=False)[:300])
    return str(result.get("output") or "").strip()


def is_open(token: str) -> str:
    raw = skill(
        token,
        f'if(dbFindOpenCellViewByName("{LIB}" "{CELL}" "symbol") "OPEN" "CLOSED")')
    return raw.strip().strip('"')


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--token", default=DEFAULT_TOKEN)
    ap.add_argument("--out", type=Path,
                    default=ROOT / "test" / "artifacts" / "evidence" / "round4-probes")
    args = ap.parse_args(argv)
    token = args.token
    report: dict[str, Any] = {"token": token}

    try:
        # 干净的探针 cell（先建视图，schematic.write 是 append 语义）
        call(token, "virtuoso.cellview.view.create", library=LIB, cell=CELL,
             view="schematic", view_type="schematic", timeout=120)
        call(token, "virtuoso.schematic.write", library=LIB, cell=CELL, view="schematic",
             timeout=300, commands=[
                 {"op": "place_pin", "name": "vin", "direction": "input",
                  "pos": [-2.0, 0.0]},
                 {"op": "place_pin", "name": "vout", "direction": "output",
                  "pos": [2.0, 0.0]},
             ])
        call(token, "virtuoso.schematic.check_and_save", library=LIB, cell=CELL,
             view="schematic", timeout=180)

        first = call(token, "virtuoso.symbol.generate", library=LIB, cell=CELL,
                     schematic_view="schematic", symbol_view="symbol",
                     overwrite=True, timeout=600)
        report["first_generate_ok"] = bool(first.get("ok"))
        report["first_generate_error"] = first.get("error")
        report["open_after_first"] = is_open(token)

        second = call(token, "virtuoso.symbol.generate", library=LIB, cell=CELL,
                      schematic_view="schematic", symbol_view="symbol",
                      overwrite=True, timeout=600)
        report["second_generate_ok"] = bool(second.get("ok"))
        report["second_generate_error"] = second.get("error")

        # 手工关掉遗留 view 后再试
        skill(token, f'let((cv) cv = dbFindOpenCellViewByName("{LIB}" "{CELL}" "symbol") '
                     f'if(cv progn(dbClose(cv) "closed") "none"))')
        report["open_after_manual_close"] = is_open(token)
        third = call(token, "virtuoso.symbol.generate", library=LIB, cell=CELL,
                     schematic_view="schematic", symbol_view="symbol",
                     overwrite=True, timeout=600)
        report["third_generate_ok"] = bool(third.get("ok"))
        report["third_generate_error"] = third.get("error")
    except Exception as exc:  # noqa: BLE001
        report["error"] = f"{type(exc).__name__}: {exc}"

    leaks = (report.get("open_after_first") == "OPEN"
             and report.get("second_generate_ok") is False)
    report["verdict"] = ("clean" if not leaks else "leaks-open-view")
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "round4-symbol-regen-handle.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    print(f"verdict: {report['verdict']}")
    print(f"evidence: {path}")
    return 0 if report["verdict"] == "clean" else 1


if __name__ == "__main__":
    raise SystemExit(main())
