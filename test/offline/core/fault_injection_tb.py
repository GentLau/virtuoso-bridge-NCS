# === TB 注释头（规范见 test/docs/写TB规范.md §0）=====================
# 作者: 设计/Codex
# 最后改动: 2026-09-28 12:04
# 依赖: 无
# =====================================================================
# 六步流程（按 test/docs/写TB规范.md §1–§6）：
# §1 环境检查：离线故障注入，无需远端环境 → 跳过。
# §2 构建：每个 case 自建临时 work root、registry、server/子进程。
# §3 最终检查：先确认故障注入夹具和初始状态，再触发故障。
# §4 执行：断链、租约竞争、缓存失效、容量/队列等单点动作。
# §5 比对：错误 kind/返回码/字段与期望逐项比对。
# §6 重复/收尾：runner 逐 case 子进程重复；临时目录回收，JSON 留证。
"""Fault-injection TB.

This TB is intentionally adversarial: it drives edge conditions that the
normal multi-user success-path TB does not cover.  Run with:

    PYTHONPATH=src python test/offline/core/fault_injection_tb.py

Exit code is non-zero when any fault-injection case fails; the JSON output is
the raw evidence consumed by the final test report.
"""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from common.registry import Registry, UserEntry, load_registry  # noqa: E402
from transport.roles import resolve  # noqa: E402
from common.paths import init_work_dir, registry_path  # noqa: E402
from common.ssh import SSHRunner  # noqa: E402
from transport.tunnel import RemoteClient  # noqa: E402
from transport.middle import BusinessServer  # noqa: E402
from pyapi.models import ExecutionStatus, VirtuosoResult  # noqa: E402


class ProbeFailure(AssertionError):
    pass


_TEMP_DIRS: list[Path] = []


def temp_dir(prefix: str) -> Path:
    """Per-case temp dir, removed by ``cleanup_temp_dirs`` at the end of the run."""
    # 六步 §1–§3：离线故障注入不使用远端环境，临时 work root 即基础设施。
    path = Path(tempfile.mkdtemp(prefix=prefix))
    _TEMP_DIRS.append(path)
    return path


def cleanup_temp_dirs() -> int:
    import shutil

    removed = 0
    for path in _TEMP_DIRS:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
            removed += 1
    _TEMP_DIRS.clear()
    return removed


def make_remote_entry(token: str = "tok", *, max_sessions: int = 10) -> UserEntry:
    e = UserEntry(token=token, mode="remote")
    e.ssh.default.host = "server-a"
    e.ssh.default.user = "alice"
    e.runtime.channel_budget = max_sessions
    e.roles.daemon.daemon_port = 65081
    e.roles.daemon.local_port = 65082
    for name in ("gui", "daemon", "command", "file", "spectre"):
        r = getattr(e.roles, name)
        r.host = "server-a"
        r.user = "alice"
        r.root = f"/home/alice/.virtuoso-bridge/{name}"
        r.max_sessions = max_sessions
        r.expected_fingerprint = "SHA256:test"
    return e


class FakePersistentRunner:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []
        FakePersistentRunner.instances.append(self)

    @property
    def persistent_shell_enabled(self):
        return True

    def run_command(self, cmd, timeout=None):
        self.calls.append((cmd, timeout))
        return __import__("pyapi.models", fromlist=["CommandResult"]).CommandResult(
            returncode=0, stdout="", stderr=""
        )

    def close(self):
        pass

    def stop_port_forward(self):
        pass

    @property
    def is_tunnel_alive(self):
        return False


def case_lease_race():
    """A first concurrent burst on one token must create exactly one lease."""
    entry = make_remote_entry()
    targets = resolve(entry, "alice")
    FakePersistentRunner.instances.clear()
    with mock.patch("transport.tunnel.SSHRunner", FakePersistentRunner):
        client = RemoteClient(entry, targets, "alice")
        original = client.budgets.try_acquire_channel

        def delayed(**kwargs):
            lease = original(**kwargs)
            # widen the check-then-act window deterministically
            time.sleep(0.03)
            return lease

        client.budgets.try_acquire_channel = delayed
        barrier = threading.Barrier(16)
        returned = []
        errors = []

        def worker():
            try:
                barrier.wait(timeout=3)
                returned.append(client._acquire_command_channel(targets.command))
            except Exception as exc:  # noqa: BLE001
                errors.append(repr(exc))

        threads = [threading.Thread(target=worker) for _ in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        in_use = client.budgets.channels_in_use
        leases = len(client._persistent_leases)
        client.close()
        if errors or in_use != 1 or leases != 1:
            raise ProbeFailure(
                f"lease race: errors={errors}, returned={len(returned)}, "
                f"channels_in_use={in_use}, persistent_leases={leases}"
            )
    return {"channels_in_use": 1, "persistent_leases": 1, "threads": 16}


class DeadShell:
    def __init__(self):
        self.stdin = mock.Mock()
        self.stdout = mock.Mock()
        self.closed = False

    def poll(self):
        return 1

    def close(self):
        self.closed = True


def case_dead_shell_close():
    """An already-exited persistent shell must still be released."""
    runner = SSHRunner("server-a", user="alice", backend="openssh")
    dead = DeadShell()
    runner._shell_proc = dead
    runner._shell_reader = None
    runner._shell_queue = None
    runner._close_persistent_shell_locked()
    if not dead.closed:
        raise ProbeFailure("dead shell was not closed; session permit would leak")
    return {"dead_shell_closed": True}


class FailingParamikoBackend:
    def run_command(self, command, timeout):
        return 255, "", "VB-TRANSPORT: simulated disconnect"


def case_transport_kind():
    """Paramiko rc=255 transport errors must not look like real commands."""
    runner = SSHRunner("server-a", user="alice", backend="paramiko")
    runner._paramiko_backend = FailingParamikoBackend()
    result = runner.run_command("echo never")
    if result.kind != "transport":
        raise ProbeFailure(
            f"transport failure classified as kind={result.kind!r}, rc={result.returncode}"
        )
    return {"kind": result.kind, "returncode": result.returncode}


class BytesBuffer:
    def __init__(self, data=b""):
        self.data = bytearray(data)
        self.written = bytearray()

    def read(self, n=1):
        if not self.data:
            return b""
        out = bytes(self.data[:n])
        del self.data[:n]
        return out

    def write(self, data):
        self.written.extend(data)

    def flush(self):
        return None


class FakeStream:
    def __init__(self, data=b""):
        self.buffer = BytesBuffer(data)


class FakeConn:
    def __init__(self, request: bytes):
        self.request = request
        self.sent = bytearray()
        self.closed = False
        self.timeout: float | None = None

    def settimeout(self, timeout: float | None) -> None:
        self.timeout = timeout

    def recv(self, _n):
        data, self.request = self.request, b""
        return data

    def sendall(self, data):
        self.sent.extend(data)

    def shutdown(self, _how):
        return None

    def close(self):
        self.closed = True


def _load_daemon(name: str):
    import importlib.util

    path = SRC / "bridge" / "resources" / "ramic_bridge_daemon_3.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.DAEMON_TOKEN = "tok"
    return mod


def _run_daemon_request(daemon, request: dict, first_frame: bytes):
    req = json.dumps(request, ensure_ascii=False).encode("utf-8")
    conn = FakeConn(req)
    fake_in = FakeStream(first_frame)
    fake_out = FakeStream()
    old_in, old_out = daemon.sys.stdin, daemon.sys.stdout
    try:
        daemon.sys.stdin, daemon.sys.stdout = fake_in, fake_out
        daemon.handle_connection(conn)
    finally:
        daemon.sys.stdin, daemon.sys.stdout = old_in, old_out
        daemon._timeout_flag = True
        if daemon._watchdog:
            daemon._watchdog.cancel()
    return bytes(fake_out.buffer.written), bytes(conn.sent)


def case_daemon_log_protocol():
    """Missing/invalid log fields must be handled per the log contract."""
    daemon = _load_daemon("fault_daemon_log")
    stx, rs = b"\x02", b"\x1e"
    first = stx + b"2" + rs
    request = {"skill": "1+1", "timeout": 0.05, "token": "tok"}
    out, sent = _run_daemon_request(daemon, request, first)
    if b"RBDLogOn=nil" not in out:
        raise ProbeFailure(
            "missing log_level did not default OFF: " + repr(out[:160])
        )
    bad_level = {"skill": "1+1", "timeout": 0.05, "token": "tok", "log_level": "bogus"}
    out2, sent2 = _run_daemon_request(daemon, bad_level, first)
    if not sent2.startswith(b"\x15") or b"invalid log_level" not in sent2:
        raise ProbeFailure(
            "invalid log_level was not NAKed: " + repr(sent2[:160])
        )
    bad_max = {"skill": "1+1", "timeout": 0.05, "token": "tok", "log_max_bytes": 0}
    out3, sent3 = _run_daemon_request(daemon, bad_max, first)
    if not sent3.startswith(b"\x15") or b"invalid log_max_bytes" not in sent3:
        raise ProbeFailure(
            "invalid log_max_bytes was not NAKed: " + repr(sent3[:160])
        )
    return {"missing_default_off": True, "invalid_level": True, "invalid_max": True}


def case_runtime_cache_invalidation():
    """A live BusinessServer must not keep a stale token cache after overwrite."""
    wd = temp_dir("vb-fault-cache-")
    init_work_dir(wd)
    reg = load_registry(registry_path())
    first = make_remote_entry("tok-cache")
    reg.register("alice", first)
    server = BusinessServer()
    try:
        c1 = server._remote("tok-cache")
        replacement = make_remote_entry("tok-cache")
        replacement.roles.command.root = "/home/alice/.virtuoso-bridge/command-v2"
        # Use the same Registry object BusinessServer is actually consuming.
        server.registry.register("alice", replacement, overwrite=True)
        c2 = server._remote("tok-cache")
        if c2 is c1:
            raise ProbeFailure("BusinessServer reuses stale RemoteClient after registry overwrite")
        return {"recreated": True}
    finally:
        server.close()


class BlockingSkillClient:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def execute_skill(self, code, timeout=None, *, log_level=None, log_max_bytes=None):
        self.started.set()
        self.release.wait(2)
        return VirtuosoResult(status=ExecutionStatus.SUCCESS, output="2")


def case_skill_capacity_fields():
    """r3: Skill capacity rejection lives in errors, never a kind field."""
    wd = temp_dir("vb-fault-cap-")
    init_work_dir(wd)
    reg = load_registry(registry_path())
    entry = UserEntry(token="tok-cap", mode="local")
    entry.runtime.thread_pool_size = 1
    reg.register("alice", entry)
    server = BusinessServer()
    client = BlockingSkillClient()
    try:
        with mock.patch.object(BusinessServer, "_skill", lambda self, token: client):
            first = threading.Thread(
                target=lambda: server.execute_skill("1+1", timeout=2, token="tok-cap")
            )
            first.start()
            if not client.started.wait(1):
                raise ProbeFailure("first Skill request did not occupy the budget")
            second = server.execute_skill("2+2", timeout=1, token="tok-cap")
            client.release.set()
            first.join(timeout=3)
        if second.status != ExecutionStatus.ERROR or not any(
            "thread pool exceeded" in item for item in second.errors
        ):
            raise ProbeFailure(f"unexpected capacity result: {second.model_dump()}")
        if "kind" in second.model_dump():
            raise ProbeFailure("Skill capacity rejection exposed a CommandResult kind field")
        return {"status": second.status.value, "errors": second.errors}
    finally:
        server.close()


def case_skill_queue_before_delivery():
    """r3: queued Skill timeout is withdrawn before delivery."""
    wd = temp_dir("vb-fault-queue-")
    init_work_dir(wd)
    reg = load_registry(registry_path())
    entry = UserEntry(token="tok-queue", mode="local")
    entry.runtime.thread_pool_size = 2
    reg.register("alice", entry)
    server = BusinessServer()
    client = BlockingSkillClient()
    try:
        with mock.patch.object(BusinessServer, "_skill", lambda self, token: client):
            first = threading.Thread(
                target=lambda: server.execute_skill("1+1", timeout=2, token="tok-queue")
            )
            first.start()
            if not client.started.wait(1):
                raise ProbeFailure("first queued Skill request did not start")
            second = server.execute_skill("2+2", timeout=0.05, token="tok-queue")
            client.release.set()
            first.join(timeout=3)
        if second.status != ExecutionStatus.ERROR or second.errors != ["SKILL execution timed out"]:
            raise ProbeFailure(f"unexpected queued timeout: {second.model_dump()}")
        if "metadata" in second.model_dump():
            raise ProbeFailure("queued timeout exposed delivery metadata")
        return {"errors": second.errors, "metadata": "absent"}
    finally:
        server.close()


def case_windows_casefold_overwrite():
    """Windows case-insensitive overwrite must replace, not duplicate, the user."""
    import common.registry as registry_mod

    wd = temp_dir("vb-fault-casefold-")
    reg = Registry(wd / "registry.json").load()
    a = make_remote_entry("tok-a")
    b = make_remote_entry("tok-a")  # token is immutable (多用户与注册 §1)
    with mock.patch.object(registry_mod.os, "name", "nt"):
        reg.register("Alice", a)
        reg.register("alice", b, overwrite=True)
    names = reg.users()
    if len(names) != 1:
        raise ProbeFailure(f"case-insensitive overwrite left duplicate users: {names}")
    return {"users": names}


CASES = {
    "lease-race": case_lease_race,
    "dead-shell-close": case_dead_shell_close,
    "transport-kind": case_transport_kind,
    "daemon-log-protocol": case_daemon_log_protocol,
    "runtime-cache-invalidation": case_runtime_cache_invalidation,
    "windows-casefold-overwrite": case_windows_casefold_overwrite,
    "skill-capacity-fields": case_skill_capacity_fields,
    "skill-queue-before-delivery": case_skill_queue_before_delivery,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", choices=sorted(CASES), action="append", default=[])
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    if not args.case:
        # P-072 口径：一进程一 work root —— 多 case 各自要绑不同的临时根，
        # 整跑必须每个 case 一个子进程（见 test/docs/写TB规范.md §3）。
        return _run_all_in_children(args.out)
    selected = args.case
    results = {}
    failed = 0
    for name in selected:
        started = time.monotonic()
        try:
            results[name] = {"status": "pass", "detail": CASES[name]()}
        except Exception as exc:  # noqa: BLE001
            failed += 1
            results[name] = {"status": "fail", "error": f"{type(exc).__name__}: {exc}"}
        results[name]["elapsed_s"] = time.monotonic() - started
    cleaned = cleanup_temp_dirs()
    payload = {"ok": failed == 0, "failed": failed,
               "temp_dirs_removed": cleaned, "results": results}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 1 if failed else 0


def _run_all_in_children(out_path: str) -> int:
    """每个 case 起一个子进程跑（子进程内只绑一次 work root），父进程只汇总。"""
    results: dict = {}
    failed = 0
    for name in sorted(CASES):
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix=f"vb-fi-child-{name}-") as tmp:
            child_out = Path(tmp) / "case.json"
            proc = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--case", name,
                 "--out", str(child_out)],
                cwd=str(Path(__file__).resolve().parents[3]),
                capture_output=True, text=True, timeout=600,
            )
            payload: dict = {}
            if child_out.is_file():
                try:
                    payload = json.loads(child_out.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    payload = {}
            case = (payload.get("results") or {}).get(name)
            if case is None:
                case = {"status": "fail",
                        "error": f"child rc={proc.returncode} produced no result; "
                                 f"stderr={(proc.stderr or '')[-200:]}"}
            results[name] = case
            if case.get("status") != "pass":
                failed += 1
        results[name]["elapsed_s"] = round(time.monotonic() - started, 3)
    payload_out = {"ok": failed == 0, "failed": failed,
                   "mode": "per-case-subprocess", "results": results}
    text = json.dumps(payload_out, ensure_ascii=False, indent=2)
    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
