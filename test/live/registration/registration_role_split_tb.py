# === TB 注释头（规范见 test/docs/写TB规范.md §0）=====================
# 作者: 设计/Codex
# 最后改动: 2026-09-28 15:52
# 依赖: 无
# =====================================================================
# 六步流程（按 test/docs/写TB规范.md §1–§6）：
# §1 环境检查：wsl-gent/w1-gent SSH、两把客户端钥匙、display、spectre bin、两端可写根。
# §2 构建：本地工作根 + RegistrationServer + 唯一 user/token/端口与五 role 目标。
# §3 最终检查：五 role 的 host/root/display/bin 回退解析正确，端口空闲。
# §4 执行：apply→validate→probe→deploy→verify（fake daemon）→commit。
# §5 比对：每 role host/root/expected_fingerprint、部署只落 daemon 根、后续真中间层跨机路由。
# §6 重复/收尾：停止 daemon、清理两端测试根，保留 JSON 证据。
"""注册阶段五 role 跨主机 live TB（P3）。

不只看“接口 ok”：注册一个用户，把五个 role 明确拆到两/三台机器，
要求注册探测逐 role 固化 host/root/fingerprint，部署只落 daemon 根；
commit 后再用真实中层消费这份注册表，验证 command/file 真的落 w1、
skill/daemon 真的落 wsl。

拓扑（可用参数覆盖）：

* gui / daemon / spectre → wsl-gent (Gent, display :11, spectre path)
* command / file           → w1-gent (dev, ``lab_w1_ed25519``)

用法::

    PYTHONPATH=src python test/live/registration/registration_role_split_tb.py \
        --work-dir test/artifacts/env/reg-role-split \
        --out test/artifacts/evidence/tb-sixstep-20260928/registration-role-split.json
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import threading
import time
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
from registration_tb_support import (  # noqa: E402
    Http,
    ProbeFailure,
    Results,
    local_free_port,
    no_window,
    remote_free_port,
    remote_home,
    ssh,
    wait_remote_port,
)

FAKE_DAEMON = _FIXTURES / "fake_daemon_host.py"


class RemoteFakeDaemon:
    """Protocol fake daemon on the daemon host (used only for step-5 smoke)."""

    def __init__(self, host: str, root: str, port: int, token: str) -> None:
        self.host = host
        self.root = root
        self.port = port
        self.token = token
        self.tag = uuid.uuid4().hex[:8]
        self.remote_dir = f"{root.rstrip('/')}/tmp/tb-rolefake-{self.tag}"
        self.proc: subprocess.Popen | None = None

    def _script(self) -> str:
        return f"{self.remote_dir}/fake_daemon_host.py"

    def start(self) -> None:
        result = ssh(self.host, f"mkdir -p {shlex.quote(self.remote_dir)}", timeout=30)
        if result.returncode != 0:
            raise ProbeFailure(f"cannot create fake daemon dir: {result.stderr.strip()}")
        copied = subprocess.run(
            ["scp", "-q", str(FAKE_DAEMON), f"{self.host}:{self._script()}"],
            capture_output=True, text=True, timeout=60, **no_window(),
        )
        if copied.returncode != 0:
            raise ProbeFailure(f"scp fake daemon failed: {copied.stderr.strip()}")
        prefix = self.token[:-3] if self.token.endswith("-00") else self.token
        command = (
            f"exec python3 {shlex.quote(self._script())} "
            f"--base-port {self.port} --count 1 --token-prefix {shlex.quote(prefix)}"
        )
        self.proc = subprocess.Popen(
            ["ssh", self.host, command],
            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, **no_window(),
        )
        if not wait_remote_port(self.host, self.port, timeout=25):
            self.stop()
            raise ProbeFailure(f"fake daemon did not listen on {self.host}:{self.port}")

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
            f"pkill -f 'fake_daemon_host[.]py --base-port {self.port}' || true",
            timeout=30)
        ssh(self.host, f"rm -rf {shlex.quote(self.remote_dir)}", timeout=30)


def default_lab_key_dir() -> str:
    return r"C:\wsl\shared\keys" if os.name == "nt" else "~/.ssh"


def ensure_lab_host(host: str, timeout: float = 120.0) -> tuple[bool, subprocess.Popen | None]:
    """Lab WSLs stop themselves when idle; pin w1 open for this TB."""
    if ssh(host, "hostname", timeout=12).returncode == 0:
        return True, None
    if os.name != "nt":
        return False, None
    keepalive = subprocess.Popen(
        ["wsl.exe", "-d", host, "--", "sleep", "infinity"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **no_window(),
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if ssh(host, "hostname", timeout=12).returncode == 0:
            return True, keepalive
        time.sleep(3.0)
    return False, keepalive


def environment_checks(args) -> tuple[bool, list[dict]]:
    checks: list[dict] = []
    tag = uuid.uuid4().hex[:8]

    for label, host, user in (("wsl", args.ws_host, args.ws_user),
                              ("lab", args.lab_host, args.lab_user)):
        reachable = ssh(host, "echo vb-ok", timeout=30)
        reachable_ok = reachable.returncode == 0 and "vb-ok" in reachable.stdout
        checks.append({"name": f"{label}-ssh-reachable",
                       "ok": reachable_ok,
                       "detail": {"host": host, "user": user,
                                  "output": (reachable.stdout or reachable.stderr).strip()}})
        if not reachable_ok:
            continue
        for tool in ("python3", "ss", "scp"):
            result = ssh(host, f"command -v {tool}", timeout=30)
            checks.append({"name": f"{label}-tool-{tool}",
                           "ok": result.returncode == 0,
                           "detail": (result.stdout or result.stderr).strip()})
        probe_root = f"{remote_home(host).rstrip('/')}/.virtuoso-bridge/.regprobe-{tag}"
        writable = ssh(
            host,
            f"mkdir -p {shlex.quote(probe_root)} && touch "
            f"{shlex.quote(probe_root + '/ok')} && rm -rf {shlex.quote(probe_root)}",
            timeout=30,
        )
        checks.append({"name": f"{label}-home-writable",
                       "ok": writable.returncode == 0,
                       "detail": (writable.stdout or writable.stderr).strip()})

    ws_key = Path(args.ws_key_dir).expanduser() / args.ws_key
    lab_key = Path(args.lab_key_dir).expanduser() / args.lab_key
    checks.append({"name": "wsl-key-present",
                   "ok": ws_key.is_file() and Path(str(ws_key) + ".pub").is_file(),
                   "detail": str(ws_key)})
    checks.append({"name": "lab-key-present",
                   "ok": lab_key.is_file() and Path(str(lab_key) + ".pub").is_file(),
                   "detail": str(lab_key)})

    display = ssh(args.ws_host,
                  f"DISPLAY={shlex.quote(args.ws_display)} xdpyinfo >/dev/null 2>&1",
                  timeout=30)
    checks.append({"name": "wsl-display-valid",
                   "ok": display.returncode == 0, "detail": args.ws_display})

    spectre = ssh(args.ws_host, f"test -x {shlex.quote(args.spectre_bin)}", timeout=30)
    checks.append({"name": "spectre-bin-present",
                   "ok": spectre.returncode == 0, "detail": args.spectre_bin})
    return all(item["ok"] for item in checks), checks


def cleanup_remote_root(host: str, root: str) -> None:
    ssh(host, f"rm -rf {shlex.quote(root)}", timeout=60)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--out", default="")
    parser.add_argument("--ws-host", default="wsl-gent")
    parser.add_argument("--ws-user", default="Gent")
    parser.add_argument("--ws-key-dir", default="~/.ssh")
    parser.add_argument("--ws-key", default="id_ed25519")
    parser.add_argument("--ws-display", default=":11")
    parser.add_argument("--lab-host", default="w1-gent")
    parser.add_argument("--lab-user", default="dev")
    parser.add_argument("--lab-key-dir", default=default_lab_key_dir())
    parser.add_argument("--lab-key", default="lab_w1_ed25519")
    parser.add_argument("--spectre-bin", default="/opt/eda/cadence/SPECTRE241/bin/spectre")
    parser.add_argument("--keep-remote", action="store_true")
    args = parser.parse_args(argv)

    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    init_work_dir(work_dir)
    out = Path(args.out) if args.out else work_dir / "registration-role-split.json"
    out.parent.mkdir(parents=True, exist_ok=True)

    lab_keepalive: subprocess.Popen | None = None
    if args.lab_host in ("w1-gent", "w2-gent", "w3-gent", "w4-gent"):
        _, lab_keepalive = ensure_lab_host(args.lab_host)

    env_ok, env_checks = environment_checks(args)
    if not env_ok:
        payload = {"tb": "registration_role_split_tb", "status": "environment_failed",
                   "environment": {"ws_host": args.ws_host, "lab_host": args.lab_host},
                   "checks": env_checks}
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        print(f"[ENV-FAIL] role-split registration environment not ready; evidence: {out}")
        if lab_keepalive is not None:
            lab_keepalive.terminate()
        return 2

    tag = uuid.uuid4().hex[:8]
    user = f"vbrole{tag}"
    token = f"vbrole{tag}-00"
    daemon_port = remote_free_port(args.ws_host)
    local_port = local_free_port()
    ws_root = f"{remote_home(args.ws_host).rstrip('/')}/.virtuoso-bridge/{user}"
    lab_root = f"{remote_home(args.lab_host).rstrip('/')}/.virtuoso-bridge/{user}"
    registry = load_registry(registry_path())
    if registry.get(user) is not None:
        registry.remove(user)

    http_port = local_free_port()
    server = RegistrationServer(("127.0.0.1", http_port), registry)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    http = Http(f"http://127.0.0.1:{http_port}")
    results = Results()
    steps: list[dict] = []
    fake: RemoteFakeDaemon | None = None
    error = ""
    entry: dict = {}
    setup_path = ""
    registry_snapshot = registry_path().read_bytes() if registry_path().exists() else None
    try:
        payload = {
            "action": "apply", "user": user, "mode": "remote", "token": token,
            "ssh": {"default": {"host": args.ws_host, "user": args.ws_user,
                                "key_dir": args.ws_key_dir, "key": args.ws_key}},
            "root": {"default": None},
            "roles": {
                "gui": {"host": args.ws_host, "user": args.ws_user,
                        "key_dir": args.ws_key_dir, "key": args.ws_key,
                        "root": f"{ws_root}/gui", "display": args.ws_display},
                "daemon": {"host": args.ws_host, "user": args.ws_user,
                           "key_dir": args.ws_key_dir, "key": args.ws_key,
                           "root": f"{ws_root}/daemon",
                           # 注册探测用 `test -x <显式值>` 校验，裸命令名会被拒（P-077）；
                           # 这里给绝对路径（= 目标机 `command -v python3`）。
                           "python": "/usr/local/bin/python3",
                           "daemon_port": daemon_port, "local_port": local_port},
                "command": {"host": args.lab_host, "user": args.lab_user,
                            "key_dir": args.lab_key_dir, "key": args.lab_key,
                            "root": f"{lab_root}/command"},
                "file": {"host": args.lab_host, "user": args.lab_user,
                         "key_dir": args.lab_key_dir, "key": args.lab_key,
                         "root": f"{lab_root}/file"},
                "spectre": {"host": args.ws_host, "user": args.ws_user,
                            "key_dir": args.ws_key_dir, "key": args.ws_key,
                            "root": f"{ws_root}/spectre", "bin": args.spectre_bin},
            },
            "log_level": "off",
        }
        status, body = http.call("POST", "/api/register", payload)
        session = body.get("token")
        results.add("step1-apply", status == 200 and body.get("stage") == "applied",
                    status=status, stage=body.get("stage"))
        steps.append({"step": 1, "status": status, "stage": body.get("stage")})
        if not (status == 200 and body.get("stage") == "applied" and session):
            raise ProbeFailure(f"step 1 failed: {body}")

        for action, step_no, expected_stage in (
            ("validate", 2, "validated"),
            ("probe", 3, "probed"),
            ("deploy", 4, "deployed"),
        ):
            status, body = http.call("POST", "/api/register",
                                     {"action": action, "user": user, "token": session})
            results.add(f"step{step_no}-{action}",
                        status == 200 and body.get("stage") == expected_stage,
                        status=status, stage=body.get("stage"), errors=body.get("errors"))
            steps.append({"step": step_no, "status": status, "stage": body.get("stage"),
                          "setup_path": body.get("setup_path")})
            if not (status == 200 and body.get("stage") == expected_stage):
                raise ProbeFailure(f"step {step_no} failed: {body}")
            if action == "probe":
                entry = body.get("entry") or {}
                roles = entry.get("roles") or {}
                results.add("probe-five-role-entries",
                            all(name in roles for name in
                                ("gui", "daemon", "command", "file", "spectre")),
                            roles=sorted(roles))
                for name in ("gui", "daemon", "command", "file", "spectre"):
                    role = roles.get(name) or {}
                    root = role.get("root") or ""
                    results.add(f"probe-{name}-root-absolute",
                                bool(root) and str(root).startswith("/"),
                                root=root)
                    results.add(f"probe-{name}-fingerprint",
                                bool(role.get("expected_fingerprint")) or name == "spectre",
                                expected_fingerprint=role.get("expected_fingerprint"))
                results.add("probe-per-role-hosts",
                            (roles.get("gui") or {}).get("host") == args.ws_host
                            and (roles.get("daemon") or {}).get("host") == args.ws_host
                            and (roles.get("command") or {}).get("host") == args.lab_host
                            and (roles.get("file") or {}).get("host") == args.lab_host
                            and (roles.get("spectre") or {}).get("host") == args.ws_host,
                            gui=(roles.get("gui") or {}).get("host"),
                            daemon=(roles.get("daemon") or {}).get("host"),
                            command=(roles.get("command") or {}).get("host"),
                            file=(roles.get("file") or {}).get("host"),
                            spectre=(roles.get("spectre") or {}).get("host"))
                results.add("probe-gui-display",
                            (roles.get("gui") or {}).get("display") == args.ws_display,
                            display=(roles.get("gui") or {}).get("display"))
                results.add("probe-spectre-bin",
                            (roles.get("spectre") or {}).get("bin") == args.spectre_bin,
                            bin=(roles.get("spectre") or {}).get("bin"))
            if action == "deploy":
                setup_path = str(body.get("setup_path") or "")
                ws_setup = ssh(args.ws_host,
                               f"test -f {shlex.quote(setup_path)} && echo present",
                               timeout=30)
                results.add("deploy-setup-on-daemon-host",
                            ws_setup.returncode == 0 and "present" in (ws_setup.stdout or ""),
                            setup_path=setup_path)
                ws_tree = ssh(
                    args.ws_host,
                    f"test -d {shlex.quote(f'{ws_root}/daemon/ramic')} && "
                    f"test -d {shlex.quote(f'{ws_root}/daemon/setup')} && "
                    f"test -d {shlex.quote(f'{ws_root}/daemon/status')} && echo present",
                    timeout=30,
                )
                results.add("deploy-tree-on-daemon-host",
                            ws_tree.returncode == 0 and "present" in (ws_tree.stdout or ""),
                            root=f"{ws_root}/daemon")
                lab_no_tree = ssh(
                    args.lab_host,
                    f"test ! -e {shlex.quote(f'{lab_root}/command/ramic')} && "
                    f"test ! -e {shlex.quote(f'{lab_root}/file/ramic')} && echo clean",
                    timeout=30,
                )
                results.add("deploy-not-on-command-file-roots",
                            lab_no_tree.returncode == 0 and "clean" in (lab_no_tree.stdout or ""),
                            command_root=f"{lab_root}/command", file_root=f"{lab_root}/file")
        results.add("steps-1-4-zero-registry-write",
                    (registry_path().read_bytes() if registry_path().exists() else None)
                    == registry_snapshot)

        fake = RemoteFakeDaemon(args.ws_host, f"{ws_root}/daemon", daemon_port, token)
        fake.start()
        status, body = http.call("POST", "/api/register",
                                 {"action": "verify", "user": user, "token": session})
        report = body.get("report") or {}
        results.add("step5-verify-cross-host",
                    status == 200 and body.get("stage") == "verified"
                    and report.get("command_ok") and report.get("skill_ok")
                    and report.get("token_ok"),
                    status=status, stage=body.get("stage"), report=report)
        steps.append({"step": 5, "status": status, "stage": body.get("stage"),
                      "report": report})
        if not (status == 200 and body.get("stage") == "verified"):
            raise ProbeFailure(f"step 5 failed: {body}")
        results.add("step5-zero-registry-write",
                    (registry_path().read_bytes() if registry_path().exists() else None)
                    == registry_snapshot)

        status, body = http.call("POST", "/api/register",
                                 {"action": "commit", "user": user, "token": session})
        committed = registry.get(user)
        results.add("step6-commit",
                    status == 200 and body.get("stage") == "committed"
                    and committed is not None and committed.registered_at is not None,
                    status=status, stage=body.get("stage"))
        steps.append({"step": 6, "status": status, "stage": body.get("stage")})
        if not (status == 200 and body.get("stage") == "committed" and committed):
            raise ProbeFailure(f"step 6 failed: {body}")

        # 用真实中层消费刚提交的注册表：command/file 必须落 lab，skill 必须落 ws。
        from transport.middle import BusinessServer  # noqa: E402
        middle = BusinessServer()
        try:
            direct_lab = ssh(args.lab_host, "hostname", timeout=30).stdout.strip()
            ran = middle.run_command("hostname", timeout=60, token=token)
            results.add("postcommit-command-lands-lab",
                        ran.returncode == 0 and ran.stdout.strip() == direct_lab,
                        direct=direct_lab, stdout=ran.stdout.strip(), kind=ran.kind)
            skill = middle.execute_skill("RBDToken", timeout=60, token=token)
            results.add("postcommit-skill-lands-ws",
                        skill.ok and (skill.output or "").strip().strip('"') == token,
                        output=(skill.output or "").strip()[:80], status=str(skill.status))
            local_file = work_dir / "role-split-upload.txt"
            local_file.write_text(f"role-split-{tag}\n", encoding="utf-8")
            remote_file = f"{lab_root}/file/roundtrip.txt"
            up = middle.upload_file(local_file, remote_file, timeout=60, token=token)
            cat = ssh(args.lab_host, f"cat {shlex.quote(remote_file)}", timeout=30)
            down_file = work_dir / "role-split-download.txt"
            down = middle.download_file(remote_file, down_file, timeout=60, token=token)
            results.add("postcommit-file-lands-lab",
                        up.returncode == 0 and down.returncode == 0
                        and cat.returncode == 0
                        and cat.stdout == local_file.read_text(encoding="utf-8")
                        and down_file.read_text(encoding="utf-8")
                        == local_file.read_text(encoding="utf-8"),
                        upload_rc=up.returncode, download_rc=down.returncode,
                        remote=cat.stdout.strip(), local=down_file.read_text(encoding="utf-8").strip())
        finally:
            middle.close()
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
        results.add("role-split-registration-error", False, error=error)
    finally:
        if fake is not None:
            fake.stop()
        if not args.keep_remote:
            cleanup_remote_root(args.ws_host, ws_root)
            cleanup_remote_root(args.lab_host, lab_root)
        try:
            server.shutdown()
            server.server_close()
        except Exception:  # noqa: BLE001
            pass
        thread.join(timeout=5)
        if lab_keepalive is not None:
            lab_keepalive.terminate()

    payload = {
        "tb": "registration_role_split_tb",
        "status": "PASS" if results.passed == len(results.items) and not error else "FAIL",
        "environment": {
            "ws_host": args.ws_host, "ws_user": args.ws_user,
            "lab_host": args.lab_host, "lab_user": args.lab_user,
            "display": args.ws_display, "spectre_bin": args.spectre_bin,
            "checks": env_checks,
        },
        "work_dir": str(work_dir),
        "user": user,
        "daemon_port": daemon_port,
        "local_port": local_port,
        "ws_root": ws_root,
        "lab_root": lab_root,
        "entry": entry,
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
