"""Registration HTTP server (the registration page).

Stdlib-only ``ThreadingHTTPServer`` guiding a user step by step through the
six-step manual registration flow:

  1 申请        POST /api/register/apply
  2 本地校验    POST /api/register/<user>/validate
  3 探测        POST /api/register/<user>/probe
  4 部署        POST /api/register/<user>/deploy
  5 连通性      POST /api/register/<user>/verify   (also performs step 6)
  6 写注册表    (inside verify; the only durable write)

``POST /api/register`` remains as a one-shot steps 1-4 convenience.
State is kept in memory only; the single durable write is the step-6 commit.
"""

from __future__ import annotations

import argparse
import json
from importlib.resources import files
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from pydantic import ValidationError

from transport.register import RegistrationFlow, RegistrationRequest
from transport.registry import Registry, load_registry
from transport.runtime_paths import registry_path, set_working_dir

_PAGE = files("server").joinpath("registration_page.html").read_text(encoding="utf-8")


class RegistrationHandler(BaseHTTPRequestHandler):
    server_version = "vb-registration/0.2"

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, status: int, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8")) if raw else {}

    def _flow(self, user: str):
        with self.server.flow_lock:  # type: ignore[attr-defined]
            return self.server.flows.get(user)  # type: ignore[attr-defined]

    def _store(self, flow: RegistrationFlow, user: str) -> None:
        with self.server.flow_lock:  # type: ignore[attr-defined]
            self.server.flows[user] = flow  # type: ignore[attr-defined]

    def _state_payload(self, state) -> dict:
        payload = {
            "user": state.user,
            "stage": state.stage,
            "step": state.step,
            "token": state.token,
            "errors": state.errors,
            "warnings": state.warnings,
        }
        if state.setup_path:
            payload["setup_path"] = state.setup_path
        if state.report is not None:
            payload["report"] = {
                "command_ok": state.report.command_ok,
                "skill_ok": state.report.skill_ok,
                "token_ok": state.report.token_ok,
                "banner_hostname": state.report.banner_hostname,
                "expected_hostname": state.report.expected_hostname,
                "detail": state.report.detail,
                "warnings": state.report.warnings,
            }
        return payload

    # -- routing --------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/":
            self._send_html(200, _PAGE)
            return
        if path.startswith("/api/register/"):
            user = unquote(path[len("/api/register/"):].rstrip("/"))
            flow = self._flow(user)
            if flow is None or flow.state is None:
                self._send_json(404, {"error": "no registration in progress", "user": user})
                return
            self._send_json(200, self._state_payload(flow.state))
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/register/apply":
            self._handle_apply()
            return
        if path == "/api/register":
            self._handle_apply(granular=False)
            return
        if path.startswith("/api/register/"):
            rest = path[len("/api/register/"):].rstrip("/")
            for action in ("validate", "probe", "deploy", "verify"):
                if rest.endswith("/" + action):
                    user = unquote(rest[: -(len(action) + 1)])
                    self._handle_step(user, action)
                    return
        self._send_json(404, {"error": "not found"})

    def _parse_request(self):
        try:
            raw = self._read_json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json(400, {"error": "invalid JSON body"})
            return None
        try:
            return RegistrationRequest(**raw)
        except ValidationError as exc:
            detail = [str(e) for e in exc.errors()]
            self._send_json(400, {"error": "invalid request", "detail": detail})
            return None

    def _handle_apply(self, granular: bool = True) -> None:
        request = self._parse_request()
        if request is None:
            return
        flow = RegistrationFlow(self.server.registry)  # type: ignore[attr-defined]
        state = flow.start(request) if granular else flow.apply(request)
        self._store(flow, request.user)
        self._send_json(200, self._state_payload(state))

    def _handle_step(self, user: str, action: str) -> None:
        flow = self._flow(user)
        if flow is None:
            self._send_json(404, {"error": "no registration in progress", "user": user})
            return
        state = getattr(flow, action)()
        self._send_json(200, self._state_payload(state))

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        print(f"[registration] {self.address_string()} - {format % args}")


class RegistrationServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, server_address, registry: Registry) -> None:
        super().__init__(server_address, RegistrationHandler)
        self.registry = registry
        self.flows: dict[str, RegistrationFlow] = {}
        self.flow_lock = threading.Lock()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Virtuoso Bridge registration page")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8124)
    parser.add_argument("--work-dir", default=None, help="local working directory holding registry.json")
    args = parser.parse_args(argv)

    set_working_dir(args.work_dir)
    registry = load_registry(registry_path())
    server = RegistrationServer((args.host, args.port), registry)
    print(f"registration page: http://{args.host}:{args.port}  (registry: {registry.path})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
