"""Semantics TB: contracts the success-path TB does not drive.

Each case encodes one *spec* contract and is expected to fail on the code
baseline that does not implement it (red first, fix second):

* ``local-file-timeout``   - 五接口 deadline：本地模式的文件接口也必须消费 timeout
* ``local-tree-timeout``   - 同上，递归（目录）传输必须按预算中止
* ``local-download-timeout`` - 下载方向同理
* ``registry-cross-process`` - registry 跨进程写不得丢更新（OS 文件锁 + 读改写）
* ``install-crash-safety`` - 目标替换中途崩溃不得丢失已存在的目标

Run with::

    PYTHONPATH=src python test/offline/core/semantics_tb.py [--case NAME] [--out FILE]

Exit code is non-zero when any case fails; the JSON printed on stdout is the
raw evidence consumed by the final test report.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
_SUPPORT = Path(__file__).resolve().parents[2] / "shared" / "fixtures"
if str(_SUPPORT) not in sys.path:
    sys.path.insert(0, str(_SUPPORT))

from transport.middle import BusinessServer  # noqa: E402
from common.registry import Registry, UserEntry, load_registry  # noqa: E402
from common.paths import registry_path, override_work_dir_for_tests  # noqa: E402

try:  # Windows: never pop a console for child processes
    from _win import no_window  # type: ignore
except ImportError:  # pragma: no cover - direct import when run as a module
    def no_window(**kwargs):  # type: ignore
        return dict(kwargs)


class ProbeFailure(AssertionError):
    pass


_TEMP_DIRS: list[Path] = []


def temp_dir(prefix: str) -> Path:
    """Per-case temp dir, removed by ``cleanup_temp_dirs`` at the end of the run."""
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


class StepClock:
    """Deterministic clock: every call advances a fixed number of seconds.

    A deadline-aware transfer consults the clock per chunk/file and therefore
    expires inside the budget; a transfer that copies first and checks later
    (or never) succeeds instead, which is exactly the contract violation this
    case must catch.  ``origin`` keeps the (unused) monotonic base stable.
    """

    def __init__(self, step: float = 0.05, origin: float = 1_000.0) -> None:
        self.step = step
        self.now = origin
        self.calls = 0

    def __call__(self) -> float:
        self.calls += 1
        value = self.now
        self.now += self.step
        return value


def local_server(token: str, *, root: Path | None = None) -> tuple[BusinessServer, Path]:
    wd = temp_dir("vb-sem-")
    override_work_dir_for_tests(wd)
    registry = load_registry(registry_path())
    entry = UserEntry(token=token, mode="local")
    if root is not None:
        entry.roles.file.root = str(root)
    registry.register(token, entry)
    return BusinessServer(wd), wd


def _timeout_case(*, kind: str, recursive: bool, timeout: float) -> dict:
    token = f"tok-{kind}"
    server, wd = local_server(token)
    store = wd / "store"
    store.mkdir(exist_ok=True)
    clock = StepClock()
    try:
        if kind == "upload":
            if recursive:
                source = wd / "tree"
                (source / "nested").mkdir(parents=True)
                for index in range(8):
                    (source / f"f{index}.bin").write_bytes(b"u" * (64 * 1024))
                    (source / "nested" / f"g{index}.bin").write_bytes(b"u" * (64 * 1024))
            else:
                source = wd / "big.bin"
                source.write_bytes(b"u" * (1 << 24))
            target = store / "target"
            with mock.patch("transport.middle.time.monotonic", clock):
                result = server.upload_file(
                    source, str(target), timeout=timeout, token=token, recursive=recursive
                )
        else:
            source = store / "big.bin"
            source.write_bytes(b"d" * (1 << 24))
            target = wd / "pulled.bin"
            with mock.patch("transport.middle.time.monotonic", clock):
                result = server.download_file(
                    str(source), target, timeout=timeout, token=token, recursive=recursive
                )
    finally:
        server.close()

    if result.kind != "timeout" or result.returncode != 124:
        raise ProbeFailure(
            f"{kind} (recursive={recursive}) ignored the budget: "
            f"kind={result.kind!r} rc={result.returncode} stderr={result.stderr!r}"
        )
    if target.exists() and kind == "upload":
        raise ProbeFailure("timed-out upload left a partial target behind")
    if target.exists() and kind == "download":
        raise ProbeFailure("timed-out download left a partial target behind")
    return {
        "kind": result.kind,
        "returncode": result.returncode,
        "stderr": result.stderr,
        "clock_calls": clock.calls,
        "partial_target": target.exists(),
    }


def case_local_file_timeout() -> dict:
    return _timeout_case(kind="upload", recursive=False, timeout=0.2)


def case_local_tree_timeout() -> dict:
    return _timeout_case(kind="upload", recursive=True, timeout=0.2)


def case_local_download_timeout() -> dict:
    return _timeout_case(kind="download", recursive=False, timeout=0.2)


CHILD_REGISTRY = textwrap.dedent(
    """
    import sys, time
    from pathlib import Path
    sys.path.insert(0, sys.argv[1])
    from common.registry import UserEntry, load_registry

    _, src, reg_path, user, token, ready, gate, done = sys.argv
    registry = load_registry(Path(reg_path))
    Path(ready).write_text("1", encoding="utf-8")
    deadline = time.monotonic() + 30
    while not Path(gate).exists():
        if time.monotonic() > deadline:
            raise SystemExit("gate timeout")
        time.sleep(0.01)
    entry = UserEntry(token=token, mode="remote")
    registry.register(user, entry)
    Path(done).write_text("1", encoding="utf-8")
    """
)


def case_registry_cross_process() -> dict:
    wd = temp_dir("vb-reg-xproc-")
    reg_path = wd / "registry.json"
    seed = Registry(reg_path).load()
    seed.register("seed", UserEntry(token="tok-seed", mode="remote"))

    child = wd / "child.py"
    child.write_text(CHILD_REGISTRY, encoding="utf-8")
    users = [f"user{i}" for i in range(4)]
    procs = []
    for user in users:
        procs.append(
            subprocess.Popen(
                [
                    sys.executable, str(child), str(SRC), str(reg_path), user,
                    f"tok-{user}", str(wd / f"ready-{user}"), str(wd / "gate"),
                    str(wd / f"done-{user}"),
                ],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                **no_window(),
            )
        )
    deadline = time.monotonic() + 30
    while not all((wd / f"ready-{u}").exists() for u in users):
        if time.monotonic() > deadline:
            for proc in procs:
                proc.kill()
            raise ProbeFailure("children never reached the load barrier")
        time.sleep(0.02)
    (wd / "gate").write_text("1", encoding="utf-8")
    errors = []
    for proc, user in zip(procs, users):
        try:
            _out, err = proc.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            proc.kill()
            errors.append(f"{user}: child timeout")
            continue
        if proc.returncode != 0:
            errors.append(f"{user}: rc={proc.returncode} {err.strip()}")
    if errors:
        raise ProbeFailure("; ".join(errors))

    on_disk = json.loads(reg_path.read_text(encoding="utf-8"))
    missing = [user for user in users if user not in on_disk]
    if missing:
        raise ProbeFailure(
            f"cross-process writes lost users {missing}; file holds {sorted(on_disk)}"
        )
    if "seed" not in on_disk:
        raise ProbeFailure(
            f"cross-process writes dropped the pre-existing user; file holds {sorted(on_disk)}"
        )
    tokens = {value.get("token") for value in on_disk.values()}
    if len(tokens) != len(on_disk):
        raise ProbeFailure(f"token index corrupted after concurrent writes: {sorted(on_disk)}")
    return {"users": sorted(on_disk), "tokens": sorted(t for t in tokens if t)}


CHILD_INSTALL = textwrap.dedent(
    """
    import os, sys
    from pathlib import Path
    sys.path.insert(0, sys.argv[1])
    from transport.middle import BusinessServer

    _, src, stage, target, marker = sys.argv
    real_replace = os.replace
    state = {"count": 0}

    def crashing_replace(source, destination, *args, **kwargs):
        result = real_replace(source, destination, *args, **kwargs)
        state["count"] += 1
        if state["count"] == 1:
            Path(marker).write_text("crashed-after-first-rename", encoding="utf-8")
            os._exit(9)
        return result

    os.replace = crashing_replace
    BusinessServer._install_staged(Path(stage), Path(target))
    Path(marker).write_text("completed", encoding="utf-8")
    """
)


def case_install_crash_safety() -> dict:
    wd = temp_dir("vb-install-crash-")
    target = wd / "target.bin"
    target.write_text("OLD", encoding="utf-8")
    stage = wd / ".vbtmp-crash"
    stage.write_text("NEW", encoding="utf-8")
    child = wd / "child.py"
    child.write_text(CHILD_INSTALL, encoding="utf-8")
    marker = wd / "marker"

    proc = subprocess.run(
        [sys.executable, str(child), str(SRC), str(stage), str(target), str(marker)],
        capture_output=True, text=True, timeout=60, **no_window(),
    )
    if proc.returncode != 9:
        raise ProbeFailure(
            f"crash injection did not fire: rc={proc.returncode} {proc.stderr.strip()}"
        )
    if not target.exists():
        leftovers = sorted(p.name for p in wd.iterdir() if p.name.startswith(".vbbak"))
        raise ProbeFailure(
            "crash between the two renames lost the existing target "
            f"(leftovers={leftovers})"
        )
    content = target.read_text(encoding="utf-8")
    if content not in ("OLD", "NEW"):
        raise ProbeFailure(f"target holds a partial payload: {content!r}")
    return {
        "target_content": content,
        "leftovers": sorted(p.name for p in wd.iterdir() if p.name.startswith(".vbbak")),
        "marker": marker.read_text(encoding="utf-8") if marker.exists() else "",
    }


class _BlockingSkillClient:
    """Skill client that occupies its slot until released (budget tests)."""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def execute_skill(self, code, timeout=None, *, log_level=None, log_max_bytes=None):
        from pyapi.models import ExecutionStatus, VirtuosoResult

        self.started.set()
        self.release.wait(10)
        return VirtuosoResult(status=ExecutionStatus.SUCCESS, output="2")


def _facts_server() -> tuple[BusinessServer, Path]:
    wd = temp_dir("vb-facts-")
    override_work_dir_for_tests(wd)
    registry = load_registry(registry_path())
    for name, host, root, bin_path in (
        ("alpha", "server-a", "/srv/alpha", "/cadence/bin/spectre"),
        ("beta", "server-b", "/srv/beta", None),
    ):
        entry = UserEntry(token=f"tok-{name}", mode="remote")
        entry.ssh.default.host = host
        entry.ssh.default.user = name
        for role_name in ("gui", "daemon", "command", "file", "spectre"):
            role = getattr(entry.roles, role_name)
            role.host = host
            role.user = name
            role.root = f"{root}/{role_name}"
        entry.roles.spectre.bin = bin_path
        entry.roles.gui.display = ":11"
        registry.register(name, entry)
    return BusinessServer(wd), wd


def case_query_shape() -> dict:
    """spec §4.2（r12）：query 只返回 root、gui.display、spectre.bin。"""
    server, wd = _facts_server()
    try:
        snapshot = (wd / "registry.json").read_bytes()
        result = server.query(token="tok-alpha")
        if str(result.status) not in ("success", "ExecutionStatus.SUCCESS"):
            raise ProbeFailure(f"query failed for a known token: {result}")
        roles = result.roles
        if set(roles) != {"gui", "daemon", "command", "file", "spectre"}:
            raise ProbeFailure(f"query must return the five roles: {sorted(roles)}")
        dumped = result.model_dump(mode="json")
        for name, role in dumped["roles"].items():
            # spec §4.2：返回角色的 root；gui 额外 display、spectre 额外 bin；
            # **未配置的键省略**（角色自带用户组也允许透传）——所以不能要求三者同时出现。
            if set(role) - {"root", "bin", "display"}:
                raise ProbeFailure(
                    f"{name} exposed fields outside root/bin/display: {sorted(set(role) - {'root', 'bin', 'display'})}"
                )
            if "root" not in role:
                raise ProbeFailure(f"{name} missing root fact")
            if role["root"] != f"/srv/alpha/{name}":
                raise ProbeFailure(f"{name}.root wrong: {role['root']}")
            expected_bin = "/cadence/bin/spectre" if name == "spectre" else None
            if role.get("bin") != expected_bin:
                raise ProbeFailure(f"{name}.bin wrong: {role.get('bin')!r}")
            expected_display = ":11" if name == "gui" else None
            if role.get("display") != expected_display:
                raise ProbeFailure(
                    f"{name}.display wrong: {role.get('display')!r}"
                )
        for banned in ("mode", "host", "user", "jump_host", "proxy"):
            # 只扫 roles 段：local 段是路径事实，路径文本里出现 "user" 属正常
            if banned in json.dumps(dumped["roles"]):
                raise ProbeFailure(f"query leaked topology field {banned!r}")
        # 本机路径不从中层查询：query 只返回 role 的 root/bin（顶层用路径端口供货）
        if "local" in dumped:
            raise ProbeFailure("query must not expose local paths (top layer owns them)")
        if (wd / "registry.json").read_bytes() != snapshot:
            raise ProbeFailure("query wrote the registry (must be read-only)")
        if server._clients or server._skill_clients:
            raise ProbeFailure("query opened a transport client (must not connect)")
        return {"roles": sorted(roles), "spectre_bin": roles["spectre"].bin}
    finally:
        server.close()


def case_query_unknown_token() -> dict:
    """未知 token 返回 {"status":"error","errors":["invalid token"]}，不抛异常。"""
    server, _wd = _facts_server()
    try:
        try:
            result = server.query(token="tok-does-not-exist")
        except Exception as exc:  # noqa: BLE001 - any raise violates the contract
            raise ProbeFailure(f"unknown token raised {type(exc).__name__}: {exc}") from exc
        dumped = result.model_dump(mode="json")
        if dumped.get("status") != "error" or dumped.get("errors") != ["invalid token"]:
            raise ProbeFailure(f"unknown token shape wrong: {dumped}")
        if dumped.get("roles"):
            raise ProbeFailure(f"failed query returned roles: {dumped}")
        return {"status": dumped["status"], "errors": dumped["errors"]}
    finally:
        server.close()


def case_query_isolation() -> dict:
    """query 按 token 隔离：A 的查询不得泄露 B 的 root/bin。"""
    server, _wd = _facts_server()
    try:
        alpha = server.query(token="tok-alpha")
        beta = server.query(token="tok-beta")
        if alpha.roles["daemon"].root == beta.roles["daemon"].root:
            raise ProbeFailure("query leaked another token's root")
        if beta.roles["spectre"].bin is not None:
            raise ProbeFailure(f"beta has no spectre bin: {beta.roles['spectre'].bin!r}")
        return {"alpha_root": alpha.roles["daemon"].root,
                "beta_root": beta.roles["daemon"].root}
    finally:
        server.close()


def case_query_no_budget() -> dict:
    """只读查询不占三类预算、不进队列：线程池被占满时仍立即返回。"""
    wd = temp_dir("vb-query-budget-")
    override_work_dir_for_tests(wd)
    registry = load_registry(registry_path())
    entry = UserEntry(token="tok-query", mode="local")
    entry.runtime.thread_pool_size = 1
    registry.register("alice", entry)
    server = BusinessServer(wd)
    client = _BlockingSkillClient()
    try:
        with mock.patch.object(BusinessServer, "_skill", lambda self, token: client):
            holder = threading.Thread(
                target=lambda: server.execute_skill("1+1", timeout=5, token="tok-query")
            )
            holder.start()
            if not client.started.wait(2):
                raise ProbeFailure("could not occupy the only thread-pool slot")
            started = time.monotonic()
            result = server.query(token="tok-query")
            elapsed = time.monotonic() - started
            client.release.set()
            holder.join(timeout=5)
        if str(result.status) not in ("success", "ExecutionStatus.SUCCESS"):
            raise ProbeFailure(f"query was refused while the pool was busy: {result}")
        if elapsed > 0.5:
            raise ProbeFailure(f"query waited for the thread pool ({elapsed:.3f}s)")
        return {"elapsed_s": round(elapsed, 4), "ok": True}
    finally:
        server.close()


def case_skill_no_retry_after_delivery() -> dict:
    """已投递的 Skill 绝不能重发（spec：重试只发生在未产生副作用的阶段）。"""
    import socket as _socket

    deliveries: list[bytes] = []
    listener = _socket.socket()
    listener.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(16)
    port = listener.getsockname()[1]
    stop = threading.Event()

    def serve() -> None:
        listener.settimeout(0.5)
        while not stop.is_set():
            try:
                conn, _ = listener.accept()
            except (_socket.timeout, OSError):
                continue
            try:
                raw = b""
                while True:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    raw += chunk
                deliveries.append(raw)
                # the request has been delivered: kill the connection without
                # answering, mimicking a daemon crash right after execution
                conn.setsockopt(_socket.SOL_SOCKET, _socket.SO_LINGER,
                                b"\x01\x00\x00\x00\x00\x00\x00\x00")
            except OSError:
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        from common.skill_client import SkillClient

        client = SkillClient(host="127.0.0.1", port=port, timeout=5.0, token="tok")
        started = time.monotonic()
        result = client.execute_skill("1+2", timeout=2.0)
        elapsed = time.monotonic() - started
    finally:
        stop.set()
        try:
            listener.close()
        except OSError:
            pass
        thread.join(timeout=3)

    if len(deliveries) > 1:
        raise ProbeFailure(
            f"Skill request was delivered {len(deliveries)} times after a "
            "post-delivery failure (must never be resent)"
        )
    if len(deliveries) == 0:
        raise ProbeFailure("the fake daemon never received the request")
    if result.ok:
        raise ProbeFailure(f"crash after delivery reported success: {result}")
    if result.errors != ["SKILL execution timed out"]:
        raise ProbeFailure(
            "post-delivery failure must use the frozen timeout wording: "
            f"{result.errors}"
        )
    return {"deliveries": len(deliveries), "errors": result.errors,
            "elapsed_s": round(elapsed, 3)}


CASES = {
    "skill-no-retry-after-delivery": case_skill_no_retry_after_delivery,
    "query-shape": case_query_shape,
    "query-unknown-token": case_query_unknown_token,
    "query-isolation": case_query_isolation,
    "query-no-budget": case_query_no_budget,
    "local-file-timeout": case_local_file_timeout,
    "local-tree-timeout": case_local_tree_timeout,
    "local-download-timeout": case_local_download_timeout,
    "registry-cross-process": case_registry_cross_process,
    "install-crash-safety": case_install_crash_safety,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=sorted(CASES), action="append", default=[])
    parser.add_argument("--out", default="")
    args = parser.parse_args()
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
    cleaned = cleanup_temp_dirs()
    payload = {"ok": failed == 0, "failed": failed, "temp_dirs_removed": cleaned,
               "results": results}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
