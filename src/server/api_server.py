"""Top-layer HTTP server (spec 顶层 §1/§2): entry point + dispatch only.

The handler parses JSON, calls :func:`server.dispatch.dispatch`, returns the
business result body directly, and renders ``{"ok", "error"}`` only for
requests that never reach a business package; it never touches transport code.  The
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
from typing import Any
from urllib.parse import parse_qs, urlsplit

from server import dispatch as dispatch_module
from server.dispatch import dispatch
from server.manual import Manual
from common import config as config_base
from common.paths import config_path, init_work_dir, work_root
from common.jsonutil import dumps_strict, loads_strict


#: Top-layer overall thread-pool size when ``config.json`` does not set
#: ``business_thread_pool_size`` (spec 顶层补充 §5 owns the config file).
DEFAULT_MAX_INFLIGHT = 1024

#: Global config snapshot file (startup import once; PUT /api/config writes it).
CONFIG_FILENAME = "config.json"


def pool_size_from_snapshot(
    snapshot, default: int = DEFAULT_MAX_INFLIGHT
) -> int:
    value = snapshot.get("business_thread_pool_size")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return default
    return value


#: Fixed over-limit answer: the request was *not* accepted; the caller may retry.
BUSY_ERROR = "server thread pool exceeded (max {limit} in-flight), please retry"

#: Restart drain window (顶层补充 v27 §3): total drain budget for restart.
DRAIN_TIMEOUT = 30.0

#: 请求体上限，与控制面同口径（顶层 §3：16 MiB，超限 413）。
_MAX_REQUEST_BYTES = 16 * 1024 * 1024

#: Supervised mode event channel (父进程通过 stdout 读 VB-EVENT 行).
EVENT_PREFIX = "VB-EVENT "

#: Business /help fallback when the manual is not shipped with the service.
_FALLBACK_QUICKSTART = (
    "POST /api/operation with {operation, token, ...}; "
    "GET /help/operations lists every registered operation."
)


def _package_name(spec) -> str:
    """Manual package name, derived from the registered package module."""
    module = getattr(spec.package, "__module__", "")
    return module.rsplit(".", 1)[-1] or "unknown"


def _request_schema(request_model: Any) -> dict:
    """JSON schema for a Request model (pydantic model or plain dataclass)."""
    model_json_schema = getattr(request_model, "model_json_schema", None)
    if callable(model_json_schema):
        try:
            return model_json_schema()
        except Exception:  # noqa: BLE001 - help must not break business
            pass
    try:
        from pydantic import TypeAdapter

        return TypeAdapter(request_model).json_schema()
    except Exception:  # noqa: BLE001 - degrade to an empty object shape
        return {
            "type": "object",
            "properties": {},
            "required": [],
            "title": getattr(request_model, "__name__", "Request"),
        }


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "vb-api/0.1"
    protocol_version = "HTTP/1.1"

    # -- helpers ---------------------------------------------------------------
    def _send(self, status: int, payload: Any, *,
              retry_after: int | None = None,
              allow: str | None = None,
              close: bool = False) -> None:
        try:
            text = dumps_strict(payload)
        except (TypeError, ValueError) as exc:
            status = 500
            text = dumps_strict({
                "ok": False,
                "error": f"invalid response payload: {exc}",
            })
        body = text.encode("utf-8")
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

    def _read_json(self) -> tuple[int, Any]:
        """Return ``(status, payload)``: 200 = ok, 400 = bad, 413 = too large."""
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except (TypeError, ValueError):
            return 400, None
        if length < 0:
            return 400, None
        # 超限直接拒绝，不按声明的长度读取 body（与注册面同口径）
        if length > _MAX_REQUEST_BYTES:
            return 413, None
        raw = self.rfile.read(length) if length > 0 else b""
        if not raw:
            return 400, None
        try:
            return 200, loads_strict(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError):
            return 400, None

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
            # quickstart + 兼容保留的 operations 清单（帮助体系 §2.1/§4）
            quickstart = server.manual.quickstart()
            self._send(200, {
                "ok": True,
                "data": {
                    "quickstart": quickstart or _FALLBACK_QUICKSTART,
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
        if path == "/help/operations":
            query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
            name = (query.get("name") or [""])[0].strip()
            if name:
                status, body = self._help_operation_detail(name, query)
            else:
                status, body = 200, {
                    "ok": True,
                    "data": self._help_operation_list(query),
                    "error": None,
                }
            self._send(status, body)
            return
        allowed = self._PATH_ALLOWED.get(path)
        if allowed is not None:
            # 已定义路径 + 非支持方法 → 405 + Allow（顶层 §3）
            self._method_not_allowed(allow=allowed)
            return
        self._send(404, {"ok": False, "error": "not found"})

    def _help_operation_list(self, query: dict) -> dict:
        """``{count, groups}``: groups = package, entries ``{name, summary?}``."""
        group_filter = (query.get("group") or [""])[0].strip()
        groups: dict[str, list[dict]] = {}
        for operation in dispatch_module.operations():
            spec = dispatch_module.PACKAGES.get(operation)
            if spec is None:
                continue
            package = _package_name(spec)
            if group_filter and package != group_filter:
                continue
            entry = {"name": operation}
            summary = self.server.manual.summary(
                self.server.manual.operation_section(package, operation)
            )
            if summary:
                entry["summary"] = summary
            groups.setdefault(package, []).append(entry)
        return {
            "count": sum(len(items) for items in groups.values()),
            "groups": groups,
        }

    def _help_operation_detail(self, name: str, query: dict) -> tuple[int, dict]:
        spec = dispatch_module.PACKAGES.get(name)
        if spec is None:
            return 404, {"ok": False, "error": f"unknown operation: {name}"}
        package = _package_name(spec)
        schema = _request_schema(spec.request_model)
        section = self.server.manual.operation_section(package, name)
        data: dict[str, Any] = {
            "name": name,
            "package": package,
            "method": spec.method,
            "required_fields": list(schema.get("required") or []),
            "request_schema": schema,
            "doc": {
                "file": f"packages/{package}.md",
                "section_title": section.title if section is not None else None,
            },
            "content_format": "markdown",
        }
        common = self.server.manual.common()
        if common is not None:
            data["common_ref"] = {
                "file": "common.md",
                "section_title": common.title,
            }
            include_common = (query.get("common") or ["1"])[0]
            if include_common not in ("0", "false", "no"):
                data["common"] = common.body
        if section is not None:
            data["content"] = section.body
        else:
            data["content_unavailable"] = self.server.manual.unavailable_reason(
                f"packages/{package}.md"
            )
        return 200, {"ok": True, "data": data, "error": None}

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path != "/api/operation":
            allowed = self._PATH_ALLOWED.get(path)
            if allowed is not None:
                self._method_not_allowed(allow=allowed)
                return
            self._send(404, {"ok": False, "error": "not found"})
            return
        status, payload = self._read_json()
        if status == 413:
            self._send(
                413,
                {"ok": False, "error": "request body too large"},
                close=True,
            )
            return
        if status != 200:
            self._send(
                400,
                {"ok": False, "error": "invalid JSON body"},
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
                {"ok": False, "error": "server is restarting, please retry"},
                retry_after=1,
            )
            return
        if not server.acquire_slot():
            self._send(
                429,
                {"ok": False, "error": BUSY_ERROR.format(limit=server.max_inflight)},
                retry_after=1,
            )
            return
        try:
            status, body = dispatch(server.middle, payload)
        finally:
            server.release_slot()
        self._send(status, body)

    def _method_not_allowed(
        self, *, body: bool = True, allow: str = "GET, POST"
    ) -> None:
        self._drain_request_body()
        if body:
            self._send(405, {
                "ok": False,
                "error": "method not allowed",
            }, allow=allow, close=True)
            return
        self.close_connection = True
        self.send_response(405)
        self.send_header("Allow", allow)
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

    _DEFINED_PATHS = frozenset({
        "/api/operation", "/health", "/help", "/help/operations",
    })

    #: 已定义路径 → 该路径真正支持的方法（405 的 Allow 用）
    _PATH_ALLOWED = {
        "/api/operation": "POST",
        "/health": "GET",
        "/help": "GET",
        "/help/operations": "GET",
    }

    def _unknown_method(self) -> None:
        if self.path.split("?", 1)[0] in self._DEFINED_PATHS:
            self._method_not_allowed()
            return
        self._send(
            404, {"ok": False, "error": "not found"},
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

    def __init__(
        self,
        address,
        middle,
        *,
        max_inflight: int = DEFAULT_MAX_INFLIGHT,
        manual_root=None,
    ) -> None:
        super().__init__(address, ApiHandler)
        if max_inflight < 1:
            raise ValueError("max_inflight must be >= 1")
        self.middle = middle
        self.max_inflight = max_inflight
        self.manual = Manual(manual_root)
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
    ("pyapi.packages.gui", "Package", "OPERATIONS"),
    ("pyapi.packages.cellview", "Package", "OPERATIONS"),
    ("pyapi.packages.schematic", "Package", "OPERATIONS"),
    ("pyapi.packages.maestro", "Package", "OPERATIONS"),
    ("pyapi.packages.symbol", "Package", "OPERATIONS"),
    ("pyapi.packages.layout", "Package", "OPERATIONS"),
    ("pyapi.packages.skillref", "Package", "OPERATIONS"),
    ("pyapi.packages.spectre", "Package", "OPERATIONS"),
    ("pyapi.packages.verilog", "Package", "OPERATIONS"),
    ("pyapi.packages.veriloga", "Package", "OPERATIONS"),
    ("pyapi.packages.calibre", "Package", "OPERATIONS"),
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
                 max_inflight: int = DEFAULT_MAX_INFLIGHT,
                 manual_root=None) -> ApiServer:
    return ApiServer(
        (host, port), middle,
        max_inflight=max_inflight, manual_root=manual_root,
    )


# -- supervised mode (顶层补充 v27 §1.1/§3) -----------------------------------

def _emit_event(**payload: Any) -> None:
    """Write one control event line for the parent supervisor."""
    try:
        sys.stdout.write(
            EVENT_PREFIX + dumps_strict(payload) + "\n"
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
        config_base.reload_config(config_path())
        server.set_max_inflight(
            pool_size_from_snapshot(config_base.snapshot())
        )
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
    from common.runtime_env import warn_if_client_python_unsupported

    warn_if_client_python_unsupported()
    parser = argparse.ArgumentParser(description="virtuoso-bridge top layer (HTTP)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8126)
    parser.add_argument("--work-dir", default=None,
                        help="directory holding registry.json + config.json "
                             "(assembly only)")
    parser.add_argument("--manual-root", default=None,
                        help="read-only manual root for /help "
                             "(default: skills/virtuoso-bridge/manual)")
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
    config_base.init_config(config_path())
    middle = BusinessServer()
    # global config snapshot: imported once at startup, never read per request
    pool_size = pool_size_from_snapshot(config_base.snapshot())
    server = build_server(
        args.host, args.port, middle,
        max_inflight=pool_size, manual_root=args.manual_root,
    )
    banner = (
        f"virtuoso-bridge API (business): http://{args.host}:{args.port}  "
        f"({len(dispatch_module.operations())} operations, "
        f"business_thread_pool_size={pool_size})"
    )
    loop_thread: threading.Thread | None = None
    if args.supervised:
        print(banner, file=sys.stderr)
        # stdout 留给 VB-EVENT 控制事件；普通日志走 stderr
        loop_thread = threading.Thread(
            target=_supervised_loop, args=(server, middle), daemon=True
        )
        loop_thread.start()
    else:
        print(banner)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        # server.shutdown() lets serve_forever() return first; wait for the
        # control loop to finish so drain_done is written before we exit.
        if loop_thread is not None:
            loop_thread.join(timeout=DRAIN_TIMEOUT + 5)
        server.server_close()
        middle.close()


if __name__ == "__main__":
    main()
