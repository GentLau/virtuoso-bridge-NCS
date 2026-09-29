# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-29 18:01
# 依赖: 无
# =======================================================================
"""P-093 / P-094 半真机回归：flat DRC 不再带 ``-turbo``，秒退作业快速报 failed。

六步流程（test/docs/写TB规范.md §1）：
① 环境检查 = 提交前确认 PDK deck / GDS / command role 可见；
②③ 基线 = 每次新建独立 run_dir，并读回 launcher 确认 flat argv；
④ 只做被测动作：一次 flat 正例、一次坏 deck 秒退负例；
⑤ 读回比对：状态、failure_kind、日志原文、launcher 中不含 ``-turbo``；
⑥ 不清理现场（run_dir 保留，便于 review）。

P-093 验收：flat DRC 的 launcher 不含 ``-turbo``，工具不再打
``The -turbo option is not valid``，任务进入终态。
P-094 验收：坏 deck 的 Calibre 作业秒退后，``blocking=true`` 应快速返回
``status=failed``，且 ``failure_kind`` / ``log_tail`` 带可归因信息。
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
LOCAL_TMP = ROOT / "test" / "artifacts" / "tmp" / "calibre-probes"


def _call(operation: str, **fields: Any) -> dict[str, Any]:
    body = json.dumps(
        {"operation": operation, "token": TOKEN, **fields},
        ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        API, data=body,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=1200) as response:
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


def _status(job_id: str, run_dir: str) -> dict[str, Any]:
    return _value("calibre.status", job_id=job_id, run_dir=run_dir)


def _log_text(run_dir: str) -> str:
    return _command(
        f"for f in {shlex.quote(run_dir)}/*.log; do "
        "[ -f \"$f\" ] && { echo \"== $f\"; cat \"$f\"; }; done 2>/dev/null "
        "|| true", timeout=120)


def _upload_text(local: Path, remote: str) -> None:
    response = _call(
        "basic.file.upload", local_path=str(local), remote_path=remote,
        timeout=120)
    if response.get("ok") is not True:
        raise AssertionError(
            f"upload {local} -> {remote} failed: {response.get('error')}")


def _wait_terminal(job_id: str, run_dir: str, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = _status(job_id, run_dir)
        if last.get("status") in ("completed", "failed"):
            return last
        time.sleep(1)
    return {**last, "status": "timeout"}


def _flat_case(stamp: int, evidence: dict[str, Any]) -> None:
    run_dir = f"{RUN_DIR}/p093-flat-{stamp}"
    job_id = f"p093_flat_{stamp}"
    started = _value(
        "calibre.drc",
        gds=GDS, top=TOP, deck=DRC_DECK, run_dir=run_dir,
        hier=False, turbo=2, job_id=job_id,
        blocking=False, timeout=1200)
    if started.get("job_id") != job_id:
        raise AssertionError(f"flat DRC 未返回 job_id: {started}")
    launcher = _command(
        f"grep -n -- '-turbo' {shlex.quote(run_dir + '/launch.sh')} "
        "2>/dev/null || true", timeout=60)
    evidence["flat"] = {
        "job_id": job_id,
        "run_dir": run_dir,
        "launcher_turbo_hits": launcher.strip(),
    }
    if launcher.strip():
        raise AssertionError(
            f"P-093：flat DRC launcher 仍含 -turbo: {launcher.strip()}")
    state = _wait_terminal(job_id, run_dir, timeout=600)
    log = _log_text(run_dir)
    evidence["flat"].update({
        "status": state.get("status"),
        "failure_kind": state.get("failure_kind"),
        "log_tail": log[-1200:],
    })
    if "-turbo option is not valid" in log:
        raise AssertionError("P-093：Calibre 仍报 flat 模式不接受 -turbo")
    if state.get("status") != "completed":
        raise AssertionError(
            f"flat DRC 未完成: status={state.get('status')} "
            f"failure_kind={state.get('failure_kind')} "
            f"log={log[-400:]}")


def _quick_fail_case(stamp: int, evidence: dict[str, Any]) -> None:
    run_dir = f"{RUN_DIR}/p094-quickfail-{stamp}"
    deck_dir = f"{RUN_DIR}/p094-bad-deck-dir-{stamp}"
    remote_deck = f"{deck_dir}/bad.cal"
    local = LOCAL_TMP / f"p094-bad-deck-{stamp}.cal"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(
        "\n".join([
            f'LAYOUT PATH "{GDS}" "{TOP}"',
            f'LAYOUT PRIMARY "{TOP}"',
            "LAYOUT SYSTEM GDSII",
            'DRC RESULTS DATABASE "drc.results" ASCII',
            "THIS_IS_NOT_A_VALID_CALIBRE_COMMAND",
            "",
        ]),
        encoding="utf-8",
        newline="\n")
    _command(f"mkdir -p {shlex.quote(deck_dir)} && echo deck-dir-ok",
             timeout=60)
    _upload_text(local, remote_deck)
    job_id = f"p094_bad_{stamp}"
    started_at = time.monotonic()
    response = _call(
        "calibre.drc",
        gds=GDS, top=TOP, deck=remote_deck, run_dir=run_dir,
        job_id=job_id, blocking=True, poll_interval=1, timeout=60)
    elapsed = round(time.monotonic() - started_at, 3)
    value = (response.get("value") or {}) if isinstance(response, dict) else {}
    log = _log_text(run_dir)
    evidence["quick_fail"] = {
        "ok": response.get("ok"),
        "elapsed_s": elapsed,
        "job_id": job_id,
        "run_dir": run_dir,
        "status": value.get("status"),
        "failure_kind": value.get("failure_kind"),
        "log_tail": log[-1200:],
    }
    if response.get("ok") is True:
        raise AssertionError(f"P-094：坏 deck 作业不应 ok=true: {response}")
    if elapsed > 30:
        raise AssertionError(
            f"P-094：秒退作业阻塞了 {elapsed}s（应 <30s 返回）")
    if value.get("status") != "failed":
        raise AssertionError(
            f"P-094：坏 deck 状态不是 failed: {value}")
    if not value.get("failure_kind"):
        raise AssertionError(f"P-094：failure_kind 为空: {value}")
    if not any(marker in log for marker in ("ERROR:", "FATAL")):
        raise AssertionError(f"P-094：日志未回带错误原文: {log[-500:]}")


def main() -> int:
    global API, TOKEN
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default=API)
    parser.add_argument("--token", default=TOKEN)
    parser.add_argument("--out", default=str(
        ROOT / "test" / "artifacts" / "evidence" /
        "p093-p094-quickfail-green.json"))
    args = parser.parse_args()
    API, TOKEN = args.api, args.token

    evidence: dict[str, Any] = {
        "api": API,
        "token": TOKEN,
        "deck": DRC_DECK,
        "gds": GDS,
        "top": TOP,
        "results": [],
    }
    stamp = int(time.time() * 1000)
    try:
        # 第 1 步：命令角色必须能看到 GDS 和 PDK deck。
        _command(
            f"test -r {shlex.quote(GDS)} && test -r {shlex.quote(DRC_DECK)} "
            "&& echo env-ok", timeout=60)
        _flat_case(stamp, evidence)
        _quick_fail_case(stamp, evidence)
        evidence["results"] = [
            {"case": "P-093 flat DRC 无 -turbo 并完成", "status": "PASS"},
            {"case": "P-094 坏 deck 秒退→status=failed", "status": "PASS"},
        ]
        rc = 0
    except Exception as exc:  # noqa: BLE001 - 探针要把失败现场写盘
        evidence["results"] = [
            {"case": "P-093/P-094", "status": f"FAIL: {type(exc).__name__}: {exc}"},
        ]
        print(f"FAIL: {type(exc).__name__}: {exc}", flush=True)
        rc = 1
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    for row in evidence["results"]:
        print(f"{row['status']:6}  {row['case']}")
    print(f"evidence: {out_path}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
