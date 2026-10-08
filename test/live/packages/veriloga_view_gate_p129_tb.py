# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-10-08 15:06
# 依赖: 无
# =======================================================================
"""P-129 红钉（真机）：veriloga 对不存在 view 的 `set_source` 必须给存在性门。

verilog 包的前置门原文（`verilog.py:386-394`）：
  `view {lib}/{cell}/{view} not found; call ensure_view first (set create_if_missing=true)`
veriloga 包没有该门（`veriloga.py::write` 直接落到 `_set_source`）：

  * 期望（修复后）：ok=false 且错误里点名 `ensure_view`（与 verilog 同门同文案）；
  * 现状（2026-10-08 实测）：**静默 ok=true**，孤儿文件落盘、view 未创建。

多点攻击（每路都入证据 JSON）：
  ① 写：对新鲜不存在的 view 调 set_source，记录 ok/error；
  ② 读回：对同一 view 调 `veriloga.read`，看是否出现"写说成功、读不存在"的撕裂；
  ③ DB：写入前后各查一次 `ddGetObj(lib cell view)`，证明是否被隐式创建；
  ④ 落盘：command 角色检查 `<view_dir>/veriloga.va` 是否存在（孤儿文件）；
  ⑤ 是否符合创建流程：`master.tag` 是否存在（spec 规定 ensure_view 写 master.tag）；
  ⑥ 再攻击：patch_source 对不存在的 view 是否也"成功"；check_and_save 能否通过；
  ⑦ 对照：同一场景换 `verilog.write`，必须按 verilog 门报错（对照证明漂移）。

红钉标记 `[P-129-RED-PIN]`；转绿即 rc=0（run_redpins 报 UNEXPECTED-GREEN）。

第 1 步（环境检查）：8127 业务面 + token `vb-vblog`；lib `schemtest` 需存在。
用法：PYTHONPATH=src python test/live/packages/veriloga_view_gate_p129_tb.py
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[3]
API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"
LIB = "schemtest"
EVIDENCE = ROOT / "test" / "artifacts" / "evidence" / "redpins" / "p129-veriloga-view-gate.json"
SOURCE = """// p129 minimal Verilog-A
`include "constants.vams"
`include "disciplines.vams"

module va_gate_p129(a, b);
  inout a, b;
  electrical a, b;
  analog V(b) <+ V(a);
endmodule
"""


def _call(payload: dict, timeout: int = 300) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        API, data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return json.loads(error.read().decode("utf-8"))


def _op(operation: str, **fields) -> dict:
    return _call({"operation": operation, "token": TOKEN, **fields})


def _skill(code: str) -> str:
    response = _op("basic.skill.execute", skill_code=code, timeout=60)
    result = response.get("result") or {}
    return str(result.get("output") or "").strip()


def _command(cmd: str, timeout: int = 60) -> str:
    response = _op("basic.command.run", cmd=cmd, timeout=timeout)
    result = response.get("result")
    if not isinstance(result, dict):
        return ""
    return str(result.get("stdout") or "").strip()


def main() -> int:
    # ① 环境检查：lib 必须存在
    if _skill(f'if(ddGetObj("{LIB}") t nil)') != "t":
        print(f"[P-129-BROKEN] lib {LIB} 不存在，环境不满足")
        return 1
    stamp = int(time.time())
    cell = f"va_gate_p129_{stamp}"
    sv_cell = f"sv_gate_p129_{stamp}"
    if _skill(f'if(ddGetObj("{LIB}" "{cell}") t nil)') == "t":
        print(f"[P-129-BROKEN] 预热 cell {cell} 已存在（不应发生）")
        return 1

    view_dir = _skill(
        'let((lib p) lib = ddGetObj("%s") p = ddGetObjReadPath(lib) '
        'sprintf(nil "%%s/%s/veriloga" p))' % (LIB, cell)
    ).strip().strip('"')
    if not view_dir or view_dir == "nil":
        print(f"[P-129-BROKEN] 无法解析 view_dir: {view_dir!r}")
        return 1
    orphan_file = f"{view_dir}/veriloga.va"
    disk_before = _command(f"test -f {orphan_file} && echo PRESENT || echo ABSENT")
    db_before = _skill(f'if(ddGetObj("{LIB}" "{cell}" "veriloga") t nil)')

    # ② 写：对不存在 view 的 set_source
    response = _op(
        "virtuoso.veriloga.write",
        library=LIB, cell=cell, view="veriloga",
        commands=[{"op": "set_source", "text": SOURCE}],
        timeout=180,
    )
    ok = bool(response.get("ok"))
    error = str(response.get("error") or "")

    # ③ 读回：write 说成功，read 是否也认这个 view？
    read_response = _op(
        "virtuoso.veriloga.read",
        library=LIB, cell=cell, view="veriloga", focus=["source"],
        timeout=120,
    )
    read_ok = bool(read_response.get("ok"))
    read_error = str(read_response.get("error") or "")

    # ④ DB：view 是否真的被创建
    db_after = _skill(f'if(ddGetObj("{LIB}" "{cell}" "veriloga") t nil)')

    # ⑤ 落盘：孤儿文件
    disk_after = _command(f"test -f {orphan_file} && echo PRESENT || echo ABSENT")
    files_listing = _command(f"ls -1a {view_dir} 2>/dev/null | sort")
    master_tag = _command(f"test -f {view_dir}/master.tag && echo PRESENT || echo ABSENT")

    # ⑥a 下游可用性：隐式创建出来的 view 能否通过 check_and_save
    cs_response = _op(
        "virtuoso.veriloga.check_and_save",
        library=LIB, cell=cell, view="veriloga", timeout=120,
    )
    cs_ok = bool(cs_response.get("ok"))
    cs_error = str(cs_response.get("error") or "")

    # ⑥b 再攻击：patch_source 对不存在的 view
    patch_response = _op(
        "virtuoso.veriloga.write",
        library=LIB, cell=cell, view="veriloga",
        commands=[{
            "op": "patch_source",
            "edits": [{"old_text": "V(b) <+ V(a)", "new_text": "V(b) <+ 2.0 * V(a)"}],
        }],
        timeout=120,
    )
    patch_ok = bool(patch_response.get("ok"))

    # ⑦ 对照：verilog 同场景必须有存在性门
    sv_response = _op(
        "virtuoso.verilog.write",
        library=LIB, cell=sv_cell, view="verilog",
        commands=[{
            "op": "set_source",
            "text": "module sv_gate_p129(a, b);\ninout a, b;\nendmodule\n",
        }],
        timeout=120,
    )
    sv_ok = bool(sv_response.get("ok"))
    sv_error = str(sv_response.get("error") or "")

    # 判定
    reasons: list[str] = []
    if ok and db_before == "nil":
        reasons.append("set_source 对不存在 view 未拒绝（verilog 同场景结构化拒绝）")
    if ok and db_before == "nil" and db_after == "t":
        reasons.append("set_source 隐式创建 view（绕过 ensure_view 创建流程）")
    if ok and db_after == "t" and master_tag != "PRESENT":
        reasons.append("隐式创建的 view 缺 master.tag（spec 规定 ensure_view 写 master.tag）")
    if ok and disk_after == "PRESENT" and db_after != "t":
        reasons.append(f"孤儿文件落盘: {orphan_file}")
    if not ok and "ensure_view" not in error:
        reasons.append(f"失败文案缺少 ensure_view 指引: {error[:160]!r}")
    if patch_ok:
        reasons.append("patch_source 对不存在 view 也返回 ok=true")
    if sv_ok or "ensure_view" not in sv_error:
        reasons.append(f"对照组 verilog 门异常: ok={sv_ok} err={sv_error[:160]!r}")

    # 证据
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(
        json.dumps(
            {
                "tb": "veriloga_view_gate_p129_tb",
                "lib": LIB, "cell": cell, "view": "veriloga",
                "view_dir": view_dir,
                "db_view_before": db_before, "db_view_after": db_after,
                "disk_before": disk_before, "disk_after": disk_after,
                "files_listing": files_listing.splitlines(),
                "master_tag": master_tag,
                "write_ok": ok, "write_error": error,
                "read_ok": read_ok, "read_error": read_error,
                "patch_ok": patch_ok,
                "check_save_ok": cs_ok, "check_save_error": cs_error,
                "sv_control_ok": sv_ok, "sv_control_error": sv_error,
                "reasons": reasons,
                "write_response": response,
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    if reasons:
        for reason in reasons:
            print(f"[P-129-RED-PIN] {reason}")
        print(f"[P-129-RED-PIN] 证据: {EVIDENCE.relative_to(ROOT).as_posix()}")
        return 1
    print(
        "[P-129-GREEN] veriloga 已按 verilog 同门文案拒绝、无孤儿落盘"
        f"（证据: {EVIDENCE.relative_to(ROOT).as_posix()}）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
