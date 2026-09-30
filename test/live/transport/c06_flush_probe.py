# === TB 注释头（规范见 test/docs/写TB规范.md §0）=====================
# 作者: 设计/Codex
# 最后改动: 2026-09-30
# 依赖: wsl-gent disposable CIW（destb1, port 64600, token vb-destb1）
# =======================================================================
"""C06 单变量探针：找出**真正**把无换行 print 缓冲刷进 CDS.log 的调用。

目的与背景：C06 卡片建议在 `ramic_bridge.il` 的 `evalstring` 之后插
`errset(hiFlushInfo())`，但 disposable 真机上 hiFlushInfo / hiFlushCIW
都没能让同一请求的 CDSlog 变非空。本探针不改 IL：把候选 flush 调用**放进
用户 SKILL 载荷内部**（即 `evalstring` 内部、print 之后），由 IL 既有的
`lo_end = fileLength(hiGetLogFileName())` 窗口判定"文字有没有落进 CDS.log"。

六步流程：
  ① 环境检查：每条用例前 `1+1` 探活（daemon_ping）；
  ②③ 无需构建：每个标记带唯一时间戳；
  ④ 只做被测动作：print(MARK) + 一个候选 flush；
  ⑤ 读回比对：断言 MARK 是否出现在**该请求**的 CDSlog 窗口内；
  ⑥ 不改共享库/CIW 资源，结果落 JSON。

用法::

    PYTHONPATH=src python test/live/transport/c06_flush_probe.py --out <json>
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

from common.skill_client import SkillClient  # noqa: E402


def _run(cmd: list[str], timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
        **({"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}),
    )


def _ssh(host: str, command: str, timeout: float = 60) -> subprocess.CompletedProcess:
    return _run(["ssh", "-o", "BatchMode=yes", host, command], timeout=timeout)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_port(port: int, timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"local forwarded port {port} not ready")


# (case name, SKILL body; %(m)s = unique mark)
FLUSH_CASES: list[tuple[str, str]] = [
    ("baseline_no_flush", 'progn(print("%(m)s") 1)'),
    ("hiFlushInfo", 'progn(print("%(m)s") errset(hiFlushInfo()))'),
    ("hiFlushCIW", 'progn(print("%(m)s") errset(hiFlushCIW()))'),
    ("hiFlushLogFile", 'progn(print("%(m)s") errset(hiFlushLogFile()))'),
    ("hiFlush", 'progn(print("%(m)s") errset(hiFlush()))'),
    ("flush_stdout", 'progn(print("%(m)s") errset(flush(stdout)))'),
    ("drain_stdout", 'progn(print("%(m)s") errset(drain(stdout)))'),
    ("flush_ciw", 'progn(print("%(m)s") errset(flush(ciw)))'),
    ("hiFlushInfo_then_LogFile",
     'progn(print("%(m)s") errset(hiFlushInfo()) errset(hiFlushLogFile()))'),
    ("hiFlushCIW_then_LogFile",
     'progn(print("%(m)s") errset(hiFlushCIW()) errset(hiFlushLogFile()))'),
    ("hiFlushInfo_twice",
     'progn(print("%(m)s") errset(hiFlushInfo()) errset(hiFlushInfo()))'),
    # 换行对照（已知能立即落日志）
    ("printf_newline_control", 'progn(printf("%(m)s\\n"))'),
]

# round2：验证"evalstring 后补一个换行"作为修复原型的副作用（是否多出空行）。
APPEND_NEWLINE_CASES: list[tuple[str, str]] = [
    ("bare_newline_only", 'progn(printf("\\n"))'),
    ("silent_then_newline", 'progn(1+1 printf("\\n"))'),
    ("printf_newline_then_newline", 'progn(printf("%(m)s\\n") printf("\\n"))'),
    ("print_then_newline", 'progn(print("%(m)s") printf("\\n"))'),
    ("print_flushinfo_then_newline",
     'progn(print("%(m)s") errset(hiFlushInfo()) printf("\\n"))'),
    ("printciw_then_newline",
     'progn(print("%(m)s") errset(hiFlushCIW()) printf("\\n"))'),
    ("print_then_newline_then_logfile",
     'progn(print("%(m)s") printf("\\n") errset(hiFlushLogFile()))'),
]

# round3：候选"窗口/事件/刷新"调用，看有没有不用输出换行就能提交 partial line 的。
REFRESH_CASES: list[tuple[str, str]] = [
    ("hiRedraw_ciw", 'progn(print("%(m)s") errset(hiRedraw(hiGetCIWindow())))'),
    ("hiSynchronize_nil", 'progn(print("%(m)s") errset(hiSynchronize(nil)))'),
    ("hiSynchronize_t", 'progn(print("%(m)s") errset(hiSynchronize(t)))'),
    ("hiUpdate", 'progn(print("%(m)s") errset(hiUpdate()))'),
    ("hiRefreshTextWindow",
     'progn(print("%(m)s") errset(hiRefreshTextWindow(hiGetCIWindow())))'),
    ("hiInsertBlankCIWOutputPage",
     'progn(print("%(m)s") errset(hiInsertBlankCIWOutputPage()))'),
    ("hiFlushInfo_hiRedraw",
     'progn(print("%(m)s") errset(hiFlushInfo()) errset(hiRedraw(hiGetCIWindow())))'),
    ("hiRedraw_then_logfile",
     'progn(print("%(m)s") errset(hiRedraw(hiGetCIWindow())) errset(hiFlushLogFile()))'),
]

# round4：SKILL 端口层 flush。`printf` 写的是 poport（不是 stdout），
# `drain(port)` 是 SKILL 语言里等价的 fflush；验证它是否就是缺失的 flush 点。
PPORT_CASES: list[tuple[str, str]] = [
    ("drain_poport", 'progn(print("%(m)s") errset(drain(poport)))'),
    ("drain_no_arg", 'progn(print("%(m)s") errset(drain()))'),
    ("newline_poport", 'progn(print("%(m)s") errset(newline(poport)))'),
    ("silent_drain_poport", 'progn(1+1 errset(drain(poport)))'),
    ("bare_drain_poport", 'progn(errset(drain(poport)))'),
    ("printf_newline_drain_poport",
     'progn(printf("%(m)s\\n") errset(drain(poport)))'),
    ("drain_then_logfile",
     'progn(print("%(m)s") errset(drain(poport)) errset(hiFlushLogFile()))'),
]

# round5：探测"CIW 窗口文本长度"能否作为 pending 输出检测器（避免给静默请求注入空行）。
DETECT_CASES: list[tuple[str, str]] = [
    ("len_print_pending",
     'progn(let((w b a) w = hiGetCIWindow() b = hiGetTextSourceLength(w) '
     'print("%(m)s") a = hiGetTextSourceLength(w) list(b a w)))'),
    ("len_silent",
     'progn(let((w b a) w = hiGetCIWindow() b = hiGetTextSourceLength(w) '
     '1+1 a = hiGetTextSourceLength(w) list(b a w)))'),
    ("len_printf_newline",
     'progn(let((w b a) w = hiGetCIWindow() b = hiGetTextSourceLength(w) '
     'printf("%(m)s\\n") a = hiGetTextSourceLength(w) list(b a w)))'),
    ("idx_print_pending",
     'progn(let((w b a) w = hiGetCIWindow() b = hiGetCurrentIndex(w) '
     'print("%(m)s") a = hiGetCurrentIndex(w) list(b a)))'),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="wsl-gent")
    parser.add_argument("--remote-port", type=int, default=64600)
    parser.add_argument("--token", default="vb-destb1")
    parser.add_argument("--out", default="")
    parser.add_argument("--set", choices=("flush", "append", "refresh", "pport", "detect"),
                        default="flush")
    args = parser.parse_args(argv)
    cases = {"flush": FLUSH_CASES, "append": APPEND_NEWLINE_CASES,
             "refresh": REFRESH_CASES, "pport": PPORT_CASES, "detect": DETECT_CASES}[args.set]

    ping = _ssh(
        args.host,
        "python3 ~/.virtuoso-bridge/disposable/bin/daemon_ping.py "
        f"{args.remote_port} {args.token} '1+1'",
    )
    if ping.returncode != 0 or "OK" not in ping.stdout:
        raise SystemExit(f"environment check failed: {ping.stdout} {ping.stderr}")

    local_port = _free_port()
    tunnel = subprocess.Popen(
        ["ssh", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes",
         "-N", "-L", f"127.0.0.1:{local_port}:127.0.0.1:{args.remote_port}",
         args.host],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    stamp = time.strftime("%H%M%S")
    evidence: dict = {"stamp": stamp, "cases": []}
    try:
        _wait_port(local_port)
        for index, (name, template) in enumerate(cases):
            mark = f"C06P{index}_{stamp}"
            # 冲掉上一条用例可能残留的行缓冲（换行触发 flush），隔离本用例。
            purge_client = SkillClient(host="127.0.0.1", port=local_port,
                                       timeout=30, token=args.token, log_level="all")
            purge_client.execute_skill('printf("\\n")', timeout=30, log_level="all")
            client = SkillClient(host="127.0.0.1", port=local_port,
                                 timeout=60, token=args.token, log_level="all")
            code = template % {"m": mark}
            result = client.execute_skill(code, timeout=60, log_level="all")
            record = {
                "case": name,
                "mark": mark,
                "code": code,
                "ok": result.ok,
                "output": result.output,
                "errors": list(result.errors),
                "CDSlog": result.log,
                "mark_in_same_request_log": mark in (result.log or ""),
            }
            evidence["cases"].append(record)
            print(json.dumps(record, ensure_ascii=False), flush=True)
    finally:
        tunnel.terminate()
        try:
            tunnel.wait(timeout=3)
        except subprocess.TimeoutExpired:
            tunnel.kill()

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        print(f"evidence: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
