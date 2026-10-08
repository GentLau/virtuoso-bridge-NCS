"""P-132 红钉（离线）：daemon 在 CIW 侧消失（stdin EOF）后应自行退出、释放端口。

现状（缺陷，见 `test/reports/bugs/P-132-daemon-survives-stdin-eof.md`）：
两个 daemon 变体都把 stdin EOF 当「暂无数据」
（``if not ch: time.sleep(0.001); continue``），daemon 永不自退。
正常路径由 Cadence ``cdsServIpc`` 兜底清理（见
``test/reports/internal/CIW-daemon停止语义-调查-2026-10-08.md``），所以本钉用
「绕过 cdsServIpc 直接启动 daemon、stdin 立即 EOF」把缺口钉出来。

回归判据（P-132 已修）：stdin EOF（CIW 侧消失）后 daemon 必须 ≤10s 退出并释放端口。
请求按真实协议以 ``shutdown(SHUT_WR)`` 结束（否则 daemon 先卡在请求读取，
根本走不到 stdin 分支——建钉时踩过）。
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
DAEMONS = {
    "daemon_3": ROOT / "src" / "bridge" / "resources" / "ramic_bridge_daemon_3.py",
    "daemon_27": ROOT / "src" / "bridge" / "resources" / "ramic_bridge_daemon_27.py",
}


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _wait_port(port: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as probe:
            probe.settimeout(0.3)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.1)
    return False


@pytest.mark.parametrize("daemon_path", DAEMONS.values(), ids=DAEMONS.keys())
def test_daemon_exits_when_ciw_side_stdin_eofs(
    tmp_path: Path, daemon_path: Path
) -> None:
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, str(daemon_path), "127.0.0.1", str(port),
         "tok-p132", str(tmp_path)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        if not _wait_port(port, 15.0):
            pytest.skip("daemon 未启动（环境问题）：红钉不成立，先查 daemon 能否独立启动")

        # 发一次请求：daemon 会读 stdin 等 CIW 应答，从而走到 EOF 分支
        with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
            sock.sendall(json.dumps(
                {"skill": "1+1", "timeout": 3, "token": "tok-p132"}
            ).encode())
            # 真实协议里请求以 EOF 结束（SkillClient 会 shutdown(SHUT_WR)）；
            # 不 shutdown 的话 daemon 会先卡在请求读取、根本走不到 stdin 分支。
            sock.shutdown(socket.SHUT_WR)
            sock.settimeout(12.0)
            try:
                sock.recv(65536)
            except OSError:
                pass

        # 期望：察觉 CIW 侧消失后自行退出（不依赖外部收尸）
        try:
            proc.wait(timeout=10.0)
        except subprocess.TimeoutExpired:
            raise AssertionError(
                "P-132: stdin EOF 后 daemon 仍在运行（未自保退出）——见 "
                "test/reports/bugs/P-132-daemon-survives-stdin-eof.md"
            )
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
