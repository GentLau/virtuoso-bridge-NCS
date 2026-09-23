"""调查探针：用 Virtuoso 自带 auCdl（CDL Out）机制生成 LVS 用的 CDL。

官方口径（IC6.1.8 自带文档 ``doc/cdloutta/``）：

* 交互式：File → Export → CDL（CDL Out 表单，Netlisting Mode = Analog）；
* 批处理：先有 ``si.env``，再在 run dir 里执行 ``si -batch -command netlist``
  （run dir 需含 ``cds.lib``，环境变量 ``CDS_Netlisting_Mode=Analog``）。

本探针**手工构造 si.env**（字段取自官方 Sample si.env File），验证"不依赖手工 GUI"
的批处理路线是否成立。

用法::

    python test/semi/probes/calibre_cdl_probe.py --lib schemtest --cell sch_e2e --view schematic
"""
from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

WORK_DIR = ROOT / "test" / "artifacts" / "log-vblog"
STAGE_DIR = ROOT / "test" / "artifacts" / "skill-tooling-tb"
CDS_LIB = "/home/Gent/project/vblog/cds.lib"
RUN_ROOT = "/home/Gent/project/vblog/calibre_probe"
TOKEN = "vb-vblog"

SI_ENV_TEMPLATE = """simLibName = "{lib}"
simCellName = "{cell}"
simViewName = "{view}"
hnlNetlistFileName = "{cell}.cdl"
simRunDir = "{run_dir}/"
simSimulator = "{simulator}"
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

#: .simrc 覆盖 si.env（CDL Out Task Assistant: How to Set Default View List,
#: Stop List, Netlist Type）。默认 stop list 是 '("auCdl")：命中即停止下钻，
#: 由 primitive 的 CDF netlist procedure 生成器件行。
SIMRC = """cdlSimViewList = '("auCdl" "schematic")
cdlSimStopList = '("auCdl")
cdlNetlistType = 'hnl
cdlPrintComments = 't
"""


def build_middle():
    from common.paths import init_work_dir
    from transport.middle import BusinessServer

    init_work_dir(str(WORK_DIR))
    return BusinessServer()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lib", default="schemtest")
    parser.add_argument("--cell", default="sch_e2e")
    parser.add_argument("--view", default="schematic")
    parser.add_argument("--run-dir", default=f"{RUN_ROOT}/cdl_run")
    parser.add_argument("--cds-lib-file", default=CDS_LIB,
                        help="复制到 run dir 的 cds.lib（指向被测库）")
    parser.add_argument("--simulator", default="cdl",
                        help="si.env 的 simSimulator（cdl=auCdl / hspiceD / spectre）")
    args = parser.parse_args()

    middle = build_middle()
    run_dir = args.run_dir
    si_env = SI_ENV_TEMPLATE.format(
        lib=args.lib, cell=args.cell, view=args.view, run_dir=run_dir,
        simulator=args.simulator,
    )
    try:
        prep = middle.run_command(
            f"rm -rf {run_dir} && mkdir -p {run_dir} && cp {args.cds_lib_file} {run_dir}/",
            timeout=60, token=TOKEN,
        )
        print(f"[prep] rc={prep.returncode} kind={prep.kind}")

        # si.env 用持久 staging 目录（TemporaryDirectory 下的文件曾报 VB-PATH-NOT-VISIBLE）
        STAGE_DIR.mkdir(parents=True, exist_ok=True)
        local_env = STAGE_DIR / f"{args.cell}_si.env"
        local_env.write_text(si_env, encoding="utf-8")
        upload = middle.upload_file(local_env, f"{run_dir}/si.env", timeout=60, token=TOKEN)
        print(f"[upload si.env] rc={upload.returncode} kind={upload.kind} "
              f"stderr={upload.stderr[:200]!r} local={local_env}")
        if upload.returncode != 0:
            # 退路：base64 写入（无引号转义问题）
            payload = base64.b64encode(si_env.encode("utf-8")).decode("ascii")
            fallback = middle.run_command(
                f"echo {payload} | base64 -d > {run_dir}/si.env && wc -l {run_dir}/si.env",
                timeout=60, token=TOKEN,
            )
            print(f"[fallback write] rc={fallback.returncode} kind={fallback.kind} "
                  f"stdout={fallback.stdout.strip()[:120]!r} stderr={fallback.stderr[:120]!r}")

        # .simrc：view list / stop list / netlist type（会被 si 读取并覆盖 si.env）
        simrc_local = STAGE_DIR / f"{args.cell}_simrc"
        simrc_local.write_text(SIMRC, encoding="utf-8")
        upload_rc = middle.upload_file(simrc_local, f"{run_dir}/.simrc",
                                       timeout=60, token=TOKEN)
        if upload_rc.returncode != 0:
            payload = base64.b64encode(SIMRC.encode("utf-8")).decode("ascii")
            middle.run_command(
                f"echo {payload} | base64 -d > {run_dir}/.simrc", timeout=60, token=TOKEN
            )
        print(f"[.simrc] {'uploaded' if upload_rc.returncode == 0 else 'base64-write'} "
              f"(rc={upload_rc.returncode})")

        cmd = (
            f"cd {run_dir} && echo '--- si.env:'; cat si.env; "
            "CDS_Netlisting_Mode=Analog timeout 180 si -batch -command netlist > si.log 2>&1; "
            "echo \"si_rc=$?\"; echo '--- si.log tail:'; tail -25 si.log; "
            "echo '--- files:'; ls -la; "
            "echo '--- netlist head:'; for f in *.cdl netlist; do "
            "[ -f \"$f\" ] && { echo \"== $f\"; head -30 \"$f\"; }; done"
        )
        result = middle.run_command(cmd, timeout=300, token=TOKEN)
        print(f"rc={result.returncode} kind={result.kind}")
        print(result.stdout[:8000])
        if (result.stderr or "").strip():
            print("STDERR:", result.stderr[:800])
    finally:
        close = getattr(middle, "close", None)
        if callable(close):
            close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
