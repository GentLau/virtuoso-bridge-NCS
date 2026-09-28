# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-28 23:00
# 依赖: 无
# =======================================================================
"""半真机探针：`calibre.drc(hier=False)` 的两处缺陷（P-093 / P-094）。

为什么单独一条：这不是"跑一次 DRC 看结果"的常规用例，而是**攻击参数组合 + 失败检测**：

* P-093：`_argv_for()` 对 drc/lvs **无条件**追加 `-turbo <n>`（`src/pyapi/packages/calibre.py:994-995`），
  但 Calibre 对 flat DRC（`hier=False`）拒绝该选项 → `ERROR: The -turbo option is not valid with this flat
  application.` + 打印 usage。桥把这条命令行原样交给工具，用户拿到的是 usage 而不是可读错误。
* P-094：工具**秒退**后桥不检测（轮询只看报告是否出现），`blocking=True` 会一直等到 `timeout`
  （实测 `params-drc-1790606320955` 卡满 1800s 才可能返回）。AGENTS.md 的 dual-defense 要求
  每轮 poll 必须 tail 工具日志里的终态标记，calibre 运行器没做。

判据（**预期红**）：提交后 15s 内，`calibre.status` 应把这条秒退任务报成失败/终态，并带上日志里的
`ERROR:` 行；今天它只会一直说 running/queued。

六步流程（test/docs/写TB规范.md §1）：
① 环境检查=本文件先确认 deck/gds/role.calibre.bin 都在；②③ 基线=新建独立 run_dir；
④ 只做被测动作（一次非阻塞提交）；⑤ 读回=status + 远端 drc.log 原文；⑥ 不清理现场（run_dir 保留）。
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
API = os.environ.get("VB_CALIBRE_API", "http://127.0.0.1:8127/api/operation")
TOKEN = os.environ.get("VB_CALIBRE_TOKEN", "vb-vblog")
PDK = "/opt/eda/PDK/CRN65GPNEW/CRN65GPNEW/Calibre"
GDS = os.environ.get("VB_CALIBRE_GDS", "/home/Gent/project/vblog/s11_inv/s11/inv.gds")
TOP = os.environ.get("VB_CALIBRE_TOP", "inv")
DRC_DECK = os.environ.get("VB_CALIBRE_DRC_DECK", f"{PDK}/drc/calibre.drc")
RUN_DIR = os.environ.get("VB_CALIBRE_RUN_DIR", "/home/Gent/project/vblog/calibre-e2e")
EVIDENCE = ROOT / "test" / "artifacts" / "evidence" / "round8" / "p093-flat-turbo-probe.json"


def _call(operation: str, **fields: Any) -> dict[str, Any]:
    payload = {"operation": operation, "token": TOKEN, **fields}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        API, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return json.loads(error.read().decode("utf-8"))


def main() -> int:
    global API, TOKEN

    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default=API)
    parser.add_argument("--token", default=TOKEN)
    parser.add_argument("--wait", type=float, default=15.0)
    parser.add_argument("--out", default=str(EVIDENCE))
    args = parser.parse_args()
    API, TOKEN = args.api, args.token

    stamp = int(time.time() * 1000)
    run_dir = f"{RUN_DIR}/p093-flat-{stamp}"
    job_id = f"p093_flat_{stamp}"
    evidence: dict[str, Any] = {"run_dir": run_dir, "job_id": job_id, "steps": []}

    submitted = _call("calibre.drc", gds=GDS, top=TOP, deck=DRC_DECK, run_dir=run_dir,
                      hier=False, turbo=2, job_id=job_id, blocking=False, timeout=120)
    evidence["steps"].append({"name": "submit", "ok": submitted.get("ok"),
                              "detail": str(submitted)[:400]})
    if not submitted.get("ok"):
        print(f"submit 就失败（也算暴露）: {submitted.get('error')}")
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                                  encoding="utf-8")
        return 1

    time.sleep(args.wait)
    tail = _call("basic.command.run",
                 cmd=(f"grep -m3 -n -E 'ERROR:|-turbo option is not valid' {run_dir}/drc.log "
                      f"2>/dev/null; echo ---; tail -n 3 {run_dir}/drc.log 2>/dev/null"),
                 timeout=60)
    log_text = ""
    if tail.get("ok"):
        log_text = str(((tail.get("data") or {}).get("result") or ["", "", "", ""])[1])
    evidence["steps"].append({"name": "tool-log-tail", "text": log_text[:600]})
    tool_failed = "-turbo option is not valid" in log_text or "ERROR:" in log_text

    status = _call("calibre.status", job_id=job_id, run_dir=run_dir)
    value = (status.get("data") or {}).get("value") or {}
    evidence["steps"].append({"name": "status", "ok": status.get("ok"),
                              "detail": json.dumps(value, ensure_ascii=False)[:400]})
    state = str(value.get("state") or value.get("status") or "")
    surfaced = bool(value.get("error")) or state in ("failed", "error", "tool_failed")
    evidence["tool_failed"] = tool_failed
    evidence["status_state"] = state
    evidence["error_surfaced"] = surfaced

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
    print(f"tool_failed={tool_failed} status_state={state!r} error_surfaced={surfaced}")
    print(f"log_tail: {log_text[:200]!r}")

    if not tool_failed:
        print("NOTE  这次没复现 Calibre 的 -turbo/flat 报错（可能是环境或 deck 差异）")
        return 2
    if surfaced:
        print("PASS  status 已把工具秒退报成失败（P-094 已修）")
        return 0
    print("FAIL  P-094：工具已秒退并打 ERROR，但 calibre.status 仍不报失败")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
