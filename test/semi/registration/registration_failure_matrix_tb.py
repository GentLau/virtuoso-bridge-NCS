# === TB 注释头（规范见 test/docs/写TB规范.md §0）=====================
# 作者: 设计/Codex
# 最后改动: 2026-09-28 15:19
# 依赖: 无
# =====================================================================
# 六步流程（按 test/docs/写TB规范.md §1–§6）：
# §1 环境检查：自包含半真机 TB，不依赖外部环境；只检查本机 Python/HTTP/临时目录可用。
# §2 构建：独立 work-dir + seed registry + 本机 HTTP 注册服务 + 协议兼容 fake daemon。
# §3 最终检查：确认 seed 注册表、端口和临时 root 基线干净。
# §4 执行：逐步注入失败，验证原样重试、cancel 后重 apply、服务重启清候选。
# §5 比对：每步 stage/step/errors、registry 字节零写入、最终 commit 条目逐项比对。
# §6 重复/收尾：失败后恢复环境再重试；停止 daemon/server，保留 JSON 与最终注册表。
"""六步注册失败/重试矩阵（半真机、自包含）。

覆盖 X4-③：六步里逐步骤失败注入，以及 {失败, 原样重试成功, 失败后 cancel/重 apply}。
不依赖 8127、不依赖 wsl-gent、不依赖 CIW；用真实 HTTP 注册服务、真实
``RegistrationFlow``、真实本机文件系统和一个协议兼容 fake daemon。

判据：

* 第 1/2/3/4/5/6 步失败均不得写入 registry；
* 失败后同一步原样重试可成功（环境恢复后）；
* 修正参数必须先 cancel 再 apply；cancel 幂等；
* 第 5 步通过后仍不落盘，必须显式 commit；第 6 步失败可原地重试；
* 服务重启后内存候选消失，注册表不变。

用法::

    PYTHONPATH=src python test/semi/registration/registration_failure_matrix_tb.py \
        --work-dir test/artifacts/env/reg-failure \
        --out test/artifacts/evidence/tb-sixstep-20260928/registration-failure-matrix.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
_FIXTURES = Path(__file__).resolve().parents[2] / "shared" / "fixtures"
if str(_FIXTURES) not in sys.path:
    sys.path.insert(0, str(_FIXTURES))

from common.paths import init_work_dir, registry_path  # noqa: E402
from common.registry import UserEntry, load_registry  # noqa: E402
from register.server import RegistrationServer  # noqa: E402

try:
    from _win import no_window  # type: ignore
except ImportError:  # pragma: no cover - POSIX
    def no_window(**kwargs):  # type: ignore
        return dict(kwargs)


FAKE_DAEMON = _FIXTURES / "fake_daemon_host.py"
SEED_USER = "regseed"
SEED_TOKEN = "regseed-token"
RUN_ID = uuid.uuid4().hex[:8]


class ProbeFailure(AssertionError):
    """Raised when one matrix check has enough context to be reported."""


class Results:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, name: str, ok: bool, **detail) -> bool:
        self.items.append({"name": name, "ok": bool(ok), **_redact(detail)})
        flag = "PASS" if ok else "FAIL"
        print(f"[{flag}] {name}" + (f"  {detail}" if detail else ""))
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


def require(results: Results, name: str, ok: bool, **detail) -> None:
    results.add(name, ok, **detail)
    if not ok:
        raise ProbeFailure(f"{name}: {detail}")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def unique_user(prefix: str) -> str:
    return f"regfail{prefix}-{RUN_ID}"


def unique_token(prefix: str) -> str:
    return f"rftok{prefix}-{RUN_ID}-00"


def registry_bytes() -> bytes | None:
    path = registry_path()
    return path.read_bytes() if path.exists() else None


class Http:
    """Small JSON client; stores the response trail for evidence."""

    def __init__(self, base: str) -> None:
        self.base = base
        self.trail: list[dict] = []

    def call(self, method: str, path: str, payload: dict | None = None,
             timeout: float = 180.0) -> tuple[int, dict]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base + path,
            data=data,
            method=method,
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


class FakeDaemon:
    """Protocol-compatible daemon started only at the step-5 boundary."""

    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None

    def start(self, port: int, token: str) -> None:
        prefix = token[:-3] if token.endswith("-00") else token
        self.proc = subprocess.Popen(
            [sys.executable, str(FAKE_DAEMON),
             "--base-port", str(port), "--count", "1",
             "--token-prefix", prefix],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            **no_window(),
        )
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            with socket.socket() as probe:
                probe.settimeout(0.3)
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    return
            time.sleep(0.2)
        self.stop()
        raise ProbeFailure(f"fake daemon did not listen on 127.0.0.1:{port}")

    def stop(self) -> None:
        proc = self.proc
        self.proc = None
        if proc is None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass


def local_payload(user: str, token: str, root: Path, port: int) -> dict:
    """Local-mode canonical registration payload."""
    return {
        "mode": "local",
        "token": token,
        "enhanced_token": SEED_TOKEN,
        "root": {"default": str(root)},
        "roles": {"daemon": {"daemon_port": port, "local_port": port}},
        "log_level": "off",
    }


def apply(ctx: SimpleNamespace, user: str, token: str, root: Path, port: int) -> tuple[int, dict]:
    return ctx.http.call("POST", "/api/register",
                         {"action": "apply", "user": user,
                          **local_payload(user, token, root, port)})


def action(ctx: SimpleNamespace, user: str, action_name: str,
           session_token: str) -> tuple[int, dict]:
    return ctx.http.call("POST", "/api/register", {
        "action": action_name, "user": user, "token": session_token,
    })


def is_absolute(value: str | None) -> bool:
    return bool(value) and Path(value).is_absolute()


def case_invalid_apply(ctx: SimpleNamespace) -> None:
    """Step 1: malformed application is rejected before any candidate exists."""
    cases = [
        ("missing-mode", {"action": "apply", "user": unique_user("badmode")}),
        ("unknown-field", {
            "action": "apply", "user": unique_user("badfield"),
            "mode": "local", "enhanced_token": SEED_TOKEN, "bogus": True,
        }),
        ("bad-user", {"action": "apply", "user": "bad/user",
                      "mode": "local", "enhanced_token": SEED_TOKEN}),
    ]
    for label, payload in cases:
        status, body = ctx.http.call("POST", "/api/register", payload)
        require(ctx.results, f"step1-{label}-rejected",
                status == 400 and "invalid" in json.dumps(body, ensure_ascii=False),
                status=status, body=body)
    require(ctx.results, "step1-zero-registry-write",
            registry_bytes() == ctx.snapshot, snapshot="unchanged")
    # Corrected application after the rejected ones: a fresh candidate is
    # accepted and cancelled without any durable write.
    retry_user = unique_user("step1retry")
    retry_token = unique_token("step1retry")
    retry_root = ctx.work_dir / "roots" / retry_user
    retry_root.mkdir(parents=True, exist_ok=True)
    retry_port = free_port()
    while retry_port == ctx.seed_port:
        retry_port = free_port()
    status, body = apply(ctx, retry_user, retry_token, retry_root, retry_port)
    require(ctx.results, "step1-corrected-apply",
            status == 200 and body.get("stage") == "applied",
            status=status, body=body)
    action(ctx, retry_user, "cancel", body.get("token"))
    require(ctx.results, "step1-retry-zero-registry-write",
            registry_bytes() == ctx.snapshot)


def case_step2_conflict_cancel_reapply(ctx: SimpleNamespace) -> None:
    """Step 2 conflict, same-step retry, idempotent cancel, corrected re-apply."""
    user = unique_user("step2")
    token = unique_token("step2")
    root = ctx.work_dir / "roots" / user
    root.mkdir(parents=True, exist_ok=True)

    status, body = apply(ctx, user, token, root, ctx.seed_port)
    require(ctx.results, "step2-apply", status == 200 and body.get("stage") == "applied",
            status=status, body=body)
    session = body.get("token")

    status, body = action(ctx, user, "validate", session)
    require(ctx.results, "step2-conflict-fails",
            status == 200 and body.get("stage") == "failed" and body.get("step") == 2
            and any("port" in str(e) for e in body.get("errors") or []),
            status=status, body=body)
    require(ctx.results, "step2-conflict-zero-registry-write",
            registry_bytes() == ctx.snapshot)

    status, body = action(ctx, user, "validate", session)
    require(ctx.results, "step2-same-step-retry-still-fails",
            status == 200 and body.get("stage") == "failed" and body.get("step") == 2,
            status=status, body=body)

    status, body = action(ctx, user, "cancel", session)
    require(ctx.results, "step2-cancel", status == 200 and body.get("stage") == "cancelled",
            status=status, body=body)
    status, body = action(ctx, user, "cancel", session)
    require(ctx.results, "step2-cancel-idempotent",
            status == 200 and body.get("stage") == "cancelled",
            status=status, body=body)

    fixed_port = free_port()
    while fixed_port == ctx.seed_port:
        fixed_port = free_port()
    status, body = apply(ctx, user, token, root, fixed_port)
    require(ctx.results, "step2-reapply-after-cancel",
            status == 200 and body.get("stage") == "applied",
            status=status, body=body)
    session = body.get("token")
    status, body = action(ctx, user, "validate", session)
    require(ctx.results, "step2-corrected-validate",
            status == 200 and body.get("stage") == "validated",
            status=status, body=body)
    require(ctx.results, "step2-zero-registry-write",
            registry_bytes() == ctx.snapshot)
    action(ctx, user, "cancel", session)


def case_steps3_to_6(ctx: SimpleNamespace) -> None:
    """One candidate: probe/deploy/verify/commit failures and same-step retries."""
    user = unique_user("chain")
    token = unique_token("chain")
    port = free_port()
    while port == ctx.seed_port:
        port = free_port()
    root = ctx.work_dir / "roots" / user
    root.parent.mkdir(parents=True, exist_ok=True)
    # Step 3 failure: root.default points at a regular file, not a directory.
    root.write_text("not-a-directory", encoding="utf-8")

    status, body = apply(ctx, user, token, root, port)
    require(ctx.results, "step3-apply",
            status == 200 and body.get("stage") == "applied", status=status, body=body)
    session = body.get("token")
    status, body = action(ctx, user, "validate", session)
    require(ctx.results, "step3-validate",
            status == 200 and body.get("stage") == "validated", status=status, body=body)
    status, body = action(ctx, user, "probe", session)
    require(ctx.results, "step3-probe-fails",
            status == 200 and body.get("stage") == "failed" and body.get("step") == 3
            and bool(body.get("errors")), status=status, body=body)
    require(ctx.results, "step3-failure-zero-registry-write",
            registry_bytes() == ctx.snapshot)
    status, body = action(ctx, user, "probe", session)
    require(ctx.results, "step3-same-step-retry-still-fails",
            status == 200 and body.get("stage") == "failed" and body.get("step") == 3,
            status=status, body=body)

    root.unlink()
    root.mkdir(parents=True, exist_ok=True)
    status, body = action(ctx, user, "probe", session)
    require(ctx.results, "step3-same-step-retry-succeeds",
            status == 200 and body.get("stage") == "probed", status=status, body=body)
    entry = body.get("entry") or {}
    roles = entry.get("roles") or {}
    for role_name in ("gui", "daemon", "command", "file"):
        require(ctx.results, f"step3-{role_name}-root-absolute",
                is_absolute((roles.get(role_name) or {}).get("root")),
                root=(roles.get(role_name) or {}).get("root"))
    daemon_python = (roles.get("daemon") or {}).get("python")
    require(ctx.results, "step3-daemon-python-recorded", bool(daemon_python),
            python=daemon_python)
    spectre_root = (roles.get("spectre") or {}).get("root")
    spectre_warning = any(
        "spectre" in str(warning).lower() for warning in body.get("warnings") or []
    )
    require(ctx.results, "step3-spectre-failure-nonblocking",
            bool(spectre_root) or spectre_warning,
            spectre_root=spectre_root, warnings=body.get("warnings") or [])
    require(ctx.results, "step3-probe-zero-registry-write",
            registry_bytes() == ctx.snapshot)

    daemon_root = Path((roles.get("daemon") or {}).get("root", ""))
    require(ctx.results, "step4-daemon-root-precondition", daemon_root.is_dir(),
            daemon_root=str(daemon_root))
    shutil.rmtree(daemon_root)
    daemon_root.write_text("block-deploy", encoding="utf-8")
    status, body = action(ctx, user, "deploy", session)
    require(ctx.results, "step4-deploy-fails",
            status == 200 and body.get("stage") == "failed" and body.get("step") == 4
            and bool(body.get("errors")), status=status, body=body)
    require(ctx.results, "step4-failure-zero-registry-write",
            registry_bytes() == ctx.snapshot)
    status, body = action(ctx, user, "deploy", session)
    require(ctx.results, "step4-same-step-retry-still-fails",
            status == 200 and body.get("stage") == "failed" and body.get("step") == 4,
            status=status, body=body)

    daemon_root.unlink()
    daemon_root.mkdir(parents=True, exist_ok=True)
    status, body = action(ctx, user, "deploy", session)
    require(ctx.results, "step4-same-step-retry-succeeds",
            status == 200 and body.get("stage") == "deployed", status=status, body=body)
    setup_path = Path(body.get("setup_path") or "")
    require(ctx.results, "step4-deploy-files-present",
            setup_path.is_file()
            and (daemon_root / "ramic").is_dir()
            and (daemon_root / "setup").is_dir()
            and (daemon_root / "status").is_dir(),
            setup_path=str(setup_path))
    for other_role in ("gui", "command", "file", "spectre"):
        other_root = (roles.get(other_role) or {}).get("root")
        if other_root:
            require(ctx.results, f"step4-{other_role}-root-not-deployed",
                    not (Path(other_root) / "ramic").exists(), root=other_root)
    require(ctx.results, "step4-deploy-zero-registry-write",
            registry_bytes() == ctx.snapshot)

    # Step 5 failure: no daemon yet; retry after the fake daemon is up.
    status, body = action(ctx, user, "verify", session)
    require(ctx.results, "step5-verify-fails-without-daemon",
            status == 200 and body.get("stage") == "failed" and body.get("step") == 5
            and bool(body.get("errors")), status=status, body=body)
    require(ctx.results, "step5-failure-zero-registry-write",
            registry_bytes() == ctx.snapshot)
    status, body = action(ctx, user, "verify", session)
    require(ctx.results, "step5-same-step-retry-still-fails",
            status == 200 and body.get("stage") == "failed" and body.get("step") == 5,
            status=status, body=body)
    daemon = FakeDaemon()
    ctx.daemons.append(daemon)
    daemon.start(port, token)
    status, body = action(ctx, user, "verify", session)
    require(ctx.results, "step5-same-step-retry-succeeds",
            status == 200 and body.get("stage") == "verified" and body.get("step") == 5,
            status=status, body=body)
    report = body.get("report") or {}
    require(ctx.results, "step5-dual-smoke-report",
            report.get("command_ok") and report.get("skill_ok") and report.get("token_ok"),
            report=report)
    require(ctx.results, "step5-verified-still-zero-registry-write",
            registry_bytes() == ctx.snapshot)

    # Step 6 failure: inject a final-check port conflict, then resolve and retry.
    conflict_user = unique_user("conflict")
    conflict_token = unique_token("conflict")
    conflict_root = ctx.work_dir / "roots" / conflict_user
    conflict_root.mkdir(parents=True, exist_ok=True)
    ctx.registry.register(conflict_user, UserEntry(
        token=conflict_token,
        mode="local",
        root={"default": str(conflict_root)},
        roles={"daemon": {"daemon_port": port, "local_port": port}},
    ))
    conflict_snapshot = registry_bytes()
    status, body = action(ctx, user, "commit", session)
    require(ctx.results, "step6-commit-fails-on-conflict",
            status == 200 and body.get("stage") == "failed" and body.get("step") == 6
            and bool(body.get("errors")), status=status, body=body)
    require(ctx.results, "step6-failure-does-not-commit-candidate",
            ctx.registry.get(user) is None
            and registry_bytes() == conflict_snapshot)
    status, body = action(ctx, user, "commit", session)
    require(ctx.results, "step6-same-step-retry-still-fails",
            status == 200 and body.get("stage") == "failed" and body.get("step") == 6,
            status=status, body=body)
    ctx.registry.remove(conflict_user)
    before_commit = registry_bytes()
    status, body = action(ctx, user, "commit", session)
    require(ctx.results, "step6-same-step-retry-succeeds",
            status == 200 and body.get("stage") == "committed" and body.get("step") == 6,
            status=status, body=body)
    committed = ctx.registry.get(user)
    require(ctx.results, "step6-committed-entry-present",
            committed is not None and committed.registered_at is not None,
            registered_at=getattr(committed, "registered_at", None))
    require(ctx.results, "step6-is-the-durable-write",
            registry_bytes() is not None and registry_bytes() != before_commit)
    daemon.stop()


def case_restart_clears_candidate(ctx: SimpleNamespace) -> None:
    """Service restart drops in-memory candidates without touching registry."""
    user = unique_user("restart")
    token = unique_token("restart")
    port = free_port()
    root = ctx.work_dir / "roots" / user
    root.mkdir(parents=True, exist_ok=True)
    status, body = apply(ctx, user, token, root, port)
    require(ctx.results, "restart-apply",
            status == 200 and body.get("stage") == "applied", status=status, body=body)
    before = registry_bytes()

    ctx.server.shutdown()
    ctx.server.server_close()
    ctx.server_thread.join(timeout=5)

    registry2 = load_registry(registry_path())
    port2 = free_port()
    server2 = RegistrationServer(("127.0.0.1", port2), registry2)
    thread2 = threading.Thread(target=server2.serve_forever, daemon=True)
    thread2.start()
    try:
        status, body = Http(f"http://127.0.0.1:{port2}").call(
            "GET", f"/api/register/{user}")
        require(ctx.results, "restart-candidate-cleared",
                status == 404 and body.get("error") == "no registration in progress",
                status=status, body=body)
        require(ctx.results, "restart-registry-unchanged", registry_bytes() == before)
    finally:
        server2.shutdown()
        server2.server_close()
        thread2.join(timeout=5)


def run_case(name: str, fn, ctx: SimpleNamespace) -> None:
    try:
        fn(ctx)
    except Exception as exc:  # noqa: BLE001
        ctx.results.add(f"{name}-case-error", False,
                        error=f"{type(exc).__name__}: {exc}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    init_work_dir(work_dir)
    registry = load_registry(registry_path())

    # Cleanup only our own deterministic prefixes; never touch foreign users.
    for name in list(registry.users()):
        if name == SEED_USER or name.startswith("regfail"):
            registry.remove(name)

    seed_root = work_dir / "seed-root"
    seed_root.mkdir(parents=True, exist_ok=True)
    seed_port = free_port()
    registry.register(SEED_USER, UserEntry(
        token=SEED_TOKEN,
        mode="local",
        root={"default": str(seed_root)},
        roles={"daemon": {"daemon_port": seed_port, "local_port": seed_port}},
    ))
    snapshot = registry_bytes()

    http_port = free_port()
    server = RegistrationServer(("127.0.0.1", http_port), registry)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    ctx = SimpleNamespace(
        work_dir=work_dir,
        registry=registry,
        snapshot=snapshot,
        seed_port=seed_port,
        results=Results(),
        http=Http(f"http://127.0.0.1:{http_port}"),
        server=server,
        server_thread=server_thread,
        daemons=[],
    )

    try:
        # 六步 §1：本 TB 自建半真机环境，不需要外部环境检查；
        #       下面的本地 HTTP + socket + 文件系统自检即环境判定。
        run_case("step1", case_invalid_apply, ctx)
        run_case("step2", case_step2_conflict_cancel_reapply, ctx)
        run_case("step3-6", case_steps3_to_6, ctx)
        run_case("restart", case_restart_clears_candidate, ctx)
    finally:
        for daemon in ctx.daemons:
            daemon.stop()
        try:
            server.shutdown()
            server.server_close()
        except Exception:  # noqa: BLE001
            pass
        server_thread.join(timeout=5)

    registry_now = registry_path()
    payload = {
        "tb": "registration_failure_matrix_tb",
        "work_dir": str(work_dir),
        "registry": str(registry_now),
        "registry_written": registry_now.exists(),
        "seed_port": seed_port,
        "checks": ctx.results.items,
        "passed": ctx.results.passed,
        "total": len(ctx.results.items),
        "python": sys.version,
    }
    out = Path(args.out) if args.out else work_dir / "registration-failure-matrix.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    ok = ctx.results.passed == len(ctx.results.items)
    print(f"\n{ctx.results.passed}/{len(ctx.results.items)} 通过；证据：{out}")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
