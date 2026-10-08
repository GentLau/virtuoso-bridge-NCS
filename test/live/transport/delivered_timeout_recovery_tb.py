# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-30 21:45
# 依赖: wsl-gent disposable CIW（destb2, port 64601, token vb-destb2）+ SSH 免密
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
# ① 环境检查：`ssh wsl-gent` 免密可用 + disposable 起停脚本在靶机上 + 本机可开 SSH 本地转发；
# ② 构建：起**专属** disposable 实例 destb2（**不复用常驻 vblog，也不占用他人 destb1**），
#    并开 `ssh -N -L <local>:127.0.0.1:64601` 本地转发；本 TB 的注册表用**自己**的
#    work-dir（`test/artifacts/env/delivered-timeout`，可重复跑：overwrite=True），
#    不写常驻 log-vblog 的注册表；
# ③ 最终检查：直连 daemon `1+1` == OK，且 **middle 层** 的 `1+1` 也 ok（基线）；
# ④ 只做被测动作：经 middle 投递一个**注定超时**的长 SKILL（`hiSleep(6)` + timeout=1）；
# ⑤ 读回比对（目标行为；**2026-09-30 修复 `97baf13` 后本 TB 已全绿，作为回归钉**）：
#    * ① 超时必须**快速**失败且语义为 timeout；
#    * ② 之后**不需要重启 CIW**，下一条正常请求必须在有界时间内成功（自动 probe idle → 清 dirty）；
#    * ③ 再等一拍仍可用（不是"偶发通过"）。
#    修复前实测（2026-09-30 早）：实例被判 dirty 后永久 busy（直连 daemon 报 `SKILL channel busy`），
#    必须重启 CIW 才恢复 —— 用户判定为 bug 并由设计修复（probe 收齐迟到帧后自动恢复）。
#    修复后实测：`test/artifacts/evidence/round9/delivered-timeout-recovery.json` 5/5 全绿。
# ⑥ 收尾：停掉 destb2（kill CIW + 清根）并关闭本地转发；不触碰常驻实例。
"""投递超时后的自恢复（P-086 家族）真机红钉：**不得把实例永久置忙**。

背景：设计侧已实现"投递超时 → 标记 dirty → 下次请求先 probe idle"的机制，
但实测（2026-09-30）在 disposable 实例上，超时后：
  * daemon 直连报 `SKILL channel busy`；
  * 经 middle 的后续请求持续 `SKILL execution timed out`；
  * 只有重启 CIW 才能恢复。
用户已判定这是 bug 并在修；本 TB 是**测试侧回归钉**。2026-09-30 修复 `97baf13`
（"delivered-timeout 后由 probe 收齐迟到帧自动恢复"）落地后复跑 5/5 全绿；日后若
`DT-02/DT-03` 再红即回归，按 bug 处理。

用法::

    PYTHONPATH=src python test/live/transport/delivered_timeout_recovery_tb.py \
        --out test/artifacts/evidence/round9/delivered-timeout-recovery.json
"""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from common.paths import init_work_dir, registry_path  # noqa: E402
from common.registry import UserEntry, load_registry  # noqa: E402
from transport.middle import BusinessServer  # noqa: E402

DEFAULT_HOST = "wsl-gent"
DEFAULT_REMOTE_PORT = 64601
DEFAULT_TOKEN = "vb-destb2"
DEFAULT_NAME = "destb2"
BIN = "$HOME/.virtuoso-bridge/disposable/bin"
RES = "$HOME/.virtuoso-bridge/disposable/ramic"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _ssh(host: str, script: str, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(["ssh", "-o", "BatchMode=yes", host, script],
                          capture_output=True, text=True, timeout=timeout,
                          encoding="utf-8", errors="replace")


def _start_instance(host: str, name: str, port: int) -> tuple[bool, str]:
    script = (f"bash {BIN}/stop_disposable_ciw.sh {name} {port} vb-{name} >/dev/null 2>&1 || true; "
              f"VB_RESOURCES={RES} bash {BIN}/start_disposable_ciw.sh {name} {port}")
    proc = _ssh(host, script, timeout=600)
    text = (proc.stdout or "") + (proc.stderr or "")
    ok = "NAME=" in text and f"PORT={port}" in text
    return ok, text[-300:]


def _ping(host: str, port: int, token: str) -> str:
    proc = _ssh(host, f"python3 {BIN}/daemon_ping.py {port} {token} '1+1'", timeout=60)
    return ((proc.stdout or "") + (proc.stderr or "")).strip()[:120]


def _stop_instance(host: str, name: str, port: int) -> None:
    _ssh(host, f"bash {BIN}/stop_disposable_ciw.sh {name} {port} vb-{name} "
               f">/dev/null 2>&1 || true", timeout=180)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--remote-port", type=int, default=DEFAULT_REMOTE_PORT)
    parser.add_argument("--token", default=DEFAULT_TOKEN)
    parser.add_argument("--name", default=DEFAULT_NAME)
    parser.add_argument("--work-dir",
                        default=str(ROOT / "test" / "artifacts" / "env"
                                    / "delivered-timeout"))
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    results: list[tuple[str, str]] = []
    evidence: dict = {"host": args.host, "remote_port": args.remote_port,
                      "token": args.token, "cases": {}}
    server_ref: dict = {}
    forward: subprocess.Popen | None = None
    local_port = _free_port()

    def run(name: str, func) -> object:
        try:
            value = func()
        except Exception as exc:  # noqa: BLE001
            results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
            print(f"FAIL    {name}: {type(exc).__name__}: {exc}", flush=True)
            return None
        results.append((name, "PASS"))
        print(f"PASS    {name}", flush=True)
        return value

    def case_env() -> None:
        proc = _ssh(args.host, "echo ok", timeout=60)
        assert proc.returncode == 0 and "ok" in (proc.stdout or ""), \
            f"ssh {args.host} 不可用: {proc.stderr[:120]}"
        probe = _ssh(args.host, f"test -x {BIN}/start_disposable_ciw.sh "
                                f"&& test -f {RES}/ramic_bridge.il && echo READY", timeout=60)
        assert "READY" in (probe.stdout or ""), f"disposable 脚本/资源缺失: {probe.stdout[:120]}"
        ok, tail = _start_instance(args.host, args.name, args.remote_port)
        assert ok, f"{args.name} 启动失败: {tail}"
        ping = _ping(args.host, args.remote_port, args.token)
        assert ping.startswith("OK"), f"daemon 探活失败: {ping}"
        evidence["cases"]["env"] = {"ping": ping}

    def case_middle_baseline() -> None:
        nonlocal forward
        forward = subprocess.Popen(
            ["ssh", "-N", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes",
             "-L", f"{local_port}:127.0.0.1:{args.remote_port}", args.host],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        for _ in range(20):
            with socket.socket() as probe:
                probe.settimeout(0.5)
                if probe.connect_ex(("127.0.0.1", local_port)) == 0:
                    break
            time.sleep(0.5)
        init_work_dir(args.work_dir)
        registry = load_registry(registry_path())
        entry = UserEntry(token=args.token, mode="local")
        entry.runtime.thread_pool_size = 4
        entry.roles.daemon.daemon_port = local_port
        entry.roles.daemon.local_port = local_port
        # 可重复跑：同一 work-dir（TB 自有）里覆盖同名 fixture 用户。
        registry.register("delivered_timeout_tb", entry, overwrite=True)
        server = BusinessServer()
        baseline = server.execute_skill("1+1", token=args.token, timeout=30)
        assert baseline.ok, f"middle 基线失败: {baseline.errors}"
        server_ref["server"] = server
        evidence["cases"]["middle_baseline"] = {"output": str(baseline.output)[:40]}

    def case_delivered_timeout() -> None:
        server = server_ref.get("server")
        assert server is not None, "前置未完成"
        started = time.time()
        result = server.execute_skill("hiSleep(6)", token=args.token, timeout=1)
        elapsed = round(time.time() - started, 2)
        errors = "; ".join(result.errors or [])
        evidence["cases"]["delivered_timeout"] = {
            "ok": result.ok, "errors": errors[:160], "elapsed_s": elapsed}
        assert not result.ok, "长 SKILL 必须超时失败"
        assert "timeout" in errors.lower() or "timed out" in errors.lower(), \
            f"失败语义应为超时（实测 {errors[:120]!r}）"
        assert elapsed < 6, f"超时必须快速返回（实测 {elapsed}s）"

    def case_recovery_without_restart() -> None:
        server = server_ref.get("server")
        assert server is not None, "前置未完成"
        started = time.time()
        result = server.execute_skill("1+1", token=args.token, timeout=30)
        elapsed = round(time.time() - started, 2)
        probe = _ping(args.host, args.remote_port, args.token)
        evidence["cases"]["recovery_after_timeout"] = {
            "ok": result.ok, "errors": "; ".join(result.errors or [])[:160],
            "elapsed_s": elapsed, "daemon_ping": probe}
        assert result.ok, (
            "投递超时后**必须能自恢复**（无需重启 CIW），实测仍失败："
            f"{'; '.join(result.errors or [])[:140]!r}；daemon 直连={probe!r}")

    def case_still_usable() -> None:
        server = server_ref.get("server")
        assert server is not None, "前置未完成"
        time.sleep(10)
        result = server.execute_skill("2+2", token=args.token, timeout=30)
        evidence["cases"]["still_usable"] = {
            "ok": result.ok, "errors": "; ".join(result.errors or [])[:120]}
        assert result.ok, f"实例应保持可用: {'; '.join(result.errors or [])[:120]}"

    run("DT-ENV 环境（ssh + 脚本 + destb2 起停 + daemon 探活）", case_env)
    run("DT-BASE middle 基线（1+1 经 middle）", case_middle_baseline)
    run("DT-01 投递超时（hiSleep(6)+timeout=1 快速失败）", case_delivered_timeout)
    run("DT-02 超时后自恢复（不重启 CIW）【目标行为·当前红钉】", case_recovery_without_restart)
    run("DT-03 恢复后仍可用（再等 10s）", case_still_usable)

    if forward is not None:
        forward.terminate()
        try:
            forward.wait(timeout=10)
        except subprocess.TimeoutExpired:
            forward.kill()
    _stop_instance(args.host, args.name, args.remote_port)

    failures = [name for name, status in results if status != "PASS"]
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        evidence["results"] = [{"case": name, "status": status} for name, status in results]
        out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        print(f"evidence: {out}")
    print(f"{len(results) - len(failures)}/{len(results)} 通过"
          + (f"；失败 {failures}" if failures else ""))
    return 0 if not failures and results else 1


if __name__ == "__main__":
    raise SystemExit(main())
