# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-29 20:37
# 依赖: registration_http_six_step_tb.FakeDaemon（远端协议兼容 fake daemon）
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1–§6）：
# ① 环境检查：w4-gent 可达、sudo 免密轮换脚本可用、known_hosts 有基线
#    （缺失则按首信任补录，运行结束恢复备份）；
# ② 构建：临时 work-dir/registry + 自起 RegistrationServer；host key 恢复 A 套；
# ③ 最终检查：A 套实况指纹 == known_hosts 基线（产品 probe 读同一值）；
# ④ 执行：apply → validate → probe → deploy → 起 fake daemon → use-b →
#    verify（必须失败）→ restore → verify 原样重试（必须成功）→ commit →
#    update 改 role host（§6.5 按首信任重建指纹）；
# ⑤ 比对：轮换期 verify = stage failed / step 5 / registry 零落盘；
#    恢复后原样重试转绿、commit 落盘；update 后指纹 == 新 endpoint 的
#    known_hosts 基线；显式 expected_fingerprint 不被覆盖；
# ⑥ 收尾：删用户、恢复 host key（finally 必做）、恢复 known_hosts、
#    清远端部署 root。
"""P5 host-key 轮换：远端换 key 必须阻断注册（零落盘），恢复后重试可成功。

覆盖 spec `design-concepts/其他/1-多用户与注册.md`：
* §2 表格「host-key 指纹不匹配 → **ERROR**（唯一阻断的期望类校验）」；
* §6.5 update 改变 role 连接身份/凭据组时按首信任重新探测 host-key
  （显式 expected_fingerprint 优先，不被覆盖）。

环境接口（`test/shared/runners/w4_hostkey_cycle.sh`，需 sudo；测试期间独占 w4）::

    status / use-a / use-b / restore     # 每次输出 SET= 与 SHA256 指纹

本 TB 的控制通道使用**私有 known_hosts + StrictHostKeyChecking=no**，
因此远端换 key 不会打断轮换本身；被测注册流程走正常 ssh 配置与用户
known_hosts，与生产行为一致。实况指纹通过宿主机的 host pub 文件现算
（`ssh-keyscan` 不解析 ssh_config 别名，不能用）。

用法::

    PYTHONPATH=src python test/live/registration/registration_hostkey_rotation_tb.py \
        --work-dir test/artifacts/env/reg-hostkey \
        --out test/artifacts/evidence/round9/reg-hostkey-rotation.json
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shlex
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
_SUPPORT = Path(__file__).resolve().parents[2] / "shared" / "fixtures"
for _path in (str(SRC), str(_SUPPORT), str(Path(__file__).resolve().parent)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from common.paths import init_work_dir, registry_path  # noqa: E402
from common.registry import load_registry  # noqa: E402
from register import probe as reg_probe  # noqa: E402
from register.server import RegistrationServer  # noqa: E402
from registration_http_six_step_tb import (  # noqa: E402
    ADMIN_HEADERS,
    FakeDaemon,
    Http,
    free_port,
)
from registration_tb_support import (  # noqa: E402
    ProbeFailure,
    Results,
    no_window,
    remote_free_port,
)

HOST_KEY_ALGS = ("ed25519", "rsa", "ecdsa")


@dataclass
class Env:
    work_dir: Path
    host: str
    ssh_user: str
    key_dir: str
    key: str
    script: str
    user: str
    control_kh: Path
    control_log: list[dict] = field(default_factory=list)
    fingerprints: dict[str, object] = field(default_factory=dict)


def ssh_capture(env: Env, command: str, timeout: float = 60.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
            "-o", "StrictHostKeyChecking=no",
            "-o", f"UserKnownHostsFile={env.control_kh}",
            env.host, command,
        ],
        capture_output=True, text=True, timeout=timeout, **no_window(),
    )


def ctl(env: Env, command: str, timeout: float = 60.0) -> str:
    """Control-channel ssh (immune to host-key rotation)."""
    result = ssh_capture(env, command, timeout=timeout)
    env.control_log.append({
        "cmd": command, "rc": result.returncode,
        "stdout": (result.stdout or "").strip()[:400],
        "stderr": (result.stderr or "").strip()[:400],
    })
    if result.returncode != 0:
        raise ProbeFailure(
            f"control ssh failed rc={result.returncode}: {result.stderr.strip()}"
        )
    return result.stdout


def hostkey(env: Env, action: str) -> dict[str, str]:
    """Run the sudo-only rotation script; returns SET/FINGERPRINT map."""
    out = ctl(env, f"sudo -n {shlex.quote(env.script)} {action}", timeout=120)
    data: dict[str, str] = {}
    for line in out.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip()
    env.control_log.append({"hostkey_action": action, "parsed": data})
    return data


def live_fingerprints(env: Env) -> dict[str, str]:
    """Fingerprint each host pub key via the control channel (no ssh-keyscan)."""
    fingerprints: dict[str, str] = {}
    for alg in HOST_KEY_ALGS:
        result = ssh_capture(
            env, f"cat /etc/ssh/ssh_host_{alg}_key.pub", timeout=30,
        )
        if result.returncode != 0:
            continue
        parts = (result.stdout or "").split()
        if len(parts) < 2:
            continue
        try:
            blob = base64.b64decode(parts[1], validate=True)
        except Exception:  # noqa: BLE001 - unreadable pub file is simply skipped
            continue
        fingerprints[alg] = "SHA256:" + base64.b64encode(
            hashlib.sha256(blob).digest()
        ).decode("ascii").rstrip("=")
    return fingerprints


def known_hosts_path() -> Path:
    return Path.home() / ".ssh" / "known_hosts"


def request_payload(env: Env, token: str, daemon_port: int, local_port: int,
                    root: str) -> dict:
    return {
        "user": env.user,
        "token": token,
        "mode": "remote",
        "ssh": {"default": {
            "host": env.host, "user": env.ssh_user,
            "key_dir": env.key_dir, "key": env.key,
        }},
        "root": {"default": root},
        "roles": {"daemon": {
            "daemon_port": daemon_port,
            "local_port": local_port,
            "root": root,
        }},
        "log_level": "off",
        "thread_pool_size": 8,
        "channel_budget": 8,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--out", default="")
    parser.add_argument("--host", default="w4-gent")
    parser.add_argument("--ssh-user", default="dev")
    parser.add_argument(
        "--key-dir",
        default=os.environ.get(
            "VB_HOSTKEY_KEY_DIR",
            "C:\\wsl\\shared\\keys" if os.name == "nt" else "/mnt/c/wsl/shared/keys",
        ),
    )
    parser.add_argument("--key", default="lab_ed25519")
    parser.add_argument("--script", default="/usr/local/sbin/w4_hostkey_cycle.sh")
    parser.add_argument("--daemon-port", type=int, default=0)
    parser.add_argument("--token", default="")
    args = parser.parse_args()

    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out).resolve() if args.out else work_dir / "evidence.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    init_work_dir(work_dir)
    registry = load_registry(registry_path())

    env = Env(
        work_dir=work_dir,
        host=args.host,
        ssh_user=args.ssh_user,
        key_dir=args.key_dir,
        key=args.key,
        script=args.script,
        user=f"vbhk{uuid.uuid4().hex[:6]}",
        control_kh=work_dir / "control_known_hosts",
    )
    env.control_kh.parent.mkdir(parents=True, exist_ok=True)
    env.control_kh.touch(exist_ok=True)

    steps: list[dict] = []
    results = Results()
    cleanup: list[dict] = []
    started = time.time()
    known_hosts_original: bytes | None = None
    known_hosts_backup: Path | None = None
    hostkey_rotated = False
    daemon: FakeDaemon | None = None
    server: RegistrationServer | None = None
    thread: threading.Thread | None = None
    http: Http | None = None
    session_token = ""
    daemon_port = args.daemon_port
    root = f"/home/{env.ssh_user}/.virtuoso-bridge/{env.user}"
    remote_root_abs: str | None = None
    ok = False

    def cleanup_add(name: str, passed: bool, **detail) -> None:
        cleanup.append({"name": name, "ok": bool(passed), **detail})

    try:
        # -- ① environment check -------------------------------------------
        probe_out = ctl(env, "echo vb-ok", timeout=30).strip()
        status = hostkey(env, "status")
        env.fingerprints["status_initial"] = status
        results.add("env-w4-reachable", probe_out == "vb-ok", out=probe_out)
        if not status.get("FINGERPRINT"):
            raise ProbeFailure(f"hostkey script status lacks fingerprint: {status}")

        kh_path = known_hosts_path()
        if kh_path.is_file():
            known_hosts_original = kh_path.read_bytes()
            known_hosts_backup = work_dir / "known_hosts.backup"
            known_hosts_backup.write_bytes(known_hosts_original)

        # -- ② build: temp registry + in-process server ---------------------
        if daemon_port <= 0:
            daemon_port = remote_free_port(env.host, start=65440)
        local_port = free_port()
        token = args.token or f"{env.user}-00"
        server_port = free_port()
        registry_before = registry_path().read_bytes() if registry_path().exists() else None

        def registry_snapshot() -> bytes | None:
            return registry_path().read_bytes() if registry_path().exists() else None

        def assert_no_registry_write(step: str) -> None:
            if registry_snapshot() != registry_before:
                raise ProbeFailure(f"{step} touched registry.json (step 6 owns the write)")

        server = RegistrationServer(("127.0.0.1", server_port), registry)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        http = Http(f"http://127.0.0.1:{server_port}")
        if registry.get(env.user) is not None:
            status_code, body = http.call(
                "DELETE", f"/api/user/{env.user}", headers=ADMIN_HEADERS,
            )
            steps.append({"action": "pre-cleanup", "status": status_code})
            if status_code != 200:
                raise ProbeFailure(f"pre-cleanup failed: {body}")
        registry_before = registry_snapshot()

        # -- ③ ensure set A and known_hosts baseline ------------------------
        hostkey(env, "use-a")
        live_a = live_fingerprints(env)
        env.fingerprints["live_a"] = live_a
        baseline = reg_probe.host_key_fingerprint(env.host)
        if baseline is None:
            # first-trust: record the current host key under the alias name,
            # exactly like the user doing one interactive ssh would.
            subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                 "-o", "StrictHostKeyChecking=accept-new", env.host, "true"],
                capture_output=True, text=True, timeout=60, **no_window(),
            )
            baseline = reg_probe.host_key_fingerprint(env.host)
        if baseline is None:
            raise ProbeFailure(
                f"cannot establish known_hosts baseline for {env.host}"
            )
        if baseline not in live_a.values() and live_a:
            # 复跑自愈：known_hosts 与 A 套不一致时按首信任重录（有备份）
            subprocess.run(
                ["ssh-keygen", "-R", env.host],
                capture_output=True, text=True, timeout=30, **no_window(),
            )
            subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                 "-o", "StrictHostKeyChecking=accept-new", env.host, "true"],
                capture_output=True, text=True, timeout=60, **no_window(),
            )
            baseline = reg_probe.host_key_fingerprint(env.host)
        env.fingerprints["known_hosts_baseline"] = baseline
        if not results.add("env-baseline-matches-live-a",
                           baseline in live_a.values(),
                           baseline=baseline, live=sorted(live_a.values())):
            raise ProbeFailure("known_hosts baseline does not match set A")

        # -- ④ step 1..3: apply / validate / probe --------------------------
        apply_body = {
            "action": "apply",
            **request_payload(env, token, daemon_port, local_port, root),
        }
        status_code, body = http.call("POST", "/api/register", apply_body)
        steps.append({"step": 1, "action": "apply", "status": status_code,
                      "stage": body.get("stage")})
        if status_code != 200 or body.get("stage") != "applied":
            raise ProbeFailure(f"step 1 failed: {body}")
        session_token = body.get("token") or ""
        if not session_token:
            raise ProbeFailure("apply did not return the session token")
        assert_no_registry_write("step 1")

        status_code, body = http.call(
            "POST", "/api/register",
            {"user": env.user, "action": "validate", "token": session_token},
        )
        steps.append({"step": 2, "action": "validate", "status": status_code,
                      "stage": body.get("stage")})
        if status_code != 200 or body.get("stage") != "validated":
            raise ProbeFailure(f"step 2 failed: {body}")
        assert_no_registry_write("step 2")

        status_code, body = http.call(
            "POST", "/api/register",
            {"user": env.user, "action": "probe", "token": session_token},
        )
        steps.append({"step": 3, "action": "probe", "status": status_code,
                      "stage": body.get("stage"),
                      "probe_results": body.get("probe_results")})
        if status_code != 200 or body.get("stage") != "probed":
            raise ProbeFailure(f"step 3 failed: {body}")
        entry = body.get("entry") or {}
        probed_fp = ((entry.get("roles") or {}).get("daemon") or {}) \
            .get("expected_fingerprint")
        if not results.add("probe-recorded-baseline",
                           probed_fp == baseline,
                           probed=probed_fp, baseline=baseline):
            raise ProbeFailure(f"probe recorded {probed_fp!r}, expected {baseline!r}")
        results.add("probe-results-present",
                    isinstance(body.get("probe_results"), list)
                    and len(body["probe_results"]) == 5,
                    count=len(body.get("probe_results") or []))
        assert_no_registry_write("step 3")

        # -- ④ step 4: deploy (still set A) ---------------------------------
        status_code, body = http.call(
            "POST", "/api/register",
            {"user": env.user, "action": "deploy", "token": session_token},
        )
        steps.append({"step": 4, "action": "deploy", "status": status_code,
                      "stage": body.get("stage"),
                      "setup_path": body.get("setup_path")})
        if status_code != 200 or body.get("stage") != "deployed":
            raise ProbeFailure(f"step 4 deploy failed: {body}")
        deployed_root = ((entry.get("roles") or {}).get("daemon") or {}) \
            .get("root") or root
        assert_no_registry_write("step 4")

        # fake daemon must answer step 5 before/after the rotation window
        remote_root_abs = deployed_root
        daemon = FakeDaemon(env.host, daemon_port, env.user,
                            remote_root=remote_root_abs)
        daemon.start()

        # -- rotate to set B: live fingerprint must change ------------------
        hostkey(env, "use-b")
        hostkey_rotated = True
        live_b = live_fingerprints(env)
        env.fingerprints["live_b"] = live_b
        if not results.add("rotate-b-live-changed",
                           baseline not in live_b.values() and bool(live_b),
                           baseline=baseline, live=sorted(live_b.values())):
            raise ProbeFailure("set B did not change the live host key set")

        # -- step 5 while rotated: must block, must not persist -------------
        verify_snapshot = registry_snapshot()
        status_code, body = http.call(
            "POST", "/api/register",
            {"user": env.user, "action": "verify", "token": session_token},
        )
        report = body.get("report") or {}
        steps.append({"step": 5, "action": "verify-rotated", "status": status_code,
                      "stage": body.get("stage"), "step_field": body.get("step"),
                      "errors": body.get("errors"), "report": report})
        results.add("verify-blocked-while-rotated",
                    status_code == 200 and body.get("stage") == "failed"
                    and body.get("step") == 5,
                    status=status_code, stage=body.get("stage"),
                    step_field=body.get("step"), errors=body.get("errors"))
        # 失败形状随传输层而异：paramiko 在直接连接期就抛出 host-key 异常
        # （无 report），openssh 可能先拿到 report 再失败。两种都必须满足
        # "被阻断"的实质：report 非全绿 或 errors 非空。
        report_blocked = bool(report) and not (
            report.get("command_ok") and report.get("skill_ok")
            and report.get("token_ok") and report.get("fingerprint_ok")
        )
        error_blocked = (not report) and bool(body.get("errors"))
        results.add("verify-rotated-blocked-evidence",
                    report_blocked or error_blocked,
                    report_blocked=report_blocked, error_blocked=error_blocked,
                    report={key: report.get(key) for key in (
                        "command_ok", "skill_ok", "token_ok", "fingerprint_ok")}
                    if report else None,
                    errors=body.get("errors"))
        blocked_text = " ".join(
            [str(item) for item in (body.get("errors") or [])]
            + [str(report.get("detail") or "")]
        ).lower()
        results.add("verify-rotated-error-names-host-key",
                    any(token in blocked_text for token in (
                        "host key", "host-key", "identification",
                        "does not match")),
                    text=blocked_text[:400])
        results.add("verify-rotated-zero-persist",
                    registry_snapshot() == verify_snapshot
                    and registry.get(env.user) is None,
                    users=sorted(json.loads(
                        (registry_path().read_text(encoding="utf-8")
                         if registry_path().exists() else "{}")
                    ).keys()))
        results.add(
            "note-fingerprint-ok-during-rotation", True,
            fingerprint_ok=report.get("fingerprint_ok"),
            detail=report.get("detail"),
            note="仅记录实际值：paramiko 直接在传输层拒绝（report 缺失、值为 "
                 "None）；known_hosts 未被改写时 openssh 路径该标志可能仍为 "
                 "True——旋转由传输层 known_hosts 校验强制阻断",
        )

        # -- restore: same step must now pass on unchanged retry ------------
        hostkey(env, "restore")
        hostkey_rotated = False
        live_restored = live_fingerprints(env)
        env.fingerprints["live_restored"] = live_restored
        if not results.add("restore-live-baseline",
                           baseline in live_restored.values(),
                           live=sorted(live_restored.values())):
            raise ProbeFailure("restore did not bring back the baseline key set")

        status_code, body = http.call(
            "POST", "/api/register",
            {"user": env.user, "action": "verify", "token": session_token},
        )
        report = body.get("report") or {}
        steps.append({"step": 5, "action": "verify-retry", "status": status_code,
                      "stage": body.get("stage"), "report": report})
        if not results.add("verify-retry-after-restore",
                           status_code == 200 and body.get("stage") == "verified",
                           status=status_code, stage=body.get("stage")):
            raise ProbeFailure(f"verify retry after restore failed: {body}")
        results.add("verify-retry-report-four-checks",
                    bool(report) and all(
                        report.get(name) is True
                        for name in ("command_ok", "skill_ok", "token_ok",
                                     "fingerprint_ok")
                    ),
                    report={k: report.get(k) for k in (
                        "command_ok", "skill_ok", "token_ok", "fingerprint_ok")})
        assert_no_registry_write("step 5 retry")

        # -- step 6: commit --------------------------------------------------
        status_code, body = http.call(
            "POST", "/api/register",
            {"user": env.user, "action": "commit", "token": session_token},
        )
        steps.append({"step": 6, "action": "commit", "status": status_code,
                      "stage": body.get("stage")})
        if status_code != 200 or body.get("stage") != "committed":
            raise ProbeFailure(f"step 6 commit failed: {body}")
        if not results.add("commit-persisted",
                           registry.get(env.user) is not None,
                           users=sorted(json.loads(
                               registry_path().read_text(encoding="utf-8")
                           ).keys())):
            raise ProbeFailure("commit did not persist the user")

        # -- §6.5: update 改 role host → 按首信任重建 fingerprint ------------
        w1_baseline = reg_probe.host_key_fingerprint("w1-gent")
        if not w1_baseline:
            raise ProbeFailure("known_hosts lacks the w1-gent baseline")
        status_code, body = http.call(
            "POST", f"/api/user/{env.user}/update",
            {"roles": {"file": {"host": "w1-gent"}}},
            headers=ADMIN_HEADERS,
        )
        updated = (body.get("entry") or {}).get("roles") or {}
        file_fp = (updated.get("file") or {}).get("expected_fingerprint")
        steps.append({"action": "update-role-host", "status": status_code,
                      "file_fingerprint": file_fp, "w1_baseline": w1_baseline})
        if not results.add("update-reprobes-new-endpoint",
                           status_code == 200 and file_fp == w1_baseline,
                           file_fingerprint=file_fp, expected=w1_baseline):
            raise ProbeFailure(
                f"update did not rebuild fingerprint: {file_fp!r} != {w1_baseline!r}"
            )
        other_unchanged = (
            ((updated.get("daemon") or {}).get("expected_fingerprint")) == baseline
            and ((updated.get("command") or {}).get("expected_fingerprint")) == baseline
        )
        results.add("update-keeps-other-roles", other_unchanged,
                    daemon=((updated.get("daemon") or {})
                            .get("expected_fingerprint")),
                    command=((updated.get("command") or {})
                             .get("expected_fingerprint")),
                    baseline=baseline)

        explicit = "SHA256:" + "A" * 43
        status_code, body = http.call(
            "POST", f"/api/user/{env.user}/update",
            {"roles": {"file": {"host": "w3-gent",
                                "expected_fingerprint": explicit}}},
            headers=ADMIN_HEADERS,
        )
        updated = (body.get("entry") or {}).get("roles") or {}
        file_fp = (updated.get("file") or {}).get("expected_fingerprint")
        steps.append({"action": "update-explicit-fingerprint",
                      "status": status_code, "file_fingerprint": file_fp})
        results.add("update-explicit-fingerprint-not-overwritten",
                    status_code == 200 and file_fp == explicit,
                    file_fingerprint=file_fp, explicit=explicit)

        ok = all(item["ok"] for item in results.items)
    except Exception as exc:  # noqa: BLE001 - TB records the failure itself
        steps.append({"action": "error", "error": f"{type(exc).__name__}: {exc}"})
        ok = False
    finally:
        # 1) host key first: everything below needs working ssh
        try:
            hostkey(env, "restore")
            cleanup_add("hostkey-restored",
                        True, set=hostkey(env, "status").get("SET"))
        except Exception as exc:  # noqa: BLE001
            cleanup_add("hostkey-restored", False, error=str(exc))
        # 2) fake daemon + deployed tree
        if daemon is not None:
            try:
                daemon.stop()
                cleanup_add("fake-daemon-stopped", True)
            except Exception as exc:  # noqa: BLE001
                cleanup_add("fake-daemon-stopped", False, error=str(exc))
        try:
            target_root = remote_root_abs or root
            ctl(env, f"rm -rf {shlex.quote(target_root)}", timeout=30)
            cleanup_add("remote-root-removed", True, root=target_root)
        except Exception as exc:  # noqa: BLE001
            cleanup_add("remote-root-removed", False, error=str(exc))
        # 3) delete the registry user
        if http is not None:
            try:
                status_code, body = http.call(
                    "DELETE", f"/api/user/{env.user}", headers=ADMIN_HEADERS,
                )
                cleanup_add("user-deleted", status_code in (200, 404),
                            status=status_code, removed=body.get("removed"))
            except Exception as exc:  # noqa: BLE001
                cleanup_add("user-deleted", False, error=str(exc))
        # 4) known_hosts restore (only when this TB changed it)
        try:
            if known_hosts_backup is not None and known_hosts_original is not None:
                current = known_hosts_path().read_bytes() \
                    if known_hosts_path().is_file() else None
                if current != known_hosts_original:
                    known_hosts_path().parent.mkdir(parents=True, exist_ok=True)
                    known_hosts_path().write_bytes(known_hosts_original)
                    cleanup_add("known-hosts-restored", True, modified=True)
                else:
                    cleanup_add("known-hosts-restored", True, modified=False)
            else:
                cleanup_add("known-hosts-restored", True, note="no backup")
        except Exception as exc:  # noqa: BLE001
            cleanup_add("known-hosts-restored", False, error=str(exc))
        if server is not None:
            try:
                server.shutdown()
                server.server_close()
            except Exception:  # noqa: BLE001
                pass
        if thread is not None:
            thread.join(timeout=3)

    cleanup_ok = all(item["ok"] for item in cleanup)
    evidence = {
        "tb": "registration_hostkey_rotation_tb",
        "ok": bool(ok and cleanup_ok),
        "host": env.host,
        "user": env.user,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started)),
        "duration_s": round(time.time() - started, 1),
        "daemon_port": daemon_port,
        "checks": results.items,
        "cleanup": cleanup,
        "steps": steps,
        "fingerprints": env.fingerprints,
        "control_log": env.control_log,
    }
    out_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    passed = sum(1 for item in results.items if item["ok"])
    print(f"\n[hostkey-rotation] checks {passed}/{len(results.items)} passed; "
          f"cleanup {'ok' if cleanup_ok else 'FAILED'}; evidence -> {out_path}")
    return 0 if evidence["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
