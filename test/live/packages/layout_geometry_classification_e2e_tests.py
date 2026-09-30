# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-29 20:46
# 依赖: 真机 vblog token；schemtest 库（layout 套件同款）；独立 cell 避免互相干扰
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
# ① 环境检查：业务面可达 + vblog token 能建 view；②③ 造独立 cell/视图并校验基线；
# ④ 只做被测动作（三类 rect 写入）；⑤ 读回比对：失败必须**可归因**、成功必须落盘；
# ⑥ 不清理现场（保留 cell 与证据）。
"""layout#179（第八轮缺口动作）：`dbCreateXxx` 失败的分类断言。

spec `上层/4-layout.md`：非法 LPP → SKILL 硬错误；几何非法 → nil+WARNING。
实测（2026-09-28，`test/artifacts/tmp/probe_layout_geom_class.py`）：

* **非法 LPP**：`dbCreateRect: Invalid layer/purpose` 硬错误浮出（并带
  `layout.write is not transactional` 提示）——与 spec 一致；
* **几何非法（零面积）**：被包层**预校验**拦截，错误为
  `bbox requires pos0 < pos1（对角两点，先小后大）`——比 spec 描述的
  “nil+WARNING” 更早、更可归因（记为口径差异，非缺陷；见 P-082/P-085 之后的 region 口径统一）。

判据：非法输入必须 `ok=false` 且错误文本点明原因；正常输入必须 ok 且读回可见。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"
LIB = "schemtest"
VIEW = "layout"
#: 证据目录不再挂在 round8（round9 接线时改到中性目录，避免产物跨轮串档）
OUT = ROOT / "test" / "artifacts" / "evidence" / "layout-geometry-classification"


class HttpTransport:
    def __init__(self, base: str, token: str) -> None:
        self.base, self.token = base, token

    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps({**payload, "token": self.token}, ensure_ascii=False).encode()
        request = urllib.request.Request(
            self.base, data=body, headers={"Content-Type": "application/json"},
            method="POST")
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return json.loads(error.read().decode("utf-8"))


def _value(transport, operation: str, **fields: Any) -> dict[str, Any]:
    body = transport.call({"operation": operation, **fields})
    data = body
    if body.get("ok") is False or data.get("ok") is False:
        raise AssertionError(f"{operation} failed: {body.get('error') or data.get('error')}")
    return data.get("value") or data


def _expect_fail(transport, operation: str, **fields: Any) -> str:
    body = transport.call({"operation": operation, **fields})
    data = body
    if body.get("ok") is not False and data.get("ok") is not False:
        raise AssertionError(f"{operation} expected failure, got ok")
    return str(body.get("error") or data.get("error") or "")


def main() -> int:
    parser = argparse.ArgumentParser()
    #: 本 TB 只走 8127 业务面（自己的 HttpTransport），故传输形态固定 http；
    #: 参数只为兼容 `run_all_http.py` 统一追加的 `--transport http`（round9 接线）。
    parser.add_argument("--transport", choices=("http",), default="http")
    parser.add_argument("--base", default=API)
    parser.add_argument("--token", default=TOKEN)
    args = parser.parse_args()
    transport = HttpTransport(args.base, args.token)
    OUT.mkdir(parents=True, exist_ok=True)
    cell = f"geom_cls_{time.strftime('%H%M%S')}"
    results: list[dict] = []

    def run(name: str, check: Callable[[], Any]) -> None:
        try:
            detail = check()
            results.append({"case": name, "ok": True, "detail": detail})
            print(f"[PASS] {name}")
        except Exception as exc:  # noqa: BLE001
            results.append({"case": name, "ok": False,
                            "detail": f"{type(exc).__name__}: {exc}"})
            print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")

    def case_env() -> dict:
        created = _value(transport, "virtuoso.cellview.view.create",
                         library=LIB, cell=cell, view=VIEW, view_type="maskLayout")
        return {"cell": cell, "created": bool(created)}

    def case_normal() -> dict:
        _value(transport, "virtuoso.layout.write", library=LIB, cell=cell, view=VIEW,
               commands=[{"op": "place_rect", "layer": "y0", "purpose": "drawing",
                          "bbox": [[0, 0], [2, 1]]}])
        read = _value(transport, "virtuoso.layout.read", library=LIB, cell=cell, view=VIEW)
        assert read.get("shape_count", 0) >= 1, f"读回无形状: {read.get('shape_count')}"
        return {"shape_count": read.get("shape_count")}

    def case_zero_area() -> dict:
        error = _expect_fail(transport, "virtuoso.layout.write",
                             library=LIB, cell=cell, view=VIEW,
                             commands=[{"op": "place_rect", "layer": "y0",
                                        "purpose": "drawing",
                                        "bbox": [[0, 0], [0, 0]]}])
        assert "bbox" in error and "pos0" in error, f"零面积未点名 bbox: {error[:160]}"
        return {"error": error[:160]}

    def case_illegal_lpp() -> dict:
        error = _expect_fail(transport, "virtuoso.layout.write",
                             library=LIB, cell=cell, view=VIEW,
                             commands=[{"op": "place_rect",
                                        "layer": "NO_SUCH_LAYER_XYZ",
                                        "purpose": "drawing",
                                        "bbox": [[0, 0], [1, 1]]}])
        assert "Invalid layer/purpose" in error or "dbCreateRect" in error, \
            f"非法 LPP 未给 SKILL 硬错误: {error[:160]}"
        assert "not transactional" in error or "applied" in error, \
            f"缺少非事务性提示: {error[:160]}"
        return {"error": error[:200]}

    run("ENV-01 独立 cell + layout 视图", case_env)
    run("CLS-01 正常 rect 成功且读回", case_normal)
    run("CLS-02 几何非法（零面积）可归因失败", case_zero_area)
    run("CLS-03 非法 LPP → SKILL 硬错误", case_illegal_lpp)

    evidence = {"tb": "layout_geometry_classification_e2e_tests", "library": LIB,
                "cell": cell, "token": args.token, "cases": results,
                "ok": all(r["ok"] for r in results)}
    out = OUT / "layout-geometry-classification.json"
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    print(f"\n{sum(1 for r in results if r['ok'])}/{len(results)} 通过；证据：{out}")
    return 0 if evidence["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
