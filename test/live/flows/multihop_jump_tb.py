# === TB 注释头（规范见 test/docs/写TB规范.md §0）=====================
# 作者: 设计/Codex
# 最后改动: 2026-09-28 14:56
# 依赖: 无
# =====================================================================
# 六步流程（按 test/docs/写TB规范.md §1–§6）：
# §1 环境检查：两种模式都先用 vb-hopfake 跑 require_environment（command role + 两跳 + fake daemon 的 skill）；
#    不通过则写 environment_failed 证据并直接退出，不进入后续步骤。
# §2 构建：BusinessServer + stage 目录；SOCKS5 隧道由本 TB 拉起（起不来按构建失败处理）。
# §3 最终检查：确认直连/跳板 SSH_CONNECTION 基线不同。
# §4 执行：经两跳的命令、文件和端到端 HTTP 动作。
# §5 比对：client IP、hostname、文件内容与期望一致。
# §6 重复/收尾：重复检查；绿色才回收 stage，JSON 留证。
"""多跳跳板 / SOCKS5 代理 真机 TB（补 spec 缺口 X1）。

背景：endpoint 身份 = `(host, user, jump_host, jump_user, proxy)`（spec《中层配置文档》§6.5），
但第五轮之前**从没有真的走过两跳**——只有离线单测。本 TB 用真实链路验证：

    Windows ──ssh──► w3-gent (172.20.170.23, dev) ──ssh──► w1-gent (172.20.170.21, dev)

判据（不是"接口返回 ok"）：

* `SSH_CONNECTION` 的**客户端 IP** 在跳板路径下必须是 w3-gent（说明流量真的过了跳板），
  并在直连路径下取到不同 IP（负控制：证明这个判据有区分力）；
* 文件上下行（SFTP over direct-tcpip channel）SHA-256 一致；
* 同一 host/user 但一条带跳板、一条直连时，两条连接的来源 IP 不同（endpoint 身份含 jump/proxy）；
* SOCKS5 路径（`socks5://127.0.0.1:11080`，由本 TB 自己拉起 `ssh -N -D`）同样能跑命令 + 传文件。

用法::

    python test/shared/runners/make_multihop_env.py
    PYTHONPATH=src python test/live/flows/multihop_jump_tb.py \
        --work-dir test/artifacts/env/multihop \
        --out test/artifacts/evidence/round5-multihop/multihop-jump.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import socket
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
_RUNNERS = Path(__file__).resolve().parents[2] / "shared" / "runners"
if str(_RUNNERS) not in sys.path:
    sys.path.insert(0, str(_RUNNERS))
from env_check import require_environment  # noqa: E402

from transport.middle import BusinessServer  # noqa: E402
from common.paths import init_work_dir  # noqa: E402

TARGET_HOST = "w1-gent"
TARGET_USER = "dev"
JUMP_HOST = "w3-gent"
ENV_TOKEN = "vb-hopfake"
SOCKS_PORT = 11080
SOCKS_URL = f"socks5://127.0.0.1:{SOCKS_PORT}"


class Results:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, name: str, ok: bool, **detail) -> bool:
        self.items.append({"name": name, "ok": bool(ok), **detail})
        flag = "PASS" if ok else "FAIL"
        print(f"[{flag}] {name}" + (f"  {detail}" if detail else ""))
        return bool(ok)

    @property
    def passed(self) -> int:
        return sum(1 for item in self.items if item["ok"])


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def client_ip_from_ssh_connection(text: str) -> str:
    """`SSH_CONNECTION` = '<client_ip> <client_port> <server_ip> <server_port>'。"""
    parts = (text or "").split()
    return parts[0] if parts else ""


def start_socks_tunnel() -> subprocess.Popen | None:
    """起一个真实 SOCKS5 端点（sshd 反向不需要：本机 ssh -D）。"""
    with socket.socket() as probe:
        probe.settimeout(0.4)
        if probe.connect_ex(("127.0.0.1", SOCKS_PORT)) == 0:
            return None  # 已经有现成的
    proc = subprocess.Popen(
        ["ssh", "-N", "-o", "ExitOnForwardFailure=yes", "-D", f"127.0.0.1:{SOCKS_PORT}", JUMP_HOST],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(40):
        time.sleep(0.25)
        with socket.socket() as probe:
            probe.settimeout(0.3)
            if probe.connect_ex(("127.0.0.1", SOCKS_PORT)) == 0:
                return proc
    proc.terminate()
    return None


def http_call(base: str, operation: str, token: str, **fields) -> dict:
    payload = {"operation": operation, "token": token, **fields}
    request = urllib.request.Request(
        base, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return json.loads(error.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--out", default="")
    parser.add_argument("--base", default="", help="可选：真机业务面 HTTP 入口，做一次端到端复核")
    parser.add_argument("--no-socks", action="store_true", help="跳过 SOCKS5 段（默认自己拉隧道）")
    args = parser.parse_args(argv)

    work_dir = Path(args.work_dir).resolve()
    out = Path(args.out) if args.out else work_dir / "multihop-jump.json"
    out.parent.mkdir(parents=True, exist_ok=True)

    business_base = ""
    target: dict = {"mode": "in-process", "work_dir": str(work_dir)}
    env_target: dict = {"work_dir": str(work_dir)}
    if args.base:
        business_base = args.base.rstrip("/")
        if not business_base.endswith("/api/operation"):
            business_base += "/api/operation"
        target = {"mode": "http", "base": business_base}
        env_target = {"base": business_base}

    # 六步 §1：hop-jump / hop-socks 的 command role 相同；用带 fake daemon 的 hop-fake
    # token 一次把 command role、两跳链路和 skill 通道都检查掉。环境不对直接失败。
    try:
        environment = {
            **target,
            "env_check": require_environment(
                token=ENV_TOKEN, expect_host=TARGET_HOST, expect_user=TARGET_USER,
                **env_target,
            ),
        }
    except Exception as error:  # noqa: BLE001 - 第 1 步环境错误，写证据后直接退出
        payload = {
            "tb": "multihop_jump_tb",
            "status": "environment_failed",
            "environment": target,
            "error": f"{type(error).__name__}: {error}",
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[ENV-FAIL] {payload['error']}；证据：{out}", file=sys.stderr)
        return 2

    results = Results()
    notes: list[str] = []
    # 本 TB 自己的落盘区放环境目录下（不用 %TEMP%：2026-09-23 实测该路径会在
    # 会话中途消失，导致 TB 自己报 FileNotFoundError；同时这也符合 test/docs/文件使用规范.md）。
    stage = work_dir / f"tb-multihop-{uuid.uuid4().hex[:8]}"
    stage.mkdir(parents=True, exist_ok=True)

    socks_proc: subprocess.Popen | None = None
    started_socks_here = False
    try:
        init_work_dir(work_dir)
        server = BusinessServer()
        # ---- 0. 负控制：直连（无跳板）来源 IP -----------------------------------
        direct = server.run_command("echo $SSH_CONNECTION", token="vb-lab11")
        direct_ip = client_ip_from_ssh_connection(direct.stdout or "")
        results.add("direct_baseline_ssh_connection",
                    direct.returncode == 0 and bool(direct_ip),
                    client_ip=direct_ip, raw=(direct.stdout or "").strip()[:120])

        # ---- 1. 两跳跳板：命令通道 ---------------------------------------------
        host = server.run_command("hostname", token="vb-hopjump")
        results.add("jump_command_hostname_is_target",
                    host.returncode == 0 and "w1-gent" in (host.stdout or ""),
                    stdout=(host.stdout or "").strip(), kind=host.kind)

        conn = server.run_command("echo $SSH_CONNECTION", token="vb-hopjump")
        jump_ip = client_ip_from_ssh_connection(conn.stdout or "")
        results.add("jump_ssh_client_ip_is_jump_host",
                    bool(jump_ip) and jump_ip == "172.20.170.23",
                    client_ip=jump_ip, expected="172.20.170.23 (w3-gent)", raw=(conn.stdout or "").strip()[:120])
        results.add("jump_and_direct_are_different_paths",
                    bool(direct_ip) and bool(jump_ip) and direct_ip != jump_ip,
                    direct_ip=direct_ip, jump_ip=jump_ip)

        # ---- 2. 两跳跳板：文件通道（SFTP over direct-tcpip） --------------------
        local_in = stage / "in.bin"
        local_in.write_bytes(b"multihop-jump-payload" * 512)
        rel = f"hop/up-{uuid.uuid4().hex[:8]}.bin"
        up = server.upload_file(local_in, rel, token="vb-hopjump")
        local_out = stage / "out.bin"
        down = server.download_file(rel, local_out, token="vb-hopjump")
        digest_ok = local_out.is_file() and sha256_of(local_in) == sha256_of(local_out)
        results.add("jump_file_roundtrip_sha256",
                    up.returncode == 0 and down.returncode == 0 and digest_ok,
                    upload_kind=up.kind, download_kind=down.kind, sha256_match=digest_ok,
                    bytes=local_in.stat().st_size)

        # ---- 3. SOCKS5 代理路径 -------------------------------------------------
        if args.no_socks:
            notes.append("SOCKS5 段按 --no-socks 跳过")
        else:
            socks_proc = start_socks_tunnel()
            started_socks_here = socks_proc is not None
            if socks_proc is None and socket.socket().connect_ex(("127.0.0.1", SOCKS_PORT)) != 0:
                results.add("socks_tunnel_started", False, port=SOCKS_PORT,
                            hint=f"起不来：ssh -N -D 127.0.0.1:{SOCKS_PORT} {JUMP_HOST}")
            else:
                results.add("socks_tunnel_started", True, port=SOCKS_PORT, url=SOCKS_URL)
                shost = server.run_command("hostname", token="vb-hopsocks")
                results.add("socks_command_hostname_is_target",
                            shost.returncode == 0 and "w1-gent" in (shost.stdout or ""),
                            stdout=(shost.stdout or "").strip(), kind=shost.kind)
                sconn = server.run_command("echo $SSH_CONNECTION", token="vb-hopsocks")
                socks_ip = client_ip_from_ssh_connection(sconn.stdout or "")
                results.add("socks_traffic_exits_from_proxy_host",
                            socks_ip == "172.20.170.23", client_ip=socks_ip,
                            expected="172.20.170.23 (w3-gent)", raw=(sconn.stdout or "").strip()[:120])
                srel = f"hop/socks-{uuid.uuid4().hex[:8]}.bin"
                sup = server.upload_file(local_in, srel, token="vb-hopsocks")
                sout = stage / "socks-out.bin"
                sdown = server.download_file(srel, sout, token="vb-hopsocks")
                results.add("socks_file_roundtrip_sha256",
                            sup.returncode == 0 and sdown.returncode == 0 and sout.is_file()
                            and sha256_of(local_in) == sha256_of(sout),
                            upload_kind=sup.kind, download_kind=sdown.kind)

        # ---- 4. 两跳 + daemon（lab fake，skill 通道） ---------------------------
        marker = f"hop-skill-{uuid.uuid4().hex[:10]}"
        skill = server.execute_skill(f'strcat("{marker}")', token="vb-hopfake")
        results.add("jump_daemon_skill_roundtrip",
                    skill.ok and marker in (skill.output or ""),
                    skill_ok=skill.ok, status=str(getattr(skill, "status", "")),
                    output=(skill.output or "")[:80],
                    note="daemon 在 w1-gent 65203（fake，token 与 registry 一致），SSH 隧道经 w3-gent")

        # ---- 5. 可选：走真机业务面做一次端到端 -------------------------------
        if args.base:
            resp = http_call(business_base, "basic.command.run", "vb-hopjump", cmd="hostname")
            result = (resp).get("result") or {}
            stdout = str(result.get("stdout") or "") if isinstance(result, dict) else ""
            ok = result.get("returncode") == 0 and "w1-gent" in stdout
            results.add("http_business_face_via_jump", ok,
                        stdout=str(stdout).strip(), error=resp.get("error"))

    finally:
        if socks_proc is not None and started_socks_here:
            socks_proc.terminate()
            try:
                socks_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                socks_proc.kill()
        if results.passed == len(results.items):
            shutil.rmtree(stage, ignore_errors=True)   # 全绿才清理；有红留证据

    total = len(results.items)
    payload = {
        "tb": "multihop_jump_tb",
        "work_dir": str(work_dir),
        "environment": environment,
        "checks": results.items,
        "passed": results.passed,
        "total": total,
        "notes": notes,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{results.passed}/{total} 通过；证据：{out}")
    return 0 if results.passed == total else 2


if __name__ == "__main__":
    raise SystemExit(main())
