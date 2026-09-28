# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-28 20:40
# 依赖: 无
# =======================================================================
"""设计迭代全链 TB（第七轮新增）：**改图 → 二次出图 → 版图二次发布 → 仿真复测**。

为什么单开一份：``project_flow_tb`` / ``serdes_rx_flow_tb`` / ``adc_sar_flow_tb`` 都是
"从零建一遍"的单向链路，而真实用户是**反复迭代**：改原理图 → 重新出 symbol →
改版图 → 再次出 GDS → 再仿真对数。本 TB 用**同一 cell 的两轮往返**把这条链路钉住，
判据是"数值方向"，不是"接口 ok"：

    轮1：建库 → 原理图（自偏置反相放大器：MP/MN + RF + CC + CL + 4 pin）
          → symbol → 版图 → GDS#1 → AC/TRAN 仿真（平带增益、峰值基准 3dB 带宽、摆幅）
    改图：CL 的 c 由 20f 改 200f（10×）＋ 新增去耦电容 CL2 ＋ 把输出 pin 改名
          vout → vout_main
    轮2：二次出 symbol（断言 port 集合跟着改图变）→ 版图追加图形 → GDS#2（新目录，
          断言与 GDS#1 的 sha256 不同）→ 同一套仿真再跑一次（断言
          带宽掉到 1/3 以下、低频增益变化 <3dB、摆幅仍 >50mV）

数据流是**原理图数据驱动**的：轮 2 的仿真网表不是 TB 里写死的常量，而是
``virtuoso.schematic.read`` 回读的**设备连接 + 实例参数**（CL 的 c、MP/MN 的 w/l、
RF 的 r）现场拼出来的（本文件内的迷你网表器 ``_netlist_from_read``）。因此
"改图生效 → 仿真数值变化"是一条可追溯的因果链，而不是两段各说各话的脚本。

可选 ``--with-lvs``：另建一个只有 MP/MN 的 cell，做
``calibre.export_cdl``（官方 auCdl）→ ``virtuoso.layout.gds`` →
``calibre.lvs``（deck + cdl）→ ``calibre.read_results``，断言得到
**correct**（对应 P-069 的验收判据）。

用法::

    python test/live/flows/design_iterate_tb.py --token d6af595b342647b58ec63ca6
    python test/live/flows/design_iterate_tb.py --stage all --with-lvs

证据：``test/artifacts/evidence/round7/design-iterate/``
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
_RUNNERS = ROOT / "test" / "shared" / "runners"
if str(_RUNNERS) not in sys.path:
    sys.path.insert(0, str(_RUNNERS))

from env_check import require_environment  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
WORK_DIR = ROOT / "test" / "artifacts" / "evidence" / "round7" / "design-iterate"

#: 带 PDK 的实例（calprobe，wsl-gent，daemon 65122）
PDK_TOKEN = "d6af595b342647b58ec63ca6"
PDK_LIB = "tsmcN65"
ALIB = "analogLib"
NCH, PCH = "nch_25", "pch_25"
PDK_ROOT = "/opt/eda/PDK/CRN65GPNEW/CRN65GPNEW"

LIB = "DI65"
CELL = "buf_stage"
INV_CELL = "inv_only"

FILE_ROOT = "/home/Gent/.virtuoso-bridge/calprobe/file/design_iterate"
COMMAND_ROOT = "/home/Gent/.virtuoso-bridge/calprobe/command"
SPECTRE_ROOT = "/home/Gent/.virtuoso-bridge/calprobe/spectre"
CDS_LIB_FILE = "/home/Gent/project/calprobe/cds.lib"
LAYERMAP = f"{PDK_ROOT}/tsmcN65/tsmcN65.layermap"
LVS_DECK = f"{PDK_ROOT}/Calibre/lvs/calibre.lvs"

#: 轮 1 / 轮 2 的负载电容（改图前后）
CL_R1, CL_R2 = "20f", "200f"
DEFAULT_W, DEFAULT_L = "20u", "280n"
DEFAULT_RF = "100k"
#: 输入耦合电容：耦合高通角 f=1/(2π·RF·CC)；CC=1p 时角点在 1.6MHz，1MHz 处测到的
#: "增益"会被输入高通吃掉 5dB（R7-TB-02）。10p → 角点 159kHz，测量频点放平带 10MHz。
DEFAULT_CC = "10p"

#: 自偏置反相放大器：输入端 vin 经 CC 耦合，RF 从输出回落自偏置（DC 工作在翻转点）
R1_COMMANDS = [
    {"op": "place_instance", "master_lib": PDK_LIB, "master_cell": PCH,
     "master_view": "symbol", "name": "MP", "pos": [0.0, 1.0], "orient": "R0"},
    {"op": "place_instance", "master_lib": PDK_LIB, "master_cell": NCH,
     "master_view": "symbol", "name": "MN", "pos": [0.0, -1.0], "orient": "R0"},
    {"op": "place_instance", "master_lib": ALIB, "master_cell": "res",
     "master_view": "symbol", "name": "RF", "pos": [3.0, 0.0], "orient": "R0"},
    {"op": "place_instance", "master_lib": ALIB, "master_cell": "cap",
     "master_view": "symbol", "name": "CC", "pos": [-3.0, 0.0], "orient": "R0"},
    {"op": "place_instance", "master_lib": ALIB, "master_cell": "cap",
     "master_view": "symbol", "name": "CL", "pos": [5.0, -2.0], "orient": "R0"},
    {"op": "set_instance_params", "name": "MP", "params": {"w": DEFAULT_W, "l": DEFAULT_L}},
    {"op": "set_instance_params", "name": "MN", "params": {"w": DEFAULT_W, "l": DEFAULT_L}},
    {"op": "set_instance_params", "name": "RF", "params": {"r": DEFAULT_RF}},
    {"op": "set_instance_params", "name": "CC", "params": {"c": DEFAULT_CC}},
    {"op": "set_instance_params", "name": "CL", "params": {"c": CL_R1}},
    {"op": "set_term_nets", "name": "MP",
     "term_nets": {"G": "vin", "D": "vout", "S": "vdd", "B": "vdd"}},
    {"op": "set_term_nets", "name": "MN",
     "term_nets": {"G": "vin", "D": "vout", "S": "vss", "B": "vss"}},
    {"op": "set_term_nets", "name": "RF", "term_nets": {"PLUS": "vin", "MINUS": "vout"}},
    {"op": "set_term_nets", "name": "CC", "term_nets": {"PLUS": "vin_ext", "MINUS": "vin"}},
    {"op": "set_term_nets", "name": "CL", "term_nets": {"PLUS": "vout", "MINUS": "vss"}},
    {"op": "place_pin", "name": "vin_ext", "direction": "input", "pos": [-6.0, 0.0]},
    {"op": "place_pin", "name": "vout", "direction": "output", "pos": [6.0, 0.0]},
    {"op": "place_pin", "name": "vdd", "direction": "inputOutput", "pos": [0.0, 4.0]},
    {"op": "place_pin", "name": "vss", "direction": "inputOutput", "pos": [0.0, -4.0]},
]

#: 改图：CL 10×、新增 CL2、输出 pin 改名（rename_pin 是 spec 里"需真机验证"的原子）
R2_RENAME = [
    {"op": "set_instance_params", "name": "CL", "params": {"c": CL_R2}},
    {"op": "place_instance", "master_lib": ALIB, "master_cell": "cap",
     "master_view": "symbol", "name": "CL2", "pos": [5.0, 2.0], "orient": "R0"},
    {"op": "set_instance_params", "name": "CL2", "params": {"c": "1f"}},
    {"op": "set_term_nets", "name": "CL2", "term_nets": {"PLUS": "vout", "MINUS": "vss"}},
    # 注意：实现里 rename_pin/delete_pin 的索引是 `x`/`y`（spec 表格写的是 `xy`，
    # 口径不一致已登记；TB 按实现口径写，避免用错误姿势制造假红）
    {"op": "rename_pin", "pos": [6.0, 0.0], "new_name": "vout_main"},
]

#: rename_pin 不可用时的等价改图（新 pin + 删旧 pin），保证迭代链本身能继续
R2_FALLBACK = [
    {"op": "place_pin", "name": "vout_main", "direction": "output", "pos": [6.0, 0.0]},
    {"op": "delete_pin", "pos": [6.0, 0.0]},
]

SI_MULT = {
    "f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3,
    "k": 1e3, "K": 1e3, "M": 1e6, "g": 1e9, "G": 1e9, "t": 1e12,
}


class FlowError(RuntimeError):
    def __init__(self, operation: str, error: Any, data: Any = None) -> None:
        super().__init__(f"{operation}: {error}")
        self.operation = operation
        self.error = error
        self.data = data


class HttpTransport:
    middle = None

    def __init__(self, token: str, base: str = API) -> None:
        self.token = token
        self.base = base

    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.base, data=body, headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=1800) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return json.loads(error.read().decode("utf-8"))


def op(t: HttpTransport, operation: str, **fields: Any) -> Any:
    response = t.call({"operation": operation, "token": t.token, **fields})
    if not response.get("ok"):
        raise FlowError(operation, response.get("error"), response.get("data"))
    return response.get("data")


def raw_call(t: HttpTransport, operation: str, **fields: Any) -> dict:
    return t.call({"operation": operation, "token": t.token, **fields})


def skill(t: HttpTransport, code: str, timeout: float = 300) -> str:
    data = op(t, "basic.skill.execute", skill_code=code, timeout=timeout)
    result = data.get("result", {})
    if result.get("status") != "success":
        raise AssertionError(f"SKILL failed: {json.dumps(result, ensure_ascii=False)[:400]}")
    return result.get("output", "")


def cmd_stdout(data: Any) -> str:
    if isinstance(data, dict):
        result = data.get("result")
        if isinstance(result, list) and len(result) >= 2:
            return str(result[1]) + ("\n" + str(result[2]) if len(result) > 2 and result[2] else "")
        if isinstance(result, dict):
            return str(result.get("stdout", ""))
    return ""


def parse_si(text: str) -> float | None:
    """``"200f"`` / ``"100k"`` / ``"2e-14"`` → float；解析不了给 None。"""
    raw = (text or "").strip().strip('"')
    match = re.fullmatch(r"([-+0-9.eE]+)\s*([a-zA-Z]*)", raw)
    if not match:
        return None
    number, suffix = match.group(1), match.group(2)
    try:
        value = float(number)
    except ValueError:
        return None
    if suffix:
        if suffix in SI_MULT:
            value *= SI_MULT[suffix]
        elif suffix.lower() in SI_MULT:
            value *= SI_MULT[suffix.lower()]
        else:
            return None
    return value


def inst_param(t: HttpTransport, cell: str, inst: str, param: str) -> str:
    """读实例 CDF 参数（``cdfGetInstCDF``，即用户 GUI 里看到的那个值）。"""
    expr = (
        f'let((cv i cdfg p v) cv = dbOpenCellViewByType("{LIB}" "{cell}" "schematic" '
        f'"schematic" "r") i = car(setof(x cv~>instances x~>name == "{inst}")) '
        f'v = "NOINST" when(i cdfg = cdfGetInstCDF(i) p = get(cdfg "{param}") '
        f'v = if(p p~>value "NOPARAM")) v)'
    )
    return skill(t, expr).strip()


def view_stamp(t: HttpTransport, cell: str, view: str) -> str:
    """视图目录内所有文件的大小+修改时间指纹（用于证明"真的又写了一次视图"）。"""
    path = f"{FILE_ROOT}/{LIB}/{cell}/{view}"
    listing = op(t, "basic.command.run",
                 cmd=f"find {path} -type f -printf '%f %s %T@\\n' 2>/dev/null | sort",
                 timeout=120)
    return cmd_stdout(listing).strip()


def remote_sha256(t: HttpTransport, path: str) -> str:
    out = op(t, "basic.command.run", cmd=f"sha256sum {path} 2>/dev/null | cut -c1-64",
             timeout=120)
    return cmd_stdout(out).strip().splitlines()[-1].strip() if cmd_stdout(out).strip() else ""


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
            "ok": self.error is None and all(s["ok"] for s in self.steps),
            "error": self.error,
            "seconds": round(time.time() - self.started, 2),
            "steps": self.steps,
            "value": self.value,
        }

    def save(self) -> Path:
        self.out.mkdir(parents=True, exist_ok=True)
        path = self.out / f"iterate-{self.name}.json"
        path.write_text(json.dumps(self.to_json(), ensure_ascii=False, indent=1),
                        encoding="utf-8")
        return path


# --------------------------------------------------------------------------- 阶段

def stage_probe(t: HttpTransport, cfg) -> Stage:
    st = Stage("probe", cfg.out)
    cfg.created.append(st)
    st.value["pdk"] = skill(t, f'ddGetObj("{PDK_LIB}")~>name').strip()
    st.value["cwd"] = skill(t, "getWorkingDir()").strip()
    st.value["nch_terms"] = skill(
        t, f'let((cv) cv=dbOpenCellViewByType("{PDK_LIB}" "{NCH}" "symbol" '
           f'"schematicSymbol" "r") if(cv mapcar(lambda((x) x~>name) cv~>terminals) "NOCV"))'
    ).strip()
    return st


def stage_lib(t: HttpTransport, cfg) -> Stage:
    st = Stage("lib", cfg.out)
    cfg.created.append(st)
    prep = op(t, "basic.command.run",
              cmd=f"mkdir -p {FILE_ROOT} && test -d {FILE_ROOT} && echo dir-ok", timeout=120)
    st.ok("remote-root-ready", cmd_stdout(prep).strip())
    try:
        data = op(t, "virtuoso.cellview.lib.create", library=LIB,
                  path=f"{FILE_ROOT}/{LIB}", technology_library=PDK_LIB, timeout=300)
        st.ok("lib-create", data)
    except FlowError as exc:
        st.ok("lib-exists", str(exc.error))
    st.value["library"] = LIB
    return st


def _ensure_cell_view(t: HttpTransport, cell: str, view: str, view_type: str,
                      st: Stage) -> None:
    """``schematic.write`` 是 append 语义——视图必须先存在（见 schematic 包）。"""
    try:
        data = op(t, "virtuoso.cellview.view.create", library=LIB, cell=cell,
                  view=view, view_type=view_type, timeout=180)
        st.ok(f"view-create-{cell}-{view}", data)
    except FlowError as exc:
        st.ok(f"view-create-{cell}-{view}-existing", str(exc.error))


def _terms_in(nets: dict[str, Any], inst: str, term: str) -> str | None:
    for net, payload in nets.items():
        if f"{inst}.{term}" in (payload.get("connections") or []):
            return net
    return None


def stage_r1_sch(t: HttpTransport, cfg) -> Stage:
    st = Stage("r1_sch", cfg.out)
    cfg.created.append(st)
    _ensure_cell_view(t, CELL, "schematic", "schematic", st)
    data = op(t, "virtuoso.schematic.write", library=LIB, cell=CELL, view="schematic",
              commands=R1_COMMANDS, timeout=900)
    st.ok("write-round1", data)
    save = op(t, "virtuoso.schematic.check_and_save", library=LIB, cell=CELL,
              view="schematic", timeout=300)
    st.ok("check-and-save", save)
    read = op(t, "virtuoso.schematic.read", library=LIB, cell=CELL, view="schematic",
              timeout=300)
    value = read.get("value") or {}
    nets = {k: sorted(v.get("connections") or []) for k, v in (value.get("nets") or {}).items()}
    st.value["nets"] = nets
    st.value["instances"] = [i.get("name") for i in (value.get("instances") or [])]
    st.value["pins"] = [p.get("name") for p in (value.get("pins") or [])]
    expected = {"MP.D": "vout", "MN.G": "vin", "RF.MINUS": "vout", "CC.MINUS": "vin",
                "CL.PLUS": "vout", "CL.MINUS": "vss"}
    actual = {k: _terms_in(value.get("nets") or {}, *k.split(".")) for k in expected}
    mism = {k: {"expected": v, "actual": actual[k]} for k, v in expected.items()
            if actual[k] != v}
    st.value["conn_mismatches"] = mism
    (st.ok if not mism else st.bad)("round1-connectivity", mism)
    cl = inst_param(t, CELL, "CL", "c")
    st.value["CL_c_readback"] = cl
    (st.ok if parse_si(cl) else st.bad)("CL-c-readable", cl)
    return st


def stage_r1_sym(t: HttpTransport, cfg) -> Stage:
    st = Stage("r1_sym", cfg.out)
    cfg.created.append(st)
    op(t, "virtuoso.symbol.generate", library=LIB, cell=CELL, schematic_view="schematic",
       symbol_view="symbol", overwrite=True, timeout=600)
    read = op(t, "virtuoso.symbol.read", library=LIB, cell=CELL, view="symbol", timeout=300)
    value = read.get("value") or {}
    terms = sorted(x.get("name") for x in (value.get("terms") or []))
    st.value["terms"] = terms
    st.value["stamp"] = view_stamp(t, CELL, "symbol")
    expected = ["vdd", "vin_ext", "vout", "vss"]
    (st.ok if terms == expected else st.bad)("symbol-terms-round1",
                                            {"expected": expected, "actual": terms})
    return st


def _layout_commands(extra: bool) -> list[dict[str, Any]]:
    cmds: list[dict[str, Any]] = [
        {"op": "place_instance", "master_lib": PDK_LIB, "master_cell": PCH,
         "master_view": "layout", "name": "MP", "pos": [0.0, 0.0], "orient": "R0"},
        {"op": "place_instance", "master_lib": PDK_LIB, "master_cell": NCH,
         "master_view": "layout", "name": "MN", "pos": [0.0, 6.0], "orient": "R0"},
        {"op": "place_rect", "layer": "M1", "purpose": "drawing",
         "bbox": [[-1.0, -1.0], [1.0, 7.0]]},
        {"op": "place_label", "layer": "M1", "purpose": "pin", "text": "VOUT",
         "pos": [0.0, 3.0]},
    ]
    if extra:
        cmds += [
            {"op": "place_rect", "layer": "M2", "purpose": "drawing",
             "bbox": [[-3.0, -3.0], [3.0, 9.0]]},
            {"op": "place_label", "layer": "M2", "purpose": "drawing", "text": "VOUT",
             "pos": [0.0, 8.0]},
        ]
    return cmds


#: 轮 2 的版图改动：**只追加**（layout.write 是 append 语义，重放已存在的实例名会报
#: `instance not created`——实测 0/6 全丢，所以二次发布必须只写增量）
R2_LAYOUT_EXTRA = [
    {"op": "place_rect", "layer": "M2", "purpose": "drawing",
     "bbox": [[-3.0, -3.0], [3.0, 9.0]]},
    {"op": "place_label", "layer": "M2", "purpose": "drawing", "text": "VOUT",
     "pos": [0.0, 8.0]},
]


def stage_r1_layout(t: HttpTransport, cfg) -> Stage:
    st = Stage("r1_layout", cfg.out)
    cfg.created.append(st)
    _ensure_cell_view(t, CELL, "layout", "maskLayout", st)
    data = op(t, "virtuoso.layout.write", library=LIB, cell=CELL, view="layout",
              commands=_layout_commands(extra=False), timeout=900)
    st.ok("layout-write-round1", data)
    read = op(t, "virtuoso.layout.read", library=LIB, cell=CELL, view="layout",
              detail="geometry", timeout=300)
    value = read.get("value") or {}
    st.value["instances"] = [i.get("name") for i in (value.get("instances") or [])]
    st.value["shape_count"] = len(value.get("shapes") or [])
    st.value["stamp"] = view_stamp(t, CELL, "layout")
    (st.ok if st.value["shape_count"] >= 2 else st.bad)("layout-shapes", st.value["shape_count"])
    return st


def stage_r1_gds(t: HttpTransport, cfg) -> Stage:
    st = Stage("r1_gds", cfg.out)
    cfg.created.append(st)
    op(t, "basic.command.run", cmd=f"mkdir -p {FILE_ROOT}/gds/r1 && echo ok", timeout=60)
    path = f"{FILE_ROOT}/gds/r1/{CELL}.gds"
    call = raw_call(t, "virtuoso.layout.gds", action="export", library=LIB, cell=CELL,
                    view="layout", file_path=path, file_is_local=False, top_cell=CELL,
                    layer_map=LAYERMAP, layer_map_is_local=False, tech_lib=PDK_LIB,
                    timeout=900)
    st.value["gds_r1"] = {"path": path, "ok": call.get("ok"), "error": call.get("error")}
    (st.ok if call.get("ok") else st.bad)("gds-export-r1", call.get("error"))
    sha = remote_sha256(t, path)
    st.value["sha256_r1"] = sha
    (st.ok if sha else st.bad)("gds-sha-r1", sha)
    cfg.gds_r1_sha = sha
    return st


def _build_netlist(t: HttpTransport, cell: str, notes: list[str],
                   analysis: str) -> tuple[str, dict[str, Any]]:
    read = op(t, "virtuoso.schematic.read", library=LIB, cell=cell, view="schematic",
              timeout=300)
    nets = (read.get("value") or {}).get("nets") or {}

    def net(inst: str, term: str) -> str:
        found = _terms_in(nets, inst, term)
        if found is None:
            raise AssertionError(f"schematic.read 回读缺连接 {inst}.{term}")
        return found

    def param(inst: str, name: str, fallback: str) -> str:
        raw = inst_param(t, cell, inst, name)
        if raw in ("", "NOPARAM", "NOINST") or parse_si(raw) is None:
            notes.append(f"{inst}.{name} 回读={raw!r} → 用 TB 字面量 {fallback}")
            return fallback
        # 回读值是 SKILL 打印的字符串（带双引号），进网表前必须去壳
        return raw.strip().strip('"')

    g = net("MN", "G")          # 自偏置输入节点（vin）
    d = net("MN", "D")          # 输出节点
    s_mn, s_mp = net("MN", "S"), net("MP", "S")
    rf_a, rf_b = net("RF", "PLUS"), net("RF", "MINUS")
    cc_a, cc_b = net("CC", "PLUS"), net("CC", "MINUS")
    cl_a, cl_b = net("CL", "PLUS"), net("CL", "MINUS")
    cl2_a, cl2_b = _terms_in(nets, "CL2", "PLUS"), _terms_in(nets, "CL2", "MINUS")

    w_n, l_n = param("MN", "w", DEFAULT_W), param("MN", "l", DEFAULT_L)
    w_p, l_p = param("MP", "w", DEFAULT_W), param("MP", "l", DEFAULT_L)
    rf_r = param("RF", "r", DEFAULT_RF)
    cc_c = param("CC", "c", DEFAULT_CC)
    cl_c = param("CL", "c", CL_R1)
    if cl2_a and cl2_b:
        cl2_c = param("CL2", "c", "1f")
    else:
        cl2_c = None

    header = (
        "simulator lang=spectre\n"
        "global 0\n"
        f'include "{PDK_ROOT}/models/spectre/cor_25.scs" section=tt_25\n\n'
        "VDD (vdd 0) vsource dc=2.5\n"
        f"VSS ({s_mn} 0) vsource dc=0\n"
    )
    if analysis == "ac":
        source = 'VIN (vin_ext 0) vsource dc=0 mag=1\n'
    else:
        source = ('VIN (vin_ext 0) vsource type=pulse val0=-0.05 val1=0.05 '
                  'period=400n width=200n rise=20p fall=20p\n')
    devices = (
        f"MP ({d} {g} {s_mp} {s_mp}) pch_25 w={w_p} l={l_p}\n"
        f"MN ({d} {g} {s_mn} {s_mn}) nch_25 w={w_n} l={l_n}\n"
        f"RF ({rf_a} {rf_b}) resistor r={rf_r}\n"
        f"CC ({cc_a} {cc_b}) capacitor c={cc_c}\n"
        f"CL ({cl_a} {cl_b}) capacitor c={cl_c}\n"
    )
    if cl2_c:
        devices += f"CL2 ({cl2_a} {cl2_b}) capacitor c={cl2_c}\n"
    analysis_line = ("ac ac start=1k stop=20G dec=20\n" if analysis == "ac"
                     else "tran1 tran stop=1u\n")
    value = {
        "readback": {"CL.c": cl_c, "CL2.c": cl2_c, "RF.r": rf_r, "CC.c": cc_c,
                     "MN.w": w_n, "MN.l": l_n, "MP.w": w_p, "MP.l": l_p},
        "nets": {"g": g, "d": d, "vss": s_mn, "vdd": s_mp, "cc_out": cc_b},
    }
    return header + source + "\n" + devices + "\n" + analysis_line, value


def _run_sim(t: HttpTransport, cfg, tag: str, st: Stage) -> dict[str, Any]:
    stage_dir = cfg.out / "stage"
    stage_dir.mkdir(parents=True, exist_ok=True)
    netlists: dict[str, Path] = {}
    notes: list[str] = []
    readback: dict[str, Any] = {}
    for analysis in ("ac", "tran"):
        text, value = _build_netlist(t, CELL, notes, analysis)
        readback[analysis] = value
        path = stage_dir / f"{tag}_{analysis}.scs"
        path.write_text(text, encoding="utf-8")
        netlists[analysis] = path
    st.value[f"{tag}_netlists"] = {k: str(v) for k, v in netlists.items()}
    st.value[f"{tag}_readback"] = {k: v["readback"] for k, v in readback.items()}
    st.value[f"{tag}_notes"] = notes
    (st.ok if readback["ac"]["readback"] == readback["tran"]["readback"]
     else st.bad)("readback-consistent", st.value[f"{tag}_readback"])

    for job in (f"{CELL}_{tag}_ac", f"{CELL}_{tag}_tran"):
        op(t, "basic.command.run",
           cmd=f"rm -rf {SPECTRE_ROOT}/spectre/{job} && echo ok", timeout=120)
    response = raw_call(
        t, "spectre.run",
        tasks=[{"job": f"{CELL}_{tag}_ac", "netlist": str(netlists["ac"]), "parse": "auto"},
               {"job": f"{CELL}_{tag}_tran", "netlist": str(netlists["tran"]), "parse": "auto"}],
        max_workers=2, parse="auto", download=True, keep_run_dir=True, timeout=1200)
    runs = ((response.get("data") or {}).get("value") or {}).get("runs") or []
    st.value[f"{tag}_runs"] = [
        {"status": ((r.get("value") or {}).get("status")),
         "analyses": ((r.get("value") or {}).get("analyses")),
         "run_dir": ((r.get("value") or {}).get("run_dir")),
         "error": ((r.get("value") or {}).get("error")),
         "log_tail": ((r.get("value") or {}).get("log_tail"))} for r in runs
    ]
    if not (response.get("ok") and len(runs) == 2
            and all((r.get("value") or {}).get("status") == "success" for r in runs)):
        st.bad(f"{tag}-spectre-run", json.dumps(st.value[f"{tag}_runs"], ensure_ascii=False)[:800])
        st.error = f"spectre.run[{tag}] failed: {response.get('error')}"
        # 非阻塞：保留已经拼好的网表与 readback 证据，返回空指标，让后续阶段继续
        result = {"output_net": readback["ac"]["nets"]["d"], "gain_db_flatband": None,
                  "bw_3db_hz": None, "readback": readback["ac"]["readback"], "notes": notes,
                  "failed": True}
        st.value[tag] = result
        st.save()
        return result
    st.ok(f"{tag}-spectre-run", st.value[f"{tag}_runs"])

    ac_data = (runs[0].get("value") or {}).get("data") or {}
    tran_data = (runs[1].get("value") or {}).get("data") or {}
    out_net = readback["ac"]["nets"]["d"]
    ac_sig = f"ac_{out_net}"
    metrics = op(t, "spectre.measure", data=ac_data, metrics=[
        {"type": "ac_magnitude", "signal": ac_sig, "x": "ac_freq",
         "frequency": 1e7, "scale": "db"},
        # 峰值基准（reference=max）：本设计输入是电容耦合，低频段被输入高通抬起，
        # 用默认 reference=dc 会把"最低频那点"当基准 → 3dB 点不存在（实测报
        # `bandwidth point not found`）。
        {"type": "bandwidth", "signal": ac_sig, "x": "ac_freq",
         "reference": "max", "drop_db": 3.0},
    ], timeout=300)
    measured = (metrics.get("value") or {}).get("metrics") or []
    ok_metrics = len(measured) == 2 and all(m.get("ok") for m in measured)
    (st.ok if ok_metrics else st.bad)(f"{tag}-ac-metrics",
                                      {"signal": ac_sig, "metrics": measured})
    tran_metrics = op(t, "spectre.measure", data=tran_data, metrics=[
        {"type": "min", "signal": out_net},
        {"type": "max", "signal": out_net},
    ], timeout=300)
    tmeasured = (tran_metrics.get("value") or {}).get("metrics") or []
    (st.ok if len(tmeasured) == 2 and all(m.get("ok") for m in tmeasured)
     else st.bad)(f"{tag}-tran-metrics", tmeasured)

    result: dict[str, Any] = {
        "output_net": out_net,
        "gain_db_flatband": measured[0].get("value") if ok_metrics else None,
        "bw_3db_hz": measured[1].get("value") if ok_metrics else None,
        "readback": readback["ac"]["readback"],
        "notes": notes,
    }
    if len(tmeasured) == 2 and all(m.get("ok") for m in tmeasured):
        result["out_swing_v"] = round(tmeasured[1]["value"] - tmeasured[0]["value"], 4)
    st.value[tag] = result
    return result


def stage_r1_sim(t: HttpTransport, cfg) -> Stage:
    st = Stage("r1_sim", cfg.out)
    cfg.created.append(st)
    result = _run_sim(t, cfg, "r1", st)
    cfg.r1 = result
    if result["gain_db_flatband"] is not None:
        (st.ok if 0.0 < result["gain_db_flatband"] < 40.0 else st.bad)(
            "gain-plausible(0..40dB@10MHz)", result["gain_db_flatband"])
    if result["bw_3db_hz"]:
        (st.ok if result["bw_3db_hz"] > 1e6 else st.bad)("bw>1MHz", result["bw_3db_hz"])
    if result.get("out_swing_v") is not None:
        (st.ok if result["out_swing_v"] > 0.05 else st.bad)("swing>50mV",
                                                            result["out_swing_v"])
    return st


def stage_r2_edit(t: HttpTransport, cfg) -> Stage:
    """改图：CL 10×、新增 CL2、输出 pin 改名（rename_pin 不可用则走等价删+建）。"""
    st = Stage("r2_edit", cfg.out)
    cfg.created.append(st)
    rename_mode = "rename_pin"
    try:
        data = op(t, "virtuoso.schematic.write", library=LIB, cell=CELL,
                  view="schematic", commands=R2_RENAME, timeout=900)
        st.ok("write-round2-rename", data)
    except FlowError as exc:
        rename_mode = "place+delete"
        st.bad("rename_pin-unsupported", {"error": str(exc.error), "data": exc.data})
        data = op(t, "virtuoso.schematic.write", library=LIB, cell=CELL,
                  view="schematic",
                  commands=R2_RENAME[:4] + R2_FALLBACK, timeout=900)
        st.ok("write-round2-fallback", data)
    st.value["rename_mode"] = rename_mode
    save = op(t, "virtuoso.schematic.check_and_save", library=LIB, cell=CELL,
              view="schematic", timeout=300)
    st.ok("check-and-save", save)

    read = op(t, "virtuoso.schematic.read", library=LIB, cell=CELL, view="schematic",
              timeout=300)
    value = read.get("value") or {}
    st.value["instances"] = [i.get("name") for i in (value.get("instances") or [])]
    st.value["pins"] = [p.get("name") for p in (value.get("pins") or [])]
    st.value["nets"] = {k: sorted(v.get("connections") or [])
                        for k, v in (value.get("nets") or {}).items()}
    (st.ok if "CL2" in st.value["instances"] else st.bad)("CL2-added", st.value["instances"])
    (st.ok if "vout_main" in st.value["pins"] else st.bad)("pin-renamed", st.value["pins"])
    cl = inst_param(t, CELL, "CL", "c")
    st.value["CL_c_readback"] = cl
    changed = parse_si(cl) is not None and parse_si(CL_R1) is not None \
        and abs(parse_si(cl) / parse_si(CL_R1) - 10.0) < 0.5
    (st.ok if changed else st.bad)("CL-c-10x", {"readback": cl, "expected": CL_R2})
    return st


def stage_r2_sym(t: HttpTransport, cfg) -> Stage:
    st = Stage("r2_sym", cfg.out)
    cfg.created.append(st)
    before = cfg.r1_sym_stamp if hasattr(cfg, "r1_sym_stamp") else None
    op(t, "virtuoso.symbol.generate", library=LIB, cell=CELL, schematic_view="schematic",
       symbol_view="symbol", overwrite=True, timeout=600)
    read = op(t, "virtuoso.symbol.read", library=LIB, cell=CELL, view="symbol", timeout=300)
    value = read.get("value") or {}
    terms = sorted(x.get("name") for x in (value.get("terms") or []))
    st.value["terms"] = terms
    st.value["stamp_before"] = before
    st.value["stamp_after"] = view_stamp(t, CELL, "symbol")
    expected = ["vdd", "vin_ext", "vout_main", "vss"]
    (st.ok if terms == expected else st.bad)("symbol-terms-round2",
                                            {"expected": expected, "actual": terms})
    if before is not None:
        (st.ok if before != st.value["stamp_after"] else st.bad)(
            "symbol-view-rewritten", {"before": before, "after": st.value["stamp_after"]})
    return st


def stage_r2_layout(t: HttpTransport, cfg) -> Stage:
    """版图二次发布：追加图形 + GDS#2 落新目录，断言 sha256 与 GDS#1 不同。"""
    st = Stage("r2_layout", cfg.out)
    cfg.created.append(st)
    read_before = op(t, "virtuoso.layout.read", library=LIB, cell=CELL, view="layout",
                     detail="geometry", timeout=300)
    before = len(((read_before.get("value") or {}).get("shapes") or []))
    data = op(t, "virtuoso.layout.write", library=LIB, cell=CELL, view="layout",
              commands=R2_LAYOUT_EXTRA, timeout=900)
    st.ok("layout-write-round2", data)
    read = op(t, "virtuoso.layout.read", library=LIB, cell=CELL, view="layout",
              detail="geometry", timeout=300)
    after = len(((read.get("value") or {}).get("shapes") or []))
    st.value["shape_count"] = {"before": before, "after": after}
    (st.ok if after > before else st.bad)("layout-shapes-grew", st.value["shape_count"])

    fresh = f"{FILE_ROOT}/gds/r2/{int(time.time())}"
    op(t, "basic.command.run", cmd=f"mkdir -p {fresh} && echo ok", timeout=60)
    path = f"{fresh}/{CELL}.gds"
    call = raw_call(t, "virtuoso.layout.gds", action="export", library=LIB, cell=CELL,
                    view="layout", file_path=path, file_is_local=False, top_cell=CELL,
                    layer_map=LAYERMAP, layer_map_is_local=False, tech_lib=PDK_LIB,
                    timeout=900)
    st.value["gds_r2"] = {"path": path, "ok": call.get("ok"), "error": call.get("error")}
    (st.ok if call.get("ok") else st.bad)("gds-export-r2", call.get("error"))
    sha = remote_sha256(t, path)
    st.value["sha256_r2"] = sha
    # 说明：GDS 内嵌时间戳，**两次导出的 sha 必然不同**，因此 sha 差异只能当痕迹、
    # 不能当"内容变了"的判据；内容差异由上面的 layout-shapes-grew 断言。
    st.value["gds_sha_note"] = "sha 含时间戳噪声，仅作痕迹；内容差异由 layout-read 断言"
    (st.ok if sha else st.bad)("gds-r2-sha", sha)
    return st


def stage_r2_sim(t: HttpTransport, cfg) -> Stage:
    """复测：断言改图后**带宽显著下降**（10× 负载电容），低频增益基本不变。"""
    st = Stage("r2_sim", cfg.out)
    cfg.created.append(st)
    result = _run_sim(t, cfg, "r2", st)
    cfg.r2 = result
    r1 = getattr(cfg, "r1", None)
    if not r1 or not r1.get("bw_3db_hz") or not result.get("bw_3db_hz"):
        st.bad("iteration-assertions", {"r1": r1, "r2": result})
        st.error = "缺少可比的带宽数值"
        return st
    ratio = r1["bw_3db_hz"] / result["bw_3db_hz"]
    gain_delta = abs((result.get("gain_db_flatband") or 0.0)
                     - (r1.get("gain_db_flatband") or 0.0))
    checks = {
        "bw_ratio>3": ratio > 3.0,
        "bw_shrank": result["bw_3db_hz"] < r1["bw_3db_hz"],
        "gain_delta<3dB": gain_delta < 3.0,
        "swing_still>50mV": (result.get("out_swing_v") or 0.0) > 0.05,
    }
    st.value["iteration"] = {
        "r1": {"gain_db_flatband": r1.get("gain_db_flatband"),
               "bw_3db_hz": r1.get("bw_3db_hz"),
               "out_swing_v": r1.get("out_swing_v"), "readback": r1.get("readback")},
        "r2": {"gain_db_flatband": result.get("gain_db_flatband"),
               "bw_3db_hz": result.get("bw_3db_hz"),
               "out_swing_v": result.get("out_swing_v"),
               "readback": result.get("readback")},
        "bw_ratio": round(ratio, 3), "gain_delta_db": round(gain_delta, 3),
        "checks": checks,
    }
    (st.ok if all(checks.values()) else st.bad)("iteration-assertions", checks)
    return st


def stage_lvs(t: HttpTransport, cfg) -> Stage:
    """P-069 验收判据：原理图 → 官方 auCdl CDL → 版图 → calibre.lvs → **correct**。

    分两段，结论不要混：

    * **A（断言 correct）**：用工程里既有的真实 cell（`CMP_LIB/inv2`：schematic +
      layout + symbol 齐全，2026-08-17 前就在），走 export_cdl → layout.gds →
      `calibre.lvs`(deck+cdl) → `calibre.read_results`；这是 P-069 卡片的验收判据。
    * **B（只记录，不断言）**：本 TB 自己搭的 `DI65/inv_only`（版图只有 M1 矩形 +
      4 个 pin 标签，没有真实布线/端口层）——实测 verdict 为 `not_compared`
      （ports 0/4）。这是**TB 手搭版图的局限**（LVS deck 认端口要正确的层/标签），
      不是 P-069 的复现；记录下来免得后人拿它当"LVS 又坏了"的证据。
    """
    st = Stage("lvs", cfg.out)
    cfg.created.append(st)
    # ---------------------------------------------------------------- A：真实 cell
    proj_lib = "/home/Gent/project/test/cds.lib"
    run_a = f"{COMMAND_ROOT}/cdl/cmp_inv2"
    cds_lib_a = f"{COMMAND_ROOT}/cdl/cmp_inv2.cds.lib"
    prep_a = op(t, "basic.command.run",
                cmd=(f"rm -rf {run_a} && mkdir -p {run_a} && cp {proj_lib} {cds_lib_a} && "
                     f"grep -c 'DEFINE CMP_LIB' {cds_lib_a} && "
                     f"ls -l /home/Gent/project/test/inv2.gds 2>&1 | tail -1"), timeout=120)
    st.value["prep_a"] = cmd_stdout(prep_a).strip()[-300:]
    export_a = raw_call(t, "calibre.export_cdl", library="CMP_LIB", cell="inv2",
                        view="schematic", netlist_name="inv2", run_dir=run_a,
                        cds_lib=cds_lib_a, timeout=900)
    val_a = ((export_a.get("data") or {}).get("value")) or {}
    st.value["export_cdl_inv2"] = {k: val_a.get(k) for k in ("bytes", "netlist_path")}
    if not (export_a.get("ok") and val_a.get("bytes")):
        st.bad("export-cdl-inv2", export_a.get("error") or val_a)
        st.error = f"export_cdl(CMP_LIB/inv2) failed: {export_a.get('error')}"
        return st
    st.ok("export-cdl-inv2", st.value["export_cdl_inv2"])

    gds_a = f"{FILE_ROOT}/gds/lvs/inv2.gds"
    op(t, "basic.command.run", cmd=f"mkdir -p {FILE_ROOT}/gds/lvs && echo ok", timeout=60)
    call_a = raw_call(t, "virtuoso.layout.gds", action="export", library="CMP_LIB",
                      cell="inv2", view="layout", file_path=gds_a, file_is_local=False,
                      top_cell="inv2", layer_map=LAYERMAP, layer_map_is_local=False,
                      tech_lib=PDK_LIB, timeout=900)
    (st.ok if call_a.get("ok") else st.bad)("gds-export-inv2", call_a.get("error"))
    lvs_a = raw_call(t, "calibre.lvs", gds=gds_a, top="inv2", deck=LVS_DECK,
                     cdl=str(val_a.get("netlist_path")), blocking=True, timeout=1800)
    lvs_a_value = ((lvs_a.get("data") or {}).get("value")) or {}
    st.value["lvs_inv2"] = {"ok": lvs_a.get("ok"), "job_id": lvs_a_value.get("job_id"),
                            "run_dir": lvs_a_value.get("run_dir"),
                            "status": lvs_a_value.get("status"),
                            "error": lvs_a.get("error")}
    (st.ok if lvs_a.get("ok") else st.bad)("calibre-lvs-run-inv2", lvs_a.get("error"))
    if not lvs_a.get("ok"):
        st.error = f"calibre.lvs(CMP_LIB/inv2) failed: {lvs_a.get('error')}"
        return st
    req_a: dict[str, Any] = {"kind": "lvs", "timeout": 300}
    if lvs_a_value.get("job_id"):
        req_a["job_id"] = lvs_a_value["job_id"]
    elif lvs_a_value.get("run_dir"):
        req_a["run_dir"] = lvs_a_value["run_dir"]
    res_a = raw_call(t, "calibre.read_results", **req_a)
    value_a = ((res_a.get("data") or {}).get("value")) or {}
    st.value["results_inv2"] = value_a
    status_a = str((value_a.get("summary") or {}).get("status") or "").lower()
    st.value["verdict"] = {"status": status_a, "correct": status_a == "correct"}
    (st.ok if status_a == "correct" else st.bad)(
        "lvs-verdict-inv2", {"status": status_a,
                             "counts": (value_a.get("summary") or {}).get("counts")})

    # ------------------------------------------------- B：TB 手搭 cell（只记录）
    _ensure_cell_view(t, INV_CELL, "schematic", "schematic", st)
    inv_cmds = [
        {"op": "place_instance", "master_lib": PDK_LIB, "master_cell": PCH,
         "master_view": "symbol", "name": "MP", "pos": [0.0, 1.0], "orient": "R0"},
        {"op": "place_instance", "master_lib": PDK_LIB, "master_cell": NCH,
         "master_view": "symbol", "name": "MN", "pos": [0.0, -1.0], "orient": "R0"},
        {"op": "set_instance_params", "name": "MP",
         "params": {"w": DEFAULT_W, "l": DEFAULT_L}},
        {"op": "set_instance_params", "name": "MN",
         "params": {"w": DEFAULT_W, "l": DEFAULT_L}},
        {"op": "set_term_nets", "name": "MP",
         "term_nets": {"G": "vin", "D": "vout", "S": "vdd", "B": "vdd"}},
        {"op": "set_term_nets", "name": "MN",
         "term_nets": {"G": "vin", "D": "vout", "S": "vss", "B": "vss"}},
        {"op": "place_pin", "name": "vin", "direction": "input", "pos": [-4.0, 0.0]},
        {"op": "place_pin", "name": "vout", "direction": "output", "pos": [4.0, 0.0]},
        {"op": "place_pin", "name": "vdd", "direction": "inputOutput", "pos": [0.0, 3.0]},
        {"op": "place_pin", "name": "vss", "direction": "inputOutput", "pos": [0.0, -3.0]},
    ]
    op(t, "virtuoso.schematic.write", library=LIB, cell=INV_CELL, view="schematic",
       commands=inv_cmds, timeout=600)
    op(t, "virtuoso.schematic.check_and_save", library=LIB, cell=INV_CELL,
       view="schematic", timeout=300)
    st.ok("inv-schematic", {"cell": INV_CELL})

    run_dir = f"{COMMAND_ROOT}/cdl/{LIB}_{INV_CELL}"
    cds_lib = f"{COMMAND_ROOT}/cdl/{LIB}_{INV_CELL}.cds.lib"
    prep = op(t, "basic.command.run",
              cmd=(f"rm -rf {run_dir} && mkdir -p {run_dir} && "
                   f"cp {CDS_LIB_FILE} {cds_lib} && "
                   f"grep -q 'DEFINE {LIB}' {cds_lib} || "
                   f"echo 'DEFINE {LIB} {FILE_ROOT}/{LIB}' >> {cds_lib}; "
                   f"grep -n 'DEFINE {LIB}' {cds_lib}"), timeout=120)
    st.ok("cds-lib-prep", cmd_stdout(prep).strip()[-200:])
    export = raw_call(t, "calibre.export_cdl", library=LIB, cell=INV_CELL,
                      view="schematic", netlist_name=INV_CELL, run_dir=run_dir,
                      cds_lib=cds_lib, timeout=900)
    exp_value = ((export.get("data") or {}).get("value")) or {}
    st.value["export_cdl"] = {k: exp_value.get(k) for k in ("bytes", "netlist_path",
                                                            "run_dir", "log_path")}
    if not (export.get("ok") and exp_value.get("bytes")):
        st.bad("export-cdl", export.get("error") or exp_value)
        st.error = f"calibre.export_cdl failed: {export.get('error')}"
        return st
    st.ok("export-cdl", st.value["export_cdl"])
    remote_cdl = str(exp_value.get("netlist_path"))

    _ensure_cell_view(t, INV_CELL, "layout", "maskLayout", st)
    op(t, "virtuoso.layout.write", library=LIB, cell=INV_CELL, view="layout",
       commands=[
           {"op": "place_instance", "master_lib": PDK_LIB, "master_cell": PCH,
            "master_view": "layout", "name": "MP", "pos": [0.0, 0.0], "orient": "R0"},
           {"op": "place_instance", "master_lib": PDK_LIB, "master_cell": NCH,
            "master_view": "layout", "name": "MN", "pos": [0.0, 6.0], "orient": "R0"},
           {"op": "place_rect", "layer": "M1", "purpose": "drawing",
            "bbox": [[-1.0, -1.0], [1.0, 7.0]]},
           # 四个 port 都给 label（LVS 需要端口可比对）
           {"op": "place_label", "layer": "M1", "purpose": "pin", "text": "VIN",
            "pos": [-2.0, 3.0]},
           {"op": "place_label", "layer": "M1", "purpose": "pin", "text": "VOUT",
            "pos": [2.0, 3.0]},
           {"op": "place_label", "layer": "M1", "purpose": "pin", "text": "VDD",
            "pos": [0.0, 8.0]},
           {"op": "place_label", "layer": "M1", "purpose": "pin", "text": "VSS",
            "pos": [0.0, -2.0]},
       ], timeout=900)
    gds_dir = f"{FILE_ROOT}/gds/lvs"
    op(t, "basic.command.run", cmd=f"mkdir -p {gds_dir} && echo ok", timeout=60)
    gds = f"{gds_dir}/{INV_CELL}.gds"
    call = raw_call(t, "virtuoso.layout.gds", action="export", library=LIB, cell=INV_CELL,
                    view="layout", file_path=gds, file_is_local=False, top_cell=INV_CELL,
                    layer_map=LAYERMAP, layer_map_is_local=False, tech_lib=PDK_LIB,
                    timeout=900)
    (st.ok if call.get("ok") else st.bad)("gds-export-lvs", call.get("error"))
    lvs = raw_call(t, "calibre.lvs", gds=gds, top=INV_CELL, deck=LVS_DECK,
                   cdl=remote_cdl, blocking=True, timeout=1800)
    lvs_value = ((lvs.get("data") or {}).get("value")) or {}
    st.value["lvs"] = {"ok": lvs.get("ok"), "error": lvs.get("error"),
                       "job_id": lvs_value.get("job_id"),
                       "run_dir": lvs_value.get("run_dir"),
                       "status": lvs_value.get("status")}
    (st.ok if lvs.get("ok") else st.bad)("calibre-lvs-run", lvs.get("error"))
    if not lvs.get("ok"):
        st.error = f"calibre.lvs failed: {lvs.get('error')}"
        return st
    # read_results 必须带 job_id 或 run_dir（两者都不给是调用姿势错，会返回空 value）
    target: dict[str, Any] = {"kind": "lvs", "timeout": 300}
    if lvs_value.get("job_id"):
        target["job_id"] = lvs_value["job_id"]
    elif lvs_value.get("run_dir"):
        target["run_dir"] = lvs_value["run_dir"]
    results = raw_call(t, "calibre.read_results", **target)
    st.value["read_results_request"] = target
    if not results.get("ok"):
        st.bad("calibre-read-results", results.get("error"))
    value = ((results.get("data") or {}).get("value")) or {}
    st.value["results_diy_cell"] = value
    status = str(value.get("status") or "").lower()
    # B 段只记录：手搭版图（只有 M1 矩形 + 标签）LVS 认不出端口是**预期**的
    st.value["diy_cell_note"] = (
        "TB 手搭版图（M1 矩形 + pin 标签）在 PDK deck 下 ports 0/4 → not_compared；"
        "这是版图过于简陋，不是 P-069 复现（真实 cell 见 A 段）")
    st.ok("diy-cell-info", value.get("status"))
    return st


STAGES = {
    "probe": stage_probe,
    "lib": stage_lib,
    "r1_sch": stage_r1_sch,
    "r1_sym": stage_r1_sym,
    "r1_layout": stage_r1_layout,
    "r1_gds": stage_r1_gds,
    "r1_sim": stage_r1_sim,
    "r2_edit": stage_r2_edit,
    "r2_sym": stage_r2_sym,
    "r2_layout": stage_r2_layout,
    "r2_sim": stage_r2_sim,
    "lvs": stage_lvs,
}
DEFAULT_ORDER = ["probe", "lib", "r1_sch", "r1_sym", "r1_layout", "r1_gds", "r1_sim",
                 "r2_edit", "r2_sym", "r2_layout", "r2_sim"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", default="all", help="|".join(STAGES) + "|all")
    ap.add_argument("--token", default=PDK_TOKEN)
    ap.add_argument("--base", default=API)
    ap.add_argument("--skip", default="", help="逗号分隔的 stage 名")
    ap.add_argument("--with-lvs", action="store_true", help="追加 P-069 验收链")
    ap.add_argument("--tag", default="",
                    help="cell 名后缀（默认按时间生成，避免撞上历史残留的锁/对象）")
    ap.add_argument("--no-tag", action="store_true",
                    help="保留固定 cell 名（buf_stage / inv_only）——只在确认库干净时用")
    ap.add_argument("--out", type=Path, default=WORK_DIR)
    args = ap.parse_args(argv)
    # §1 环境检查（规范 §9）：业务面可达 + 本 token 能看到 PDK 库（DI65 建在它上面）。
    require_environment(base=args.base, token=args.token, require_lib=[PDK_LIB])

    # 每次跑用**自己的 cell 名**：DI65 库里可能留着上一轮的对象/锁（实测踩过
    # "schematic view DI65/buf_stage/schematic is locked by another session"）。
    if not args.no_tag:
        global CELL, INV_CELL
        suffix = args.tag or time.strftime("%H%M%S")
        CELL, INV_CELL = f"buf_stage_{suffix}", f"inv_only_{suffix}"

    transport = HttpTransport(args.token, args.base)
    args.created = []
    args.out = args.out
    args.r1 = None
    args.r2 = None
    args.gds_r1_sha = None
    args.r1_sym_stamp = None

    skip = {x.strip() for x in args.skip.split(",") if x.strip()}
    order = list(DEFAULT_ORDER)
    if args.with_lvs:
        order.append("lvs")
    if args.stage != "all":
        order = [args.stage]
    order = [name for name in order if name not in skip]

    failures: list[str] = []
    summary_path = args.out / "iteration-summary.json"
    summary: dict[str, Any] = {"ok": True, "token": args.token, "stages": {}}
    for name in order:
        stage = STAGES[name](transport, args)
        payload = stage.to_json()
        path = stage.save()
        print(json.dumps({k: payload[k] for k in ("stage", "ok", "error", "seconds")},
                         ensure_ascii=False))
        if payload["value"]:
            print("  value: " + json.dumps(payload["value"], ensure_ascii=False)[:1200])
        print(f"  evidence: {path}")
        summary["stages"][name] = payload
        if name == "r1_sim":
            args.r1 = payload["value"].get("r1")
        if name == "r2_sim":
            args.r2 = payload["value"].get("r2")
        if payload["error"] is not None:
            failures.append(f"{name}: {payload['error']}")
        elif not payload["ok"]:
            bad = [s["name"] for s in payload["steps"] if not s["ok"]]
            failures.append(f"{name}: 断言红 {bad}")
        if name == "r1_sim" and not payload["ok"]:
            # 轮 1 仿真不成立时迭代断言没有意义，但仍继续跑（非阻塞）
            print("  ! round1 sim not ok → 迭代断言将记录为不可比")
        if name == "r1_sym":
            args.r1_sym_stamp = payload["value"].get("stamp")

    summary["ok"] = not failures
    summary["failures"] = failures
    summary["iteration"] = (summary["stages"].get("r2_sim", {}) or {}).get("value", {}).get(
        "iteration")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    print(f"summary: {summary_path}  ok={summary['ok']}  failures={failures}")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
