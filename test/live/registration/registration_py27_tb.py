# === TB 注释头（规范见 test/docs/写TB规范.md §0）=====================
# 作者: 测试/root
# 最后改动: 2026-09-28 20:40
# 依赖: 无
# =====================================================================
# 六步流程（按 test/docs/写TB规范.md §1–§6）：
# §1 环境检查：显式检查 SSH 可达、Python 2.7 解释器可执行、客户端密钥存在；
#    不通过写 environment_failed JSON 并退出（Python 2.7 是环境前提）。
# §2 构建：本地 work-dir + 注册 HTTP 服务 + 远端部署根 + 唯一 user/token/端口。
# §3 最终检查：确认远端 root 干净、daemon_port 空闲、py27 版本为 2.7。
# §4 执行：apply→validate→probe→deploy→（失败一次）verify→commit。
# §5 比对：probe 回写的 python/端口/绝对 root、部署的 27 变体、双冒烟报告、注册表条目。
# §6 重复/收尾：同一会话 verify 原样重试；停止 py27 fake daemon，清理远端测试目录。
"""Python 2.7 端到端注册 TB（X4-①，真机/半真机）。

不是"py27 兼容语法探针"：本 TB 走完整注册六步，要求
``role.daemon.python`` 指向真实 Python 2.7，部署后 setup 引用
``ramic_bridge_daemon_27.py``，最后在远端用该 py27 解释器启动协议兼容
fake daemon，跑通第 5 步 command/token/1+1 双冒烟并 commit。

默认环境为 wsl-gent 上的 XCELIUM 自带 py2.7（路径见 ``--py27``）；缺少
SSH 或 py27 时第 1 步直接判环境失败，不进入注册流程。

用法::

    PYTHONPATH=src python test/live/registration/registration_py27_tb.py \
        --work-dir test/artifacts/env/reg-py27 \
        --out test/artifacts/evidence/tb-sixstep-20260928/registration-py27.json
"""
from __future__ import annotations

import argparse
import json
import shlex
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
_FIXTURES = ROOT / "test" / "shared" / "fixtures"
if str(_FIXTURES) not in sys.path:
    sys.path.insert(0, str(_FIXTURES))

from common.paths import init_work_dir, registry_path  # noqa: E402
from common.registry import load_registry  # noqa: E402
from register.server import RegistrationServer  # noqa: E402
import os  # noqa: E402


def _load_admin_token() -> str:
    """加强凭据（admin），用于绕过"同一 SSH 公钥已被登记"的查重闸门。

    没有它，本 TB 第二次运行（同一把 id_ed25519 + 新随机用户名）会在第 1 步被
    `credential reuse requires enhanced_token` 挡下 —— 2026-09-28 实测踩到。
    取法：``VB_ADMIN_TOKEN`` 环境变量 → gitignored 的
    ``test/artifacts/admin-token.txt``；都缺时返回空串（仅影响重复运行）。
    """
    token = os.environ.get("VB_ADMIN_TOKEN", "").strip()
    if token:
        return token
    path = ROOT / "test" / "artifacts" / "admin-token.txt"
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


ADMIN_TOKEN = _load_admin_token()

try:
    from _win import no_window  # type: ignore
except ImportError:  # pragma: no cover - POSIX
    def no_window(**kwargs):  # type: ignore
        return dict(kwargs)


DEFAULT_PY27 = (
    "/opt/eda/cadence/XCELUMMAIN2309/tools.lnx86/"
    "python2.7/bin/python2.7"
)
FAKE_DAEMON_PY27 = _FIXTURES / "fake_daemon_py27.py"


class ProbeFailure(AssertionError):
    pass


class Results:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, name: str, ok: bool, **detail) -> bool:
        self.items.append({"name": name, "ok": bool(ok), **_redact(detail)})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}"
              + (f"  {detail}" if detail else ""))
        return bool(ok)

    @property
    def passed(self) -> int:
        return sum(1 for item in self.items if item["ok"])


def _redact(value):
    """Remove credentials from the evidence trail (never persist real tokens)."""
    if isinstance(value, dict):
        return {
            key: ("***" if key in ("token", "enhanced_token") else _redact(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


class Http:
    def __init__(self, base: str) -> None:
        self.base = base
        self.trail: list[dict] = []

    def call(self, method: str, path: str, payload: dict | None = None,
             timeout: float = 180.0) -> tuple[int, dict]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base + path, data=data, method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = response.status
                body = json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as error:
            status = error.code
            raw = error.read().decode("utf-8")
            try:
                body = json.loads(raw or "{}")
            except ValueError:
                body = {"raw": raw}
        self.trail.append({"method": method, "path": path,
                           "request": _redact(payload), "status": status,
                           "response": _redact(body)})
        return status, body


def ssh(host: str, command: str, timeout: float = 60.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", host, command],
        capture_output=True, text=True, timeout=timeout, **no_window(),
    )


def remote_home(host: str) -> str:
    result = ssh(host, 'printf "%s" "$HOME"', timeout=30)
    home = (result.stdout or "").strip()
    if result.returncode != 0 or not home:
        raise ProbeFailure(f"cannot resolve remote HOME on {host}: {result.stderr.strip()}")
    return home


def remote_free_port(host: str, start: int = 65300, tries: int = 80) -> int:
    """Ask remote python3 for an ephemeral port; fall back to a scanned range."""
    command = (
        "python3 -c \"import socket; s=socket.socket(); "
        "s.bind(('127.0.0.1',0)); p=s.getsockname()[1]; s.close(); print(p)\""
    )
    result = ssh(host, command, timeout=30)
    out = (result.stdout or "").strip()
    if result.returncode == 0 and out.isdigit():
        return int(out)
    for port in range(start, start + tries):
        probe = ssh(host, f"ss -ltn | grep -c ':{port} '", timeout=20)
        if probe.returncode != 0 or (probe.stdout or "").strip() == "0":
            return port
    raise ProbeFailure(f"no free remote port found on {host}")


class RemotePy27Daemon:
    """Start the py27 fake daemon inside a kept-open ssh process."""

    def __init__(self, host: str, py27: str, root: str, port: int, token: str) -> None:
        self.host = host
        self.py27 = py27
        self.root = root
        self.port = port
        self.token = token
        self.tag = uuid.uuid4().hex[:8]
        self.remote_dir = f"{root.rstrip('/')}/tmp/tb-py27-{self.tag}"
        self.proc: subprocess.Popen | None = None

    def _remote_script(self) -> str:
        return f"{self.remote_dir}/fake_daemon_py27.py"

    def start(self) -> None:
        made = ssh(self.host, f"mkdir -p {shlex.quote(self.remote_dir)}", timeout=30)
        if made.returncode != 0:
            raise ProbeFailure(f"cannot create remote temp dir: {made.stderr.strip()}")
        copied = subprocess.run(
            ["scp", "-q", str(FAKE_DAEMON_PY27),
             f"{self.host}:{self._remote_script()}"],
            capture_output=True, text=True, timeout=60, **no_window(),
        )
        if copied.returncode != 0:
            raise ProbeFailure(f"scp py27 fake daemon failed: {copied.stderr.strip()}")
        remote_cmd = (
            f"exec {shlex.quote(self.py27)} {shlex.quote(self._remote_script())} "
            f"--port {self.port} --token {shlex.quote(self.token)}"
        )
        self.proc = subprocess.Popen(
            ["ssh", self.host, remote_cmd],
            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, **no_window(),
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            probe = ssh(self.host, f"ss -ltn | grep -c ':{self.port} '", timeout=20)
            if (probe.stdout or "").strip() == "1":
                return
            time.sleep(0.4)
        self.stop()
        raise ProbeFailure(f"py27 fake daemon did not listen on remote port {self.port}")

    def stop(self) -> None:
        proc = self.proc
        self.proc = None
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                try:
                    proc.kill()
                except Exception:  # noqa: BLE001
                    pass
        ssh(self.host,
            f"pkill -f 'fake_daemon_py27[.]py --port {self.port}' || true",
            timeout=30)
        ssh(self.host, f"rm -rf {shlex.quote(self.remote_dir)}", timeout=30)


def cleanup_remote_root(host: str, root: str) -> None:
    ssh(host, f"rm -rf {shlex.quote(root)}", timeout=60)


def environment_checks(host: str, py27: str, key_dir: str, key: str) -> tuple[bool, list[dict]]:
    checks: list[dict] = []

    reachable = ssh(host, "echo vb-ok", timeout=30)
    checks.append({
        "name": "ssh-reachable",
        "ok": reachable.returncode == 0 and "vb-ok" in reachable.stdout,
        "detail": (reachable.stdout or reachable.stderr).strip(),
    })

    version = ssh(host, f"test -x {shlex.quote(py27)} && {shlex.quote(py27)} -V 2>&1",
                  timeout=30)
    version_text = (version.stdout + version.stderr).strip()
    checks.append({
        "name": "python2.7-available",
        "ok": version.returncode == 0 and "Python 2.7" in version_text,
        "detail": {"path": py27, "version": version_text},
    })

    key_path = Path(key_dir).expanduser() / key
    checks.append({
        "name": "client-key-present",
        "ok": key_path.is_file() and Path(str(key_path) + ".pub").is_file(),
        "detail": {"key": str(key_path), "pub": str(key_path) + ".pub"},
    })
    return all(item["ok"] for item in checks), checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--out", default="")
    parser.add_argument("--host", default="wsl-gent")
    parser.add_argument("--ssh-user", default="Gent")
    parser.add_argument("--py27", default=DEFAULT_PY27)
    parser.add_argument("--ssh-key-dir", default="~/.ssh")
    parser.add_argument("--ssh-key", default="id_ed25519")
    parser.add_argument("--user", default="")
    parser.add_argument("--token", default="")
    parser.add_argument("--daemon-port", type=int, default=0)
    parser.add_argument("--root", default="")
    parser.add_argument("--keep-remote", action="store_true",
                        help="保留远端注册根（默认清理本 TB 的测试根）")
    args = parser.parse_args(argv)

    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    init_work_dir(work_dir)
    out = Path(args.out) if args.out else work_dir / "registration-py27.json"
    out.parent.mkdir(parents=True, exist_ok=True)

    env_ok, env_checks = environment_checks(
        args.host, args.py27, args.ssh_key_dir, args.ssh_key)
    if not env_ok:
        payload = {"tb": "registration_py27_tb", "status": "environment_failed",
                   "environment": {"host": args.host, "py27": args.py27,
                                   "ssh_user": args.ssh_user},
                   "checks": env_checks}
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        print(f"[ENV-FAIL] py27 registration environment not ready; evidence: {out}")
        return 2

    tag = uuid.uuid4().hex[:8]
    user = args.user or f"vbpy27{tag}"
    token = args.token or f"vbpy27{tag}-00"
    daemon_port = args.daemon_port or remote_free_port(args.host)
    root = args.root or f"{remote_home(args.host).rstrip('/')}/.virtuoso-bridge/{user}"
    # 只有 TB 自己按 `<home>/.virtuoso-bridge/<user>` 生成的根才自动清理；
    # `--root` 是调用方资产，绝不替调用方做删除。
    cleanup_allowed = not args.root
    if cleanup_allowed:
        cleanup_remote_root(args.host, root)

    registry = load_registry(registry_path())
    if registry.get(user) is not None:
        registry.remove(user)

    http_port = 0
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        http_port = int(probe.getsockname()[1])
    server = RegistrationServer(("127.0.0.1", http_port), registry)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    http = Http(f"http://127.0.0.1:{http_port}")
    results = Results()
    steps: list[dict] = []
    daemon: RemotePy27Daemon | None = None
    remote_root_removed = False
    error = ""

    def call(payload: dict) -> tuple[int, dict]:
        return http.call("POST", "/api/register", payload)

    try:
        # §1 already checked; §2 environment is built above.
        request_payload = {
            "action": "apply",
            "user": user,
            "mode": "remote",
            "token": token,
            "ssh": {"default": {
                "host": args.host, "user": args.ssh_user,
                "key_dir": args.ssh_key_dir, "key": args.ssh_key,
            }},
            "root": {"default": root},
            "roles": {"daemon": {"python": args.py27, "daemon_port": daemon_port}},
            "log_level": "off",
        }
        if ADMIN_TOKEN:
            # 同一把客户端公钥已登记过其他用户时必须带加强凭据（spec r21/r22）
            request_payload["enhanced_token"] = ADMIN_TOKEN
        status, body = call(request_payload)
        session = body.get("token")
        results.add("step1-apply", status == 200 and body.get("stage") == "applied",
                    status=status, stage=body.get("stage"))
        steps.append({"step": 1, "status": status, "stage": body.get("stage")})
        if not (status == 200 and body.get("stage") == "applied" and session):
            raise ProbeFailure(f"step 1 failed: {body}")

        status, body = call({"action": "validate", "user": user, "token": session})
        results.add("step2-validate", status == 200 and body.get("stage") == "validated",
                    status=status, stage=body.get("stage"), errors=body.get("errors"))
        steps.append({"step": 2, "status": status, "stage": body.get("stage")})
        if not (status == 200 and body.get("stage") == "validated"):
            raise ProbeFailure(f"step 2 failed: {body}")

        status, body = call({"action": "probe", "user": user, "token": session})
        entry = body.get("entry") or {}
        daemon_entry = (entry.get("roles") or {}).get("daemon") or {}
        results.add("step3-probe-py27", status == 200 and body.get("stage") == "probed"
                    and daemon_entry.get("python") == args.py27,
                    status=status, stage=body.get("stage"),
                    python=daemon_entry.get("python"), daemon_port=daemon_entry.get("daemon_port"))
        results.add("step3-root-absolute",
                    bool(daemon_entry.get("root")) and str(daemon_entry["root"]).startswith("/"),
                    root=daemon_entry.get("root"))
        steps.append({"step": 3, "status": status, "stage": body.get("stage"),
                      "entry": entry})
        if not (status == 200 and body.get("stage") == "probed"):
            raise ProbeFailure(f"step 3 failed: {body}")
        daemon_port = int(daemon_entry.get("daemon_port") or daemon_port)
        daemon_root = str(daemon_entry.get("root") or "").rstrip("/")

        status, body = call({"action": "deploy", "user": user, "token": session})
        setup_path = str(body.get("setup_path") or "")
        results.add("step4-deploy", status == 200 and body.get("stage") == "deployed",
                    status=status, stage=body.get("stage"), setup_path=setup_path)
        steps.append({"step": 4, "status": status, "stage": body.get("stage"),
                      "setup_path": setup_path})
        if not (status == 200 and body.get("stage") == "deployed" and setup_path):
            raise ProbeFailure(f"step 4 failed: {body}")

        setup_check = ssh(args.host,
                          f"test -f {shlex.quote(setup_path)} && "
                          f"grep -F ramic_bridge_daemon_27.py {shlex.quote(setup_path)} "
                          f"&& test -f {shlex.quote(daemon_root + '/ramic/ramic_bridge_daemon_27.py')}",
                          timeout=60)
        results.add("step4-py27-variant-and-setup", setup_check.returncode == 0,
                    detail=(setup_check.stdout or setup_check.stderr).strip())
        if setup_check.returncode != 0:
            raise ProbeFailure("deployed setup did not select/reference the py27 daemon")

        # Step 5 negative: daemon is not started yet; verify must fail and stay writable.
        status, body = call({"action": "verify", "user": user, "token": session})
        results.add("step5-verify-fails-before-daemon",
                    status == 200 and body.get("stage") == "failed" and body.get("step") == 5,
                    status=status, stage=body.get("stage"), step=body.get("step"))
        steps.append({"step": 5, "phase": "before-daemon", "status": status,
                      "stage": body.get("stage")})
        if not (status == 200 and body.get("stage") == "failed"):
            raise ProbeFailure(f"verify before daemon unexpectedly passed: {body}")

        daemon = RemotePy27Daemon(args.host, args.py27, root, daemon_port, token)
        daemon.start()
        status, body = call({"action": "verify", "user": user, "token": session})
        report = body.get("report") or {}
        results.add("step5-verify-py27",
                    status == 200 and body.get("stage") == "verified"
                    and report.get("command_ok") and report.get("skill_ok")
                    and report.get("token_ok"),
                    status=status, stage=body.get("stage"), report=report)
        steps.append({"step": 5, "phase": "after-daemon", "status": status,
                      "stage": body.get("stage"), "report": report})
        if not (status == 200 and body.get("stage") == "verified"):
            raise ProbeFailure(f"step 5 failed: {body}")

        status, body = call({"action": "commit", "user": user, "token": session})
        committed = registry.get(user)
        results.add("step6-commit", status == 200 and body.get("stage") == "committed"
                    and committed is not None and committed.registered_at is not None,
                    status=status, stage=body.get("stage"),
                    registered_at=getattr(committed, "registered_at", None))
        steps.append({"step": 6, "status": status, "stage": body.get("stage")})
        if not (status == 200 and body.get("stage") == "committed" and committed):
            raise ProbeFailure(f"step 6 failed: {body}")
        results.add("step6-entry-py27",
                    committed.roles.daemon.python == args.py27
                    and committed.roles.daemon.daemon_port == daemon_port
                    and committed.token == token,
                    token_ok=committed.token == token,
                    python=committed.roles.daemon.python,
                    daemon_port=committed.roles.daemon.daemon_port)
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
        results.add("py27-registration-error", False, error=error)
    finally:
        if daemon is not None:
            daemon.stop()
        try:
            server.shutdown()
            server.server_close()
        except Exception:  # noqa: BLE001
            pass
        thread.join(timeout=5)
        if cleanup_allowed and not args.keep_remote:
            cleanup_remote_root(args.host, root)
            remote_root_removed = True

    payload = {
        "tb": "registration_py27_tb",
        "status": "PASS" if results.passed == len(results.items) and not error else "FAIL",
        "environment": {
            "host": args.host, "ssh_user": args.ssh_user,
            "py27": args.py27, "checks": env_checks,
        },
        "user": user,
        "token_present": bool(token),
        "daemon_port": daemon_port,
        "remote_root": root,
        "remote_root_removed": remote_root_removed,
        "checks": results.items,
        "steps": steps,
        "http_trail": http.trail,
        "passed": results.passed,
        "total": len(results.items),
        "error": error,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    ok = results.passed == len(results.items) and not error
    print(f"\n{results.passed}/{len(results.items)} 通过；证据：{out}")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
