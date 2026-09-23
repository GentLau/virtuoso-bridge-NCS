"""探针：找出 tsmcN65 下能真正产出 CDL 的 si.env/.simrc 组合。

背景：S11 流程 TB 用 `simViewList=("auCdl" "schematic")` + `cdlNetlistType='hnl`
跑 `si -batch -command netlist`，netlister 没有在器件 auCdl 视图处停下，
报 `hnlCDLParamList ... not defined` / `hnlCDLFormatInst ...`（OSSHNL-514）。

本探针把候选组合排成矩阵，每个组合独立 run dir，回报：
`si_rc`、CDL 字节数、器件行数（`^[MmXx]`）、si.log 末尾错误行。

用法::

    python test/semi/probes/cdl_export_variants_probe.py --cell inv2
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
TOKEN = "d6af595b342647b58ec63ca6"          # calprobe：带 tsmcN65 的真实例
OUT = ROOT / "test" / "artifacts" / "scenario-project65"

#: 变体矩阵。stop list 只能写在 .simrc（Cadence CDL Out Task Assistant 文档
#: “How to Set Default View List / Stop List / Netlist Type”），**必须每个变体
#: 真的写进运行目录**，否则矩阵是假的（第一版探针就栽在这里：四个变体同输出）。
VARIANTS = [
    {"name": "A-stop-auCdl", "netlist_type": "hnl",
     "view_list": '("auCdl" "schematic")', "stop_list": '("auCdl")'},
    {"name": "B-stop-auCdl-symbol", "netlist_type": "hnl",
     "view_list": '("auCdl" "schematic")', "stop_list": '("auCdl" "symbol")'},
    {"name": "C-view-with-symbol", "netlist_type": "hnl",
     "view_list": '("auCdl" "schematic" "symbol")',
     "stop_list": '("auCdl" "symbol")'},
    {"name": "D-cdl-stop-symbol", "netlist_type": "cdl",
     "view_list": '("auCdl" "schematic")', "stop_list": '("auCdl" "symbol")'},
    # E/F：PDK 器件没有 CDF 级 CDL 属性、auCdl 视图也没有 simInfo，但**有 auLvs 视图**——
    # auLvs 是"analog LVS"网表视图，对应 simSimulator=auLvs 的 si 流程（此前没试过）。
    {"name": "E-auLvs-only", "netlist_type": "hnl", "simulator": "auLvs",
     "view_list": '("auLvs" "schematic")', "stop_list": '("auLvs")'},
    {"name": "F-auLvs-first", "netlist_type": "hnl", "simulator": "auLvs",
     "view_list": '("auLvs" "auCdl" "schematic")', "stop_list": '("auLvs" "auCdl")'},
]


def call(operation: str, **fields):
    body = json.dumps({"operation": operation, "token": TOKEN, **fields}).encode()
    req = urllib.request.Request(API, data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=900) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_cmd(cmd: str, timeout: int = 300) -> str:
    data = call("basic.command.run", cmd=cmd, timeout=timeout)
    result = (data.get("data") or {}).get("result")
    if isinstance(result, list) and len(result) >= 2:
        return str(result[1])
    return json.dumps(data)[:2000]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", default="PROJ65")
    ap.add_argument("--cell", default="inv2")
    ap.add_argument("--root", default="/home/Gent/.virtuoso-bridge/calprobe/command/cdlvar")
    args = ap.parse_args()

    rows = []
    for variant in VARIANTS:
        run_dir = f"{args.root}/{variant['name']}"
        si_env = (
            f'simLibName = "{args.lib}"\n'
            f'simCellName = "{args.cell}"\n'
            'simViewName = "schematic"\n'
            f'hnlNetlistFileName = "{args.cell}.cdl"\n'
            f'simRunDir = "{run_dir}/"\n'
            f'simSimulator = "{variant.get("simulator", "cdl")}"\n'
            f"simViewList = '{variant['view_list']}\n"
            "simPrintInhConnAttributes = 'nil\n"
            'simNetNamePrefix = "N"\n'
            'simInstNamePrefix = "X"\n'
            'simModelNamePrefix = "M"\n'
            "hnlMaxLineLength = 79\n"
            "preserveALL = t\n"
            "retainBusses = t\n"
            "CDLUsePortOrderForPinList = 'nil\n"
        )
        stages = OUT / "stage"
        stages.mkdir(parents=True, exist_ok=True)
        local_env = stages / f"variant_{variant['name']}.si.env"
        local_env.write_text(si_env, encoding="utf-8")
        simrc = (
            f"cdlSimViewList = '{variant['view_list']}\n"
            f"cdlSimStopList = '{variant['stop_list']}\n"
            f"cdlNetlistType = '{variant['netlist_type']}\n"
            "cdlPrintComments = 't\n"
        )
        local_rc = stages / f"variant_{variant['name']}.simrc"
        local_rc.write_text(simrc, encoding="utf-8")

        prep = run_cmd(
            f"rm -rf {run_dir} && mkdir -p {run_dir} && "
            f"cp /home/Gent/project/calprobe/cds.lib {run_dir}/ && echo ok", 120)
        upload = call("basic.file.upload", local_path=str(local_env),
                      remote_path=f"{run_dir}/si.env", timeout=120)
        upload_rc = call("basic.file.upload", local_path=str(local_rc),
                         remote_path=f"{run_dir}/.simrc", timeout=120)
        print(f"[{variant['name']}] prep={prep.strip()[-40:]!r} "
              f"upload_ok={upload.get('ok')}/{upload_rc.get('ok')}")

        out = run_cmd(
            f"cd {run_dir} && CDS_Netlisting_Mode=Analog timeout 240 si -batch -command netlist "
            f"> si.log 2>&1; echo si_rc=$?; "
            f"echo bytes=$(wc -c < {args.cell}.cdl 2>/dev/null || echo 0); "
            f"echo devlines=$(grep -cE '^[MmXx][A-Za-z0-9_]' {args.cell}.cdl 2>/dev/null || echo 0); "
            f"echo sha=$(sha256sum {args.cell}.cdl 2>/dev/null | cut -c1-12); "
            f"echo '--- err ---'; grep -E 'ERROR|Failed to|OSSHNL' si.log | tail -3",
            600)
        row = {"variant": variant, "run_dir": run_dir, "output": out[-2500:]}
        rows.append(row)
        print(out[-900:])

    evidence = OUT / "cdl-variants.json"
    evidence.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"evidence: {evidence}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
