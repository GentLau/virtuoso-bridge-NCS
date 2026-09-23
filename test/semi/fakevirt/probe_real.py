#!/usr/bin/env python3
"""真机行为探针 —— 在 wsl-gent（真 IC6.1.8）上取语义证据。

用法（在真机上；daemon 端口/token 见 /home/Gent/.virtuoso-bridge/<user>/）：

    python3 probe_real.py --port 65121 --token vb-vblog \
        '1+2' '"hi"' 'getHostName()' 'boom()'

输出：每条表达式一行，格式：

    <expr>  ->  OK   <value>
    <expr>  ->  ERR  <error>
    <expr>  ->  LOG  <value> | <log>

从 Windows 远程跑（推荐）：

    ssh wsl-gent 'mkdir -p ~/.virtuoso-bridge/vblog/tmp'
    scp test/semi/fakevirt/probe_real.py \
        wsl-gent:~/.virtuoso-bridge/vblog/tmp/probe_real.py
    ssh wsl-gent "python3 ~/.virtuoso-bridge/vblog/tmp/probe_real.py \
        --port 65121 --token vb-vblog '1+2'"

说明：这是 README《真机行为校验流程》的配套工具；输出请贴进
doc/report 或 README 的验证记录，作为 fake 实现的语义依据。
"""

from __future__ import annotations

import argparse
import json
import socket
import sys

STX = b"\x02"
NAK = b"\x15"
RS = b"\x1e"


def execute(expr: str, host: str, port: int, token: str, timeout: float,
            log_level: str) -> tuple[str, str, str]:
    """返回 (kind, value, log)；kind ∈ {OK, ERR}。"""
    payload = {
        "skill": expr,
        "timeout": timeout,
        "token": token,
        "log_level": log_level,
        "log_max_bytes": 65536,
    }
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout + 5)
        sock.connect((host, port))
        sock.sendall(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        sock.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    raw = b"".join(chunks)
    if not raw:
        return "ERR", "<empty response>", ""
    mark, body = raw[:1], raw[1:].rstrip(RS)
    try:
        data = json.loads(body.decode("utf-8", errors="replace"))
    except ValueError:
        return "ERR", f"<non-JSON: {body[:120]!r}>", ""
    if mark == STX:
        return "OK", data.get("value", ""), data.get("log", "")
    return "ERR", data.get("error", ""), data.get("log", "")


def main() -> int:
    parser = argparse.ArgumentParser(description="probe real Virtuoso (IC6.1.8)")
    parser.add_argument("expressions", nargs="+", help="SKILL 表达式列表")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=65121)
    parser.add_argument("--token", default="vb-vblog")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--log-level", default="off",
                        choices=["off", "all", "warn", "error"])
    args = parser.parse_args()

    failures = 0
    for expr in args.expressions:
        try:
            kind, value, log = execute(
                expr, args.host, args.port, args.token, args.timeout, args.log_level
            )
        except Exception as exc:  # noqa: BLE001 - 探针要报告任何异常
            kind, value, log = "ERR", f"<probe failure: {exc}>", ""
        if kind == "OK" and log:
            print(f"{expr!r}  ->  LOG  {value} | log={log!r}")
        else:
            print(f"{expr!r}  ->  {kind}  {value}")
        if kind == "ERR" and value.startswith("<"):
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
