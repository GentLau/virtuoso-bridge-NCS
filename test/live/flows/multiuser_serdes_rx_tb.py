# === TB 注释头（规范见 test/docs/写TB规范.md §0）=====================
# 作者: 测试/root
# 最后改动: 2026-09-28 16:15
# 依赖: 无
# =====================================================================
"""SERDES RX 多用户协同共建 TB（真机级 · S13）。

场景（两个**真实 OS 用户**，共享一个库，走 8127 业务面）：

  1. A（vbuser3）在 `/project/libs/serdes_rx` 建库（挂 tsmcN65 工艺）；
  2. A 建三个 schematic：`rx_fe`（4 个 PDK 器件 + 6 引脚）、`clk_buf`（反相器 + 4 引脚）、`rx_top`（实例化 rx_fe + 引脚）；
  3. A 给出 `rx_fe` / `clk_buf` 的 symbol；
  4. **B（vbuser4）读 A 的库**（跨用户可见性）→ 在 `rx_top` 里补一个 `clk_buf` 实例并保存（**跨用户改单**）；
  5. A **回读** `rx_top`，断言能看到 B 加上去的实例（双向可见）；
  6. B 跑 `check_and_save`；A 再读 `rx_fe` 设备数做终检。

为什么这样测：这是"多用户协同做真实项目"的最小可信闭环 —— 不同 OS 账号 / 不同 CIW /
不同 daemon，共享文件系统 + 共享库，且**每次写入都要被另一个用户读到**。

用法::

    PYTHONPATH=src python test/live/flows/multiuser_serdes_rx_tb.py \
        --work-dir test/artifacts/env/log-vblog \
        --token-a vb-vbuser3 --token-b vb-vbuser4 \
        --base http://127.0.0.1:8127/api/operation \
        --out test/artifacts/evidence/round5-serdes-rx.json
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
_RUNNERS = Path(__file__).resolve().parents[3] / "test" / "shared" / "runners"
if str(_RUNNERS) not in sys.path:
    sys.path.insert(0, str(_RUNNERS))
from env_check import require_environment  # noqa: E402


def call(base: str, operation: str, token: str, **fields) -> dict:
    payload = {"operation": operation, "token": token, **fields}
    request = urllib.request.Request(
        base, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return json.loads(error.read().decode("utf-8"))


def value_of(response: dict) -> dict:
    return ((response).get("value")) or {}


def instances_of(response: dict) -> list:
    return value_of(response).get("instances") or []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8127/api/operation")
    parser.add_argument("--work-dir", default="test/artifacts/env/log-vblog")
    parser.add_argument("--token-a", default="vb-vbuser3")
    parser.add_argument("--token-b", default="vb-vbuser4")
    parser.add_argument("--lib", default="serdes_rx")
    parser.add_argument("--lib-path", default="/project/libs/serdes_rx")
    parser.add_argument("--tech", default="tsmcN65")
    parser.add_argument("--tag", default="",
                        help="cell 名后缀（默认按时间生成，保证 TB 可重复运行）")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    require_environment(base=args.base, token=args.token_a, require_lib=[args.tech])

    token_a, token_b = args.token_a, args.token_b
    lib = args.lib
    import time as _time
    tag = args.tag or _time.strftime("%H%M%S")
    rx_fe, clk_buf, rx_top = f"rx_fe_{tag}", f"clk_buf_{tag}", f"rx_top_{tag}"
    report: dict = {"library": lib, "tag": tag,
                    "cells": {"rx_fe": rx_fe, "clk_buf": clk_buf, "rx_top": rx_top},
                    "steps": []}

    def record(name: str, ok: bool, detail) -> bool:
        report["steps"].append({"step": name, "ok": bool(ok), "detail": detail})
        return ok

    def skill(token: str, code: str) -> str:
        data = call(args.base, "basic.skill.execute", token, skill_code=code)
        result = data.get("result") or {}
        output = result.get("output")
        if output is None:
            steps = data.get("steps") or []
            output = ((steps[0].get("detail") or {}).get("output") if steps else "") or ""
        return str(output)

    def create_view(token: str, cell: str, view: str = "schematic") -> str:
        return str(skill(
            token,
            f'let((cv) cv = dbOpenCellViewByType("{lib}" "{cell}" "{view}" '
            f'"{"schematic" if view == "schematic" else "maskLayout"}" "w") '
            f'unless(cv error("create failed")) dbSave(cv) dbClose(cv) "created")',
        )).strip().strip('"')

    # ---- 0) 前置：两个会话都必须已经"看见"这个共享库 -------------------------
    #      （真实流程：库路径写进 /project/cds.lib.shared，各自的 cds.lib INCLUDE 它，重启会话生效）
    for label, token in (("A", token_a), ("B", token_b)):
        seen = str(skill(token,
                          f'let((x) x = ddGetObj("{lib}") '
                          f'if(x x sprintf(nil "MISSING")))')).strip().strip('"')
        record(f"{label}-sees-library:{lib}", seen.startswith("dd:"),
               {"seen": seen,
                "hint": f"共享库需 DEFINE 在 /project/cds.lib.shared 且该会话已重启"})
    if not all(step["ok"] for step in report["steps"]):
        created = call(args.base, "virtuoso.cellview.lib.create", token_a,
                       library=lib, path=args.lib_path, technology_library=args.tech)
        record("A-lib-create(fallback)", bool(created.get("ok")), created.get("error"))

    # ---- 1) A 建三个视图 -----------------------------------------------------
    for cell in (rx_fe, clk_buf, rx_top):
        state = create_view(token_a, cell)
        record(f"A-create-view:{cell}", state == "created", state)

    # ---- 2) A 画 rx_fe（4 器件 + 6 引脚）------------------------------------
    fe_cmds = [
        {"op": "place_instance", "master_lib": args.tech, "master_cell": "nch_25",
         "name": "MN1", "pos": [1.0, 1.0]},
        {"op": "place_instance", "master_lib": args.tech, "master_cell": "nch_25",
         "name": "MN2", "pos": [3.0, 1.0]},
        {"op": "place_instance", "master_lib": args.tech, "master_cell": "pch_25",
         "name": "MP1", "pos": [1.0, 3.0]},
        {"op": "place_instance", "master_lib": args.tech, "master_cell": "pch_25",
         "name": "MP2", "pos": [3.0, 3.0]},
        {"op": "place_pin", "name": "INP", "direction": "input", "pos": [-2.0, 2.0]},
        {"op": "place_pin", "name": "INN", "direction": "input", "pos": [-2.0, 0.0]},
        {"op": "place_pin", "name": "CLK", "direction": "input", "pos": [-2.0, 4.0]},
        {"op": "place_pin", "name": "OUT", "direction": "output", "pos": [6.0, 2.0]},
        {"op": "place_pin", "name": "VDD", "direction": "inputOutput", "pos": [2.0, 5.0]},
        {"op": "place_pin", "name": "VSS", "direction": "inputOutput", "pos": [2.0, -1.0]},
    ]
    fe = call(args.base, "virtuoso.schematic.write", token_a,
              library=lib, cell=rx_fe, commands=fe_cmds)
    record("A-write:rx_fe", bool(fe.get("ok")), fe.get("error"))

    # ---- 3) A 画 clk_buf（反相器）--------------------------------------------
    buf_cmds = [
        {"op": "place_instance", "master_lib": args.tech, "master_cell": "nch_25",
         "name": "MN", "pos": [1.0, 1.0]},
        {"op": "place_instance", "master_lib": args.tech, "master_cell": "pch_25",
         "name": "MP", "pos": [1.0, 3.0]},
        {"op": "place_pin", "name": "IN", "direction": "input", "pos": [-2.0, 2.0]},
        {"op": "place_pin", "name": "OUT", "direction": "output", "pos": [4.0, 2.0]},
        {"op": "place_pin", "name": "VDD", "direction": "inputOutput", "pos": [1.0, 5.0]},
        {"op": "place_pin", "name": "VSS", "direction": "inputOutput", "pos": [1.0, -1.0]},
    ]
    buf = call(args.base, "virtuoso.schematic.write", token_a,
               library=lib, cell=clk_buf, commands=buf_cmds)
    record("A-write:clk_buf", bool(buf.get("ok")), buf.get("error"))

    # ---- 4) A 生成 symbol ----------------------------------------------------
    for cell, cmds in ((rx_fe, fe_cmds), (clk_buf, buf_cmds)):
        gen = call(args.base, "virtuoso.symbol.generate", token_a,
                   library=lib, cell=cell, overwrite=True)
        record(f"A-symbol:{cell}", bool(gen.get("ok")), gen.get("error"))
        # B3（C0）：symbol 端口与原理图引脚**直接比对**（跨用户读回前先确认本体正确）。
        expected = sorted(c["name"] for c in cmds if c.get("op") == "place_pin")
        read = call(args.base, "virtuoso.symbol.read", token_a,
                    library=lib, cell=cell, view="symbol")
        value = (read).get("value") or {}
        terms = sorted(t.get("name") for t in (value.get("terms") or []) if t.get("name"))
        record(f"A-symbol-terms:{cell}", terms == expected,
               {"expected": expected, "terms": terms})

    # ---- 5) A 画 rx_top（实例化 rx_fe + 引脚）--------------------------------
    top_cmds = [
        {"op": "place_instance", "master_lib": lib, "master_cell": rx_fe,
         "name": "XI_FE", "pos": [0.0, 0.0]},
        {"op": "place_pin", "name": "INP", "direction": "input", "pos": [-4.0, 1.0]},
        {"op": "place_pin", "name": "INN", "direction": "input", "pos": [-4.0, -1.0]},
        {"op": "place_pin", "name": "CLK", "direction": "input", "pos": [-4.0, 3.0]},
        {"op": "place_pin", "name": "OUT", "direction": "output", "pos": [6.0, 0.0]},
        {"op": "place_pin", "name": "VDD", "direction": "inputOutput", "pos": [0.0, 5.0]},
        {"op": "place_pin", "name": "VSS", "direction": "inputOutput", "pos": [0.0, -5.0]},
    ]
    top = call(args.base, "virtuoso.schematic.write", token_a,
               library=lib, cell=rx_top, commands=top_cmds)
    record("A-write:rx_top", bool(top.get("ok")), top.get("error"))

    # ---- 6) B 读 A 的库（跨用户可见性）--------------------------------------
    b_read = call(args.base, "virtuoso.schematic.read", token_b,
                  library=lib, cell=rx_top)
    b_instances = instances_of(b_read)
    record("B-read:A's rx_top", bool(b_read.get("ok")) and len(b_instances) >= 1,
           {"ok": b_read.get("ok"), "error": b_read.get("error"),
            "instances": [item.get("name") for item in b_instances]})

    # ---- 7) B 在 rx_top 里补一个 clk_buf 实例（跨用户改单）-------------------
    b_write = call(args.base, "virtuoso.schematic.write", token_b,
                   library=lib, cell=rx_top,
                   commands=[{"op": "place_instance", "master_lib": lib,
                              "master_cell": clk_buf, "name": "XI_CLKBUF",
                              "pos": [0.0, -8.0]}])
    record("B-modify:A's rx_top", bool(b_write.get("ok")), b_write.get("error"))

    # ---- 8) A 回读，必须看到 B 加的实例（双向可见）---------------------------
    a_read = call(args.base, "virtuoso.schematic.read", token_a,
                  library=lib, cell=rx_top)
    names = [item.get("name") for item in instances_of(a_read)]
    record("A-see:B's instance", "XI_CLKBUF" in names,
           {"ok": a_read.get("ok"), "instances": names})

    # ---- 9) B check_and_save；A 终检 rx_fe 设备数 ----------------------------
    saved = call(args.base, "virtuoso.schematic.check_and_save", token_b,
                 library=lib, cell=rx_top)
    record("B-check_and_save:rx_top", bool(saved.get("ok")), saved.get("error"))
    fe_read = call(args.base, "virtuoso.schematic.read", token_a,
                   library=lib, cell=rx_fe)
    fe_instances = instances_of(fe_read)
    record("A-final:rx_fe has 4 devices", len(fe_instances) >= 4,
           [item.get("name") for item in fe_instances])

    report["passed"] = sum(1 for step in report["steps"] if step["ok"])
    report["total"] = len(report["steps"])
    report["ok"] = all(step["ok"] for step in report["steps"])
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
