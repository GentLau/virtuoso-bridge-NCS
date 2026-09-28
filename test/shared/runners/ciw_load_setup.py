"""把注册流程生成的 setup 注入可丢弃 CIW（P4 预设的 TB 侧接口）。

等价于"用户在 CIW 里粘一行 load(...)"：通过该 CIW 里预载的**注入用最小
daemon**（start_disposable_ciw.sh 起的 bootstrap）执行::

    progn(RBStop() load("<setup_path>"))

RBStop 会结束 bootstrap daemon（正在执行的这条请求可能收不到回包，属预期），
随后 CIW 原地 load 注册第 4 步生成的 setup，起真正的 daemon。用
``--verify-port/--verify-token`` 时，本脚本会轮询新 daemon 的 ``1+1``，
确认它在应答后才返回 0。

用法::

    PYTHONPATH=src python test/shared/runners/ciw_load_setup.py \
        --host wsl-gent --bootstrap-port 65301 --bootstrap-token vb-ciwtest \
        --setup /home/Gent/.virtuoso-bridge/<user>/setup/virtuoso_setup.il \
        --verify-port 65230 --verify-token vb-<user>

收尾（只停 daemon）::

    ... --stop-only --bootstrap-port 65230 --bootstrap-token vb-<user>
"""
from __future__ import annotations

import argparse
import contextlib
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from common.skill_client import SkillClient  # noqa: E402
from pyapi.models import ExecutionStatus  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def _forward(host: str, remote_port: int):
    local = _free_port()
    proc = subprocess.Popen(
        ["ssh", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes",
         "-N", "-L", f"127.0.0.1:{local}:127.0.0.1:{remote_port}", host],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", local), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError(f"ssh 端口转发未就绪: {host}:{remote_port}")
        yield local
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


def _run(host: str, port: int, token: str, skill: str, timeout: float):
    """发一条 SKILL；返回 (ok, output/errors 文本)。连接被对端切断也算一种结果。"""
    with _forward(host, port) as local:
        client = SkillClient(host="127.0.0.1", port=local, timeout=timeout, token=token)
        try:
            result = client.execute_skill(skill, timeout=timeout)
        except Exception as exc:  # noqa: BLE001 - 断连是 RBStop 的预期形态
            return False, f"transport: {type(exc).__name__}: {exc}"
        if result.status == ExecutionStatus.SUCCESS:
            return True, str(result.output)
        return False, "; ".join(result.errors) or str(result.status)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="wsl-gent")
    parser.add_argument("--bootstrap-port", type=int, required=True)
    parser.add_argument("--bootstrap-token", default="")
    parser.add_argument("--setup", default="", help="注册第 4 步生成的 virtuoso_setup.il 远端绝对路径")
    parser.add_argument("--verify-port", type=int, default=0)
    parser.add_argument("--verify-token", default="")
    parser.add_argument("--stop-only", action="store_true")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    if args.stop_only:
        ok, detail = _run(args.host, args.bootstrap_port, args.bootstrap_token,
                          "RBStop()", min(args.timeout, 15.0))
        print(json.dumps({"mode": "stop", "ok": ok, "detail": detail}, ensure_ascii=False))
        return 0

    if not args.setup:
        parser.error("--setup is required (unless --stop-only)")
    skill = f'progn(RBStop() load({json.dumps(args.setup)}))'
    inject_ok, inject_detail = _run(args.host, args.bootstrap_port, args.bootstrap_token,
                                    skill, min(args.timeout, 30.0))

    verify_ok = None
    verify_detail = ""
    if args.verify_port:
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            try:
                ok, detail = _run(args.host, args.verify_port, args.verify_token,
                                  "1+2", 10.0)
            except RuntimeError as exc:
                ok, detail = False, str(exc)
            if ok and detail.strip().endswith("3"):
                verify_ok, verify_detail = True, detail
                break
            verify_ok, verify_detail = False, detail
            time.sleep(1.0)

    summary = {
        "mode": "load",
        "setup": args.setup,
        "inject_port": args.bootstrap_port,
        "inject_transport_result": {"ok": inject_ok, "detail": inject_detail[:400]},
        "verify": {"port": args.verify_port, "ok": verify_ok, "detail": verify_detail[:400]},
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if verify_ok is None:
        return 0  # 只注入了，没要求验证：RBStop 断连属预期，不做进一步判定
    return 0 if verify_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
