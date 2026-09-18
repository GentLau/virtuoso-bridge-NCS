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
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from server import dispatch as dispatch_module
from server.dispatch import dispatch
from common.paths import config_path, init_work_dir


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


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "vb-api/0.1"
    protocol_version = "HTTP/1.1"

    # -- helpers ---------------------------------------------------------------
    def _send(self, status: int, payload: dict[str, Any], *,
              retry_after: int | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if retry_after is not None:
            self.send_header("Retry-After", str(retry_after))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> tuple[bool, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            return False, None
        raw = self.rfile.read(length) if length > 0 else b""
        if not raw:
            return False, None
        try:
            return True, json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False, None

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
                         "max_inflight": server.max_inflight},
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
            self._send(400, {"ok": False, "data": None, "error": "invalid JSON body"})
            return
        # top-layer overall pool: refuse immediately instead of queueing, so the
        # caller can retry (this bounds the top layer's own resources)
        server = self.server  # type: ignore[assignment]
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
        self._slots = threading.BoundedSemaphore(max_inflight)

    def acquire_slot(self) -> bool:
        """Take one top-layer pool slot; never blocks (over-limit -> 429)."""
        return self._slots.acquire(blocking=False)

    def release_slot(self) -> None:
        try:
            self._slots.release()
        except ValueError:  # pragma: no cover - release without acquire
            pass

    def in_flight(self) -> int:
        """Currently occupied pool slots (operational metadata for /health)."""
        return self.max_inflight - self._slots._value  # type: ignore[attr-defined]


#: Explicit package table (顶层 §2.1 / 上层 §4.1): one row per business *package*;
#: ``(module, package class, operation metadata attr)``.  The operation entries
#: themselves live in the package (``OPERATIONS``), because the registration unit
#: is the package and the entries are per business operation.
PACKAGES = (
    ("pyapi.packages.basic", "Package", "OPERATIONS"),
    ("pyapi.packages.demo", "Package", "OPERATIONS"),
    ("pyapi.packages.gui", "Package", "OPERATIONS"),
    ("pyapi.packages.cellview", "Package", "OPERATIONS"),
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="virtuoso-bridge top layer (HTTP)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8126)
    parser.add_argument("--work-dir", default=None,
                        help="directory holding registry.json + config.json "
                             "(assembly only)")
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
    print(f"virtuoso-bridge API (business): http://{args.host}:{args.port}  "
          f"({len(dispatch_module.operations())} operations, "
          f"business_thread_pool_size={pool_size})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        middle.close()


if __name__ == "__main__":
    main()
