# === TB 注释头（规范见 test/docs/写TB规范.md §0）=====================
# 作者: 测试/root
# 最后改动: 2026-09-28 21:10
# 依赖: 无
# =====================================================================
"""SerDes RX 前端全流程 TB（第五轮新增的真实业务场景）。

场景贴近用户实际用法：在带 PDK（tsmcN65）的会话里从零建一个库，做一条
**5 Gb/s 差分 SerDes 接收前端**（输入端接 + 有源 CTLE + 输出缓冲），
跨包走完整链路并带**数值判据**：

    probe → lib → 输出缓冲(inv) → CTLE leaf → 输入端接 → 顶层层次化原理图
          → symbol → 版图 → GDS（含"新目录发布"攻击面）→ CDL → DRC/LVS（可选）
          → Spectre AC/TRAN 前仿 + 指标测量（低频增益/高频峰化/3dB 带宽）

与 ``project_flow_tb.py``（单管 inv、按 stage 断点跑）的区别：本 TB 是**层次化 + 差分模拟**
的真实设计流，判据是"测出来的 AC 指标"，不是"接口返回 ok"。

用法（默认走 HTTP 业务面 8127，token 为带 PDK 的实例）::

    python test/live/flows/serdes_rx_flow_tb.py --stage all
    python test/live/flows/serdes_rx_flow_tb.py --stage sim --with-calibre

证据：``test/artifacts/evidence/round4-scenario/serdes/``
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
_RUNNERS = Path(__file__).resolve().parents[3] / "test" / "shared" / "runners"
if str(_RUNNERS) not in sys.path:
    sys.path.insert(0, str(_RUNNERS))
from env_check import require_environment  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
WORK_DIR = ROOT / "test" / "artifacts" / "evidence" / "round4-scenario" / "serdes"

#: 带 PDK 的实例（calprobe，wsl-gent，daemon 65122）
PDK_TOKEN = "d6af595b342647b58ec63ca6"
PDK_LIB = "tsmcN65"
ALIB = "analogLib"
NCH, PCH = "nch_25", "pch_25"
PDK_ROOT = "/opt/eda/PDK/CRN65GPNEW/CRN65GPNEW"

LIB = "SRX65"
CTLE, TERM, BUF, TOP = "ctle_core", "rx_term", "inv_buf", "rx_front"

#: 角色根（产物要落在 role root 下）
FILE_ROOT = "/home/Gent/.virtuoso-bridge/calprobe/file/serdes_rx"
COMMAND_ROOT = "/home/Gent/.virtuoso-bridge/calprobe/command"
SPECTRE_ROOT = "/home/Gent/.virtuoso-bridge/calprobe/spectre"
CDS_LIB_FILE = "/home/Gent/project/calprobe/cds.lib"
LAYERMAP = f"{PDK_ROOT}/tsmcN65/tsmcN65.layermap"


class FlowError(RuntimeError):
    def __init__(self, operation: str, error: Any, data: Any = None) -> None:
        super().__init__(f"{operation}: {error}")
        self.operation = operation
        self.error = error
        self.data = data


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


def op(transport, operation: str, **fields: Any) -> Any:
    payload = {"operation": operation, "token": transport.token, **fields}
    response = transport.call(payload)
    if not response.get("ok"):
        raise FlowError(operation, response.get("error"), response.get("data"))
    return response.get("data")


def raw_call(transport, operation: str, **fields: Any) -> dict:
    return transport.call({"operation": operation, "token": transport.token, **fields})


def skill(transport, code: str, timeout: float = 300) -> str:
    data = op(transport, "basic.skill.execute", skill_code=code, timeout=timeout)
    result = data.get("result", {})
    if result.get("status") != "success":
        raise AssertionError(f"SKILL failed: {json.dumps(result, ensure_ascii=False)[:400]}")
    return result.get("output", "")


def cmd_stdout(data: Any) -> str:
    if isinstance(data, dict):
        result = data.get("result")
        if isinstance(result, list) and len(result) >= 2:
            return str(result[1])
        if isinstance(result, dict):
            return str(result.get("stdout", ""))
    return ""


def ensure_view(t: HttpTransport, cell: str, view: str, view_type: str,
                st: "Stage | None" = None) -> dict:
    """``schematic.write`` 是 append 语义，视图必须先存在（见 schematic.py:405-420）。"""
    try:
        data = op(t, "virtuoso.cellview.view.create", library=LIB, cell=cell,
                  view=view, view_type=view_type, timeout=180)
        if st:
            st.ok(f"view-create-{cell}", data)
        return data
    except FlowError as exc:
        if st:
            st.ok(f"view-create-{cell}-existing", str(exc.error))
        return {"existing": str(exc.error)}


class Stage:
    def __init__(self, name: str, out: Path) -> None:
        self.name = name
        self.started = time.time()
        self.steps: list[dict[str, Any]] = []
        self.value: dict[str, Any] = {}
        self.error: str | None = None
        self.out = out

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
        self.out.mkdir(parents=True, exist_ok=True)
        path = self.out / f"serdes-{self.name}.json"
        path.write_text(
            json.dumps(self.to_json(), ensure_ascii=False, indent=1), encoding="utf-8")
        return path


def stage_probe(t: HttpTransport, cfg) -> Stage:
    st = Stage("probe", cfg.out)
    cfg.created.append(st)
    st.value["pdk"] = skill(t, f'ddGetObj("{PDK_LIB}")~>name').strip()
    st.value["alib"] = skill(t, f'ddGetObj("{ALIB}")~>name').strip()
    st.value["cwd"] = skill(t, "getWorkingDir()").strip()
    for cell, lib in ((NCH, PDK_LIB), ("res", ALIB), ("cap", ALIB)):
        terms = skill(
            t,
            f'let((cv) cv=dbOpenCellViewByType("{lib}" "{cell}" "symbol" '
            f'"schematicSymbol" "r") if(cv mapcar(lambda((vbT) vbT~>name) '
            f'cv~>terminals) "NOCV"))',
        )
        st.value[f"{cell}_terminals"] = terms.strip()
    return st


def stage_lib(t: HttpTransport, cfg) -> Stage:
    st = Stage("lib", cfg.out)
    cfg.created.append(st)
    prep = op(t, "basic.command.run",
              cmd=f"mkdir -p {FILE_ROOT} && test -d {FILE_ROOT} && echo dir-ok",
              timeout=120)
    st.ok("remote-root-ready", cmd_stdout(prep).strip())
    lib_path = f"{FILE_ROOT}/{LIB}"
    try:
        data = op(t, "virtuoso.cellview.lib.create", library=LIB, path=lib_path,
                  technology_library=PDK_LIB, timeout=180)
        st.ok("lib-create", data)
    except FlowError as exc:
        get = op(t, "virtuoso.cellview.lib.get", library=LIB, timeout=120)
        st.ok("lib-exists", {"error": str(exc.error), "get": get})
    st.value["library"], st.value["path"] = LIB, lib_path
    return st


BUF_COMMANDS = [
    {"op": "place_instance", "master_lib": PDK_LIB, "master_cell": PCH,
     "master_view": "symbol", "name": "MP", "pos": [0.0, 1.0], "orient": "R0"},
    {"op": "place_instance", "master_lib": PDK_LIB, "master_cell": NCH,
     "master_view": "symbol", "name": "MN", "pos": [0.0, -1.0], "orient": "R0"},
    {"op": "set_term_nets", "name": "MP",
     "term_nets": {"G": "vin", "D": "vout", "S": "vdd", "B": "vdd"}},
    {"op": "set_term_nets", "name": "MN",
     "term_nets": {"G": "vin", "D": "vout", "S": "vss", "B": "vss"}},
    {"op": "place_pin", "name": "vin", "direction": "input", "pos": [-2.0, 0.0]},
    {"op": "place_pin", "name": "vout", "direction": "output", "pos": [2.0, 0.0]},
    {"op": "place_pin", "name": "vdd", "direction": "inputOutput", "pos": [0.0, 3.0]},
    {"op": "place_pin", "name": "vss", "direction": "inputOutput", "pos": [0.0, -3.0]},
]


def stage_buf(t: HttpTransport, cfg) -> Stage:
    """输出缓冲（单级 CMOS 反相器）：给整条 RX 链一个可做 LVS 的确定性子块。"""
    st = Stage("buf", cfg.out)
    cfg.created.append(st)
    ensure_view(t, BUF, "schematic", "schematic", st)
    data = op(t, "virtuoso.schematic.write", library=LIB, cell=BUF, view="schematic",
              commands=BUF_COMMANDS, timeout=600)
    st.ok("schematic-write", data)
    saved = op(t, "virtuoso.schematic.check_and_save", library=LIB, cell=BUF,
               view="schematic", timeout=300)
    st.ok("check-and-save", saved)
    sym = op(t, "virtuoso.symbol.generate", library=LIB, cell=BUF,
             schematic_view="schematic", symbol_view="symbol", overwrite=True, timeout=600)
    st.ok("symbol-generate", sym)
    return st


CTLE_COMMANDS = [
    {"op": "place_instance", "master_lib": PDK_LIB, "master_cell": NCH,
     "master_view": "symbol", "name": "M1", "pos": [-3.0, 0.0], "orient": "R0"},
    {"op": "place_instance", "master_lib": PDK_LIB, "master_cell": NCH,
     "master_view": "symbol", "name": "M2", "pos": [3.0, 0.0], "orient": "R0"},
    {"op": "place_instance", "master_lib": PDK_LIB, "master_cell": NCH,
     "master_view": "symbol", "name": "M3", "pos": [0.0, -3.0], "orient": "R0"},
    {"op": "place_instance", "master_lib": ALIB, "master_cell": "res",
     "master_view": "symbol", "name": "R1", "pos": [-3.0, 3.0], "orient": "R0"},
    {"op": "place_instance", "master_lib": ALIB, "master_cell": "res",
     "master_view": "symbol", "name": "R2", "pos": [3.0, 3.0], "orient": "R0"},
    {"op": "place_instance", "master_lib": ALIB, "master_cell": "res",
     "master_view": "symbol", "name": "RS1", "pos": [-1.5, -1.5], "orient": "R0"},
    {"op": "place_instance", "master_lib": ALIB, "master_cell": "res",
     "master_view": "symbol", "name": "RS2", "pos": [1.5, -1.5], "orient": "R0"},
    {"op": "place_instance", "master_lib": ALIB, "master_cell": "cap",
     "master_view": "symbol", "name": "CS1", "pos": [-4.5, -1.5], "orient": "R0"},
    {"op": "place_instance", "master_lib": ALIB, "master_cell": "cap",
     "master_view": "symbol", "name": "CS2", "pos": [4.5, -1.5], "orient": "R0"},
    {"op": "set_instance_params", "name": "R1", "params": {"r": "500"}},
    {"op": "set_instance_params", "name": "R2", "params": {"r": "500"}},
    {"op": "set_instance_params", "name": "RS1", "params": {"r": "50"}},
    {"op": "set_instance_params", "name": "RS2", "params": {"r": "50"}},
    {"op": "set_instance_params", "name": "CS1", "params": {"c": "1p"}},
    {"op": "set_instance_params", "name": "CS2", "params": {"c": "1p"}},
    {"op": "set_term_nets", "name": "M1",
     "term_nets": {"G": "vinp", "D": "outn", "S": "s1", "B": "vss"}},
    {"op": "set_term_nets", "name": "M2",
     "term_nets": {"G": "vinn", "D": "outp", "S": "s2", "B": "vss"}},
    {"op": "set_term_nets", "name": "M3",
     "term_nets": {"G": "vbias", "D": "tail", "S": "vss", "B": "vss"}},
    {"op": "set_term_nets", "name": "R1",
     "term_nets": {"PLUS": "vdd", "MINUS": "outp"}},
    {"op": "set_term_nets", "name": "R2",
     "term_nets": {"PLUS": "vdd", "MINUS": "outn"}},
    {"op": "set_term_nets", "name": "RS1",
     "term_nets": {"PLUS": "s1", "MINUS": "tail"}},
    {"op": "set_term_nets", "name": "RS2",
     "term_nets": {"PLUS": "s2", "MINUS": "tail"}},
    {"op": "set_term_nets", "name": "CS1",
     "term_nets": {"PLUS": "s1", "MINUS": "tail"}},
    {"op": "set_term_nets", "name": "CS2",
     "term_nets": {"PLUS": "s2", "MINUS": "tail"}},
    {"op": "place_pin", "name": "vinp", "direction": "input", "pos": [-6.0, 0.5]},
    {"op": "place_pin", "name": "vinn", "direction": "input", "pos": [6.0, 0.5]},
    {"op": "place_pin", "name": "outp", "direction": "output", "pos": [6.0, 4.0]},
    {"op": "place_pin", "name": "outn", "direction": "output", "pos": [-6.0, 4.0]},
    {"op": "place_pin", "name": "vbias", "direction": "input", "pos": [0.0, -5.0]},
    {"op": "place_pin", "name": "vdd", "direction": "inputOutput", "pos": [0.0, 6.0]},
    {"op": "place_pin", "name": "vss", "direction": "inputOutput", "pos": [0.0, -7.0]},
]

EXPECTED_CTLE_NETS = {
    "vinp": {"M1.G"},
    "vinn": {"M2.G"},
    "outp": {"M2.D", "R1.MINUS"},
    "outn": {"M1.D", "R2.MINUS"},
    "s1": {"M1.S", "RS1.PLUS", "CS1.PLUS"},
    "s2": {"M2.S", "RS2.PLUS", "CS2.PLUS"},
    "tail": {"M3.D", "RS1.MINUS", "RS2.MINUS", "CS1.MINUS", "CS2.MINUS"},
    "vbias": {"M3.G"},
    "vdd": {"R1.PLUS", "R2.PLUS"},
    "vss": {"M1.B", "M2.B", "M3.S", "M3.B"},
}


def _nets_of(read_value: dict) -> dict[str, set[str]]:
    nets: dict[str, set[str]] = {}
    for name, payload in (read_value.get("nets") or {}).items():
        nets[name] = set(payload.get("connections") or [])
    return nets


def stage_ctle(t: HttpTransport, cfg) -> Stage:
    st = Stage("ctle", cfg.out)
    cfg.created.append(st)
    # 共享库污染探针：set_instance_params 前后，analogLib res 的 cell 级 CDF 默认值
    cdf_skill = ('let((ccd p) ccd = cdfGetCellCDF(ddGetObj("analogLib" "res")) '
                 'p = get(ccd "r") if(p p~>value "NOPARAM"))')
    before = skill(t, cdf_skill).strip()
    st.value["alib_res_cdf_before"] = before

    ensure_view(t, CTLE, "schematic", "schematic", st)

    data = op(t, "virtuoso.schematic.write", library=LIB, cell=CTLE, view="schematic",
              commands=CTLE_COMMANDS, timeout=900)
    st.ok("schematic-write", data)

    after = skill(t, cdf_skill).strip()
    st.value["alib_res_cdf_after"] = after
    st.value["shared_cdf_mutated"] = (before != after)
    (st.ok if before == after else st.bad)(
        "analogLib-cdf-untouched", {"before": before, "after": after})
    if before != after:
        skill(t, f'let((ccd p) ccd = cdfGetCellCDF(ddGetObj("analogLib" "res")) '
                 f'p = get(ccd "r") when(p p~>value = {before}) "restored")')
        st.value["cdf_restored"] = True

    saved = op(t, "virtuoso.schematic.check_and_save", library=LIB, cell=CTLE,
               view="schematic", timeout=300)
    st.ok("check-and-save", saved)

    read = op(t, "virtuoso.schematic.read", library=LIB, cell=CTLE, view="schematic",
              timeout=300)
    nets = _nets_of(read.get("value") or {})
    st.value["nets"] = {k: sorted(v) for k, v in nets.items()}
    mismatches = {
        net: {"expected": sorted(exp), "actual": sorted(nets.get(net, set()))}
        for net, exp in EXPECTED_CTLE_NETS.items()
        if not exp.issubset(nets.get(net, set()))
    }
    st.value["net_mismatches"] = mismatches
    (st.ok if not mismatches else st.bad)("netlist-connectivity", mismatches)

    sym = op(t, "virtuoso.symbol.generate", library=LIB, cell=CTLE,
             schematic_view="schematic", symbol_view="symbol", overwrite=True, timeout=600)
    st.ok("symbol-generate", sym)
    sym_read = op(t, "virtuoso.symbol.read", library=LIB, cell=CTLE, view="symbol",
                  timeout=300)
    st.value["symbol"] = sym_read.get("value")
    return st


TERM_COMMANDS = [
    {"op": "place_instance", "master_lib": ALIB, "master_cell": "res",
     "master_view": "symbol", "name": "RT1", "pos": [-2.0, 0.0], "orient": "R0"},
    {"op": "place_instance", "master_lib": ALIB, "master_cell": "res",
     "master_view": "symbol", "name": "RT2", "pos": [2.0, 0.0], "orient": "R0"},
    {"op": "set_instance_params", "name": "RT1", "params": {"r": "50"}},
    {"op": "set_instance_params", "name": "RT2", "params": {"r": "50"}},
    {"op": "set_term_nets", "name": "RT1",
     "term_nets": {"PLUS": "inp", "MINUS": "vcm"}},
    {"op": "set_term_nets", "name": "RT2",
     "term_nets": {"PLUS": "inn", "MINUS": "vcm"}},
    {"op": "place_pin", "name": "inp", "direction": "inputOutput", "pos": [-5.0, 0.0]},
    {"op": "place_pin", "name": "inn", "direction": "inputOutput", "pos": [5.0, 0.0]},
    {"op": "place_pin", "name": "vcm", "direction": "input", "pos": [0.0, -3.0]},
]


def stage_term(t: HttpTransport, cfg) -> Stage:
    st = Stage("term", cfg.out)
    cfg.created.append(st)
    ensure_view(t, TERM, "schematic", "schematic", st)
    data = op(t, "virtuoso.schematic.write", library=LIB, cell=TERM, view="schematic",
              commands=TERM_COMMANDS, timeout=600)
    st.ok("schematic-write", data)
    saved = op(t, "virtuoso.schematic.check_and_save", library=LIB, cell=TERM,
               view="schematic", timeout=300)
    st.ok("check-and-save", saved)
    sym = op(t, "virtuoso.symbol.generate", library=LIB, cell=TERM,
             schematic_view="schematic", symbol_view="symbol", overwrite=True, timeout=600)
    st.ok("symbol-generate", sym)
    return st


TOP_COMMANDS = [
    {"op": "place_instance", "master_lib": LIB, "master_cell": TERM,
     "master_view": "symbol", "name": "XTERM", "pos": [-8.0, 2.0], "orient": "R0"},
    {"op": "place_instance", "master_lib": LIB, "master_cell": CTLE,
     "master_view": "symbol", "name": "XCTLE", "pos": [0.0, 2.0], "orient": "R0"},
    {"op": "place_instance", "master_lib": LIB, "master_cell": BUF,
     "master_view": "symbol", "name": "XBUF", "pos": [8.0, 2.0], "orient": "R0"},
    {"op": "place_instance", "master_lib": ALIB, "master_cell": "cap",
     "master_view": "symbol", "name": "CLP", "pos": [4.0, -3.0], "orient": "R0"},
    {"op": "place_instance", "master_lib": ALIB, "master_cell": "cap",
     "master_view": "symbol", "name": "CLN", "pos": [-4.0, -3.0], "orient": "R0"},
    {"op": "set_instance_params", "name": "CLP", "params": {"c": "20f"}},
    {"op": "set_instance_params", "name": "CLN", "params": {"c": "20f"}},
    {"op": "set_term_nets", "name": "XTERM",
     "term_nets": {"inp": "vinp", "inn": "vinn", "vcm": "vcm"}},
    {"op": "set_term_nets", "name": "XCTLE",
     "term_nets": {"vinp": "vinp", "vinn": "vinn", "outp": "outp",
                   "outn": "outn", "vbias": "vbias", "vdd": "vdd", "vss": "vss"}},
    {"op": "set_term_nets", "name": "XBUF",
     "term_nets": {"vin": "outp", "vout": "rxout", "vdd": "vdd", "vss": "vss"}},
    {"op": "set_term_nets", "name": "CLP",
     "term_nets": {"PLUS": "rxout", "MINUS": "vss"}},
    {"op": "set_term_nets", "name": "CLN",
     "term_nets": {"PLUS": "outn", "MINUS": "vss"}},
    {"op": "place_pin", "name": "vinp", "direction": "inputOutput", "pos": [-14.0, 2.0]},
    {"op": "place_pin", "name": "vinn", "direction": "inputOutput", "pos": [-14.0, 0.0]},
    {"op": "place_pin", "name": "rxout", "direction": "output", "pos": [14.0, 2.0]},
    {"op": "place_pin", "name": "vcm", "direction": "input", "pos": [-14.0, -3.0]},
    {"op": "place_pin", "name": "vbias", "direction": "input", "pos": [0.0, -6.0]},
    {"op": "place_pin", "name": "vdd", "direction": "inputOutput", "pos": [0.0, 8.0]},
    {"op": "place_pin", "name": "vss", "direction": "inputOutput", "pos": [0.0, -8.0]},
]


def stage_top(t: HttpTransport, cfg) -> Stage:
    st = Stage("top", cfg.out)
    cfg.created.append(st)
    ensure_view(t, TOP, "schematic", "schematic", st)
    data = op(t, "virtuoso.schematic.write", library=LIB, cell=TOP, view="schematic",
              commands=TOP_COMMANDS, timeout=900)
    st.ok("schematic-write", data)
    saved = op(t, "virtuoso.schematic.check_and_save", library=LIB, cell=TOP,
               view="schematic", timeout=300)
    st.ok("check-and-save", saved)
    read = op(t, "virtuoso.schematic.read", library=LIB, cell=TOP, view="schematic",
              timeout=300)
    value = read.get("value") or {}
    masters = {}
    for inst in (value.get("instances") or []):
        masters[inst.get("name")] = (
            f"{inst.get('lib') or inst.get('master_lib')}/"
            f"{inst.get('cell') or inst.get('master_cell')}")
    st.value["instance_masters"] = masters
    st.value["nets"] = {k: sorted(v) for k, v in _nets_of(value).items()}
    want = {"XCTLE": f"{LIB}/{CTLE}", "XTERM": f"{LIB}/{TERM}", "XBUF": f"{LIB}/{BUF}"}
    bad = {k: v for k, v in want.items() if masters.get(k) != v}
    st.value["hierarchy_mismatches"] = bad
    (st.ok if not bad else st.bad)("hierarchy-masters", bad)
    sym = op(t, "virtuoso.symbol.generate", library=LIB, cell=TOP,
             schematic_view="schematic", symbol_view="symbol", overwrite=True, timeout=600)
    st.ok("symbol-generate", sym)
    return st


def stage_layout(t: HttpTransport, cfg) -> Stage:
    st = Stage("layout", cfg.out)
    cfg.created.append(st)
    try:
        created = op(t, "virtuoso.cellview.view.create", library=LIB, cell=CTLE,
                     view="layout", view_type="maskLayout", timeout=180)
        st.ok("view-create", created)
    except FlowError as exc:
        st.ok("view-create-existing", str(exc.error))
    commands = [
        {"op": "place_instance", "master_lib": PDK_LIB, "master_cell": NCH,
         "master_view": "layout", "name": "M1", "pos": [0.0, 0.0], "orient": "R0"},
        {"op": "place_instance", "master_lib": PDK_LIB, "master_cell": NCH,
         "master_view": "layout", "name": "M2", "pos": [0.0, 4.0], "orient": "R0"},
        {"op": "place_instance", "master_lib": PDK_LIB, "master_cell": NCH,
         "master_view": "layout", "name": "M3", "pos": [0.0, -4.0], "orient": "R0"},
        {"op": "place_rect", "layer": "M1", "purpose": "drawing",
         "bbox": [[-2.0, -5.0], [2.0, 6.0]]},
        {"op": "place_label", "layer": "M1", "purpose": "pin", "text": "OUTP",
         "pos": [0.0, 2.0]},
        {"op": "place_label", "layer": "M1", "purpose": "drawing", "text": "OUTP",
         "pos": [0.0, 2.0]},
    ]
    data = op(t, "virtuoso.layout.write", library=LIB, cell=CTLE, view="layout",
              commands=commands, timeout=900)
    st.ok("layout-write", data)
    read = op(t, "virtuoso.layout.read", library=LIB, cell=CTLE, view="layout",
              detail="geometry", timeout=300)
    value = read.get("value") or {}
    st.value["instances"] = [i.get("name") for i in (value.get("instances") or [])]
    st.value["shape_count"] = len(value.get("shapes") or [])
    (st.ok if len(st.value["instances"]) >= 3 else st.bad)(
        "layout-instances", st.value["instances"])

    # 另一个子块（PDK-only）也建版图：给 DRC/LVS 一个语义完整的对象
    ensure_view(t, BUF, "layout", "maskLayout", st)
    buf_cmds = [
        {"op": "place_instance", "master_lib": PDK_LIB, "master_cell": PCH,
         "master_view": "layout", "name": "MP", "pos": [0.0, 0.0], "orient": "R0"},
        {"op": "place_instance", "master_lib": PDK_LIB, "master_cell": NCH,
         "master_view": "layout", "name": "MN", "pos": [0.0, 6.0], "orient": "R0"},
        {"op": "place_rect", "layer": "M1", "purpose": "drawing",
         "bbox": [[-1.0, -1.0], [1.0, 7.0]]},
        {"op": "place_label", "layer": "M1", "purpose": "pin", "text": "VOUT",
         "pos": [0.0, 3.0]},
        {"op": "place_label", "layer": "M1", "purpose": "drawing", "text": "VOUT",
         "pos": [0.0, 3.0]},
    ]
    buf_layout = op(t, "virtuoso.layout.write", library=LIB, cell=BUF, view="layout",
                    commands=buf_cmds, timeout=900)
    st.ok("buf-layout-write", buf_layout)
    return st


def stage_gds(t: HttpTransport, cfg) -> Stage:
    """两个方向 + 新目录攻击面（P-051 的业务口径复验）。"""
    st = Stage("gds", cfg.out)
    cfg.created.append(st)
    local_map = cfg.out / "tsmcN65.layermap"
    try:
        op(t, "basic.file.download", remote_path=LAYERMAP, local_path=str(local_map),
           timeout=180)
        st.ok("layermap-downloaded", {"bytes": local_map.stat().st_size})
    except Exception as exc:  # noqa: BLE001
        st.bad("layermap-download", f"{type(exc).__name__}: {exc}")

    # A：目标目录已存在（对照）
    ok_dir = f"{FILE_ROOT}/gds"
    op(t, "basic.command.run", cmd=f"mkdir -p {ok_dir} && echo ok", timeout=60)
    a_path = f"{ok_dir}/{CTLE}.gds"
    a = raw_call(t, "virtuoso.layout.gds", action="export", library=LIB, cell=CTLE,
                 view="layout", file_path=a_path, file_is_local=False, top_cell=CTLE,
                 layer_map=LAYERMAP, layer_map_is_local=False, tech_lib=PDK_LIB,
                 timeout=900)
    st.value["A_existing_dir"] = {"ok": a.get("ok"), "error": a.get("error")}
    (st.ok if a.get("ok") else st.bad)("A-existing-dir", a.get("error"))

    # B：目标父目录不存在（真实用法：按 run-id 建新目录）
    fresh_dir = f"{FILE_ROOT}/gds-new/serdes_rx/{int(time.time())}"
    b_path = f"{fresh_dir}/{TOP}.gds"
    op(t, "basic.command.run", cmd=f"rm -rf {FILE_ROOT}/gds-new && echo cleaned",
       timeout=60)
    b = raw_call(t, "virtuoso.layout.gds", action="export", library=LIB, cell=CTLE,
                 view="layout", file_path=b_path, file_is_local=False, top_cell=CTLE,
                 layer_map=LAYERMAP, layer_map_is_local=False, tech_lib=PDK_LIB,
                 timeout=900)
    st.value["B_fresh_dir"] = {"ok": b.get("ok"), "error": b.get("error"),
                               "path": b_path}
    (st.ok if b.get("ok") else st.bad)("B-fresh-dir", b.get("error"))

    listing = op(t, "basic.command.run",
                 cmd=(f"ls -l {a_path} 2>&1; echo ---; ls -l {b_path} 2>&1; echo ---; "
                      f"stat -c '%n %s' {a_path} {b_path} 2>&1"),
                 timeout=120)
    st.value["remote_listing"] = cmd_stdout(listing)[-800:]
    st.value["A_bytes"] = _remote_size(t, a_path)
    st.value["B_bytes"] = _remote_size(t, b_path)
    (st.ok if (st.value["A_bytes"] or 0) > 0 else st.bad)("A-gds-bytes", st.value["A_bytes"])
    (st.ok if (st.value["B_bytes"] or 0) > 0 else st.bad)("B-gds-bytes", st.value["B_bytes"])
    return st


def _remote_size(t: HttpTransport, path: str) -> int | None:
    listing = op(t, "basic.command.run",
                 cmd=f"stat -c %s {path} 2>/dev/null || echo MISSING", timeout=60)
    text = cmd_stdout(listing).strip().splitlines()
    last = text[-1].strip() if text else ""
    return int(last) if last.isdigit() else None


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


def stage_cdl(t: HttpTransport, cfg) -> Stage:
    """导出 LVS 源网表（CDL）——走**官方 auCdl 链路的包内入口** `calibre.export_cdl`。

    2026-09-24 更新：旧路径（自己写 si.env/.simrc 再 `si -batch`）对含 PDK 器件的 cell
    会报 `hnlCDLParamList is not defined`；设计侧已把官方链路收进 `calibre.export_cdl`
    （见 spec《上层/12-calibre》"导出"节），本 TB 改为调它。
    """
    st = Stage("cdl", cfg.out)
    cfg.created.append(st)
    target = BUF
    run_dir = f"{COMMAND_ROOT}/cdl/serdes_{target}"
    prep = op(t, "basic.command.run",
              cmd=(f"rm -rf {run_dir} && mkdir -p {run_dir} && "
                   f"mkdir -p {COMMAND_ROOT}/cdl && "
                   f"cp {CDS_LIB_FILE} {COMMAND_ROOT}/cdl/serdes_{target}.cds.lib && "
                   f"grep -q 'DEFINE {LIB}' {COMMAND_ROOT}/cdl/serdes_{target}.cds.lib || "
                   f"echo 'DEFINE {LIB} {FILE_ROOT}/{LIB}' >> "
                   f"{COMMAND_ROOT}/cdl/serdes_{target}.cds.lib; "
                   f"grep -n 'DEFINE {LIB}' {COMMAND_ROOT}/cdl/serdes_{target}.cds.lib"),
              timeout=120)
    # 注意：cds.lib 必须放在 run_dir **外面**——export_cdl 会先清空自己的 run_dir 再复制
    # cds.lib，放在里面会被清掉（实测报 `cp: cannot stat <run_dir>/cds.lib`）。
    cds_lib = f"{COMMAND_ROOT}/cdl/serdes_{target}.cds.lib"
    st.ok("prep", {"run_dir": run_dir, "cds_lib": cds_lib,
                   "cds_lib_def": cmd_stdout(prep).strip()[-200:]})
    export = raw_call(t, "calibre.export_cdl", library=LIB, cell=target,
                      view="schematic", netlist_name=target,
                      run_dir=run_dir, cds_lib=cds_lib, timeout=900)
    value = ((export.get("data") or {}).get("value")) or {}
    st.value["export_cdl"] = value
    if export.get("ok") and value.get("bytes"):
        st.ok("export-cdl", {"bytes": value.get("bytes"),
                             "path": value.get("netlist_path")})
    else:
        st.bad("export-cdl", export.get("error") or value)
        st.error = f"calibre.export_cdl failed: {export.get('error')}"
        return st
    remote_cdl = str(value.get("netlist_path"))
    local_cdl = cfg.out / f"{target}.cdl"
    try:
        op(t, "basic.file.download", remote_path=remote_cdl,
           local_path=str(local_cdl), timeout=300)
        st.value["cdl_bytes"] = local_cdl.stat().st_size
        st.ok("cdl-downloaded", {"bytes": st.value["cdl_bytes"]})
    except Exception as exc:  # noqa: BLE001
        st.bad("cdl-download", f"{type(exc).__name__}: {exc}")
    st.value["cdl_remote"] = remote_cdl
    return st


def stage_calibre(t: HttpTransport, cfg) -> Stage:
    st = Stage("calibre", cfg.out)
    cfg.created.append(st)
    gds = f"{FILE_ROOT}/gds/{CTLE}.gds"
    drc_deck = f"{PDK_ROOT}/Calibre/drc/calibre.drc"
    lvs_deck = f"{PDK_ROOT}/Calibre/lvs/calibre.lvs"
    drc = raw_call(t, "calibre.drc", gds=gds, top=CTLE, deck=drc_deck,
                   blocking=True, timeout=1800)
    st.value["drc"] = {"ok": drc.get("ok"), "error": drc.get("error")}
    (st.ok if drc.get("ok") else st.bad)("drc", drc.get("error"))
    if cfg.cdl_remote:
        lvs = raw_call(t, "calibre.lvs", gds=gds, top=CTLE, deck=lvs_deck,
                       cdl=cfg.cdl_remote, blocking=True, timeout=1800)
        st.value["lvs"] = {"ok": lvs.get("ok"), "error": lvs.get("error")}
        (st.ok if lvs.get("ok") else st.bad)("lvs", lvs.get("error"))
    return st


AC_NETLIST = """simulator lang=spectre
global 0
include "{pdk}/models/spectre/cor_25.scs" section=tt_25

parameters rl=500 rdeg=50 cdeg=1p cl=20f

VDD (vdd 0) vsource dc=2.5
VB (vb 0) vsource dc=1.0
VINP (vinp 0) vsource dc=1.25 mag=1
VINN (vinn 0) vsource dc=1.25 mag=1 phase=180

M1 (outn vinp s1 0) nch_25 w=20u l=280n
M2 (outp vinn s2 0) nch_25 w=20u l=280n
M3 (tail vb 0 0) nch_25 w=40u l=280n

R1 (vdd outp) resistor r=rl
R2 (vdd outn) resistor r=rl
RS1 (s1 tail) resistor r=rdeg
RS2 (s2 tail) resistor r=rdeg
CS1 (s1 tail) capacitor c=cdeg
CS2 (s2 tail) capacitor c=cdeg
CL1 (outp 0) capacitor c=cl
CL2 (outn 0) capacitor c=cl

# 分析名必须是 `ac`：解析器只找 `ac.ac`/`*.ac.ac`，叫 `ac1` 就会丢（见第五轮 P-053）
ac ac start=1k stop=20G dec=20
"""

TRAN_NETLIST = """simulator lang=spectre
global 0
include "{pdk}/models/spectre/cor_25.scs" section=tt_25

parameters rl=500 rdeg=50 cdeg=1p cl=20f

VDD (vdd 0) vsource dc=2.5
VB (vb 0) vsource dc=1.0
VINP (vinp 0) vsource type=pulse val0=1.15 val1=1.35 period=2n width=1n rise=20p fall=20p
VINN (vinn 0) vsource type=pulse val0=1.35 val1=1.15 period=2n width=1n rise=20p fall=20p

M1 (outn vinp s1 0) nch_25 w=20u l=280n
M2 (outp vinn s2 0) nch_25 w=20u l=280n
M3 (tail vb 0 0) nch_25 w=40u l=280n

R1 (vdd outp) resistor r=rl
R2 (vdd outn) resistor r=rl
RS1 (s1 tail) resistor r=rdeg
RS2 (s2 tail) resistor r=rdeg
CS1 (s1 tail) capacitor c=cdeg
CS2 (s2 tail) capacitor c=cdeg
CL1 (outp 0) capacitor c=cl
CL2 (outn 0) capacitor c=cl

tran1 tran stop=6n
"""


def stage_sim(t: HttpTransport, cfg) -> Stage:
    """前仿：真实 PDK 模型，AC（增益/峰化/带宽）+ TRAN（摆率），判据是测出来的数。"""
    st = Stage("sim", cfg.out)
    cfg.created.append(st)
    stage_dir = cfg.out / "stage"
    stage_dir.mkdir(parents=True, exist_ok=True)
    ac_file = stage_dir / f"{CTLE}_ac.scs"
    tran_file = stage_dir / f"{CTLE}_tran.scs"
    ac_file.write_text(AC_NETLIST.format(pdk=PDK_ROOT), encoding="utf-8")
    tran_file.write_text(TRAN_NETLIST.format(pdk=PDK_ROOT), encoding="utf-8")
    st.ok("netlists-written", {"ac": str(ac_file), "tran": str(tran_file)})

    for job in (f"{CTLE}_ac", f"{CTLE}_tran"):
        op(t, "basic.command.run", cmd=f"rm -rf {SPECTRE_ROOT}/spectre/{job} && echo ok",
           timeout=120)
    response = raw_call(
        t, "spectre.run",
        tasks=[{"job": f"{CTLE}_ac", "netlist": str(ac_file), "parse": "auto"},
               {"job": f"{CTLE}_tran", "netlist": str(tran_file), "parse": "auto"}],
        max_workers=2, parse="auto", download=True, keep_run_dir=True, timeout=1200)
    data = response.get("data") or {}
    runs = (data.get("value") or {}).get("runs") or []
    st.value["run_ok"] = response.get("ok")
    st.value["run_error"] = response.get("error")
    st.value["runs"] = [
        {"status": ((r.get("value") or {}).get("status")),
         "analyses": ((r.get("value") or {}).get("analyses")),
         "steps": ((r.get("value") or {}).get("steps")),
         "run_dir": ((r.get("value") or {}).get("run_dir"))}
        for r in runs
    ]
    if not (response.get("ok") and len(runs) == 2
            and all((r.get("value") or {}).get("status") == "success" for r in runs)):
        st.bad("spectre-run", json.dumps(st.value["runs"], ensure_ascii=False)[:1200])
        st.error = "spectre run failed"
        return st
    st.ok("spectre-run", st.value["runs"])

    ac_data = (runs[0].get("value") or {}).get("data") or {}
    tran_data = (runs[1].get("value") or {}).get("data") or {}
    st.value["ac_signals"] = sorted(ac_data)
    st.value["tran_signals"] = sorted(tran_data)

    metrics = op(t, "spectre.measure", data=ac_data, metrics=[
        # 解析出来的 AC 数据一律带 `ac_` 前缀（freq→ac_freq、outp→ac_outp），
        # 而 measure 的默认 x 是 `freq`（spec 7-spectre §measure）→ 必须显式给 x。
        {"type": "ac_magnitude", "signal": "ac_outp", "x": "ac_freq",
         "frequency": 1e6, "scale": "db"},
        {"type": "ac_magnitude", "signal": "ac_outp", "x": "ac_freq",
         "frequency": 2.5e9, "scale": "db"},
        {"type": "bandwidth", "signal": "ac_outp", "x": "ac_freq",
         "reference": "dc", "drop_db": 3.0},
    ], timeout=300)
    measured = (metrics.get("value") or {}).get("metrics") or []
    st.value["ac_metrics"] = measured
    ok_all = len(measured) == 3 and all(m.get("ok") for m in measured)
    (st.ok if ok_all else st.bad)("ac-metrics-computed", measured)
    if ok_all:
        gain_db = measured[0]["value"]
        peak_db = measured[1]["value"]
        bw = measured[2]["value"]
        st.value["gain_db_1mhz"] = round(gain_db, 3)
        st.value["peak_db_2p5ghz"] = round(peak_db, 3)
        st.value["bw_3db_hz"] = bw
        st.value["peaking_db"] = round(peak_db - gain_db, 3)
        checks = {
            "gain_plausible(0<g<40dB)": 0.0 < gain_db < 40.0,
            "peaking>=gain-1dB": peak_db >= gain_db - 1.0,
            "bw>100MHz": bw > 1.0e8,
        }
        st.value["ac_checks"] = checks
        (st.ok if all(checks.values()) else st.bad)("ac-checks", checks)

    tran_metrics = op(t, "spectre.measure", data=tran_data, metrics=[
        {"type": "min", "signal": "outp"},
        {"type": "max", "signal": "outp"},
        {"type": "rms", "signal": "outp"},
    ], timeout=300)
    tmeasured = (tran_metrics.get("value") or {}).get("metrics") or []
    st.value["tran_metrics"] = tmeasured
    (st.ok if tmeasured and tmeasured[0].get("ok") and tmeasured[1].get("ok")
     else st.bad)("tran-metrics", tmeasured)
    if len(tmeasured) >= 2 and tmeasured[0].get("ok") and tmeasured[1].get("ok"):
        swing = tmeasured[1]["value"] - tmeasured[0]["value"]
        st.value["out_swing_v"] = round(swing, 4)
        (st.ok if swing > 0.05 else st.bad)("tran-swing>50mV", swing)
    return st


STAGES = {
    "probe": stage_probe,
    "lib": stage_lib,
    "buf": stage_buf,
    "ctle": stage_ctle,
    "term": stage_term,
    "top": stage_top,
    "layout": stage_layout,
    "gds": stage_gds,
    "cdl": stage_cdl,
    "sim": stage_sim,
    "calibre": stage_calibre,
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", default="all", help="|".join(STAGES) + "|all")
    ap.add_argument("--token", default=PDK_TOKEN)
    ap.add_argument("--with-calibre", action="store_true",
                    help="追加 calibre.drc/lvs（慢，需 calibre 环境）")
    ap.add_argument("--skip", default="",
                    help="逗号分隔的 stage 名，跳过（例如 --skip cdl）")
    ap.add_argument("--out", type=Path, default=WORK_DIR)
    args = ap.parse_args(argv)

    transport = HttpTransport(args.token)
    require_environment(base=API, token=args.token, require_lib=[PDK_LIB])
    args.created = []
    args.cdl_remote = None
    args.out = args.out

    skip = {item.strip() for item in args.skip.split(",") if item.strip()}
    names = list(STAGES) if args.stage == "all" else [args.stage]
    names = [n for n in names if n not in skip]
    if args.stage == "all" and not args.with_calibre:
        names = [n for n in names if n != "calibre"]
    failed = False
    results = []
    for name in names:
        try:
            st = STAGES[name](transport, args)
            st.ok("stage-done")
        except Exception as exc:  # noqa: BLE001 - 记录失败点，不掩盖
            st = args.created[-1] if args.created else Stage(name, args.out)
            st.error = f"{type(exc).__name__}: {exc}"
            failed = True
        if st.name == "cdl":
            args.cdl_remote = st.value.get("cdl_remote")
        path = st.save()
        results.append(st.to_json())
        print(json.dumps({k: v for k, v in st.to_json().items() if k != "steps"},
                         ensure_ascii=False))
        print(f"  evidence: {path}")
        if failed:
            break

    summary = args.out / "summary.json"
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"summary: {summary}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
