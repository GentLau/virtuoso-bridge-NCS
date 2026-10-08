"""标准六步注册（.cdsinit 自动 load）——把一个已在跑的独立实例注册进指定 work-dir。

对真实 HTTP API 驱动 ``register.server``（与注册页面完全同路径）：

    apply → validate → probe → deploy → [写 run/.cdsinit + 重启 CIW] → verify → commit

第 4→5 步之间的 "CIW load" 不模拟用户粘贴，而是直接把注册第 4 步生成的
``load("<setup>")`` 写进实例 run 目录的 ``.cdsinit``，然后重启该实例的 CIW：

* 等价于"用户把 load 放进 .cdsinit"；
* 实例以后每次启动都会自动加载注册后的 setup（长期可用）。

前置：实例 run 目录已由 ``bringup_instance.sh`` 备好（root/cds.lib/ramic）。
注册期间该实例的 CIW 会被本脚本**停止**（probe 要求 daemon 端口空闲），
deploy 完成后用新 .cdsinit 重启。

用法::

    PYTHONPATH=src python test/shared/runners/register_instance.py \
        --work-dir test/artifacts/env/daily-vbuser1 \
        --user vbuser1b --ssh-user vbuser1 \
        --root /home/vbuser1/.virtuoso-bridge/vbuser1b \
        --daemon-port 65411 --local-port 64411 --display :112 \
        --out test/artifacts/evidence/env-2026-10-08/register-vbuser1b.json
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "test" / "shared" / "fixtures"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from register.server import RegistrationServer  # noqa: E402
from common.paths import init_work_dir, registry_path  # noqa: E402
from common.registry import load_registry  # noqa: E402
from registration_tb_support import (  # noqa: E402
    Http, ProbeFailure, no_window, redact,
)
from ciw_load_setup import _run  # noqa: E402

DEFAULT_CALIBRE_BIN = (
    "/opt/eda/mentor/CALIBRE2025/aok_cal_2025.1_16.10/bin/calibre"
)
ADMIN_FILE = ROOT / "test" / "artifacts" / "admin-token.txt"


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _admin_token() -> str:
    token = os.environ.get("VB_ADMIN_TOKEN", "").strip()
    if token:
        return token
    if ADMIN_FILE.exists():
        return ADMIN_FILE.read_text(encoding="utf-8").strip()
    raise SystemExit(f"admin token required: VB_ADMIN_TOKEN or {ADMIN_FILE}")


def _delete_user(http_port: int, user: str) -> None:
    request = urllib.request.Request(
        f"http://127.0.0.1:{http_port}/api/user/{user}",
        method="DELETE",
        headers={"Authorization": "Bearer " + _admin_token()},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        response.read()


def _ssh(host: str, user: str, command: str,
         timeout: float = 90.0) -> subprocess.CompletedProcess:
    """以目标账号身份执行远端命令（ssh 别名的 User 是 Gent，必须显式覆盖）。"""
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
         "-o", "ControlMaster=no", "-o", "ControlPath=none",
         "-o", f"User={user}", host, command],
        capture_output=True, text=True, timeout=timeout, **no_window(),
    )


def _stop_instance(host: str, user: str, run_dir: str, port: int) -> str:
    """停掉这个实例的 CIW + daemon（绝不动别的实例），并等端口释放。

    CIW 按 cwd 精确匹配（必须用目标账号身份执行：跨账号 kill 会被 EPERM 拒绝）。
    杀 CIW 后 IPC 机制会连带清理 daemon，但有 ~0.2–1.2s 的 teardown 窗口——
    这里按"端口持有者"精确清理并轮询到端口真正释放，避免撞窗口误判。
    """
    quoted_run = shlex.quote(run_dir)
    port_grep = shlex.quote(f":{port} ")
    command = f'''
for p in $(pgrep -f "dfII/bin/64bit/virtuoso" || true); do
  if [ "$(readlink /proc/$p/cwd 2>/dev/null || true)" = {quoted_run} ]; then
    kill "$p" 2>/dev/null || true
    echo "killed-ciw=$p"
  fi
done
for _ in $(seq 1 20); do
  line=$(ss -ltnp 2>/dev/null | grep {port_grep} || true)
  if [ -z "$line" ]; then break; fi
  pid=$(echo "$line" | grep -o "pid=[0-9]*" | head -1 | cut -d= -f2)
  if [ -n "$pid" ]; then
    ppid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d " ")
    if [ -n "$ppid" ] && [ "$ppid" != "1" ] && grep -qa cdsServIpc /proc/"$ppid"/cmdline 2>/dev/null; then
      kill "$ppid" 2>/dev/null || true
    fi
    kill "$pid" 2>/dev/null || true
    echo "killed-daemon=$pid"
  fi
  sleep 1
done
if ss -ltn | grep -q {port_grep}; then echo PORT-STILL-IN-USE; else echo port-free; fi
'''
    result = _ssh(host, user, command, timeout=90)
    text = (result.stdout or "").strip()
    if result.returncode != 0 or "port-free" not in text:
        raise ProbeFailure(f"停止实例失败: rc={result.returncode} {text} "
                           f"{result.stderr.strip()}")
    return text


def _write_cdsinit(host: str, user: str, run_dir: str, setup_path: str) -> None:
    line = f'load("{setup_path}")'
    command = (
        f"mkdir -p {shlex.quote(run_dir)} && "
        f"printf '%s\\n' {shlex.quote(line)} > {shlex.quote(run_dir + '/.cdsinit')} && "
        f"cat {shlex.quote(run_dir + '/.cdsinit')}"
    )
    result = _ssh(host, user, command, timeout=60)
    if result.returncode != 0 or setup_path not in (result.stdout or ""):
        raise ProbeFailure(f"写 .cdsinit 失败: {result.stderr.strip()}")


def _start_instance(host: str, user: str, run_dir: str, display: str) -> None:
    quoted_run = shlex.quote(run_dir)
    command = (
        f"cd {quoted_run} || exit 1\n"
        "test -f cds.lib || { echo NO_CDSLIB; exit 1; }\n"
        "rm -f CDS.log.cdslck\n"
        # 只把 virtuoso 本身后台化（stdin/stdout/stderr 全部脱开 ssh 通道，
        # 否则后台 subshell 攥着通道，ssh 永不返回）。
        f"DISPLAY={shlex.quote(display)} nohup virtuoso -cdslib ./cds.lib "
        "-log ./CDS.log > start.log 2>&1 < /dev/null &\n"
        "sleep 2\n"
        "echo STARTED\n"
    )
    result = _ssh(host, user, command, timeout=60)
    if result.returncode != 0 or "STARTED" not in (result.stdout or ""):
        raise ProbeFailure(
            f"启动 CIW 失败: rc={result.returncode} {result.stdout.strip()} "
            f"{result.stderr.strip()}")


def _build_apply(user: str, token: str, args: argparse.Namespace) -> dict:
    payload = {
        "action": "apply",
        "user": user,
        "token": token,
        "mode": "remote",
        "enhanced_token": _admin_token(),  # 复用凭证（同钥多实例）走管理员路径
        "ssh": {"default": {
            "host": args.host, "user": args.ssh_user,
            "key_dir": args.key_dir, "key": args.key,
        }},
        "root": {"default": args.root},
        "roles": {
            "gui": {"display": args.display},
            "daemon": {
                "daemon_port": args.daemon_port,
                "local_port": args.local_port,
                "root": args.root,
            },
        },
    }
    if args.calibre_bin:
        payload["roles"]["command"] = {"calibre": {"bin": args.calibre_bin}}
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--token", default="")
    parser.add_argument("--host", default="wsl-gent")
    parser.add_argument("--ssh-user", required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--run-dir", default="",
                        help="默认 <root>/run")
    parser.add_argument("--daemon-port", type=int, required=True)
    parser.add_argument("--local-port", type=int, required=True)
    parser.add_argument("--display", required=True)
    parser.add_argument("--calibre-bin", default=DEFAULT_CALIBRE_BIN)
    parser.add_argument("--key-dir", default="~/.ssh")
    parser.add_argument("--key", default="id_ed25519")
    parser.add_argument("--out", default="")
    parser.add_argument("--replace", action="store_true",
                        help="先删除 work-dir 里已存在的同名 user（重跑用）")
    parser.add_argument("--timeout", type=float, default=240.0)
    args = parser.parse_args()

    user = args.user
    token = args.token or f"vb-{user}"
    run_dir = args.run_dir or args.root.rstrip("/") + "/run"

    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    if not args.out:
        args.out = str(work_dir / f"register-{user}.json")
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    init_work_dir(work_dir)
    registry = load_registry(registry_path())

    steps: list[dict] = []
    http_port = _free_port()
    server = RegistrationServer(("127.0.0.1", http_port), registry)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    http = Http(f"http://127.0.0.1:{http_port}")
    ok = False
    try:
        if args.replace and registry.get(user) is not None:
            _delete_user(http_port, user)
            steps.append({"action": "pre-cleanup", "status": "removed"})

        # probe 要求 daemon 端口空闲 → 先停该实例的 CIW（只动它自己）。
        steps.append({"action": "pre-stop",
                      "detail": _stop_instance(args.host, args.ssh_user, run_dir,
                                               args.daemon_port)})

        def expect(status: int, body: dict, want_status: int, want_stage: str,
                   label: str) -> None:
            steps.append({"step": label, "status": status,
                          "stage": body.get("stage"),
                          "errors": body.get("errors")})
            if status != want_status or body.get("stage") != want_stage:
                raise ProbeFailure(f"{label} failed: HTTP {status} {body}")

        status, body = http.call("POST", "/api/register",
                                 _build_apply(user, token, args))
        steps.append({"step": 1, "action": "apply", "status": status,
                      "stage": body.get("stage")})
        if status != 200 or body.get("stage") != "applied":
            raise ProbeFailure(f"step 1 apply failed: HTTP {status} {body}")
        session = body.get("token")
        if not session:
            raise ProbeFailure("apply 未返回会话 token")

        status, body = http.call("POST", "/api/register",
                                 {"user": user, "action": "validate",
                                  "token": session})
        expect(status, body, 200, "validated", "2-validate")

        status, body = http.call("POST", "/api/register",
                                 {"user": user, "action": "probe",
                                  "token": session}, timeout=args.timeout)
        expect(status, body, 200, "probed", "3-probe")
        entry = body.get("entry") or {}
        daemon_row = ((entry.get("roles") or {}).get("daemon") or {})
        if daemon_row.get("daemon_port") != args.daemon_port:
            raise ProbeFailure(f"probe 回写的 daemon_port 不符: {daemon_row}")

        status, body = http.call("POST", "/api/register",
                                 {"user": user, "action": "deploy",
                                  "token": session}, timeout=args.timeout)
        expect(status, body, 200, "deployed", "4-deploy")
        setup_path = body.get("setup_path") or ""
        if not setup_path.endswith("virtuoso_setup.il"):
            raise ProbeFailure(f"deploy 未返回 setup 路径: {setup_path!r}")

        _write_cdsinit(args.host, args.ssh_user, run_dir, setup_path)
        steps.append({"step": "4b-cdsinit", "action": "write",
                      "run_dir": run_dir, "setup": setup_path})
        _start_instance(args.host, args.ssh_user, run_dir, args.display)
        steps.append({"step": "4c-ciw-restart", "action": "start",
                      "display": args.display})

        deadline = time.monotonic() + args.timeout
        last = ""
        while time.monotonic() < deadline:
            up, detail = _run(args.host, args.daemon_port, token, "1+2", 10.0)
            last = str(detail)
            if up and last.strip().endswith("3"):
                break
            time.sleep(2.0)
        else:
            raise ProbeFailure(
                f"重启后 daemon {args.daemon_port} 未在 {args.timeout}s 内应答: {last}")
        steps.append({"step": "4d-daemon-up", "action": "poll",
                      "port": args.daemon_port, "result": last.strip()})

        status, body = http.call("POST", "/api/register",
                                 {"user": user, "action": "verify",
                                  "token": session}, timeout=args.timeout)
        expect(status, body, 200, "verified", "5-verify")
        report = body.get("report") or {}
        if not (report.get("command_ok") and report.get("skill_ok")
                and report.get("token_ok")):
            raise ProbeFailure(f"verify 报告不完整: {report}")

        status, body = http.call("POST", "/api/register",
                                 {"user": user, "action": "commit",
                                  "token": session})
        expect(status, body, 200, "committed", "6-commit")
        on_disk = json.loads(registry_path().read_text(encoding="utf-8"))
        if user not in on_disk:
            raise ProbeFailure("commit 后注册表里没有该 user")
        steps.append({"action": "registry-write", "users": sorted(on_disk)})
        ok = True
        print(f"[PASS] six-step registration: {user} ({token}) -> {out_path}")
    except (ProbeFailure, RuntimeError, OSError) as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}")
        steps.append({"action": "error", "error": f"{type(exc).__name__}: {exc}"})
    finally:
        server.shutdown()
        server.server_close()
        evidence = {
            "user": user,
            "token": "***",
            "work_dir": str(work_dir),
            "host": args.host,
            "ssh_user": args.ssh_user,
            "root": args.root,
            "run_dir": run_dir,
            "daemon_port": args.daemon_port,
            "local_port": args.local_port,
            "display": args.display,
            "ok": ok,
            "steps": steps,
            "http_trail": redact(http.trail),
        }
        out_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
