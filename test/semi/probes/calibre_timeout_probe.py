# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-29 18:01
# 依赖: 无
# =======================================================================
"""P-098 半真机回归：``blocking=true`` 到期必须返回 ``status=timeout``，不杀后台作业。

用真实命令 role + 业务面 HTTP + 一个**假 Calibre 可执行脚本**（只 sleep）来
稳定制造“作业仍在运行、但调用方的 blocking deadline 已到”的场景；不依赖
真实 DRC 的时长，也不会占用 Calibre license。

六步流程（test/docs/写TB规范.md §1）：
① 环境检查 = 命令角色可见 PDK deck，且能上传/执行假工具；
②③ 基线 = 新建独立 run_dir + 独立 sleeping launcher；
④ 被测动作 = 一次 ``calibre.drc(blocking=true, timeout=5)``；
⑤ 读回比对 = 返回 status=timeout、elapsed < 20s、后台进程仍活着；
⑥ 不清理现场（run_dir 保留），但本探针结束前回收自己启动的假工具进程。
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
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
GDS = os.environ.get(
    "VB_CALIBRE_GDS", "/home/Gent/project/vblog/s11_inv/s11/inv.gds")
TOP = os.environ.get("VB_CALIBRE_TOP", "inv")
DRC_DECK = os.environ.get(
    "VB_CALIBRE_DRC_DECK", f"{PDK}/drc/calibre.drc")
RUN_DIR = os.environ.get(
    "VB_CALIBRE_RUN_DIR", "/home/Gent/project/vblog/calibre-e2e")


def _call(operation: str, **fields: Any) -> dict[str, Any]:
    body = json.dumps(
        {"operation": operation, "token": TOKEN, **fields},
        ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        API, data=body,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", "replace")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"ok": False, "error": f"HTTP {error.code}: {raw[:300]}"}


def _value(operation: str, **fields: Any) -> dict[str, Any]:
    response = _call(operation, **fields)
    if response.get("ok") is not True:
        raise AssertionError(
            f"{operation} failed: {response.get('error')}; "
            f"{str(response)[:400]}")
    value = response.get("value")
    if not isinstance(value, dict):
        raise AssertionError(f"{operation} returned no value dict: {response}")
    return value


def _command(cmd: str, timeout: int = 120) -> str:
    response = _call("basic.command.run", cmd=cmd, timeout=timeout)
    if response.get("ok") is not True:
        raise AssertionError(f"command failed: {response.get('error')}")
    result = response.get("result")
    if isinstance(result, dict):
        if result.get("returncode") != 0:
            raise AssertionError(f"command rc != 0: {response}")
        return str(result.get("stdout") or "")
    raise AssertionError(f"bad command response: {response}")


def _upload_text(local: Path, remote: str) -> None:
    response = _call(
        "basic.file.upload", local_path=str(local), remote_path=remote,
        timeout=120)
    if response.get("ok") is not True:
        raise AssertionError(
            f"upload {local} -> {remote} failed: {response.get('error')}")


def main() -> int:
    global API, TOKEN
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default=API)
    parser.add_argument("--token", default=TOKEN)
    parser.add_argument("--out", default=str(
        ROOT / "test" / "artifacts" / "evidence" /
        "p098-timeout-green.json"))
    args = parser.parse_args()
    API, TOKEN = args.api, args.token

    stamp = int(time.time() * 1000)
    run_dir = f"{RUN_DIR}/p098-timeout-{stamp}"
    job_id = f"p098_timeout_{stamp}"
    remote_tool = f"{RUN_DIR}/p098-sleep-{stamp}.sh"
    local_tool = (
        ROOT / "test" / "artifacts" / "tmp" /
        f"p098-sleep-{stamp}.sh")
    evidence: dict[str, Any] = {
        "api": API,
        "token": TOKEN,
        "run_dir": run_dir,
        "job_id": job_id,
        "tool": remote_tool,
        "result": None,
    }
    started = time.monotonic()
    try:
        _command(
            f"test -r {shlex.quote(DRC_DECK)} && echo env-ok",
            timeout=60)
        local_tool.parent.mkdir(parents=True, exist_ok=True)
        # launcher 会用 `timeout <request.timeout>` 包工具；忽略 TERM 才能
        # 稳定制造“package 已到 deadline、后台进程仍活着”的 P-098 场景。
        local_tool.write_text(
            "#!/bin/sh\ntrap '' TERM\nwhile true; do sleep 1; done\n",
            encoding="ascii", newline="\n")
        _upload_text(local_tool, remote_tool)
        _command(
            f"chmod +x {shlex.quote(remote_tool)} && "
            f"test -x {shlex.quote(remote_tool)} && echo tool-ok",
            timeout=60)
        response = _call(
            "calibre.drc",
            gds=GDS, top=TOP, deck=DRC_DECK, run_dir=run_dir,
            calibre_bin=remote_tool, job_id=job_id,
            hier=True, turbo=1, blocking=True, poll_interval=1, timeout=5)
        elapsed = round(time.monotonic() - started, 3)
        value = (response.get("value") or {}) if isinstance(response, dict) else {}
        status = _value(
            "calibre.status", job_id=job_id, run_dir=run_dir)
        pgrep_pattern = f"[p]098-sleep-{stamp}.sh"
        alive = _command(
            f"pgrep -f {shlex.quote(pgrep_pattern)} | head -3 || true",
            timeout=60).strip()
        evidence["result"] = {
            "ok": response.get("ok"),
            "elapsed_s": elapsed,
            "status": value.get("status"),
            "progress_status": (value.get("progress") or {}).get("status"),
            "failure_kind": value.get("failure_kind"),
            "status_snapshot": status,
            "alive": bool(alive),
        }
        if elapsed > 20:
            raise AssertionError(
                f"P-098：blocking 超时用了 {elapsed}s（应远小于 timeout 上限）")
        if value.get("status") != "timeout":
            raise AssertionError(
                f"P-098：blocking 到期未返回 status=timeout: {value}")
        if (value.get("progress") or {}).get("status") != "timeout":
            raise AssertionError(
                f"P-098：progress 未标记 timeout: {value.get('progress')}")
        if not alive:
            raise AssertionError("P-098：超过 deadline 不应杀掉后台作业")
        if status.get("status") not in ("running", "unknown"):
            raise AssertionError(
                f"P-098：后台假工具应仍被 status 观测到: {status}")
        evidence["result"]["case"] = "PASS"
        rc = 0
    except Exception as exc:  # noqa: BLE001 - 记录失败现场
        evidence["result"] = {
            "case": f"FAIL: {type(exc).__name__}: {exc}",
        }
        print(f"FAIL: {type(exc).__name__}: {exc}", flush=True)
        rc = 1
    finally:
        # 只回收本探针自己的 sleeping 假工具，不碰真实 Calibre 作业。
        kill_pattern = f"[p]098-sleep-{stamp}.sh"
        _call(
            "basic.command.run",
            cmd=f"pkill -9 -f {shlex.quote(kill_pattern)} 2>/dev/null || true",
            timeout=30)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    print(f"evidence: {out_path}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
