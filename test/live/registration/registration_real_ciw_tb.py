# === TB 注释头（规范见 test/docs/写TB规范.md §0）=====================
# 作者: 设计/Codex
# 最后改动: 2026-09-28 15:45
# 依赖: 无
# =====================================================================
# 六步流程（按 test/docs/写TB规范.md §1–§6）：
# §1 环境检查：wsl-gent SSH、钥匙、可丢弃 CIW 依赖（xvfb/virtuoso/cds.lib/ramic 资源）。
# §2 构建：本地工作根 + RegistrationServer + 可丢弃 CIW（bootstrap daemon）。
# §3 最终检查：bootstrap 端口在听、第 3/4 步候选与部署文件就位。
# §4 执行：注册 1–4 → ciw_load_setup.py 注入 RBStop()+load(setup) → 5/6。
# §5 比对：真实 daemon 1+2 应答、第 5 步双冒烟、注册表条目与 setup 路径。
# §6 重复/收尾：停可丢弃 CIW、清测试远端根，保留 JSON 证据。
"""注册第 5 步走**真实 CIW**的 live TB（P4）。

与 fake daemon 版六步 TB 的区别：第 4 步 deploy 后，由测试侧预置的
``start_disposable_ciw.sh`` 起一个真 Virtuoso CIW；``ciw_load_setup.py``
通过该 CIW 里预载的 bootstrap daemon 执行::

    progn(RBStop() load("<注册第 4 步生成的 setup>"))

这正是“用户把 load(...) 粘进 CIW”的等价注入。随后注册第 5 步连接的是
CIW 里新起的**真实 daemon**（不是 fake），第 6 步才 commit。

用法::

    PYTHONPATH=src python test/live/registration/registration_real_ciw_tb.py \
        --work-dir test/artifacts/env/reg-real-ciw \
        --out test/artifacts/evidence/tb-sixstep-20260928/registration-real-ciw.json
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import threading
import types
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
    redact,
    remote_free_port,
    remote_home,
    ssh,
    wait_remote_port,
)

START_CIW = ROOT / "test" / "shared" / "runners" / "start_disposable_ciw.sh"
STOP_CIW = ROOT / "test" / "shared" / "runners" / "stop_disposable_ciw.sh"
CIW_LOADER = ROOT / "test" / "shared" / "runners" / "ciw_load_setup.py"


def run_remote_script(script: Path, host: str, args: list[str],
                      timeout: float) -> types.SimpleNamespace:
    command = "bash -s -- " + " ".join(shlex.quote(str(item)) for item in args)
    # Git on Windows may check the shell script out with CRLF; bash on the
    # remote side rejects `set -e\r`.  Normalise and send bytes: passing a str
    # with text=True would let Windows text mode reintroduce CRLF on stdin.
    body = script.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", host, command],
        input=body.encode("utf-8"),
        capture_output=True, timeout=timeout, **no_window(),
    )
    return types.SimpleNamespace(
        returncode=proc.returncode,
        stdout=proc.stdout.decode("utf-8", "replace"),
        stderr=proc.stderr.decode("utf-8", "replace"),
    )


def environment_checks(host: str, display: str, key_dir: str, key: str) -> tuple[bool, list[dict]]:
    checks: list[dict] = []

    reachable = ssh(host, "echo vb-ok", timeout=30)
    checks.append({"name": "ssh-reachable",
                   "ok": reachable.returncode == 0 and "vb-ok" in reachable.stdout,
                   "detail": (reachable.stdout or reachable.stderr).strip()})

    key_path = Path(key_dir).expanduser() / key
    checks.append({"name": "client-key-present",
                   "ok": key_path.is_file() and Path(str(key_path) + ".pub").is_file(),
                   "detail": {"key": str(key_path)}})

    for tool in ("bash", "python3", "ss", "scp"):
        result = ssh(host, f"command -v {tool}", timeout=30)
        checks.append({"name": f"remote-tool-{tool}",
                       "ok": result.returncode == 0,
                       "detail": (result.stdout or result.stderr).strip()})

    if display:
        display_ok = ssh(host, f"DISPLAY={shlex.quote(display)} xdpyinfo >/dev/null 2>&1",
                         timeout=30)
        checks.append({"name": "explicit-display",
                       "ok": display_ok.returncode == 0, "detail": display})
    else:
        xvfb = ssh(host, "command -v xvfb-run", timeout=30)
        checks.append({"name": "headless-xvfb-run",
                       "ok": xvfb.returncode == 0,
                       "detail": (xvfb.stdout or xvfb.stderr).strip()})

    cdslib = ssh(
        host,
        'for p in "$HOME/.virtuoso-bridge/vblog/run/cds.lib" '
        '"$HOME/project/vblog/cds.lib" "$HOME/project/test/cds.lib" '
        '"$HOME/project/main/cds.lib"; do [ -f "$p" ] && { echo "$p"; exit 0; }; done; exit 1',
        timeout=30,
    )
    checks.append({"name": "cds.lib-present",
                   "ok": cdslib.returncode == 0,
                   "detail": cdslib.stdout.strip() or cdslib.stderr.strip()})

    resources = ssh(
        host,
        'for p in "$HOME/project/vblog/tb-sandbox/linux-client/repo/src/bridge/resources/ramic_bridge.il" '
        '"$HOME/.virtuoso-bridge/vblog/ramic/ramic_bridge.il"; do '
        '[ -f "$p" ] && { echo "$p"; exit 0; }; done; exit 1',
        timeout=30,
    )
    checks.append({"name": "ramic-resources-present",
                   "ok": resources.returncode == 0,
                   "detail": resources.stdout.strip() or resources.stderr.strip()})

    virtuoso = ssh(
        host,
        "command -v virtuoso || test -x /opt/eda/cadence/IC618/tools/dfII/bin/64bit/virtuoso",
        timeout=30,
    )
    checks.append({"name": "virtuoso-binary",
                   "ok": virtuoso.returncode == 0,
                   "detail": (virtuoso.stdout or virtuoso.stderr).strip()})
    return all(item["ok"] for item in checks), checks


def parse_start_output(stdout: str) -> dict:
    for line in stdout.splitlines():
        if line.startswith("NAME="):
            result = {}
            for part in line.split():
                if "=" in part:
                    key, value = part.split("=", 1)
                    result[key] = value
            return result
    raise ProbeFailure(f"start_disposable_ciw.sh returned no NAME= line: {stdout[-500:]}")


def stop_disposable_ciw(host: str, name: str, port: int, token: str) -> subprocess.CompletedProcess:
    return run_remote_script(STOP_CIW, host, [name, str(port), token], timeout=90)


def cleanup_remote_root(host: str, root: str) -> None:
    ssh(host, f"rm -rf {shlex.quote(root)}", timeout=60)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--out", default="")
    parser.add_argument("--host", default="wsl-gent")
    parser.add_argument("--ssh-user", default="Gent")
    parser.add_argument("--ssh-key-dir", default="~/.ssh")
    parser.add_argument("--ssh-key", default="id_ed25519")
    parser.add_argument("--display", default="", help="显式 DISPLAY；缺省用 xvfb-run headless")
    parser.add_argument("--keep-remote", action="store_true")
    args = parser.parse_args(argv)

    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    init_work_dir(work_dir)
    out = Path(args.out) if args.out else work_dir / "registration-real-ciw.json"
    out.parent.mkdir(parents=True, exist_ok=True)

    env_ok, env_checks = environment_checks(
        args.host, args.display, args.ssh_key_dir, args.ssh_key)
    if not env_ok:
        payload = {"tb": "registration_real_ciw_tb", "status": "environment_failed",
                   "environment": {"host": args.host, "display": args.display},
                   "checks": env_checks}
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        print(f"[ENV-FAIL] real-CIW registration environment not ready; evidence: {out}")
        return 2

    tag = uuid.uuid4().hex[:8]
    name = f"ciwreg{tag}"
    user = f"vbciw{tag}"
    token = f"vbciw{tag}-00"
    bootstrap_port = remote_free_port(args.host)
    daemon_port = remote_free_port(args.host)
    while daemon_port == bootstrap_port:
        daemon_port = remote_free_port(args.host)
    local_port = local_free_port()
    root = f"{remote_home(args.host).rstrip('/')}/.virtuoso-bridge/{user}"

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
    ciw_info: dict = {}
    injector: dict = {}
    error = ""
    try:
        started = run_remote_script(
            START_CIW, args.host, [name, str(bootstrap_port)] + ([args.display] if args.display else []),
            timeout=240,
        )
        if started.returncode != 0:
            raise ProbeFailure(f"start_disposable_ciw.sh failed: {started.stderr.strip()}")
        ciw_info = parse_start_output(started.stdout)
        bootstrap_token = ciw_info.get("TOKEN") or f"vb-{name}"
        results.add("ciw-bootstrap-listening",
                    ciw_info.get("PORT") == str(bootstrap_port)
                    and wait_remote_port(args.host, bootstrap_port, timeout=10),
                    port=bootstrap_port)

        request_payload = {
            "action": "apply", "user": user, "mode": "remote", "token": token,
            "ssh": {"default": {"host": args.host, "user": args.ssh_user,
                                "key_dir": args.ssh_key_dir, "key": args.ssh_key}},
            "root": {"default": root},
            "roles": {"daemon": {"python": "python3",
                                  "daemon_port": daemon_port,
                                  "local_port": local_port},
                      "gui": ({"display": args.display} if args.display else {})},
            "log_level": "off",
        }
        status, body = http.call("POST", "/api/register", request_payload)
        session = body.get("token")
        results.add("step1-apply", status == 200 and body.get("stage") == "applied",
                    status=status, stage=body.get("stage"))
        steps.append({"step": 1, "status": status, "stage": body.get("stage")})
        if not (status == 200 and body.get("stage") == "applied" and session):
            raise ProbeFailure(f"step 1 failed: {body}")

        for action, step_no in (("validate", 2), ("probe", 3), ("deploy", 4)):
            status, body = http.call("POST", "/api/register",
                                     {"action": action, "user": user, "token": session})
            expected_stage = {"validate": "validated", "probe": "probed",
                              "deploy": "deployed"}[action]
            results.add(f"step{step_no}-{action}",
                        status == 200 and body.get("stage") == expected_stage,
                        status=status, stage=body.get("stage"), errors=body.get("errors"))
            steps.append({"step": step_no, "status": status,
                          "stage": body.get("stage"),
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
            if action == "deploy":
                setup_path = str(body.get("setup_path") or "")
                remote_setup = ssh(
                    args.host, f"test -f {shlex.quote(setup_path)} && echo present",
                    timeout=30)
                results.add("deploy-setup-present",
                            remote_setup.returncode == 0
                            and "present" in (remote_setup.stdout or ""),
                            setup_path=setup_path)

        # Inject the real load through the disposable CIW's bootstrap daemon.
        loader_env = dict(os.environ)
        loader_env["PYTHONPATH"] = str(SRC) + os.pathsep + loader_env.get("PYTHONPATH", "")
        loaded = subprocess.run(
            [sys.executable, str(CIW_LOADER),
             "--host", args.host,
             "--bootstrap-port", str(bootstrap_port),
             "--bootstrap-token", bootstrap_token,
             "--setup", setup_path,
             "--verify-port", str(daemon_port),
             "--verify-token", token,
             "--timeout", "120"],
            capture_output=True, text=True, timeout=180,
            env=loader_env, **no_window(),
        )
        try:
            injector = json.loads(loaded.stdout)
        except ValueError:
            injector = {"raw": loaded.stdout[-1000:], "stderr": loaded.stderr[-1000:]}
        verify_ok = bool((injector.get("verify") or {}).get("ok"))
        results.add("ciw-load-real-daemon",
                    loaded.returncode == 0 and verify_ok,
                    returncode=loaded.returncode, verify=injector.get("verify"),
                    inject_transport=injector.get("inject_transport_result"))
        steps.append({"action": "ciw-load-setup", "status": loaded.returncode,
                      "verify": injector.get("verify")})
        if not verify_ok:
            raise ProbeFailure(f"real daemon did not answer after CIW load: {injector}")

        status, body = http.call("POST", "/api/register",
                                 {"action": "verify", "user": user, "token": session})
        report = body.get("report") or {}
        results.add("step5-verify-real-ciw",
                    status == 200 and body.get("stage") == "verified"
                    and report.get("command_ok") and report.get("skill_ok")
                    and report.get("token_ok"),
                    status=status, stage=body.get("stage"), report=report)
        steps.append({"step": 5, "status": status, "stage": body.get("stage"),
                      "report": report})
        if not (status == 200 and body.get("stage") == "verified"):
            raise ProbeFailure(f"step 5 failed: {body}")

        status, body = http.call("POST", "/api/register",
                                 {"action": "commit", "user": user, "token": session})
        committed = registry.get(user)
        results.add("step6-commit-real-ciw",
                    status == 200 and body.get("stage") == "committed"
                    and committed is not None and committed.registered_at is not None,
                    status=status, stage=body.get("stage"))
        steps.append({"step": 6, "status": status, "stage": body.get("stage")})
        if not (status == 200 and body.get("stage") == "committed" and committed):
            raise ProbeFailure(f"step 6 failed: {body}")
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
        results.add("real-ciw-registration-error", False, error=error)
    finally:
        if "daemon_port" in locals():
            stopped_daemon = subprocess.run(
                [sys.executable, str(CIW_LOADER),
                 "--host", args.host,
                 "--bootstrap-port", str(daemon_port),
                 "--bootstrap-token", token,
                 "--stop-only", "--timeout", "15"],
                capture_output=True, text=True, timeout=30,
                env={**os.environ,
                     "PYTHONPATH": str(SRC) + os.pathsep + os.environ.get("PYTHONPATH", "")},
                **no_window(),
            )
            try:
                stop_payload = json.loads(stopped_daemon.stdout)
            except ValueError:
                stop_payload = {}
            # `--stop-only` intentionally exits 0 even when RBStop timed out;
            # the resource-level judgement is whether the port is still up.
            stop_ok = bool(stop_payload.get("ok"))
            if not stop_ok and not wait_remote_port(args.host, daemon_port, timeout=3):
                stop_ok = True
            results.add("registered-daemon-stopped", stop_ok,
                        detail=(stopped_daemon.stdout or stopped_daemon.stderr).strip()[-300:])
            # Best-effort fallback: the deployed daemon lives under the unique
            # user root; the disposable-CIW stop script only knows its own root.
            ssh(args.host,
                f"pkill -f 'ramic_bridge_daemon_[23][.]py.*{shlex.quote(user)}' || true",
                timeout=30)
        stopped = stop_disposable_ciw(
            args.host, ciw_info.get("NAME", name),
            bootstrap_port,
            ciw_info.get("TOKEN", f"vb-{name}"),
        )
        results.add("ciw-stopped",
                    stopped.returncode == 0,
                    detail=(stopped.stdout or stopped.stderr).strip()[-400:])
        if not args.keep_remote:
            cleanup_remote_root(args.host, root)
        try:
            server.shutdown()
            server.server_close()
        except Exception:  # noqa: BLE001
            pass
        thread.join(timeout=5)

    payload = {
        "tb": "registration_real_ciw_tb",
        "status": "PASS" if results.passed == len(results.items) and not error else "FAIL",
        "environment": {
            "host": args.host, "display": args.display, "checks": env_checks,
        },
        "work_dir": str(work_dir),
        "user": user,
        "daemon_port": daemon_port,
        "setup_path": setup_path if "setup_path" in locals() else "",
        "ciw": {key: value for key, value in ciw_info.items() if key != "TOKEN"},
        "checks": results.items,
        "steps": steps,
        "http_trail": http.trail,
        "injector": redact(injector),
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
