# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-28 17:25
# 依赖: 8127 业务面 + calprobe token；py-spy（仅在卡住时抓栈需要）
# =======================================================================
# 六步流程：① 自检 = /health 可达 + token 可用（不通过即停）；②③ 每轮用唯一 job 名，
# 不复用旧 run_dir；④ 只做被测动作（一次 spectre.run，2 任务 / max_workers=2）；
# ⑤ 读回 = 客户端 artifact 目录 vs 远端 run_dir + /health 的 in_flight 轨迹；
# ⑥ 不清现场：卡住时保留 .vbtmp-* / 日志 / py-spy 栈，供中层定位（P-076）。
"""把 spectre.run 的中层调用与 paramiko channel 一一对上（P-076 定位用）。

跑一次与 design_iterate r2_sim 同口径的 2 任务 spectre.run，同时：
① 在 stdout 打印每次中层调用的起止时间；② 把 paramiko DEBUG 写进独立日志。
两者对齐后就知道"第 N 个 channel 属于哪个调用"，再拿去做故障现场的比对。
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(r"C:\Users\user\Desktop\repos_Github\virtuoso-bridge-NCS")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(ROOT / "src"))
from common.paths import init_work_dir            # noqa: E402
from server import dispatch                       # noqa: E402
from server.api_server import register_packages   # noqa: E402
from transport.middle import BusinessServer       # noqa: E402

TOKEN = "d6af595b342647b58ec63ca6"
STAGE = ROOT / "test" / "artifacts" / "evidence" / "round7" / "design-iterate" / "stage"
LOG = ROOT / "test" / "artifacts" / "evidence" / "p076-repro" / "channel-map.log"

init_work_dir(str(ROOT / "test/artifacts/env/log-vblog"))
register_packages()
LOG.parent.mkdir(parents=True, exist_ok=True)
if LOG.exists():
    LOG.unlink()
handler = logging.FileHandler(LOG, encoding="utf-8")
handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s", "%H:%M:%S"))
for name in ("paramiko.transport", "common.ssh", "transport.middle"):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)

middle = BusinessServer()


def wrap(name: str) -> None:
    original = getattr(middle, name)

    def wrapper(*args, **kwargs):
        mark = time.strftime("%H:%M:%S")
        started = time.monotonic()
        print(f">>> {name} {mark} {str(args)[:70]}", flush=True)
        try:
            return original(*args, **kwargs)
        finally:
            print(f"<<< {name} {time.strftime('%H:%M:%S')} "
                  f"{time.monotonic() - started:.2f}s", flush=True)

    setattr(middle, name, wrapper)


for method in ("run_spectre_command", "upload_file", "download_file", "run_command",
               "execute_skill", "query"):
    wrap(method)

try:
    status, body = dispatch.dispatch(middle, {
        "operation": "spectre.run", "token": TOKEN,
        "tasks": [
            {"job": "chanmap_ac", "netlist": str(STAGE / "r2_ac.scs"), "parse": "auto"},
            {"job": "chanmap_tran", "netlist": str(STAGE / "r2_tran.scs"), "parse": "auto"},
        ],
        "max_workers": 2, "parse": "auto", "download": True,
        "keep_run_dir": True, "timeout": 300,
    })
    value = ((body.get("data") or {}).get("value") or {})
    print("status", status, "ok", body.get("ok"),
          "runs", [(r.get("job"), r.get("ok"),
                    [s["name"] for s in r.get("steps") or []]) for r in value.get("runs", [])])
finally:
    handler.flush()
    middle.close()
