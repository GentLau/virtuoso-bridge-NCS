# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-28 23:30
# 依赖: 无
# =======================================================================
"""S11 端到端工程流程 TB：建库 → 原理图 → symbol → CDL → 版图 → GDS → LVS → 仿真。

这是**跨包工程流程**测试（区别于 ``test/live/packages/*`` 的单包验收）：
一个真实 PDK（tsmcN65）环境里，从零建库开始，走完整的设计迭代链路，
每一步的产物都落盘留证；任一步失败即记录失败点与证据，不掩盖。

环境（默认 PDK 实例 = ``calprobe``，它的 cds.lib INCLUDE 了带 tsmcN65 的
``~/project/test/cds.lib``）::

    python test/live/flows/project_flow_tb.py --stage probe
    python test/live/flows/project_flow_tb.py --stage all

证据：``test/artifacts/env/scenario-project65/evidence-<stage>.json``
远端产物：``<file role root>/project65/``（库、GDS、CDL）
六步流程（test/docs/写TB规范.md §1）：
① `require_environment`（靶机指纹 / 业务面 / 需要的库）；②③ 造并校验基线（专属库、cell、前置对象）；
④ 只做被测动作；⑤ 读回比对（期望 / 实际入证据）；⑥ 跑完不清理现场。
某步不适用时，正文有一行注释说明原因。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
WORK_DIR = ROOT / "test" / "artifacts" / "env" / "scenario-project65"
#: direct 模式绑定的注册表（含 PDK token 与 vblog token 两个条目）
DIRECT_WORK_DIR = ROOT / "test" / "artifacts" / "env" / "log-vblog"

#: PDK 实例（带 tsmcN65）与普通实例（vblog）的 token
PDK_TOKEN = "d6af595b342647b58ec63ca6"
VLOG_TOKEN = "vb-vblog"

PDK_LIB = "tsmcN65"
NCH, PCH = "nch_25", "pch_25"

PROJ_LIB = "PROJ65"
INV_CELL = "inv1"

#: calibre 不在注册表里时用请求级覆盖（spec 12-calibre §3.3 允许，值即权威）
CALIBRE_BIN = "/opt/eda/mentor/CALIBRE2025/aok_cal_2025.1_16.10/bin/calibre"

#: tsmcN65 金属栈（Techfile/ 下的目录名）：1p6m_3X1Z1U 是最小栈
LVS_STACK = "1p6m_3X1Z1U"
PDK_ROOT = "/opt/eda/PDK/CRN65GPNEW/CRN65GPNEW"


class HttpTransport:
    middle = None

    def __init__(self, token: str) -> None:
        self.token = token

    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            API, data=body, headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=1800) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return json.loads(error.read().decode("utf-8"))


class DirectTransport:
    """进程内派发（与其它 TB 一致）：不依赖常驻业务面，直接跑工作树里的代码。

    绑定的注册表 = ``DIRECT_WORK_DIR``（含 PDK token 与 vblog token），
    因此 ``PDK_TOKEN`` / ``VLOG_TOKEN`` 两个身份都能用。
    """

    middle = None

    def __init__(self, token: str) -> None:
        from common.paths import init_work_dir
        from server import dispatch
        from server.api_server import register_packages
        from transport.middle import BusinessServer

        init_work_dir(str(DIRECT_WORK_DIR))
        register_packages()
        self.dispatch = dispatch
        self.middle = BusinessServer()
        self.token = token

    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        status, body = self.dispatch.dispatch(self.middle, payload)
        if status not in (200, 400):
            raise AssertionError(f"dispatch status {status}: {body}")
        return body


def make_transport(kind: str, token: str):
    if kind == "http":
        return HttpTransport(token)
    if kind == "direct":
        return DirectTransport(token)
    raise SystemExit(f"transport {kind!r} not supported yet")


def op(transport, operation: str, token: str | None = None, **fields: Any) -> Any:
    payload = {"operation": operation, "token": token or transport.token, **fields}
    response = transport.call(payload)
    if not response.get("ok"):
        raise FlowError(operation, response.get("error"), response.get("data"))
    return response.get("data")


def raw_call(transport, operation: str, token: str | None = None, **fields: Any) -> dict:
    """原始响应（失败也返回），用于把失败细节完整落证。"""
    return transport.call(
        {"operation": operation, "token": token or transport.token, **fields})


class FlowError(RuntimeError):
    def __init__(self, operation: str, error: Any, data: Any = None) -> None:
        super().__init__(f"{operation}: {error}")
        self.operation = operation
        self.error = error
        self.data = data


def skill(transport, code: str, token: str) -> str:
    data = op(transport, "basic.skill.execute", token=token, skill_code=code)
    result = data.get("result", {})
    if result.get("status") != "success":
        raise AssertionError(f"SKILL failed: {json.dumps(result)[:400]}")
    return result.get("output", "")


def cmd_stdout(data: Any) -> str:
    """``basic.command.run`` 的 data.result 是 CommandResult 序列化后的 list。"""
    if isinstance(data, dict):
        result = data.get("result")
        if isinstance(result, list) and len(result) >= 2:
            return str(result[1])
        if isinstance(result, dict):
            return str(result.get("stdout", ""))
    return ""


class Stage:
    """一步的产物 + 证据。"""

    def __init__(self, name: str, evidence_dir: Path) -> None:
        self.name = name
        self.started = time.time()
        self.steps: list[dict[str, Any]] = []
        self.value: dict[str, Any] = {}
        self.error: str | None = None
        self.evidence_dir = evidence_dir

    def ok(self, name: str, detail: Any = None) -> None:
        self.steps.append({"name": name, "ok": True, "detail": detail})

    def bad(self, name: str, detail: Any = None) -> None:
        self.steps.append({"name": name, "ok": False, "detail": detail})

    def to_json(self) -> dict[str, Any]:
        return {
            "stage": self.name,
            "ok": self.error is None,
            "error": self.error,
            "seconds": round(time.time() - self.started, 2),
            "steps": self.steps,
            "value": self.value,
        }

    def save(self) -> Path:
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        path = self.evidence_dir / f"evidence-{self.name}.json"
        path.write_text(json.dumps(self.to_json(), ensure_ascii=False, indent=1), encoding="utf-8")
        return path


# ---------------------------------------------------------------------------
# stages
# ---------------------------------------------------------------------------

def stage_probe(transport, cfg) -> Stage:
    st = Stage("probe", cfg.out)
    cfg.created.append(st)
    # 1) PDK 库在会话里可见吗
    out = skill(transport, f'ddGetObj("{PDK_LIB}" "{NCH}")~>name', PDK_TOKEN)
    st.ok("pdk-lib-visible", {"lib": PDK_LIB, "cell": NCH, "output": out.strip().strip('"')})

    for cell in (NCH, PCH):
        views = skill(
            transport,
            f'mapcar(lambda((vbV) vbV~>name) ddGetObj("{PDK_LIB}" "{cell}")~>views)',
            PDK_TOKEN,
        )
        st.value[f"{cell}_views"] = views.strip()

    terms = skill(
        transport,
        f'let((vv vt cv) '
        f'vv = car(setof(vbV ddGetObj("{PDK_LIB}" "{NCH}")~>views vbV~>name == "symbol")) '
        f'vt = vv~>viewType '
        f'cv = dbOpenCellViewByType("{PDK_LIB}" "{NCH}" "symbol" vt "r") '
        f'list(vt if(cv mapcar(lambda((vbT) vbT~>name) cv~>terminals) "NOCV")))',
        PDK_TOKEN,
    )
    st.value["nch_terminals"] = terms.strip()
    st.ok("pdk-symbol-terminals", terms.strip())

    # 2) 角色事实（路径纪律：产物要落在 role root 下）
    facts = skill(transport, "getWorkingDir()", PDK_TOKEN)
    st.value["daemon_cwd"] = facts.strip()
    return st


def stage_lib(transport, cfg) -> Stage:
    st = Stage("lib", cfg.out)
    cfg.created.append(st)
    remote_root = cfg.remote_root
    # 库目录的父目录必须先存在（ddCreateLib 不会递归建父目录）
    prep = op(
        transport, "basic.command.run", token=PDK_TOKEN,
        cmd=f"mkdir -p {remote_root} && test -d {remote_root} && echo dir-ok",
        timeout=120,
    )
    st.ok("remote-root-ready", {"root": remote_root, "stdout": cmd_stdout(prep).strip()})
    lib_path = f"{remote_root}/{PROJ_LIB}"
    # ②③ 还原基线（幂等）：库已存在时先删掉，保证本 stage 每次都能从零重建
    #（旧版直接 lib.create，重跑必报 libraryExists —— 违反 §3"下次运行自己还原基线"）
    if op(transport, "virtuoso.cellview.lib.list", token=PDK_TOKEN,
          timeout=120).get("value") and PROJ_LIB in op(
              transport, "virtuoso.cellview.lib.list", token=PDK_TOKEN,
              timeout=120)["value"]:
        op(transport, "virtuoso.cellview.lib.delete", token=PDK_TOKEN,
           library=PROJ_LIB, timeout=120)
        st.ok("lib-cleanup-existing", {"library": PROJ_LIB})
    data = op(
        transport, "virtuoso.cellview.lib.create", token=PDK_TOKEN,
        library=PROJ_LIB, path=lib_path, technology_library=PDK_LIB,
        timeout=120,
    )
    st.ok("lib-create", data)
    st.value["library"] = PROJ_LIB
    st.value["path"] = lib_path
    return st


def stage_schematic(transport, cfg) -> Stage:
    st = Stage("schematic-" + cfg.cell, cfg.out)
    cfg.created.append(st)
    stub = float(cfg.stub_length)
    # ②③ 前置：`schematic.write` 只写**已存在**的 view（实现先以 r 模式探测，缺则报 missing），
    # 所以这里先建 schematic view（重复运行也能自己还原基线：已存在就删掉重建）。
    try:
        op(transport, "virtuoso.cellview.view.delete", token=PDK_TOKEN,
           library=cfg.lib, cell=cfg.cell, view="schematic", timeout=120)
    except Exception:  # noqa: BLE001 - 不存在即跳过
        pass
    created_view = op(
        transport, "virtuoso.cellview.view.create", token=PDK_TOKEN,
        library=cfg.lib, cell=cfg.cell, view="schematic", view_type="schematic",
        timeout=120,
    )
    st.ok("schematic-view-create", created_view)
    commands = [
        {"op": "place_instance", "master_lib": PDK_LIB, "master_cell": PCH,
         "master_view": "symbol", "name": "MP", "pos": [0.0, 1.0], "orient": "R0"},
        {"op": "place_instance", "master_lib": PDK_LIB, "master_cell": NCH,
         "master_view": "symbol", "name": "MN", "pos": [0.0, -1.0], "orient": "R0"},
        {"op": "set_term_nets", "name": "MP", "stub_length": stub,
         "term_nets": {"G": "VIN", "D": "VOUT", "S": "VDD", "B": "VDD"}},
        {"op": "set_term_nets", "name": "MN", "stub_length": stub,
         "term_nets": {"G": "VIN", "D": "VOUT", "S": "VSS", "B": "VSS"}},
        {"op": "place_pin", "name": "VIN", "direction": "input", "pos": [-2.0, 0.0]},
        {"op": "place_pin", "name": "VOUT", "direction": "output", "pos": [2.0, 0.0]},
        {"op": "place_pin", "name": "VDD", "direction": "inputOutput", "pos": [0.0, 3.0]},
        {"op": "place_pin", "name": "VSS", "direction": "inputOutput", "pos": [0.0, -3.0]},
    ]
    data = op(
        transport, "virtuoso.schematic.write", token=PDK_TOKEN,
        library=cfg.lib, cell=cfg.cell, view="schematic", commands=commands, timeout=600,
    )
    st.value["stub_length"] = stub
    st.ok("schematic-write", data)

    saved = op(
        transport, "virtuoso.schematic.check_and_save", token=PDK_TOKEN,
        library=cfg.lib, cell=cfg.cell, view="schematic", timeout=300,
    )
    st.ok("schematic-check-and-save", saved)

    read = op(
        transport, "virtuoso.schematic.read", token=PDK_TOKEN,
        library=cfg.lib, cell=cfg.cell, view="schematic", timeout=300,
    )
    st.value["read"] = read
    nets = (read.get("value") or {}).get("nets") or {}
    st.value["net_connections"] = {k: v.get("connections") for k, v in nets.items()}
    st.value["expected"] = {
        "VIN": ["MN.G", "MP.G"], "VOUT": ["MN.D", "MP.D"],
        "VDD": ["MP.S", "MP.B"], "VSS": ["MN.S", "MN.B"],
    }
    return st


def stage_symbol(transport, cfg) -> Stage:
    st = Stage("symbol-" + cfg.cell, cfg.out)
    cfg.created.append(st)
    data = op(
        transport, "virtuoso.symbol.generate", token=PDK_TOKEN,
        library=cfg.lib, cell=cfg.cell, schematic_view="schematic",
        symbol_view="symbol", overwrite=True, timeout=600,
    )
    st.ok("symbol-generate", data)
    read = op(
        transport, "virtuoso.symbol.read", token=PDK_TOKEN,
        library=cfg.lib, cell=cfg.cell, view="symbol", timeout=300,
    )
    st.value["read"] = read
    return st


SI_ENV = """simLibName = "{lib}"
simCellName = "{cell}"
simViewName = "schematic"
hnlNetlistFileName = "{cell}.cdl"
simRunDir = "{run_dir}/"
simSimulator = "cdl"
simViewList = '("auCdl" "schematic")
simPrintInhConnAttributes = 'nil
simNetNamePrefix = "N"
simInstNamePrefix = "X"
simModelNamePrefix = "M"
hnlMaxLineLength = 79
preserveALL = t
retainBusses = t
CDLUsePortOrderForPinList = 'nil
"""

SIMRC = """cdlSimViewList = '("auCdl" "schematic")
cdlSimStopList = '("auCdl")
cdlNetlistType = 'hnl
cdlPrintComments = 't
"""


def stage_cdl(transport, cfg) -> Stage:
    """用产品操作 ``calibre.export_cdl``（官方 auCdl 链路）导出 LVS 用 CDL。

    旧版这里手写 si.env（Digital/hnl 模式：`simSimulator="cdl"`）并裸跑 si →
    必踩 `hnlCDLParamList`/`hnlCDLFormatInst` 未定义（见调查报告 §6/§11 的 Digital vs
    Analog 结论）。现在改调已真机验收的官方链路（auCdl + checkCAPPERI=nil）。
    """
    st = Stage("cdl-" + cfg.cell, cfg.out)
    cfg.created.append(st)
    run_dir = f"{cfg.command_root}/cdl/{cfg.cell}"
    data = op(
        transport, "calibre.export_cdl", token=PDK_TOKEN,
        library=cfg.lib, cell=cfg.cell, view="schematic",
        netlist_name=f"{cfg.cell}.cdl", run_dir=run_dir, cds_lib=cfg.cds_lib_file,
        timeout=600,
    )
    value = (data or {}).get("value") or {}
    netlist_path = value.get("netlist_path")
    st.ok("export-cdl", {"run_dir": run_dir, "netlist_path": netlist_path,
                         "bytes": value.get("bytes")})
    if not netlist_path or not value.get("bytes"):
        st.bad("export-cdl-empty", value)
        raise FlowError("cdl-export", "export_cdl 未产出非空 CDL", value)

    local_cdl = cfg.out / f"{cfg.cell}.cdl"
    try:
        op(transport, "basic.file.download", token=PDK_TOKEN,
           remote_path=str(netlist_path), local_path=str(local_cdl), timeout=180)
        st.value["cdl_path"] = str(local_cdl)
        st.ok("cdl-downloaded", {"bytes": local_cdl.stat().st_size})
    except Exception as exc:  # noqa: BLE001 - 下载失败不算致命，stdout 已留证
        st.bad("cdl-download", f"{type(exc).__name__}: {exc}")
    return st


PDK_LAYERMAP = f"{PDK_ROOT}/tsmcN65/tsmcN65.layermap"


def stage_layout(transport, cfg) -> Stage:
    """建版图视图 + 放两个 PDK pcell 实例 + 读回几何（为后续连线/ LVS 定位）。"""
    st = Stage("layout-" + cfg.cell, cfg.out)
    cfg.created.append(st)

    try:
        created = op(
            transport, "virtuoso.cellview.view.create", token=PDK_TOKEN,
            library=cfg.lib, cell=cfg.cell, view="layout", view_type="maskLayout",
            timeout=120,
        )
        st.ok("view-create", created)
    except FlowError as exc:  # 已存在则继续
        st.bad("view-create", str(exc.error))

    commands = [
        {"op": "place_instance", "master_lib": PDK_LIB, "master_cell": PCH,
         "master_view": "layout", "name": "MP", "pos": [0.0, 0.0], "orient": "R0"},
        {"op": "place_instance", "master_lib": PDK_LIB, "master_cell": NCH,
         "master_view": "layout", "name": "MN", "pos": [0.0, 2.0], "orient": "R0"},
    ]
    data = op(
        transport, "virtuoso.layout.write", token=PDK_TOKEN,
        library=cfg.lib, cell=cfg.cell, view="layout", commands=commands, timeout=600,
    )
    st.ok("place-instances", data)

    read = op(
        transport, "virtuoso.layout.read", token=PDK_TOKEN,
        library=cfg.lib, cell=cfg.cell, view="layout", detail="geometry", timeout=300,
    )
    value = read.get("value") or {}
    st.value["instances"] = [
        {k: i.get(k) for k in ("name", "cell", "pos", "bBox", "orient")}
        for i in (value.get("instances") or [])
    ]
    st.value["shape_count"] = len(value.get("shapes") or [])
    st.value["shapes"] = (value.get("shapes") or [])[:6]
    st.value["raw_keys"] = sorted(value.keys())
    return st


def stage_gds(transport, cfg) -> Stage:
    st = Stage("gds-" + cfg.cell, cfg.out)
    cfg.created.append(st)
    local_gds = cfg.out / f"{cfg.cell}.gds"
    local_map = cfg.out / "stage" / "tsmcN65.layermap"
    try:
        content = op(transport, "basic.file.download", token=PDK_TOKEN,
                     remote_path=PDK_LAYERMAP, local_path=str(local_map), timeout=180)
        st.ok("layermap-downloaded", {"bytes": local_map.stat().st_size})
    except Exception as exc:  # noqa: BLE001
        st.bad("layermap-download", f"{type(exc).__name__}: {exc}")

    data = op(
        transport, "virtuoso.layout.gds", token=PDK_TOKEN,
        action="export", library=cfg.lib, cell=cfg.cell, view="layout",
        file_path=str(local_gds), file_is_local=True,
        layer_map=str(local_map), layer_map_is_local=True,
        top_cell=cfg.cell, timeout=600,
    )
    st.ok("gds-export", data)
    if local_gds.exists():
        st.value["gds_bytes"] = local_gds.stat().st_size
        st.value["gds_path"] = str(local_gds)
    return st


def stage_sim(transport, cfg) -> Stage:
    """前仿：用 PDK 真实模型跑 Spectre（DC op + tran），再读结果/测量。"""
    st = Stage("sim-" + cfg.cell, cfg.out)
    cfg.created.append(st)
    stage = cfg.out / "stage"
    stage.mkdir(parents=True, exist_ok=True)
    netlist = stage / f"{cfg.cell}_pre.scs"
    netlist.write_text(
        "simulator lang=spectre\n"
        f'include "{PDK_ROOT}/models/spectre/cor_25.scs" section=tt_25\n'
        "\n"
        "VDD (vdd 0) vsource dc=2.5\n"
        "VIN (vin 0) vsource type=pulse val0=0 val1=2.5 period=10n width=5n "
        "rise=50p fall=50p\n"
        f"MP (vout vin vdd vdd) {PCH} w=400n l=280n\n"
        f"MN (vout vin 0 0) {NCH} w=400n l=280n\n"
        "CL (vout 0) capacitor c=1p\n"
        "\n"
        "dcOp dc oppoint=logfile\n"
        "tran1 tran stop=25n\n",
        encoding="utf-8",
    )
    st.ok("netlist-written", {"path": str(netlist), "bytes": netlist.stat().st_size})

    job = f"{cfg.cell}_pre"
    # 该 job 的 run dir 由包内推导（<spectre role root>/spectre/<job>）；
    # 包拒绝复用非空目录（防覆盖），TB 负责先清出干净目录。
    run_dir = f"{cfg.spectre_root}/spectre/{job}"
    cleaned = op(transport, "basic.command.run", token=PDK_TOKEN,
                 cmd=f"rm -rf {run_dir} && echo cleaned", timeout=120)
    st.ok("run-dir-clean", {"run_dir": run_dir, "stdout": cmd_stdout(cleaned).strip()})

    response = raw_call(
        transport, "spectre.run", token=PDK_TOKEN,
        tasks=[{"job": job, "netlist": str(netlist)}],
        max_workers=1, mode="spectre", parse="auto", download=True,
        keep_run_dir=True, timeout=900,
    )
    data = response.get("data") or {}
    value = data.get("value") or {}
    runs = value.get("runs") or []
    st.value["run"] = {k: v for k, v in (runs[0] if runs else {}).items() if k != "steps"}
    st.value["response_ok"] = response.get("ok")
    st.value["response_error"] = response.get("error")
    st.value["run_steps"] = (runs[0].get("steps") if runs else None)
    if not (response.get("ok") and runs and runs[0].get("ok")):
        st.bad("spectre-run", json.dumps(st.value, ensure_ascii=False)[:4000])
        st.error = f"spectre ran but failed: {response.get('error')}"
        return st
    st.ok("spectre-run", {"job": job, "run_value": st.value["run"].get("value")})

    try:
        run_value = st.value["run"].get("value") or {}
        measured = op(
            transport, "spectre.measure", token=PDK_TOKEN,
            data=run_value.get("data") or {},
            metrics=[
                {"type": "max", "signal": "vout"},
                {"type": "min", "signal": "vout"},
                {"type": "mean", "signal": "vout"},
                {"type": "rms", "signal": "vout"},
                {"type": "threshold_crossing", "signal": "vout", "threshold": 1.25,
                 "direction": "rise", "edge": 1},
                {"type": "delay", "from_signal": "vin", "to_signal": "vout",
                 "threshold": 1.25, "direction": "fall", "edge": 1},
            ],
            timeout=300,
        )
        st.value["metrics"] = measured.get("value")
        st.ok("spectre-measure", measured.get("value"))
    except Exception as exc:  # noqa: BLE001 - 测量失败单独记，不掩盖 run 成功
        st.bad("spectre-measure", f"{type(exc).__name__}: {exc}")
    return st


STAGES = {
    "probe": stage_probe,
    "lib": stage_lib,
    "schematic": stage_schematic,
    "symbol": stage_symbol,
    "cdl": stage_cdl,
    "layout": stage_layout,
    "gds": stage_gds,
    "sim": stage_sim,
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", default="all",
                    help="probe|lib|schematic|symbol|all")
    ap.add_argument("--transport", default="direct", choices=["http", "direct"])
    ap.add_argument("--token", default=PDK_TOKEN)
    ap.add_argument("--lib", default=PROJ_LIB)
    ap.add_argument("--cell", default=INV_CELL)
    ap.add_argument("--stub-length", type=float, default=0.5)
    ap.add_argument("--remote-root",
                    default="/home/Gent/.virtuoso-bridge/calprobe/file/project65")
    ap.add_argument("--command-root", default="/home/Gent/.virtuoso-bridge/calprobe/command")
    ap.add_argument("--cds-lib-file", default="/home/Gent/project/calprobe/cds.lib")
    ap.add_argument("--spectre-root", default="/home/Gent/.virtuoso-bridge/calprobe/spectre")
    ap.add_argument("--out", type=Path, default=WORK_DIR)
    args = ap.parse_args(argv)

    transport = make_transport(args.transport, args.token)
    args.created = []
    names = list(STAGES) if args.stage == "all" else [args.stage]
    results = []
    failed = False
    for name in names:
        fn = STAGES[name]
        try:
            st = fn(transport, args)
            st.ok("stage-done")
        except Exception as exc:  # noqa: BLE001 - TB 记录失败点，不掩盖
            st = args.created[-1] if args.created else Stage(name, args.out)
            st.error = f"{type(exc).__name__}: {exc}"
            failed = True
        path = st.save()
        results.append(st.to_json())
        print(json.dumps({k: v for k, v in st.to_json().items() if k != "steps"},
                         ensure_ascii=False))
        print(f"  evidence: {path}")
        if failed:
            break

    summary = WORK_DIR / "summary.json"
    summary.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"summary: {summary}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())


