"""Calibre 环境与三段流程探针（真机，direct dispatch，不依赖 8127）。

只做调研取证，不是 E2E 测试：

* ``--facts``            工具/环境/license/PDK deck 只读勘察
* ``--stage drc|lvs|pex`` 在服务器上建 run dir、stage deck、改写占位符并实跑一段

用法（工作目录固定为 test/artifacts/env/log-vblog，token vb-vblog）::

    python test/semi/probes/calibre_env_probe.py --facts
    python test/semi/probes/calibre_env_probe.py --stage drc --gds /path/x.gds --top x
    python test/semi/probes/calibre_env_probe.py --stage lvs --gds /path/x.gds --top x --cdl /path/x.cdl
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

WORK_DIR = ROOT / "test" / "artifacts" / "log-vblog"
TOKEN = "vb-vblog"
PDK = "/opt/eda/PDK/CRN65GPNEW/CRN65GPNEW/Calibre"
RUN_ROOT = "/home/Gent/project/vblog/calibre_probe"
FACTS_CMD = (
    "echo '--- tool:'; which calibre; timeout 60 calibre -version 2>&1 | head -3; "
    "echo '--- env:'; env | grep -E '^(MGC_HOME|CALIBRE_HOME|MGC_LIB_PATH|USE_CALIBRE_VCO|MGLS_LICENSE_FILE)=' ; "
    "echo '--- license file:'; ls -l $MGLS_LICENSE_FILE; grep -c -i calibre $MGLS_LICENSE_FILE; "
    "echo '--- decks:'; ls /opt/eda/PDK/CRN65GPNEW/CRN65GPNEW/Calibre/{drc,lvs,rcx} | head -20; "
    "echo '--- ulimit:'; ulimit -n; ulimit -u; "
    "echo '--- hosts:'; hostname; whoami"
)


def build_middle(work_dir: Path | None = None):
    from common.paths import init_work_dir
    from transport.middle import BusinessServer

    init_work_dir(str(work_dir or WORK_DIR))
    return BusinessServer()


def run(middle, cmd: str, timeout: int = 300):
    result = middle.run_command(cmd, timeout=timeout, token=TOKEN)
    print(f"rc={result.returncode} kind={result.kind}")
    print(result.stdout)
    if (result.stderr or "").strip():
        print("STDERR:", result.stderr[:800])
    return result


def stage_drc(middle, gds: str, top: str) -> None:
    run_dir = f"{RUN_ROOT}/drc_run"
    cmd = (
        f"rm -rf {run_dir} && mkdir -p {run_dir} && cd {run_dir} && "
        f"cp {PDK}/drc/calibre.drc run_drc.cal && "
        f"sed -i 's|\"GDSFILENAME\"|\"{gds}\"|; s|\"TOPCELLNAME\"|\"{top}\"|' run_drc.cal && "
        "ulimit -n 65536; timeout 240 calibre -drc -hier -turbo 4 run_drc.cal > drc.log 2>&1; "
        "echo \"calibre_rc=$?\"; tail -12 drc.log; ls -la | head -10"
    )
    run(middle, cmd, timeout=300)


def stage_lvs(middle, gds: str, top: str, cdl: str) -> None:
    run_dir = f"{RUN_ROOT}/lvs_run"
    cmd = (
        f"rm -rf {run_dir} && mkdir -p {run_dir}/DFM && cd {run_dir} && "
        f"cp {PDK}/lvs/calibre.lvs run_lvs.cal && cp {PDK}/lvs/DFM/* DFM/ 2>/dev/null; "
        f"sed -i 's|\"lvs_top.gds\"|\"{gds}\"|; s|\"lvs_top.cdl\"|\"{cdl}\"|; s|\"lvs_top\"|\"{top}\"|g' run_lvs.cal && "
        "ulimit -n 65536; timeout 240 calibre -lvs -hier -turbo 4 run_lvs.cal > lvs.log 2>&1; "
        "echo \"calibre_rc=$?\"; tail -12 lvs.log; ls -la | head -10"
    )
    run(middle, cmd, timeout=300)


def stage_pex(middle, gds: str, top: str, cdl: str) -> None:
    run_dir = f"{RUN_ROOT}/rcx_run"
    cmd = (
        f"rm -rf {run_dir} && mkdir -p {run_dir} && cp -r {PDK}/rcx/. {run_dir}/ && "
        f"cp -r {RUN_ROOT}/lvs_run/svdb {run_dir}/svdb && cd {run_dir} && "
        f"sed -i 's|\"lvs_top.gds\"|\"{gds}\"|; s|\"lvs_top.cdl\"|\"{cdl}\"|; s|\"lvs_top\"|\"{top}\"|g' calibre.rcx && "
        "ulimit -n 65536; "
        "timeout 300 calibre -xrc -phdb -turbo 4 calibre.rcx > pex_phdb.log 2>&1; echo \"phdb_rc=$?\"; tail -4 pex_phdb.log; "
        "timeout 300 calibre -xrc -pdb -rc calibre.rcx -turbo 4 > pex_pdb.log 2>&1; echo \"pdb_rc=$?\"; tail -6 pex_pdb.log; "
        "ls svdb | head -12"
    )
    run(middle, cmd, timeout=600)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--facts", action="store_true")
    parser.add_argument("--stage", choices=("drc", "lvs", "pex"))
    parser.add_argument("--gds", default="/home/Gent/project/test/ctle.gds")
    parser.add_argument("--top", default="ctle")
    parser.add_argument("--cdl", default="/home/Gent/project/test/ctle.cdl")
    parser.add_argument("--work-dir", default=str(WORK_DIR))
    parser.add_argument("--token", default="vb-vblog")
    args = parser.parse_args()

    global TOKEN
    TOKEN = args.token
    middle = build_middle(Path(args.work_dir))
    try:
        if args.facts or not args.stage:
            run(middle, FACTS_CMD, timeout=120)
        if args.stage == "drc":
            stage_drc(middle, args.gds, args.top)
        elif args.stage == "lvs":
            stage_lvs(middle, args.gds, args.top, args.cdl)
        elif args.stage == "pex":
            stage_pex(middle, args.gds, args.top, args.cdl)
    finally:
        close = getattr(middle, "close", None)
        if callable(close):
            close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
