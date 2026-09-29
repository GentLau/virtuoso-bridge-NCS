# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-28 18:05
# 依赖: 真机 calprobe token（wsl-gent）+ design_iterate r2 同口径 netlist
# =======================================================================
"""P-076 复验（上层侧）：修好后同一口径 2 任务 spectre.run 是否正常收尾。

判据（每条都要绿）：
  ① 请求正常返回且两任务 status=success；
  ② 递归下载**已安装**到最终路径（`<job>/<stem>.raw/` 有文件，且 `spectre.out` 在）
     —— 修前故障形态正是"数据在 .vbtmp-*、最终路径为空"；
  ③ 不留 `.vbtmp-*` 暂存目录（修前会静默残留）；
  ④ 返回后进程线程数不增加（修前 pump 线程会永久留存）。

六步流程：① 自检 = 本机直连 (direct transport) 能 query 到 calprobe token；
②③ 每轮唯一 job 名，不复用旧 run_dir；④ 只做被测动作（一次 spectre.run，2 任务）；
⑤ 读回 = 客户端 artifact 目录 + 线程表；⑥ 不清现场（保留 artifact 供人去查）。
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from common.paths import init_work_dir            # noqa: E402
from server import dispatch                       # noqa: E402
from server.api_server import register_packages   # noqa: E402
from transport.middle import BusinessServer       # noqa: E402

TOKEN = "d6af595b342647b58ec63ca6"
WORK = ROOT / "test" / "artifacts" / "env" / "log-vblog"
STAGE = ROOT / "test" / "artifacts" / "evidence" / "round7" / "design-iterate" / "stage"
ARTIFACT = WORK / "artifact" / "spectre"
ROUNDS = 3
TIMEOUT = 300.0

init_work_dir(str(WORK))
register_packages()
middle = BusinessServer()


def threads_now() -> dict[int, str]:
    return {item.ident: item.name for item in threading.enumerate()
            if item.ident is not None}


def run_round(index: int) -> dict:
    stamp = time.strftime("%H%M%S")
    jobs = (f"p076fix_{stamp}_{index}_ac", f"p076fix_{stamp}_{index}_tran")
    before_threads = threads_now()
    before_stage = {p.name for p in ARTIFACT.glob("*/.vbtmp-*")}
    started = time.monotonic()
    _status, body = dispatch.dispatch(middle, {
        "operation": "spectre.run", "token": TOKEN,
        "tasks": [
            {"job": jobs[0], "netlist": str(STAGE / "r2_ac.scs"), "parse": "auto"},
            {"job": jobs[1], "netlist": str(STAGE / "r2_tran.scs"), "parse": "auto"},
        ],
        "max_workers": 2, "parse": "auto", "download": True,
        "keep_run_dir": True, "timeout": TIMEOUT,
    })
    elapsed = time.monotonic() - started
    value = (_c1_wrapper(body)).get("value") or {}
    runs = value.get("runs") or []

    checks: dict[str, object] = {
        "returned": bool(body.get("ok")),
        "seconds": round(elapsed, 2),
    }
    for job, stem in ((jobs[0], "r2_ac"), (jobs[1], "r2_tran")):
        raw_dir = ARTIFACT / job / f"{stem}.raw"
        checks[f"{job}.raw_installed"] = raw_dir.is_dir() and any(raw_dir.iterdir())
        checks[f"{job}.spectre_out"] = (ARTIFACT / job / "spectre.out").is_file()
        checks[f"{job}.status"] = next(
            ((r.get("value") or {}).get("status") for r in runs
             if (r.get("value") or {}).get("job") == job), None,
        )
    new_stage = {p.name for p in ARTIFACT.glob("*/.vbtmp-*")} - before_stage
    checks["new_stage_dirs"] = sorted(new_stage)
    after_threads = threads_now()
    fresh_threads = {ident: name for ident, name in after_threads.items()
                     if ident not in before_threads}
    checks["thread_delta"] = len(fresh_threads)
    checks["fresh_threads"] = sorted(set(fresh_threads.values()))
    checks["ok"] = (
        checks["returned"]
        and checks["thread_delta"] == 0
        and not new_stage
        and all(checks[f"{job}.{key}"] is True
                for job in jobs for key in ("raw_installed", "spectre_out"))
        and all(checks[f"{job}.status"] == "success" for job in jobs)
    )
    print(json.dumps({"round": index, **checks}, ensure_ascii=False), flush=True)
    return checks


def main() -> int:
    query = middle.query(token=TOKEN)
    if query.status.value != "success":
        print(f"ENV FAIL: calprobe token 不可用: {query.errors}")
        return 2
    # 预热：先把 SSH 传输/keepalive 这类长生命线程建起来，否则首轮会把它们算成新增。
    warm = middle.run_command("true", timeout=60, token=TOKEN)
    if warm.returncode != 0:
        print(f"ENV FAIL: 预热命令失败 rc={warm.returncode} {warm.stderr}")
        return 2
    time.sleep(1.0)
    results = [run_round(index) for index in range(1, ROUNDS + 1)]
    passed = sum(1 for item in results if item.get("ok"))
    print(f"[summary] {passed}/{len(results)} rounds green")
    middle.close()
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())


# --- C1 兼容垫片（2026-09-29，C3）------------------------------------------------
# C1（2f88853）起：业务载荷直返顶层（值型 `value`、命令/skill 型 `result`）、
# 成功默认省略 `steps`、失败壳去掉 `data`。历史 TB 按 `response["data"]` 解析，
# 本垫片把新契约响应合成为旧 `data` 壳，让既有解析零改动继续工作。
def _c1_wrapper(body):
    if not isinstance(body, dict):
        return {}
    if isinstance(body.get("data"), dict):
        return body["data"]
    wrapped = {"ok": body.get("ok"), "error": body.get("error")}
    for key in ("value", "result", "steps"):
        if key in body:
            wrapped[key] = body[key]
    return wrapped
