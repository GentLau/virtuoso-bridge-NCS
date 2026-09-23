"""在**真实 Python 2.7 解释器**下驱动 py2.7 版 daemon 的协议探针（半真机级）。

背景：`src/bridge/resources/ramic_bridge_daemon_27.py` 此前只用 Python 3 导入做纯函数对照，
从未在真 py2.7 下跑过（报告里的 "py2.7 真解释器 PENDING"）。
wsl-gent 上 Cadence XCELIUM 自带 py2.7（用 `--py27 <path>` 指定），本探针覆盖
**无需 CIW 的校验分支**：token / log_level / log_max_bytes 三类拒绝路径 + 启动监听。

用法（在被测主机上，例如 wsl-gent）::

    python3 test/semi/probes/py27_daemon_probe.py \
        --py27 /opt/eda/cadence/XCELUMMAIN2309/tools.lnx86/python2.7/bin/python2.7 \
        --daemon path/to/ramic_bridge_daemon_27.py \
        --port 6599 --token py27-probe --out test/artifacts/evidence/py27-daemon-probe.json
"""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

STX, NAK, RS = 2, 21, 30


def _read_response(sock: socket.socket, timeout: float = 5.0) -> tuple[int, dict]:
    sock.settimeout(timeout)
    data = b""
    while True:
        try:
            chunk = sock.recv(65536)
        except socket.timeout:
            break
        if not chunk:
            break
        data += chunk
        if data.endswith(bytes([RS])):
            break
    if not data:
        raise AssertionError("daemon closed the connection without a response")
    status = data[0]
    payload = data[1:].rstrip(bytes([RS])).decode("utf-8")
    return status, json.loads(payload)


def _request(host: str, port: int, body: dict, timeout: float = 5.0):
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.sendall(json.dumps(body).encode("utf-8"))
        sock.shutdown(socket.SHUT_WR)
        return _read_response(sock, timeout)


def wait_port(host: str, port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--py27", required=True, help="真实 python2.7 可执行文件")
    parser.add_argument("--daemon", required=True, help="ramic_bridge_daemon_27.py 路径")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=6599)
    parser.add_argument("--token", default="py27-probe")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    cases: list[dict] = []
    workdir = Path(args.daemon).resolve().parent
    log = workdir / "py27-daemon-probe.log"
    with log.open("wb") as logf:
        proc = subprocess.Popen(
            [args.py27, str(Path(args.daemon).resolve()), args.host, str(args.port),
             args.token, str(workdir / "tmp")],
            stdin=subprocess.DEVNULL, stdout=logf, stderr=subprocess.STDOUT, cwd=workdir,
        )
        try:
            up = wait_port(args.host, args.port)
            cases.append({"case": "listen", "ok": up, "detail": f"port {args.port}"})
            if up:
                status, body = _request(args.host, args.port,
                                        {"skill": "1+1", "token": "wrong-token"})
                cases.append({"case": "reject-bad-token", "ok": status == NAK and
                              body.get("error") == "invalid token", "detail": body})

                status, body = _request(args.host, args.port,
                                        {"skill": "1+1", "token": args.token,
                                         "log_level": "bogus"})
                cases.append({"case": "reject-bad-log-level", "ok": status == NAK and
                              body.get("error") == "invalid log_level", "detail": body})

                status, body = _request(args.host, args.port,
                                        {"skill": "1+1", "token": args.token,
                                         "log_max_bytes": 0})
                cases.append({"case": "reject-bad-log-max-bytes", "ok": status == NAK and
                              body.get("error") == "invalid log_max_bytes", "detail": body})

                # 合法请求会去等 CIW 的 SKILL 帧；stdin 是 /dev/null，所以由
                # daemon 自己的看门狗（threading.Timer + flag）超时收尾 ——
                # 这条同时覆盖 py2.7 下 Timer/信号标志的真实语义。
                status, body = _request(args.host, args.port,
                                        {"skill": "1+1", "token": args.token,
                                         "timeout": 1.0}, timeout=10.0)
                cases.append({"case": "timeout-watchdog-answers", "ok": status == NAK and
                              "timed out" in str(body.get("error", "")), "detail": body})
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    # py2 prints ``-V`` to stderr, py3.4+ to stdout: accept either so the
    # evidence records the interpreter even when this probe drives python3.6.
    banner = subprocess.run([args.py27, "-V"], capture_output=True, text=True)
    version = (banner.stdout or banner.stderr).strip()
    payload = {"interpreter": args.py27, "version": version, "cases": cases,
               "passed": sum(1 for c in cases if c["ok"]), "total": len(cases),
               "daemon_log": str(log)}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
    return 0 if all(c["ok"] for c in cases) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
