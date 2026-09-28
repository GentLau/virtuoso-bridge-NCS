# === TB 注释头（规范见 test/docs/写TB规范.md §0）=====================
# 作者: 设计/Codex
# 最后改动: 2026-09-28 19:12
# 依赖: 无
# =====================================================================
# 六步流程（按 test/docs/写TB规范.md §1–§6）：
# §1 环境检查：离线确定性 case，不需要远端环境（写注释跳过）。
# §2 构建：构造“I/O 阻塞且 close 不唤醒”的最坏情况 fake client/channel。
# §3 最终检查：确认线程已启动并阻塞在预期的阻塞调用上。
# §4 执行：terminate/close 后调用有界 wait。
# §5 比对：返回后自有线程必须退出；残留必须被发现（红灯）。
# §6 重复/收尾：释放人工阻塞、join 残留线程，JSON 留证。
"""线程生命周期专项 TB（自研代码，不包含第三方 Paramiko 内部线程）。

当前覆盖：

1. ``paramiko_tunnel_pumps_stop``：ParamikoTunnel 的转发 pump 在
   ``terminate()`` + ``wait(timeout)`` 后不得残留。

后续把持久 shell reader、本地 command session reader 也纳入同一个 TB。
"""
from __future__ import annotations

import argparse
import inspect
import json
import os
import queue
import socket
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from common.paramiko_backend import ParamikoTunnel  # noqa: E402
from common.ssh import SSHRunner  # noqa: E402
from transport.middle import _LocalCommandSession  # noqa: E402


def case_paramiko_tunnel_pumps_stop() -> dict:
    release = threading.Event()

    class FakeClient:
        def __init__(self):
            self.timeout = None
            self.closed = False

        def getsockname(self):
            return ("127.0.0.1", 12345)

        def settimeout(self, value):
            self.timeout = value

        def recv(self, _n):
            if self.timeout is None:
                release.wait(timeout=10)
                return b""
            if release.wait(timeout=self.timeout):
                return b""
            raise socket.timeout()

        def sendall(self, _data):
            return None

        def close(self):
            self.closed = True

    class FakeChannel(FakeClient):
        def shutdown_write(self):
            return None

    class FakeTransport:
        def is_active(self):
            return True

        def open_channel(self, *args, **kwargs):
            return FakeChannel()

    tunnel = object.__new__(ParamikoTunnel)
    tunnel._transport_getter = lambda: FakeTransport()
    tunnel._remote_host = "remote"
    tunnel._remote_port = 22
    tunnel._stop = threading.Event()
    tunnel._lock = threading.Lock()
    tunnel._clients = set()
    tunnel._channels = set()
    tunnel._threads = set()
    tunnel._returncode = None
    tunnel._listener = type("L", (), {"close": lambda self: None})()

    client = FakeClient()
    handle = threading.Thread(target=tunnel._handle_connection, args=(client,),
                              daemon=True)
    handle.start()
    time.sleep(0.2)
    tunnel.terminate()
    handle.join(timeout=2.0)
    handle_alive = handle.is_alive()
    with tunnel._lock:
        alive = [t for t in tunnel._threads if t.is_alive()]
    wait_rc = tunnel.wait(timeout=1.0)
    release.set()
    handle.join(timeout=2.0)
    with tunnel._lock:
        leaked = [t.name or repr(t) for t in tunnel._threads if t.is_alive()]
    return {
        "ok": not handle_alive and not alive,
        "handle_alive_after_terminate": handle_alive,
        "pumps_alive_after_terminate": len(alive),
        "wait_rc": wait_rc,
        "leaked_after_release": leaked,
    }


def case_persistent_shell_reader_stops() -> dict:
    release = threading.Event()
    read_fd, write_fd = os.pipe()

    class BlockingStream:
        def fileno(self):
            return read_fd

        def __iter__(self):
            return self

        def __next__(self):
            # Worst case: close() does not release an in-flight iteration.
            release.wait(timeout=10)
            return b""

        def close(self):
            return None

    class FakeProc:
        def __init__(self):
            self.stdout = BlockingStream()
            self.stdin = type("S", (), {"close": lambda self: None})()

        def poll(self):
            return None

        def close(self):
            return None

        def terminate(self):
            return None

        def kill(self):
            return None

        def wait(self, timeout=None):
            return 0

    runner = object.__new__(SSHRunner)
    runner._host = "fake-shell"
    runner._shell_lock = threading.RLock()
    runner._shell_reader = None
    runner._shell_proc = FakeProc()
    runner._shell_queue = queue.Queue()
    runner._shell_stop = threading.Event()

    parameters = inspect.signature(SSHRunner._pump_shell_output).parameters
    if len(parameters) >= 3:
        args = (runner._shell_proc.stdout, runner._shell_queue, runner._shell_stop)
    else:
        args = (runner._shell_proc.stdout, runner._shell_queue)
    reader = threading.Thread(
        target=SSHRunner._pump_shell_output,
        args=args,
        daemon=True,
        name="ssh-shell-fake",
    )
    runner._shell_reader = reader
    reader.start()
    time.sleep(0.1)
    runner._close_persistent_shell_locked()
    reader_alive = reader.is_alive()
    release.set()
    reader.join(timeout=1.0)
    os.close(write_fd)
    os.close(read_fd)
    return {"ok": not reader_alive, "reader_alive_after_close": reader_alive}


def case_local_command_reader_stops() -> dict:
    release = threading.Event()
    read_fd, write_fd = os.pipe()

    class BlockingStream:
        def fileno(self):
            return read_fd

        def __iter__(self):
            return self

        def __next__(self):
            release.wait(timeout=10)
            return ""

        def close(self):
            return None

    class FakeProc:
        def __init__(self):
            self.stdout = BlockingStream()
            self.stdin = type("S", (), {"close": lambda self: None})()

        def poll(self):
            return None

        def terminate(self):
            return None

        def kill(self):
            return None

        def wait(self, timeout=None):
            return 0

    session = object.__new__(_LocalCommandSession)
    session._lock = threading.RLock()
    session._proc = FakeProc()
    session._reader = None
    session._stop = threading.Event()
    session._dead = False
    session._eof = False
    session._current = None
    session._seq = 0
    session._cwd = None

    parameters = inspect.signature(_LocalCommandSession._read_loop).parameters
    if len(parameters) >= 2:
        args = (session, session._stop)
    else:
        args = (session,)
    reader = threading.Thread(
        target=_LocalCommandSession._read_loop,
        args=args,
        daemon=True,
        name="local-session-reader-fake",
    )
    session._reader = reader
    reader.start()
    time.sleep(0.1)
    session._close_locked()
    reader_alive = reader.is_alive()
    release.set()
    reader.join(timeout=1.0)
    os.close(write_fd)
    os.close(read_fd)
    return {"ok": not reader_alive, "reader_alive_after_close": reader_alive}


CASES = (
    ("paramiko_tunnel_pumps_stop", case_paramiko_tunnel_pumps_stop),
    ("persistent_shell_reader_stops", case_persistent_shell_reader_stops),
    ("local_command_reader_stops", case_local_command_reader_stops),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    results = []
    for name, case in CASES:
        try:
            detail = case()
        except Exception as exc:  # noqa: BLE001
            detail = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        results.append({"name": name, **detail})

    passed = sum(1 for item in results if item["ok"])
    payload = {
        "tb": "thread_lifecycle_tb",
        "status": "PASS" if passed == len(results) else "RED",
        "passed": passed,
        "total": len(results),
        "cases": results,
    }
    out = Path(args.out) if args.out else (
        ROOT / "test" / "artifacts" / "evidence" / "thread-lifecycle.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"evidence: {out}")
    return 0 if passed == len(results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
