# === TB 注释头（规范见 test/docs/写TB规范.md §0）=====================
# 作者: 设计/Codex
# 最后改动: 2026-09-30 16:06
# 依赖: wsl-gent disposable CIW（destb1, port 64600, token vb-destb1）
# =======================================================================
"""Disposable-CIW real test: C06 log flushing + P-086 dirty gate recovery.

The test uses one isolated disposable CIW.  It first runs the existing C06
semantic matrix through a direct daemon transport, then drives the middle
BusinessServer through:

    delivered timeout -> dirty -> probe/busy -> CIW restart -> probe idle
    -> next SKILL succeeds

No permanent vblog/8127 instance is touched.
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
PACKAGES = ROOT / "test" / "live" / "packages"
for path in (SRC, PACKAGES):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from common.paths import init_work_dir, registry_path  # noqa: E402
from common.registry import UserEntry, load_registry  # noqa: E402
from common.skill_client import SkillClient  # noqa: E402
from pyapi.models import ExecutionStatus  # noqa: E402
from skill_log_semantics_e2e_tests import run_suite as run_c06_suite  # noqa: E402
from transport.middle import BusinessServer  # noqa: E402


def _run(cmd: list[str], timeout: float = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
        **({"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}),
    )


def _ssh(host: str, command: str, timeout: float = 120) -> subprocess.CompletedProcess:
    return _run(["ssh", "-o", "BatchMode=yes", host, command], timeout=timeout)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class DirectDaemonTransport:
    """Map the C06 HTTP operation shape onto the disposable daemon."""

    def __init__(self, host: str, local_port: int, token: str) -> None:
        self.host = host
        self.local_port = local_port
        self.token = token

    def _skill(self, payload: dict) -> dict:
        client = SkillClient(
            host="127.0.0.1",
            port=self.local_port,
            timeout=float(payload.get("timeout") or 600),
            token=self.token,
            log_level=payload.get("log_level", "all"),
        )
        result = client.execute_skill(
            payload["skill_code"],
            timeout=payload.get("timeout"),
            log_level=payload.get("log_level"),
        )
        body = {
            "status": result.status.value,
            "output": result.output,
            "errors": list(result.errors),
            "warnings": list(result.warnings),
            "CDSlog": result.log,
            "execution_time": result.execution_time,
        }
        return {"ok": result.ok, "result": body,
                "error": None if result.ok else "; ".join(result.errors)}

    def _command(self, payload: dict) -> dict:
        proc = _ssh(self.host, payload["cmd"], timeout=payload.get("timeout") or 120)
        result = {
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "kind": "command",
        }
        return {"ok": proc.returncode == 0, "result": result,
                "error": None if proc.returncode == 0 else proc.stderr.strip()}

    def _upload(self, payload: dict) -> dict:
        proc = _run([
            "scp", "-q", payload["local_path"],
            f"{self.host}:{payload['remote_path']}",
        ], timeout=payload.get("timeout") or 120)
        result = {"returncode": proc.returncode, "stdout": "", "stderr": proc.stderr}
        return {"ok": proc.returncode == 0, "result": result,
                "error": None if proc.returncode == 0 else proc.stderr.strip()}

    def call(self, payload: dict) -> dict:
        operation = payload.get("operation")
        if operation == "basic.skill.execute":
            return self._skill(payload)
        if operation == "basic.command.run":
            return self._command(payload)
        if operation == "basic.file.upload":
            return self._upload(payload)
        return {"ok": False, "error": f"unsupported operation: {operation}"}


def _cdslog_increment(transport: DirectDaemonTransport, skill_code: str) -> str:
    response = transport.call({"operation": "basic.skill.execute",
                               "skill_code": skill_code, "log_level": "all"})
    if response.get("ok") is not True:
        raise AssertionError(f"skill failed: {response.get('error')}")
    result = response.get("result") or {}
    return str(result.get("CDSlog") or "")


def _check_silent_increment(transport: DirectDaemonTransport) -> dict:
    """修复回归：IL 补的行终止符不得漏进返回值。

    静默请求（1+1）的增量必须仍是空串；带 print 的请求必须拿到自己的标记
    且不把它留给下一条请求；off 请求也补终止符（不返回），同样不留给下一条。
    """
    transport.call({"operation": "basic.skill.execute",
                    "skill_code": 'printf("\\n")', "log_level": "all"})
    silent = _cdslog_increment(transport, "1+1")
    mark = f"C06S_{time.strftime('%H%M%S')}"
    printed = _cdslog_increment(transport, f'print("{mark}")')
    after = _cdslog_increment(transport, "1+1")
    off_mark = f"C06O_{time.strftime('%H%M%S')}"
    off_resp = transport.call({"operation": "basic.skill.execute",
                               "skill_code": f'print("{off_mark}")',
                               "log_level": "off"})
    off_log = str((off_resp.get("result") or {}).get("CDSlog") or "")
    off_after = _cdslog_increment(transport, "1+1")
    return {
        "silent_prefix_len": len(silent),
        "silent_prefix": silent[:80],
        "print_log": printed[:200],
        "after_log": after[:200],
        "mark": mark,
        "off_mark": off_mark,
        "off_print_log": off_log,
        "off_after_log": off_after[:120],
        "ok": (
            silent == ""
            and mark in printed and mark not in after and after == ""
            and off_resp.get("ok") is True
            and off_log == "" and off_mark not in off_after and off_after == ""
        ),
    }


def _check_error_extraction(transport: DirectDaemonTransport) -> dict:
    """errset 评估：log 块的 errset 不得污染用户错误的提取。

    用户 SKILL 先 print 再抛错：NAK 载荷必须是原始 SKILL 错误（不是 flush
    错误），print 落同一请求且不留给下一条；log_level=off 时错误同样完整。
    """
    mark = f"C06E_{time.strftime('%H%M%S')}"
    skill = f'progn(print("{mark}") boom_c06())'
    with_log = transport.call({"operation": "basic.skill.execute",
                               "skill_code": skill, "log_level": "all"})
    after = _cdslog_increment(transport, "1+1")
    without_log = transport.call({"operation": "basic.skill.execute",
                                  "skill_code": skill, "log_level": "off"})
    with_result = with_log.get("result") or {}
    off_result = without_log.get("result") or {}
    with_errors = list(with_result.get("errors") or [])
    off_errors = list(off_result.get("errors") or [])
    with_text = str(with_result.get("CDSlog") or "")
    off_text = str(off_result.get("CDSlog") or "")

    def is_original_boom(errors: list[str]) -> bool:
        return any("undefined function" in e and "boom_c06" in e for e in errors)

    return {
        "mark": mark,
        "with_log_ok_false": with_log.get("ok") is False,
        "with_log_errors": with_errors,
        "with_log_CDSlog": with_text[:200],
        "after_log": after[:120],
        "off_errors": off_errors,
        "off_CDSlog": off_text,
        "ok": (
            with_log.get("ok") is False
            and is_original_boom(with_errors)
            and mark in with_text
            and mark not in after
            and without_log.get("ok") is False
            and is_original_boom(off_errors)
            and off_text == ""
        ),
    }


def _check_load_path(transport: DirectDaemonTransport) -> dict:
    """load 路径（skill 含换行 → daemon 写临时 .il 再 load）同类问题排查。

    覆盖：无换行 print 同请求归属、off 也补终止符（下一条不串场）、
    load 内 print 后抛错时错误仍被检出且原错误可从 CDSlog 读出。
    """
    stamp = time.strftime("%H%M%S")
    mark_all = f"C06L_A_{stamp}"
    mark_off = f"C06L_C_{stamp}"
    mark_err = f"C06L_E_{stamp}"
    all_resp = transport.call({
        "operation": "basic.skill.execute",
        "skill_code": f'progn(\nprint("{mark_all}"))', "log_level": "all"})
    off_resp = transport.call({
        "operation": "basic.skill.execute",
        "skill_code": f'progn(\nprint("{mark_off}"))', "log_level": "off"})
    after = _cdslog_increment(transport, "1+1")
    err_resp = transport.call({
        "operation": "basic.skill.execute",
        "skill_code": f'progn(\nprint("{mark_err}")\nboom_c06_load())',
        "log_level": "all"})
    all_text = str((all_resp.get("result") or {}).get("CDSlog") or "")
    off_text = str((off_resp.get("result") or {}).get("CDSlog") or "")
    err_result = err_resp.get("result") or {}
    err_text = str(err_result.get("CDSlog") or "")
    return {
        "mark_all": mark_all,
        "mark_off": mark_off,
        "mark_err": mark_err,
        "all_CDSlog": all_text[:160],
        "off_CDSlog": off_text,
        "after_log": after[:120],
        "error_payload": list(err_result.get("errors") or []),
        "error_CDSlog": err_text[:240],
        "ok": (
            all_resp.get("ok") is True and mark_all in all_text
            and off_resp.get("ok") is True and off_text == ""
            and mark_off not in after and after == ""
            and err_resp.get("ok") is False
            and mark_err in err_text
            and "*Error* eval: undefined function - boom_c06_load" in err_text
        ),
    }


def _wait_port(port: int, timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"local forwarded port {port} not ready")


def _restart_destb1(host: str, port: int, token: str) -> None:
    stop = (
        "bash ~/.virtuoso-bridge/disposable/bin/stop_disposable_ciw.sh "
        f"destb1 {port} {token}"
    )
    _ssh(host, stop, timeout=90)
    start = (
        "VB_RESOURCES=$HOME/.virtuoso-bridge/disposable/ramic "
        "bash ~/.virtuoso-bridge/disposable/bin/start_disposable_ciw.sh "
        f"destb1 {port}"
    )
    started = _ssh(host, start, timeout=150)
    if started.returncode != 0:
        raise RuntimeError(f"start disposable CIW failed: {started.stderr[-400:]}")
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        ping = _ssh(
            host,
            "python3 ~/.virtuoso-bridge/disposable/bin/daemon_ping.py "
            f"{port} {token} '1+1'",
            timeout=20,
        )
        if ping.returncode == 0 and "OK" in ping.stdout:
            return
        time.sleep(2)
    raise RuntimeError("disposable daemon did not recover after restart")


def _business_server(work_dir: Path, local_port: int, token: str) -> BusinessServer:
    init_work_dir(str(work_dir))
    registry = load_registry(registry_path())
    entry = UserEntry(token=token, mode="local")
    entry.runtime.thread_pool_size = 4
    entry.roles.daemon.daemon_port = local_port
    entry.roles.daemon.local_port = local_port
    registry.register("destb1", entry)
    return BusinessServer()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="wsl-gent")
    parser.add_argument("--remote-port", type=int, default=64600)
    parser.add_argument("--token", default="vb-destb1")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    # The disposable CIW may have been started before the current resources
    # were synced.  Restart first so C06/P086 run against this checkout.
    _restart_destb1(args.host, args.remote_port, args.token)
    local_port = _free_port()
    tunnel = subprocess.Popen(
        ["ssh", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes",
         "-N", "-L", f"127.0.0.1:{local_port}:127.0.0.1:{args.remote_port}",
         args.host],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    evidence: dict = {"host": args.host, "remote_port": args.remote_port,
                      "token": args.token, "local_port": local_port,
                      "startup_restart_ok": True}
    try:
        _wait_port(local_port)
        c06_results, c06_evidence = run_c06_suite(
            DirectDaemonTransport(args.host, local_port, args.token)
        )
        evidence["c06"] = c06_evidence
        evidence["c06_results"] = [
            {"case": name, "status": status} for name, status in c06_results
        ]
        evidence["c06_silent_increment"] = _check_silent_increment(
            DirectDaemonTransport(args.host, local_port, args.token)
        )
        evidence["c06_error_extraction"] = _check_error_extraction(
            DirectDaemonTransport(args.host, local_port, args.token)
        )
        evidence["c06_load_path"] = _check_load_path(
            DirectDaemonTransport(args.host, local_port, args.token)
        )

        work_dir = Path(tempfile.mkdtemp(prefix="vb-p086-"))
        server = _business_server(work_dir, local_port, args.token)
        try:
            # Phase 1（1A）：自动恢复，不重启。hiSleep(5) 超时后 dirty；
            # 旧 SKILL 结束（watchdog SIGINT 可能提前中断它）后，middle 的
            # probe 应确认 idle 并放行下一条，不许“卡到重启”。
            started = time.monotonic()
            timed_out = server.execute_skill("hiSleep(5)", timeout=1, token=args.token)
            evidence["dirty_after_timeout"] = args.token in server._skill_dirty
            recovered = server.execute_skill("1+3", timeout=20, token=args.token)
            evidence["recovered_without_restart"] = {
                "ok": recovered.ok,
                "output": recovered.output,
                "dirty": args.token in server._skill_dirty,
                "elapsed_s": round(time.monotonic() - started, 2),
            }
            auto_ok = (
                bool(timed_out and not timed_out.ok)
                and evidence["dirty_after_timeout"]
                and recovered.ok
                and recovered.output.strip().strip('"') == "4"
                and not evidence["recovered_without_restart"]["dirty"]
            )

            # Phase 2：daemon 进程重启 → dirty 清零（兜底路径仍可用）。
            timed_out2 = server.execute_skill("hiSleep(30)", timeout=1, token=args.token)
            evidence["dirty_before_restart"] = args.token in server._skill_dirty
            _restart_destb1(args.host, args.remote_port, args.token)
            recovered2 = server.execute_skill("1+3", timeout=10, token=args.token)
            evidence["recovered_after_restart"] = {
                "ok": recovered2.ok,
                "output": recovered2.output,
                "dirty": args.token in server._skill_dirty,
            }
            restart_ok = (
                bool(timed_out2 and not timed_out2.ok)
                and evidence["dirty_before_restart"]
                and recovered2.ok
                and recovered2.output.strip().strip('"') == "4"
                and not evidence["recovered_after_restart"]["dirty"]
            )
            p086_ok = auto_ok and restart_ok
        finally:
            server.close()
        evidence["p086_ok"] = p086_ok
        c06_ok = (
            bool(c06_results)
            and all(status == "PASS" for _, status in c06_results)
            and evidence["c06_silent_increment"]["ok"]
            and evidence["c06_error_extraction"]["ok"]
            and evidence["c06_load_path"]["ok"]
        )
        evidence["c06_ok"] = c06_ok
        out = Path(args.out) if args.out else (
            ROOT / "test" / "artifacts" / "evidence" /
            f"disposable-c06-p086-{time.strftime('%Y%m%dT%H%M%S')}.json"
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        print(json.dumps({"c06_ok": c06_ok, "p086_ok": p086_ok,
                          "evidence": str(out)}, ensure_ascii=False))
        return 0 if c06_ok and p086_ok else 1
    finally:
        tunnel.terminate()
        try:
            tunnel.wait(timeout=3)
        except subprocess.TimeoutExpired:
            tunnel.kill()


if __name__ == "__main__":
    raise SystemExit(main())
