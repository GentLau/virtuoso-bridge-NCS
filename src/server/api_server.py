"""Top-layer HTTP server (spec 顶层 §1/§2): entry point + dispatch only.

The handler parses JSON, calls :func:`server.dispatch.dispatch`, and renders the
``{"ok", "data", "error"}`` shell; it never touches transport code.  The
``Middle`` implementation is created once at process assembly and injected.

Run::

    python -m server.api_server --host 127.0.0.1 --port 8126 --work-dir <dir>

``--work-dir`` only selects which ``registry.json`` the middle layer loads; it
is read by the assembly, never by the request path.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from server import dispatch as dispatch_module
from server.dispatch import dispatch
from common.paths import config_path, init_work_dir, work_root
from common.jsonutil import loads_strict


#: Top-layer overall thread-pool size when ``config.json`` does not set
#: ``business_thread_pool_size`` (spec 顶层补充 §5 owns the config file).
DEFAULT_MAX_INFLIGHT = 1024

#: Global config snapshot file (startup import once; PUT /api/config writes it).
CONFIG_FILENAME = "config.json"


def load_business_thread_pool_size(config_path: Path) -> int:
    """Read the business pool size from the config snapshot, once at startup."""
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return DEFAULT_MAX_INFLIGHT
    value = data.get("business_thread_pool_size")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return DEFAULT_MAX_INFLIGHT
    return value

#: Fixed over-limit answer: the request was *not* accepted; the caller may retry.
BUSY_ERROR = "server thread pool exceeded (max {limit} in-flight), please retry"

#: Restart drain window (顶层补充 v27 §3): total drain budget for restart.
DRAIN_TIMEOUT = 30.0

#: Supervised mode event channel (父进程通过 stdout 读 VB-EVENT 行).
EVENT_PREFIX = "VB-EVENT "


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "vb-api/0.1"
    protocol_version = "HTTP/1.1"

    # -- helpers ---------------------------------------------------------------
    def _send(self, status: int, payload: dict[str, Any], *,
              retry_after: int | None = None,
              allow: str | None = None,
              close: bool = False) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if retry_after is not None:
            self.send_header("Retry-After", str(retry_after))
        if allow is not None:
            self.send_header("Allow", allow)
        if close:
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> tuple[bool, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except (TypeError, ValueError):
            return False, None
        if length < 0:
            return False, None
        raw = self.rfile.read(length) if length > 0 else b""
        if not raw:
            return False, None
        try:
            return True, loads_strict(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError):
            return False, None

    def _drain_request_body(self, limit: int = 1_048_576) -> None:
        """Consume a bounded request body before closing the connection."""
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except (TypeError, ValueError):
            return
        remaining = min(max(length, 0), limit)
        while remaining > 0:
            chunk = self.rfile.read(min(remaining, 65536))
            if not chunk:
                break
            remaining -= len(chunk)

    # -- routes ----------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        server = self.server  # type: ignore[assignment]
        if path == "/health":
            self._send(200, {
                "ok": True,
                "data": {"status": "ok", "face": "business",
                         "operations": len(dispatch_module.operations()),
                         "in_flight": server.in_flight(),
                         "max_inflight": server.max_inflight,
                         "draining": server.draining},
                "error": None,
            })
            return
        if path == "/help":
            # 端点清单与用法说明（顶层补充 §4）
            self._send(200, {
                "ok": True,
                "data": {
                    "face": "business",
                    "endpoints": ["POST /api/operation", "GET /health", "GET /help"],
                    "operations": dispatch_module.operations(),
                    "package_load_errors": dispatch_module.PACKAGE_LOAD_ERRORS,
                    "max_inflight": server.max_inflight,
                    "usage": {
                        "method": "POST",
                        "path": "/api/operation",
                        "body": {"operation": "<业务操作名>", "token": "<个人 token>",
                                 "…": "业务字段"},
                    },
                },
                "error": None,
            })
            return
        self._send(404, {"ok": False, "data": None, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?")[0] != "/api/operation":
            self._send(404, {"ok": False, "data": None, "error": "not found"})
            return
        ok, payload = self._read_json()
        if not ok:
            self._send(
                400,
                {"ok": False, "data": None, "error": "invalid JSON body"},
                close=True,
            )
            return
        # top-layer overall pool: refuse immediately instead of queueing, so the
        # caller can retry (this bounds the top layer's own resources)
        server = self.server  # type: ignore[assignment]
        if server.draining:
            # 排队中的 restart/停服：监听保持，新请求结构化拒绝（v27 §3）。
            self._send(
                503,
                {"ok": False, "data": None,
                 "error": "server is restarting, please retry"},
                retry_after=1,
            )
            return
        if not server.acquire_slot():
            self._send(
                429,
                {"ok": False, "data": None,
                 "error": BUSY_ERROR.format(limit=server.max_inflight)},
                retry_after=1,
            )
            return
        try:
            status, body = dispatch(server.middle, payload)
        finally:
            server.release_slot()
        self._send(status, body)

    def _method_not_allowed(self, *, body: bool = True) -> None:
        self._drain_request_body()
        if body:
            self._send(405, {
                "ok": False,
                "data": None,
                "error": "method not allowed",
            }, allow="GET, POST", close=True)
            return
        self.close_connection = True
        self.send_response(405)
        self.send_header("Allow", "GET, POST")
        self.send_header("Connection", "close")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_PUT(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_DELETE(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_TRACE(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_PATCH(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_CONNECT(self) -> None:  # noqa: N802
        self._method_not_allowed()

    def do_HEAD(self) -> None:  # noqa: N802
        self._method_not_allowed(body=False)

    _DEFINED_PATHS = frozenset({"/api/operation", "/health", "/help"})

    def _unknown_method(self) -> None:
        if self.path.split("?", 1)[0] in self._DEFINED_PATHS:
            self._method_not_allowed()
            return
        self._send(
            404, {"ok": False, "data": None, "error": "not found"},
            close=True,
        )

    def __getattr__(self, name: str):
        if name.startswith("do_"):
            return self._unknown_method
        raise AttributeError(name)

    def log_message(self, fmt: str, *args: Any) -> None:  # keep stdout clean
        return


class ApiServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 1024

    def __init__(self, address, middle, *, max_inflight: int = DEFAULT_MAX_INFLIGHT) -> None:
        super().__init__(address, ApiHandler)
        if max_inflight < 1:
            raise ValueError("max_inflight must be >= 1")
        self.middle = middle
        self.max_inflight = max_inflight
        self.draining = False
        self._slots_lock = threading.Lock()
        self._slots_idle = threading.Condition(self._slots_lock)
        self._in_flight = 0

    def acquire_slot(self) -> bool:
        """Take one top-layer pool slot; never blocks (over-limit -> 429)."""
        with self._slots_idle:
            if self._in_flight >= self.max_inflight:
                return False
            self._in_flight += 1
            return True

    def release_slot(self) -> None:
        with self._slots_idle:
            if self._in_flight > 0:
                self._in_flight -= 1
            self._slots_idle.notify_all()

    def in_flight(self) -> int:
        """Currently occupied pool slots (operational metadata for /health)."""
        with self._slots_idle:
            return self._in_flight

    def set_max_inflight(self, limit: int) -> int:
        """Reload `business_thread_pool_size` (v27: hot admission limit).

        不打断在途请求；在途数 ≥ 新上限时新请求按 429 拒绝，直到低于上限。
        """
        value = max(1, int(limit))
        with self._slots_idle:
            self.max_inflight = value
            self._slots_idle.notify_all()
        return value

    def wait_idle(self, timeout: float) -> bool:
        """Wait until no request is in flight; True when drained in time."""
        deadline = time.monotonic() + max(0.0, float(timeout))
        with self._slots_idle:
            while self._in_flight > 0:
                left = deadline - time.monotonic()
                if left <= 0:
                    return False
                self._slots_idle.wait(left)
            return True


#: Explicit package table (顶层 §2.1 / 上层 §4.1): one row per business *package*;
#: ``(module, package class, operation metadata attr)``.  The operation entries
#: themselves live in the package (``OPERATIONS``), because the registration unit
#: is the package and the entries are per business operation.
PACKAGES = (
    ("pyapi.packages.basic", "Package", "OPERATIONS"),
    ("pyapi.packages.demo", "Package", "OPERATIONS"),
    ("pyapi.packages.gui", "Package", "OPERATIONS"),
    ("pyapi.packages.cellview", "Package", "OPERATIONS"),
    ("pyapi.packages.schematic", "Package", "OPERATIONS"),
    ("pyapi.packages.maestro", "Package", "OPERATIONS"),
)


def register_packages() -> dict[str, str]:
    """Build the dispatch registry once, isolating per-package load failures."""
    errors: dict[str, str] = {}
    for module_name, class_name, operations_attr in PACKAGES:
        try:
            module = __import__(module_name, fromlist=["*"])
            package = getattr(module, class_name)
            operations = getattr(module, operations_attr)
        except Exception as exc:  # noqa: BLE001 - only this package is disabled
            errors[module_name] = f"{type(exc).__name__}: {exc}"
            dispatch_module.PACKAGE_LOAD_ERRORS[module_name] = errors[module_name]
            continue
        for operation, method, request_model, _result in operations:
            # duplicate operation names are a startup error (顶层 §2.1), not a
            # "package unavailable" case
            dispatch_module.register_operation(operation, package, method, request_model)
    return errors


def build_server(host: str, port: int, middle, *,
                 max_inflight: int = DEFAULT_MAX_INFLIGHT) -> ApiServer:
    return ApiServer((host, port), middle, max_inflight=max_inflight)


def build_middle(work_dir: str | None = None):
    """Assembly helper: initialize the shared base once, then build the middle."""
    from transport.middle import BusinessServer

    init_work_dir(work_dir)
    return BusinessServer()


# -- supervised mode (顶层补充 v27 §1.1/§3) -----------------------------------

def _emit_event(**payload: Any) -> None:
    """Write one control event line for the parent supervisor."""
    try:
        sys.stdout.write(
            EVENT_PREFIX + json.dumps(payload, ensure_ascii=False) + "\n"
        )
        sys.stdout.flush()
    except (OSError, ValueError):
        pass


def reload_business_state(server: ApiServer, middle) -> tuple[bool, str | None]:
    """Re-import registry.json + config.json without interrupting in-flight.

    v27: 注册表快照立即切换（新请求按新表路由），旧 token 缓存由其 in-flight
    归零后关闭；`business_thread_pool_size` 作为可变准入上限热生效。
    """
    try:
        middle.reload_registry()
        server.set_max_inflight(load_business_thread_pool_size(config_path()))
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def drain_and_stop(server: ApiServer, middle, timeout: float = DRAIN_TIMEOUT) -> bool:
    """Refuse new requests, drain in-flight (<= timeout), then stop cleanly."""
    server.draining = True
    idle = server.wait_idle(timeout)
    try:
        server.shutdown()
    finally:
        server.server_close()
        middle.close()
    return idle


def _supervised_loop(server: ApiServer, middle) -> None:
    """Read parent commands from stdin; EOF (parent exit) stops the child."""
    _emit_event(
        event="ready",
        pid=os.getpid(),
        port=server.server_address[1],
        work_dir=str(work_root()),
    )
    while True:
        line = sys.stdin.readline()
        if not line:
            # 管理进程退出（管道 EOF）：按 v27 "管理退出停止业务" 收尾
            drain_and_stop(server, middle)
            return
        try:
            command = json.loads(line).get("cmd")
        except (ValueError, AttributeError):
            _emit_event(event="error", error="invalid control command")
            continue
        if command == "reload":
            ok, error = reload_business_state(server, middle)
            _emit_event(event="reload_done", ok=ok, error=error)
        elif command in ("drain", "shutdown"):
            _emit_event(event="drain_started")
            idle = drain_and_stop(server, middle)
            _emit_event(event="drain_done", ok=idle)
            return
        else:
            _emit_event(event="error", error=f"unknown command: {command!r}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="virtuoso-bridge top layer (HTTP)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8126)
    parser.add_argument("--work-dir", default=None,
                        help="directory holding registry.json + config.json "
                             "(assembly only)")
    parser.add_argument("--supervised", action="store_true",
                        help="run as the business child of a supervisor: "
                             "control commands on stdin, VB-EVENT lines on stdout")
    args = parser.parse_args(argv)

    errors = register_packages()
    for operation, message in sorted(errors.items()):
        print(f"[api] package unavailable: {operation}: {message}")

    # process assembly: the only place that knows about the middle layer
    from transport.middle import BusinessServer

    # 本机路径由顶层解析一次，注入中层（中层不再自己决定工作目录）
    init_work_dir(args.work_dir)          # 进程级环境：入口初始化一次
    middle = BusinessServer()
    # global config snapshot: imported once at startup, never read per request
    pool_size = load_business_thread_pool_size(config_path())
    server = build_server(args.host, args.port, middle, max_inflight=pool_size)
    banner = (
        f"virtuoso-bridge API (business): http://{args.host}:{args.port}  "
        f"({len(dispatch_module.operations())} operations, "
        f"business_thread_pool_size={pool_size})"
    )
    if args.supervised:
        # stdout 留给 VB-EVENT 控制事件；普通日志走 stderr
        print(banner, file=sys.stderr)
        threading.Thread(
            target=_supervised_loop, args=(server, middle), daemon=True
        ).start()
    else:
        print(banner)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        middle.close()


if __name__ == "__main__":
    main()
