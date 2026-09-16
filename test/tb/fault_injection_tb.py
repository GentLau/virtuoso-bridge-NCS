"""Fault-injection TB.

This TB is intentionally adversarial: it drives edge conditions that the
normal multi-user success-path TB does not cover.  Run with:

    PYTHONPATH=src python test/tb/fault_injection_tb.py

Exit code is non-zero when any fault-injection case fails; the JSON output is
the raw evidence consumed by the final test report.
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from transport.registry import Registry, UserEntry, load_registry  # noqa: E402
from transport.roles import resolve  # noqa: E402
from transport.runtime_paths import registry_path, set_working_dir  # noqa: E402
from transport.ssh import SSHRunner  # noqa: E402
from transport.tunnel import RemoteClient  # noqa: E402
from transport.middle import BusinessServer  # noqa: E402
from pyapi.models import ExecutionStatus, VirtuosoResult  # noqa: E402


class ProbeFailure(AssertionError):
    pass


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
        return __import__("pyapi.models", fromlist=["CommandResult"]).CommandResult(0, "", "")

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
    wd = Path(tempfile.mkdtemp(prefix="vb-fault-cache-"))
    set_working_dir(wd)
    reg = load_registry()
    first = make_remote_entry("tok-cache")
    reg.register("alice", first)
    server = BusinessServer(wd)
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

    def execute_skill(self, code, timeout=None):
        self.started.set()
        self.release.wait(2)
        return VirtuosoResult(status=ExecutionStatus.SUCCESS, output="2")


def case_skill_capacity_fields():
    """r3: Skill capacity rejection lives in errors, never a kind field."""
    wd = Path(tempfile.mkdtemp(prefix="vb-fault-cap-"))
    set_working_dir(wd)
    reg = load_registry()
    entry = UserEntry(token="tok-cap", mode="local")
    entry.runtime.thread_pool_size = 1
    reg.register("alice", entry)
    server = BusinessServer(wd)
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
    wd = Path(tempfile.mkdtemp(prefix="vb-fault-queue-"))
    set_working_dir(wd)
    reg = load_registry()
    entry = UserEntry(token="tok-queue", mode="local")
    entry.runtime.thread_pool_size = 2
    reg.register("alice", entry)
    server = BusinessServer(wd)
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
        if second.metadata:
            raise ProbeFailure("queued timeout exposed delivery metadata")
        return {"errors": second.errors, "metadata": second.metadata}
    finally:
        server.close()


def case_windows_casefold_overwrite():
    """Windows case-insensitive overwrite must replace, not duplicate, the user."""
    import transport.registry as registry_mod

    wd = Path(tempfile.mkdtemp(prefix="vb-fault-casefold-"))
    reg = Registry(wd / "registry.json").load()
    a = make_remote_entry("tok-a")
    b = make_remote_entry("tok-b")
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
    args = ap.parse_args()
    selected = args.case or sorted(CASES)
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
    print(json.dumps({"ok": failed == 0, "failed": failed, "results": results}, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
