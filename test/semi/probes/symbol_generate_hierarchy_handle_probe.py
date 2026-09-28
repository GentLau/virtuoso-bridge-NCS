# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-28 20:45
# 依赖: 无
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
#   ① 环境/前置：见正文的 require_environment 或首段只读探测（本节不适用时正文写明）；
#   ②③ 构建/校验被改对象：由用例内建前置保证；④ 只做被测动作；
#   ⑤ 打印期望 vs 实测（判据见正文）；⑥ 半真机不清理现场，留下状态便于复核。
"""层次化 symbol.generate 的句柄残留探针（第五轮新增，真机）。

现场（SerDes RX 场景连跑两次）：

* 第 1 次全绿（probe/lib/buf/ctle/term/top/layout/gds/sim），跑完 CIW 里
  ``ctle_core / rx_term / inv_buf`` 三个**子单元 symbol view 仍处于打开状态**；
* 第 2 次同一条流程立刻失败在 ``buf`` 阶段：
  ``symbol.generate: target symbol is open``（守卫位于
  ``src/pyapi/packages/_symbol_generate.py:143-144``）。

本探针用最小层次化结构复现：叶子 ``hdl_leaf`` + 顶层 ``hdl_top``：

1. 生成叶子 symbol → 记录打开状态（预期关闭）；
2. 生成**顶层** symbol（顶层实例化了叶子）→ 再记录**叶子** symbol 打开状态；
3. 再次生成叶子 symbol → 预期成功；若报 "target symbol is open" 即坐实残留。

verdict ∈ {clean, child-symbol-left-open}
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
LIB = "SRX65"
LEAF, TOP = "hdl_leaf", "hdl_top"


def call(token: str, operation: str, **fields: Any) -> dict:
    body = json.dumps({"operation": operation, "token": token, **fields},
                      ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        API, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=900) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return json.loads(error.read().decode("utf-8"))


def skill(token: str, code: str) -> str:
    response = call(token, "basic.skill.execute", skill_code=code, timeout=300)
    result = ((response.get("data") or {}).get("result") or {})
    if result.get("status") != "success":
        raise AssertionError(json.dumps(result, ensure_ascii=False)[:300])
    return str(result.get("output") or "").strip()


def open_state(token: str, cell: str) -> str:
    raw = skill(token,
                f'if(dbFindOpenCellViewByName("{LIB}" "{cell}" "symbol") "OPEN" "CLOSED")')
    return raw.strip().strip('"')


def close_symbol(token: str, cell: str) -> None:
    skill(token,
          f'let((cv) cv = dbFindOpenCellViewByName("{LIB}" "{cell}" "symbol") '
          f'if(cv progn(dbClose(cv) "closed") "none"))')


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--token", default=DEFAULT_TOKEN)
    ap.add_argument("--out", type=Path,
                    default=ROOT / "test" / "artifacts" / "evidence" / "round4-probes")
    args = ap.parse_args(argv)
    token = args.token
    report: dict[str, Any] = {"token": token, "lib": LIB, "leaf": LEAF, "top": TOP}

    try:
        close_symbol(token, LEAF)
        call(token, "virtuoso.cellview.view.create", library=LIB, cell=LEAF,
             view="schematic", view_type="schematic", timeout=120)
        call(token, "virtuoso.schematic.write", library=LIB, cell=LEAF,
             view="schematic", timeout=300, commands=[
                 {"op": "place_pin", "name": "vin", "direction": "input",
                  "pos": [-2.0, 0.0]},
                 {"op": "place_pin", "name": "vout", "direction": "output",
                  "pos": [2.0, 0.0]},
             ])
        call(token, "virtuoso.schematic.check_and_save", library=LIB, cell=LEAF,
             view="schematic", timeout=180)

        leaf = call(token, "virtuoso.symbol.generate", library=LIB, cell=LEAF,
                    schematic_view="schematic", symbol_view="symbol",
                    overwrite=True, timeout=600)
        report["leaf_generate_ok"] = bool(leaf.get("ok"))
        report["leaf_open_after_generate"] = open_state(token, LEAF)

        call(token, "virtuoso.cellview.view.create", library=LIB, cell=TOP,
             view="schematic", view_type="schematic", timeout=120)
        call(token, "virtuoso.schematic.write", library=LIB, cell=TOP,
             view="schematic", timeout=300, commands=[
                 {"op": "place_instance", "master_lib": LIB, "master_cell": LEAF,
                  "master_view": "symbol", "name": "XLEAF", "pos": [0.0, 0.0]},
                 {"op": "set_term_nets", "name": "XLEAF",
                  "term_nets": {"vin": "vin", "vout": "vout"}},
                 {"op": "place_pin", "name": "vin", "direction": "input",
                  "pos": [-4.0, 0.0]},
                 {"op": "place_pin", "name": "vout", "direction": "output",
                  "pos": [4.0, 0.0]},
             ])
        call(token, "virtuoso.schematic.check_and_save", library=LIB, cell=TOP,
             view="schematic", timeout=180)

        top = call(token, "virtuoso.symbol.generate", library=LIB, cell=TOP,
                   schematic_view="schematic", symbol_view="symbol",
                   overwrite=True, timeout=600)
        report["top_generate_ok"] = bool(top.get("ok"))
        report["leaf_open_after_top_generate"] = open_state(token, LEAF)

        again = call(token, "virtuoso.symbol.generate", library=LIB, cell=LEAF,
                     schematic_view="schematic", symbol_view="symbol",
                     overwrite=True, timeout=600)
        report["leaf_regenerate_ok"] = bool(again.get("ok"))
        report["leaf_regenerate_error"] = again.get("error")
    except Exception as exc:  # noqa: BLE001
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            close_symbol(token, LEAF)
            close_symbol(token, TOP)
            report["cleanup_leaf_open"] = open_state(token, LEAF)
        except Exception as exc:  # noqa: BLE001
            report["cleanup_error"] = f"{type(exc).__name__}: {exc}"

    leaks = (report.get("leaf_open_after_top_generate") == "OPEN"
             and report.get("leaf_regenerate_ok") is False)
    report["verdict"] = "child-symbol-left-open" if leaks else "clean"
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "round4-symbol-hierarchy-handle.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    print(f"verdict: {report['verdict']}")
    print(f"evidence: {path}")
    return 0 if report["verdict"] == "clean" else 1


if __name__ == "__main__":
    raise SystemExit(main())
