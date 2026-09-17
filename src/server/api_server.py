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
from typing import Any

from server import dispatch as dispatch_module
from server.dispatch import dispatch


#: Top-layer overall thread-pool size.  Provisional value for this version; it
#: becomes a configuration item later (see 接口调用指南 §1.2).
DEFAULT_MAX_INFLIGHT = 1024

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
        if self.path.split("?")[0] == "/api/operations":
            # operational metadata only: what this process can dispatch
            self._send(200, {
                "ok": True,
                "data": {
                    "operations": dispatch_module.operations(),
                    "package_load_errors": dispatch_module.PACKAGE_LOAD_ERRORS,
                    "max_inflight": self.server.max_inflight,  # type: ignore[attr-defined]
                },
                "error": None,
            })
            return
        self._send(404, {"ok": False, "data": None, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
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


#: Explicit operation table (顶层 §2.1): one row per business operation.
#: ``operation -> (module, package class, method, request model attr)``.
PACKAGES = (
    ("virtuoso.netlist.import", "pyapi.packages.netlist_import", "Package",
     "run", "Request"),
    ("demo.pipeline.run", "pyapi.packages.file_skill_command_file",
     "FileSkillCommandFilePackage", "run_request", "Request"),
    ("demo.parallel.probe", "pyapi.packages.parallel_probe",
     "ParallelProbePackage", "run_request", "Request"),
)


def register_packages() -> dict[str, str]:
    """Build the dispatch registry once, isolating per-package load failures."""
    errors: dict[str, str] = {}
    for operation, module_name, class_name, method, request_attr in PACKAGES:
        try:
            module = __import__(module_name, fromlist=["*"])
            package = getattr(module, class_name)
            request_model = getattr(module, request_attr)
        except Exception as exc:  # noqa: BLE001 - only this package is disabled
            errors[operation] = f"{type(exc).__name__}: {exc}"
            dispatch_module.PACKAGE_LOAD_ERRORS[operation] = errors[operation]
            continue
        # duplicate operation names are a startup error (顶层 §2.1), not a
        # "package unavailable" case
        dispatch_module.register_operation(operation, package, method, request_model)
    return errors


def build_server(host: str, port: int, middle, *,
                 max_inflight: int = DEFAULT_MAX_INFLIGHT) -> ApiServer:
    return ApiServer((host, port), middle, max_inflight=max_inflight)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="virtuoso-bridge top layer (HTTP)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8126)
    parser.add_argument("--work-dir", default=None,
                        help="directory holding registry.json (assembly only)")
    parser.add_argument("--max-inflight", type=int, default=DEFAULT_MAX_INFLIGHT,
                        help="top-layer overall thread-pool size (provisional, "
                             f"default {DEFAULT_MAX_INFLIGHT})")
    args = parser.parse_args(argv)

    errors = register_packages()
    for operation, message in sorted(errors.items()):
        print(f"[api] package unavailable: {operation}: {message}")

    # process assembly: the only place that knows about the middle layer
    from transport.middle import BusinessServer

    middle = BusinessServer(args.work_dir)
    server = build_server(args.host, args.port, middle,
                          max_inflight=args.max_inflight)
    print(f"virtuoso-bridge API: http://{args.host}:{args.port}  "
          f"({len(dispatch_module.operations())} operations, "
          f"max_inflight={args.max_inflight})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        middle.close()


if __name__ == "__main__":
    main()
