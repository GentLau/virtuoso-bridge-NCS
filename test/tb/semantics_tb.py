"""Semantics TB: contracts the success-path TB does not drive.

Each case encodes one *spec* contract and is expected to fail on the code
baseline that does not implement it (red first, fix second):

* ``local-file-timeout``   - 五接口 deadline：本地模式的文件接口也必须消费 timeout
* ``local-tree-timeout``   - 同上，递归（目录）传输必须按预算中止
* ``local-download-timeout`` - 下载方向同理
* ``registry-cross-process`` - registry 跨进程写不得丢更新（OS 文件锁 + 读改写）
* ``install-crash-safety`` - 目标替换中途崩溃不得丢失已存在的目标

Run with::

    PYTHONPATH=src python test/tb/semantics_tb.py [--case NAME] [--out FILE]

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
import time
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from transport.middle import BusinessServer  # noqa: E402
from transport.registry import Registry, UserEntry, load_registry  # noqa: E402
from transport.runtime_paths import set_working_dir  # noqa: E402

try:  # Windows: never pop a console for child processes
    from _win import no_window  # type: ignore
except ImportError:  # pragma: no cover - direct import when run as a module
    def no_window(**kwargs):  # type: ignore
        return dict(kwargs)


class ProbeFailure(AssertionError):
    pass


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
    wd = Path(tempfile.mkdtemp(prefix="vb-sem-"))
    set_working_dir(wd)
    registry = load_registry()
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
    from transport.registry import UserEntry, load_registry

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
    wd = Path(tempfile.mkdtemp(prefix="vb-reg-xproc-"))
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
    wd = Path(tempfile.mkdtemp(prefix="vb-install-crash-"))
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


def _facts_server() -> tuple[BusinessServer, Path]:
    wd = Path(tempfile.mkdtemp(prefix="vb-facts-"))
    set_working_dir(wd)
    registry = load_registry()
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
        registry.register(name, entry)
    return BusinessServer(wd), wd


def case_role_facts_shape() -> dict:
    """spec §4.2：role_facts 返回五个 role 的已解析参数，且只读、无副作用。"""
    server, wd = _facts_server()
    try:
        facts_before = (wd / "registry.json").read_bytes()
        facts = server.role_facts("tok-alpha")
        if not facts.ok:
            raise ProbeFailure(f"role_facts failed for a known token: {facts}")
        roles = facts.roles
        if set(roles) != {"gui", "daemon", "command", "file", "spectre"}:
            raise ProbeFailure(f"role_facts must return the five roles: {sorted(roles)}")
        for name, role in roles.items():
            if role.mode != "remote":
                raise ProbeFailure(f"{name}.mode wrong: {role.mode}")
            if role.host != "server-a" or role.user != "alpha":
                raise ProbeFailure(f"{name} endpoint leaked: {role.host}/{role.user}")
            if role.root != f"/srv/alpha/{name}":
                raise ProbeFailure(f"{name}.root wrong: {role.root}")
            expected_bin = "/cadence/bin/spectre" if name == "spectre" else None
            if role.bin != expected_bin:
                raise ProbeFailure(f"{name}.bin wrong: {role.bin!r}")
        if (wd / "registry.json").read_bytes() != facts_before:
            raise ProbeFailure("role_facts wrote the registry (must be read-only)")
        if server._clients or server._skill_clients:
            raise ProbeFailure("role_facts opened a transport client (must not connect)")
        return {"roles": sorted(roles), "spectre_bin": roles["spectre"].bin}
    finally:
        server.close()


def case_role_facts_unknown_token() -> dict:
    """未知 token 必须是结构化失败，不抛异常（spec §4.2）。"""
    server, _wd = _facts_server()
    try:
        try:
            result = server.role_facts("tok-does-not-exist")
        except Exception as exc:  # noqa: BLE001 - any raise violates the contract
            raise ProbeFailure(f"unknown token raised {type(exc).__name__}: {exc}") from exc
        if result.ok or result.error != "invalid token" or result.roles:
            raise ProbeFailure(f"unknown token was not a structured failure: {result}")
        return {"error": result.error}
    finally:
        server.close()


def case_role_facts_isolation() -> dict:
    """role_facts 按 token 隔离：A 的查询不得泄露 B 的目标。"""
    server, _wd = _facts_server()
    try:
        alpha = server.role_facts("tok-alpha")
        beta = server.role_facts("tok-beta")
        if alpha.roles["daemon"].host == beta.roles["daemon"].host:
            raise ProbeFailure("role_facts leaked another token's endpoint")
        if alpha.roles["daemon"].root == beta.roles["daemon"].root:
            raise ProbeFailure("role_facts leaked another token's root")
        return {
            "alpha": alpha.roles["daemon"].host,
            "beta": beta.roles["daemon"].host,
        }
    finally:
        server.close()


CASES = {
    "role-facts-shape": case_role_facts_shape,
    "role-facts-unknown-token": case_role_facts_unknown_token,
    "role-facts-isolation": case_role_facts_isolation,
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
    payload = {"ok": failed == 0, "failed": failed, "results": results}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
