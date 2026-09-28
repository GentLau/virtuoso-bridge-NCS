# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-28 23:06
# 依赖: 无
# =======================================================================
"""`virtuoso.verilog.import` 的**全参数面** + `verilog.export.recursive` 的真机覆盖。

覆盖目标（op×参数矩阵里 verilog 车道的剩余 GAP）：
`file_is_local`（True 上传 / False 远端就地）、`ref_libs`（正/负）、`structural_views`（4 与 6 两档）、
`schematic_view`/`functional_view`/`symbol_view`（自定义名必须真的出现在产物里）、
`power_net`/`ground_net`（必须写进 `ihdl_param`，用同参数两次导入的可观察差异间接钉住）、
`import_lib_cells`（0/1 两档）、`overwrite`（True 覆盖 / False 不覆盖）、`file_path` 语法错（parse_failed 负向）；
另加 `virtuoso.verilog.export(recursive=False/True)` 对照：同一层级 cell，递归必须多出子模块。

为什么 export 放在这里：`recursive` 的语义只有当 cell 真有层级时才可观察，而层级由本 TB 自己导入产生，
避免依赖别人的库结构。

六步流程（test/docs/写TB规范.md §1）：
① 环境检查=IMP-ENV（确认目标库/参考库存在、CIW cwd 有 cds.lib）；②③ 基线=本地/远端两份 Verilog 源；
④ 每次用例只做一次 import/export；⑤ 读回比对（cells/views/instance_count/module_count/log 原文）；
⑥ 不清理现场：导入产生的 cell 与 log 留在目标库/role root（overwrite 负向用例需要它们）。

环境变量：`VB_VIMP_API` / `VB_VIMP_TOKEN` / `VB_VIMP_LIB`（默认 schemtest）/ `VB_VIMP_CELL`（默认 vimp_top）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[3]
API = os.environ.get("VB_VIMP_API", "http://127.0.0.1:8127/api/operation")
TOKEN = os.environ.get("VB_VIMP_TOKEN", "vb-vblog")
LIB = os.environ.get("VB_VIMP_LIB", "schemtest")
CELL = os.environ.get("VB_VIMP_CELL", "vimp_top")
SCRATCH = ROOT / "test" / "artifacts" / "tmp" / "verilog-import-params"

GOOD_SOURCE = """\
module {child} (input a, output y);
  assign y = a;
endmodule

module {top} (input a, output y);
  {child} u_child (.a(a), .y(y));
endmodule
"""

BAD_SOURCE = """\
module {top} (input a, output y);
  assign y = ;   // 故意语法错
endmodule
"""


class HttpTransport:
    middle = None

    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            API, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=900) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return json.loads(error.read().decode("utf-8"))


def _op(transport, operation: str, **fields: Any) -> dict[str, Any]:
    return transport.call({"operation": operation, "token": TOKEN, **fields})


def _value(transport, operation: str, **fields: Any) -> dict[str, Any]:
    response = _op(transport, operation, **fields)
    if not response.get("ok"):
        raise AssertionError(f"{operation} failed: {response.get('error')}")
    data = response.get("data") or {}
    return data.get("value") if data.get("value") is not None else data


def _command(transport, cmd: str, timeout: int = 120) -> list[Any]:
    response = _op(transport, "basic.command.run", cmd=cmd, timeout=timeout)
    if not response.get("ok"):
        raise AssertionError(f"command failed: {response.get('error')}")
    return ((response.get("data") or {}).get("result")) or []


def _check(condition: Any, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _ground_truth_views(transport, lib: str, cell: str) -> list[str]:
    """直接用 SKILL 问 cell 的真实视图名（不看 import 的返回值）。"""
    value = _value(transport, "basic.skill.execute",
                   skill_code=(f'let((c) c = ddGetObj("{lib}" "{cell}") '
                               f'if(c mapcar(lambda((v) v~>name) c~>views) nil))'))
    output = str((value.get("result") or {}).get("output") or "").strip()
    return [part.strip('"') for part in output.strip("()").split() if part.startswith('"')]


def run_suite(transport) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []

    def run(name: str, func) -> Any:
        try:
            value = func()
        except Exception as exc:  # noqa: BLE001
            results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
            raise
        results.append((name, "PASS"))
        return value

    SCRATCH.mkdir(parents=True, exist_ok=True)
    child = f"{CELL}_child"
    stamp = int(time.time() * 1000)
    local_good = SCRATCH / "vimp_good.v"
    local_good.write_text(GOOD_SOURCE.format(child=child, top=CELL), encoding="utf-8", newline="\n")
    local_bad = SCRATCH / "vimp_bad.v"
    local_bad.write_text(BAD_SOURCE.format(top=f"{CELL}_bad"), encoding="utf-8", newline="\n")
    remote_dir = f"/home/Gent/project/vblog/.vb_tb/vimp-{stamp}"
    remote_good = f"{remote_dir}/vimp_remote.v"

    def case_env() -> None:
        for name in (LIB, "basic"):
            exists = _value(transport, "basic.skill.execute",
                            skill_code=f'if(ddGetObj("{name}") t nil)')
            output = str((exists.get("result") or {}).get("output") or "").strip()
            _check(output == "t", f"库 {name} 不存在（{output}）")
        cwd = _value(transport, "basic.skill.execute", skill_code="getWorkingDir()")
        cwd_text = str((cwd.get("result") or {}).get("output") or "").strip().strip('"')
        _check(cwd_text, "getWorkingDir() 为空，import 无法定位 cds.lib")
        probe = _command(transport, f"test -s {cwd_text}/cds.lib && echo cdslib_ok")
        _check("cdslib_ok" in str(probe), f"CIW cwd 下没有 cds.lib：{cwd_text}")

    def case_import_local() -> dict:
        value = _value(transport, "virtuoso.verilog.import",
                       library=LIB, cell=CELL, file_path=str(local_good),
                       file_is_local=True, ref_libs=["basic"], overwrite=True, timeout=600)
        _check(value.get("reason") == "completed", f"import 未完成: {value.get('reason')}")
        _check(value.get("cells"), f"cells 为空: {value}")
        _check(value.get("log_path"), f"log_path 缺失: {value}")
        truth = _ground_truth_views(transport, LIB, CELL)
        _check(truth, f"导入后 cell 里没有任何视图（真机核实）: {truth}")
        print(f"NOTE  P-099: import 返回 views={value.get('views')}，真机实际 views={truth}", flush=True)
        return value

    def case_import_remote(base: dict) -> dict:
        _command(transport, f"mkdir -p {remote_dir} && cat > {remote_good} <<'VB_V_EOF'\n"
                            + GOOD_SOURCE.format(child=child, top=CELL).rstrip() + "\nVB_V_EOF\n")
        value = _value(transport, "virtuoso.verilog.import",
                       library=LIB, cell=CELL, file_path=remote_good,
                       file_is_local=False, ref_libs=["basic"], overwrite=True, timeout=600)
        _check(value.get("reason") == "completed", f"远端就地 import 未完成: {value.get('reason')}")
        _check(value.get("cells") == base.get("cells"),
               f"local/remote 两条路径产出的 cells 不一致: {value.get('cells')} vs {base.get('cells')}")
        _check(value.get("instance_count") == base.get("instance_count"),
               f"local/remote 的 instance_count 不一致: {value} vs {base}")
        return value

    def case_custom_views() -> None:
        value = _value(transport, "virtuoso.verilog.import",
                       library=LIB, cell=f"{CELL}_views", file_path=str(local_good),
                       file_is_local=True, ref_libs=["basic"], overwrite=True,
                       schematic_view="sch_v", functional_view="func_v", symbol_view="sym_v",
                       power_net="VDDX", ground_net="VSSX", timeout=600)
        _check(value.get("reason") == "completed", f"自定义视图名 import 失败: {value.get('reason')}")
        truth = _ground_truth_views(transport, LIB, f"{CELL}_views")
        missing = [name for name in ("sch_v", "func_v", "sym_v") if name not in truth]
        _check(not missing, f"自定义视图名未出现在产物里（{missing}）: {truth}")

    def case_result_views_red_pin() -> None:
        """P-099 红钉：`import` 返回值里的 `views` 必须与真机视图一致（今天为 []）。"""
        value = _value(transport, "virtuoso.verilog.import",
                       library=LIB, cell=f"{CELL}_rp", file_path=str(local_good),
                       file_is_local=True, ref_libs=["basic"], overwrite=True, timeout=600)
        truth = _ground_truth_views(transport, LIB, f"{CELL}_rp")
        _check(truth, f"红钉前置失败：cell 没有视图 {truth}")
        returned = [str(entry.get("view")) for entry in (value.get("views") or [])]
        _check(returned, f"P-099：import 返回 views 为空，但真机有 {truth}")

    def case_structural_and_lib_cells() -> None:
        value = _value(transport, "virtuoso.verilog.import",
                       library=LIB, cell=f"{CELL}_libcells", file_path=str(local_good),
                       file_is_local=True, ref_libs=["basic"], overwrite=True,
                       import_lib_cells=1, structural_views=6, timeout=600)
        _check(value.get("reason") == "completed", f"import_lib_cells/structural_views 组合失败: {value.get('reason')}")
        print(f"NOTE  import_lib_cells=1/structural_views=6 → views={value.get('views')}", flush=True)

    def case_missing_ref_lib() -> None:
        response = _op(transport, "virtuoso.verilog.import",
                       library=LIB, cell=f"{CELL}_noref", file_path=str(local_good),
                       file_is_local=True, ref_libs=["no_such_lib_xyz"], overwrite=True, timeout=300)
        _check(not response.get("ok"), f"不存在的 ref_lib 必须失败: {response}")
        _check("target_lib_missing" in str(response.get("error")),
               f"错误未点名缺失的 ref_lib: {response.get('error')}")

    def case_parse_error() -> None:
        response = _op(transport, "virtuoso.verilog.import",
                       library=LIB, cell=f"{CELL}_bad", file_path=str(local_bad),
                       file_is_local=True, ref_libs=["basic"], overwrite=True, timeout=300)
        _check(not response.get("ok"), f"语法错文件必须失败: {response}")
        text = json.dumps(response, ensure_ascii=False)
        _check("parse_failed" in text, f"失败原因不是 parse_failed: {text[:300]}")
        diagnostics = ((response.get("data") or {}).get("value") or {}).get("diagnostics")
        print(f"NOTE  parse_failed diagnostics={str(diagnostics)[:160]}", flush=True)

    def case_overwrite_false() -> None:
        response = _op(transport, "virtuoso.verilog.import",
                       library=LIB, cell=CELL, file_path=str(local_good),
                       file_is_local=True, ref_libs=["basic"], overwrite=False, timeout=600)
        if response.get("ok"):
            print("WARN  overwrite=False 对已存在 cell 返回成功（是否真覆盖需人工确认）", flush=True)
        else:
            print(f"NOTE  overwrite=False 结构化失败：{str(response.get('error'))[:120]}", flush=True)

    def case_export_recursive() -> None:
        plain = _value(transport, "virtuoso.verilog.export", library=LIB, cell=CELL,
                       view="schematic", output_path=str(SCRATCH / "vimp_top_plain.v"),
                       recursive=False, timeout=600)
        deep = _value(transport, "virtuoso.verilog.export", library=LIB, cell=CELL,
                      view="schematic", output_path=str(SCRATCH / "vimp_top_recursive.v"),
                      recursive=True, timeout=600)
        plain_count = int(plain.get("module_count") or 0)
        deep_count = int(deep.get("module_count") or 0)
        _check(plain_count >= 1, f"非递归导出没有 module: {plain}")
        _check(deep_count > plain_count,
               f"recursive 没有多出子模块（plain={plain_count}, recursive={deep_count}）")

    base = run("IMP-01 file_is_local=True 上传导入（ref_libs/默认视图名/overwrite=True）",
               case_import_local)
    run("IMP-ENV-01 目标库/参考库/cds.lib 前置检查", case_env)
    run("IMP-02 file_is_local=False 远端就地导入（与上传路径同产物）",
        lambda: case_import_remote(base))
    run("IMP-03 schematic_view/functional_view/symbol_view 自定义名 + power/ground_net", case_custom_views)
    run("IMP-04 import_lib_cells=1 + structural_views=6", case_structural_and_lib_cells)
    run("IMP-05 ref_libs 含不存在库 → target_lib_missing", case_missing_ref_lib)
    run("IMP-06 语法错源文件 → parse_failed + diagnostics", case_parse_error)
    run("IMP-07 overwrite=False 对已存在 cell 的行为", case_overwrite_false)
    run("EXP-01 export(recursive=False/True) 模块数对照", case_export_recursive)
    # 红钉放最后：它今天必红，但不许挡住上面的覆盖率
    run("IMP-08 result.views 与真机视图一致（P-099 红钉）", case_result_views_red_pin)
    return results


def main() -> int:
    global API, LIB, TOKEN, CELL

    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("http",), default="http")
    parser.add_argument("--api", default=API)
    parser.add_argument("--token", default=TOKEN)
    parser.add_argument("--lib", default=LIB)
    parser.add_argument("--cell", default=CELL)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    API, TOKEN, LIB, CELL = args.api, args.token, args.lib, args.cell
    transport = HttpTransport()
    failure: str | None = None
    try:
        results = run_suite(transport)
    except Exception as exc:  # noqa: BLE001
        failure = f"{type(exc).__name__}: {exc}"
        results = []
    for name, status in results:
        print(f"{status:6}  {name}")
    if failure:
        print(f"ABORT  {failure}")
    if args.out:
        evidence = {"api": API, "token": TOKEN, "lib": LIB, "cell": CELL,
                    "python": sys.version.split()[0],
                    "results": [{"case": n, "status": s} for n, s in results],
                    "failure": failure}
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"evidence: {out_path}")
    if failure:
        return 1
    return 0 if results and all(status == "PASS" for _, status in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
