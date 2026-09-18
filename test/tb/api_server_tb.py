"""Top-layer HTTP TB (spec 顶层): dispatch shell, status codes, isolation.

Starts the real ``server.api_server`` against a local-mode token with an
in-process daemon stub, then drives it over HTTP:

* ``GET /api/operations`` lists the registered operations;
* structural failures are 4xx and business failures are 2xx ``ok=false``;
* an unexpected exception is 5xx, is not leaked as a stack trace, and does not
  stop the server (next request still works);
* a full ``demo.pipeline.run`` (upload -> skill -> command -> download) succeeds
  and the token travels unchanged to the middle (never echoed back);
* the dispatch module imports no transport/socket/subprocess code (顶层 §2.4).

Run with::

    PYTHONPATH=src python test/tb/api_server_tb.py --out test/tb/artifacts/api-server.json
"""
from __future__ import annotations

import argparse
import ast
import json
import socket
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from server import dispatch as dispatch_module  # noqa: E402
from server.api_server import (  # noqa: E402
    BUSY_ERROR,
    CONFIG_FILENAME,
    DEFAULT_MAX_INFLIGHT,
    build_server,
    load_business_thread_pool_size,
    register_packages,
)
from transport.middle import BusinessServer  # noqa: E402
from common.registry import UserEntry, load_registry  # noqa: E402
from common.paths import registry_path, override_work_dir_for_tests  # noqa: E402


class ProbeFailure(AssertionError):
    pass


class _DaemonStub:
    """Protocol-compatible daemon stub that echoes the requested SKILL text."""

    def __init__(self, port: int, token: str) -> None:
        self.port = port
        self.token = token
        self._stop = threading.Event()
        self._sock: socket.socket | None = None
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self.seen_tokens: list[str] = []

    def _serve(self) -> None:
        assert self._sock is not None
        self._sock.settimeout(0.5)
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except (socket.timeout, OSError):
                continue
            try:
                raw = b""
                while True:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    raw += chunk
                request = json.loads(raw.decode("utf-8"))
                self.seen_tokens.append(str(request.get("token")))
                if request.get("token") != self.token:
                    conn.sendall(b"\x15" + json.dumps({"error": "invalid token", "log": ""}).encode() + b"\x1e")
                    continue
                skill = str(request.get("skill", ""))
                value = "2" if skill.strip() in ("1+1", "") else skill
                conn.sendall(b"\x02" + json.dumps({"value": value, "log": ""}).encode() + b"\x1e")
            except Exception:  # noqa: BLE001
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

    def start(self) -> None:
        self._sock = socket.socket()
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", self.port))
        self._sock.listen(32)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        self._thread.join(timeout=5)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _post(base: str, payload, *, raw: bytes | None = None, path: str = "/api/operation"):
    data = raw if raw is not None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        base + path, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8") or "{}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    work_dir = Path(tempfile.mkdtemp(prefix="vb-api-tb-"))
    override_work_dir_for_tests(work_dir)
    registry = load_registry(registry_path())
    token = f"tok-api-{uuid.uuid4().hex[:8]}"
    daemon_port = _free_port()
    entry = UserEntry(token=token, mode="local")
    entry.roles.daemon.daemon_port = daemon_port
    entry.roles.daemon.local_port = daemon_port
    entry.roles.daemon.root = str(work_dir / "root")
    for name in ("gui", "command", "file", "spectre"):
        getattr(entry.roles, name).root = str(work_dir / "root" / name)
    registry.register("api-user", entry)

    stub = _DaemonStub(daemon_port, token)
    stub.start()
    middle = BusinessServer(work_dir)

    errors = register_packages()
    if errors:
        raise ProbeFailure(f"packages failed to load: {errors}")

    # spec 守卫（顶层 §2.4 / 上层 §2.2）：业务包构造只允许接收一个 Middle
    seen_ctor_args: list[tuple] = []

    class _CtorGuardPackage:
        def __init__(self, *args) -> None:
            seen_ctor_args.append(args)

        def run(self, _request):
            return {"ok": True, "steps": [{"name": "ctor", "ok": True,
                                           "detail": {"argc": len(seen_ctor_args[-1])}}],
                    "error": None, "argc": len(seen_ctor_args[-1])}

    dispatch_module.register_operation("test.ctor", _CtorGuardPackage, "run", dict)

    # a test-only operation that raises an unexpected error (5xx path)
    class _BoomPackage:
        def __init__(self, _middle) -> None:
            pass

        def run(self, _request):
            raise RuntimeError("boom")

    dispatch_module.register_operation("test.boom", _BoomPackage, "run", dict)

    port = _free_port()
    server = build_server("127.0.0.1", port, middle)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    results: dict[str, object] = {}
    started = time.monotonic()
    try:
        # -- health / help（业务端口运维端点，顶层补充 §4）---------------------
        with urllib.request.urlopen(base + "/health", timeout=30) as response:
            health = json.loads(response.read().decode("utf-8"))
        if response.status != 200 or health["data"]["face"] != "business":
            raise ProbeFailure(f"business /health failed: {health}")
        with urllib.request.urlopen(base + "/help", timeout=30) as response:
            listing = json.loads(response.read().decode("utf-8"))
        if "POST /api/operation" not in listing["data"]["endpoints"]:
            raise ProbeFailure(f"business /help lacks the operation endpoint: {listing}")
        ops = set(listing["data"]["operations"])
        required = {
            "basic.skill.execute", "basic.command.run", "basic.file.upload",
            "basic.file.download", "basic.gui.run", "basic.spectre.run",
            "demo.pipeline.run", "demo.parallel.probe", "virtuoso.netlist.import",
        }
        if not required <= ops:
            raise ProbeFailure(f"operations listing incomplete: {sorted(required - ops)}")
        results["operations"] = sorted(ops)

        # -- structural failures (4xx) ----------------------------------------
        status, body = _post(base, None, raw=b"{not json")
        if status != 400 or body.get("ok") is not False:
            raise ProbeFailure(f"bad JSON must be 400: {status} {body}")
        status, body = _post(base, {"token": token})
        if status != 400 or "operation" not in str(body.get("error")):
            raise ProbeFailure(f"missing operation must be 400: {status} {body}")
        status, body = _post(base, {"operation": "demo.parallel.probe"})
        if status != 400 or "token" not in str(body.get("error")):
            raise ProbeFailure(f"missing token must be 400: {status} {body}")
        status, body = _post(base, {"operation": "nope.nope.nope", "token": token})
        if status != 404:
            raise ProbeFailure(f"unknown operation must be 404: {status} {body}")
        status, body = _post(base, {"operation": "demo.parallel.probe", "token": token,
                                    "commands": "not-a-list"})
        if status != 400:
            raise ProbeFailure(f"bad field type must be 400: {status} {body}")
        status, body = _post(base, {"operation": "basic.command.run", "token": token})
        if status != 400:
            raise ProbeFailure(f"basic.command.run without cmd must be 400: {status} {body}")
        status, body = _post(base, {"operation": "basic.command.run", "token": token,
                                    "cmd": "echo x"}, path="/")
        if status != 404:
            raise ProbeFailure(f"business port must only serve /api/operation: {status} {body}")
        results["structural"] = "400/404 as specified (path isolation)"

        # -- basic package: six direct middle passthroughs ----------------------
        marker = f"BASIC-{uuid.uuid4().hex[:8]}"

        status, body = _post(base, {"operation": "basic.command.run", "token": token,
                                    "cmd": f"echo {marker}"})
        if status != 200 or body.get("ok") is not True or marker not in str(body["data"]):
            raise ProbeFailure(f"basic.command.run failed: {status} {json.dumps(body)[:200]}")

        status, body = _post(base, {"operation": "basic.skill.execute", "token": token,
                                    "skill_code": f'strcat("{marker}")'})
        skill_data = body.get("data") or {}
        if status != 200 or body.get("ok") is not True or marker not in json.dumps(skill_data):
            raise ProbeFailure(f"basic.skill.execute failed: {status} {json.dumps(body)[:200]}")

        basic_src = work_dir / "basic_in.txt"
        basic_src.write_text(f"payload-{marker}", encoding="utf-8")
        basic_dst = work_dir / "basic_out.txt"
        remote = str(work_dir / "root" / "file" / f"{marker}.bin")
        status, body = _post(base, {"operation": "basic.file.upload", "token": token,
                                    "local_path": str(basic_src), "remote_path": remote})
        if status != 200 or body.get("ok") is not True:
            raise ProbeFailure(f"basic.file.upload failed: {status} {json.dumps(body)[:200]}")
        status, body = _post(base, {"operation": "basic.file.download", "token": token,
                                    "remote_path": remote, "local_path": str(basic_dst)})
        if status != 200 or body.get("ok") is not True:
            raise ProbeFailure(f"basic.file.download failed: {status} {json.dumps(body)[:200]}")
        if basic_dst.read_text(encoding="utf-8") != f"payload-{marker}":
            raise ProbeFailure("basic file round trip content mismatch")

        for operation in ("basic.gui.run", "basic.spectre.run"):
            status, body = _post(base, {"operation": operation, "token": token,
                                        "cmd": f"echo {marker}"})
            if status != 200 or body.get("ok") is not True or marker not in str(body["data"]):
                raise ProbeFailure(f"{operation} failed: {status} {json.dumps(body)[:200]}")
        results["basic_package"] = "skill/command/upload/download/gui/spectre ok"

        # -- business success over HTTP (upload -> skill -> command -> download)
        local_in = work_dir / "in.txt"
        local_in.write_text("payload", encoding="utf-8")
        local_out = work_dir / "out.txt"
        marker = f"API-{uuid.uuid4().hex[:8]}"
        payload = {
            "operation": "demo.pipeline.run",
            "token": token,
            "local_input": str(local_in),
            "remote_input": str(work_dir / "root" / "file" / "in.txt"),
            "skill_code": f'strcat("{marker}")',
            "command": f"echo {marker}",
            "remote_output": str(work_dir / "root" / "file" / "in.txt"),
            "local_output": str(local_out),
        }
        status, body = _post(base, payload)
        if status != 200 or body.get("ok") is not True:
            raise ProbeFailure(f"pipeline operation failed: {status} {json.dumps(body)[:300]}")
        steps = body["data"]["steps"]
        if [step["name"] for step in steps] != ["upload", "skill", "command", "download"]:
            raise ProbeFailure(f"unexpected step trace: {steps}")
        if local_out.read_text(encoding="utf-8") != "payload":
            raise ProbeFailure("downloaded payload differs")
        if marker not in json.dumps(steps):
            raise ProbeFailure("skill/command markers missing from the step trace")
        if token in json.dumps(body):
            raise ProbeFailure("the top layer echoed the token back")
        if token not in stub.seen_tokens:
            raise ProbeFailure("token did not reach the middle layer unchanged")
        results["pipeline"] = {"steps": len(steps), "echoed_token": False}

        # -- business failure is 2xx ok=false with step trace ------------------
        failing = dict(payload, local_input=str(work_dir / "missing.txt"))
        status, body = _post(base, failing)
        if status != 200 or body.get("ok") is not False or not body.get("error"):
            raise ProbeFailure(f"business failure must be 2xx ok=false: {status} {body}")
        if body["data"] is None or not body["data"].get("steps"):
            raise ProbeFailure(f"business failure lost its step trace: {body}")
        results["business_failure"] = body["error"][:60]

        # -- unexpected exception: 5xx, no stack trace, server survives --------
        status, body = _post(base, {"operation": "test.boom", "token": token})
        if status != 500 or "boom" not in str(body.get("error")):
            raise ProbeFailure(f"unexpected exception must be 500: {status} {body}")
        if "Traceback" in json.dumps(body):
            raise ProbeFailure("stack trace leaked to the client")
        status, body = _post(base, {"operation": "demo.parallel.probe", "token": token,
                                    "commands": [f"echo {marker}"]})
        if status != 200 or body.get("ok") is not True:
            raise ProbeFailure(f"server did not survive the 5xx path: {status} {body}")
        results["error_isolation"] = "500 then next request ok"

        # -- concurrency smoke --------------------------------------------------
        outcomes: list[bool] = []
        lock = threading.Lock()

        def one() -> None:
            status, body = _post(base, {"operation": "demo.parallel.probe", "token": token,
                                        "commands": [f"echo {marker}"]})
            with lock:
                outcomes.append(status == 200 and body.get("ok") is True)

        threads = [threading.Thread(target=one) for _ in range(8)]
        for item in threads:
            item.start()
        for item in threads:
            item.join(timeout=180)
        if len(outcomes) != 8 or not all(outcomes):
            raise ProbeFailure(f"concurrent requests not all answered: {outcomes}")
        results["concurrent"] = f"{sum(outcomes)}/8"

        # -- spec §2.4: dispatch imports no transport/socket/subprocess ---------
        tree = ast.parse((SRC / "server" / "dispatch.py").read_text(encoding="utf-8"))
        banned: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                banned += [alias.name for alias in node.names
                           if alias.name.split(".")[0] in {"transport", "socket", "subprocess", "paramiko"}]
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".")[0] in {"transport", "socket", "subprocess", "paramiko"}:
                    banned.append(node.module)
        if banned:
            raise ProbeFailure(f"dispatch module imports transport code: {banned}")
        results["dispatch_purity"] = "no transport/socket/subprocess imports"

        # -- spec 上层 §4.2: every package exports Package + OPERATIONS ----------
        for module_name, expected in (
            ("pyapi.packages.basic", {
                "basic.skill.execute", "basic.command.run", "basic.file.upload",
                "basic.file.download", "basic.gui.run", "basic.spectre.run"}),
            ("pyapi.packages.demo", {
                "demo.pipeline.run", "demo.parallel.probe", "virtuoso.netlist.import",
                "demo.paths.facts"}),
        ):
            module = __import__(module_name, fromlist=["*"])
            if not hasattr(module, "Package") or not hasattr(module, "OPERATIONS"):
                raise ProbeFailure(f"{module_name} lacks Package/OPERATIONS metadata")
            declared = {entry[0] for entry in module.OPERATIONS}
            if declared != expected:
                raise ProbeFailure(f"{module_name} metadata mismatch: {sorted(declared)}")
        results["package_metadata"] = "basic(6) + demo(3) operations declared"

        # duplicate operation registration must be a startup error (顶层 §2.1)
        try:
            dispatch_module.register_operation(
                "demo.pipeline.run", object, "run", dict
            )
        except ValueError as exc:
            results["duplicate_registration"] = f"startup error: {exc}"
        else:
            raise ProbeFailure("duplicate operation registration was accepted")

        # -- global config snapshot: business_thread_pool_size from server.json --
        if DEFAULT_MAX_INFLIGHT != 1024:
            raise ProbeFailure(f"provisional default drifted: {DEFAULT_MAX_INFLIGHT}")
        config_path = work_dir / CONFIG_FILENAME
        config_path.write_text(json.dumps({"business_thread_pool_size": 7}),
                               encoding="utf-8")
        if load_business_thread_pool_size(config_path) != 7:
            raise ProbeFailure("server.json business_thread_pool_size was not honoured")
        config_path.write_text(json.dumps({"business_thread_pool_size": 0}),
                               encoding="utf-8")
        if load_business_thread_pool_size(config_path) != DEFAULT_MAX_INFLIGHT:
            raise ProbeFailure("invalid pool size must fall back to the default")
        config_path.write_text("{not json", encoding="utf-8")
        if load_business_thread_pool_size(config_path) != DEFAULT_MAX_INFLIGHT:
            raise ProbeFailure("broken server.json must fall back to the default")
        results["config_snapshot"] = {
            "file": CONFIG_FILENAME,
            "honoured": 7,
            "fallback": DEFAULT_MAX_INFLIGHT,
        }

        # -- spec 守卫：dispatch 只把 Middle 传给业务包（顶层 §2.4 / 上层 §2.2）---
        status, body = _post(base, {"operation": "test.ctor", "token": token})
        if status != 200 or body.get("ok") is not True:
            raise ProbeFailure(f"constructor guard package failed: {status} {body}")
        if body["data"].get("argc") != 1:
            raise ProbeFailure(
                f"business package must be constructed with Middle only: argc="
                f"{body['data'].get('argc')}"
            )
        first_arg = seen_ctor_args[-1][0]
        if not hasattr(first_arg, "execute_skill"):
            raise ProbeFailure("the single constructor argument is not the Middle")
        results["ctor_contract"] = {"arguments": 1, "argument": type(first_arg).__name__}

        # -- 上层业务包直接读 common 基座拿本机目录（经顶层 HTTP 返回）------------
        status, body = _post(base, {"operation": "demo.paths.facts", "token": token})
        if status != 200 or body.get("ok") is not True:
            raise ProbeFailure(f"demo.paths.facts failed: {status} {body}")
        facts = body["data"]
        if facts.get("work_root") != str(work_dir):
            raise ProbeFailure(f"business package did not read the common base: {facts}")
        for key in ("temp_dir", "log_dir", "artifact_dir"):
            if not Path(facts.get(key) or "").is_dir():
                raise ProbeFailure(f"{key} not a directory: {facts}")
        results["upper_layer_paths"] = {
            "work_root_matches": True,
            "temp_dir": facts["temp_dir"],
        }

        class _SlowPackage:
            def __init__(self, _middle) -> None:
                pass

            def run(self, _request):
                time.sleep(0.6)
                return {"ok": True, "steps": [], "error": None}

        dispatch_module.register_operation("test.slow", _SlowPackage, "run", dict)
        limit = 2
        limited_port = _free_port()
        limited = build_server("127.0.0.1", limited_port, middle, max_inflight=limit)
        limited_thread = threading.Thread(target=limited.serve_forever, daemon=True)
        limited_thread.start()
        limited_base = f"http://127.0.0.1:{limited_port}"
        try:
            outcomes: list[tuple[int, str]] = []
            lock = threading.Lock()

            def slow_call() -> None:
                status, body = _post(limited_base, {"operation": "test.slow", "token": token})
                with lock:
                    outcomes.append((status, str(body.get("error"))))

            callers = [threading.Thread(target=slow_call) for _ in range(limit + 3)]
            for item in callers:
                item.start()
            for item in callers:
                item.join(timeout=120)
            busy = [item for item in outcomes if item[0] == 429]
            ok_calls = [item for item in outcomes if item[0] == 200]
            if len(ok_calls) != limit or not busy:
                raise ProbeFailure(f"pool limit not enforced: {outcomes}")
            expected = BUSY_ERROR.format(limit=limit)
            if any(expected not in item[1] for item in busy):
                raise ProbeFailure(f"over-limit text wrong: {busy}")
            # slots are released: the next call is accepted again
            time.sleep(0.8)
            status, body = _post(limited_base, {"operation": "test.slow", "token": token})
            if status != 200:
                raise ProbeFailure(f"pool slot was not released: {status} {body}")
            results["pool_limit"] = {
                "max_inflight": DEFAULT_MAX_INFLIGHT,
                "tested_limit": limit,
                "accepted": len(ok_calls),
                "refused_429": len(busy),
                "recovered": True,
            }
        finally:
            limited.shutdown()
            limited.server_close()
    finally:
        server.shutdown()
        server.server_close()
        middle.close()
        stub.stop()
        import shutil
        shutil.rmtree(work_dir, ignore_errors=True)

    payload = {"ok": True, "failed": 0, "elapsed_s": round(time.monotonic() - started, 3),
               "results": results}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
