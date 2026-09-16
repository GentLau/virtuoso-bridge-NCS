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
from transport.register.reservation import ReservationTable
from transport.registry import Registry, UserEntry, load_registry
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
        if state.entry is not None:
            payload["entry"] = state.entry.model_dump()
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
        if path == "/api/users":
            self._send_json(200, {
                "users": [
                    {"user": name, "entry": entry.model_dump()}
                    for name, entry in self.server.registry.entries()
                ]
            })
            return
        if path.startswith("/api/user/"):
            user = unquote(path[len("/api/user/"):].rstrip("/"))
            entry = self.server.registry.get(user)
            if entry is None:
                self._send_json(404, {"error": "unknown user", "user": user})
            else:
                self._send_json(200, {"user": user, "entry": entry.model_dump()})
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

    def do_DELETE(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path.startswith("/api/user/"):
            user = unquote(path[len("/api/user/"):].rstrip("/"))
            self._handle_delete(user)
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path.startswith("/api/user/") and path.endswith("/update"):
            user = unquote(path[len("/api/user/"):-len("/update")])
            self._handle_update(user)
            return
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
        with self.server.flow_lock:  # type: ignore[attr-defined]
            previous = self.server.flows.get(request.user)  # type: ignore[attr-defined]
        if previous is not None:
            previous.cancel()
            self._store(previous, request.user)
        flow = RegistrationFlow(
            self.server.registry, self.server.reservations
        )  # type: ignore[attr-defined]
        state = flow.start(request) if granular else flow.apply(request)
        self._store(flow, request.user)
        self._send_json(200, self._state_payload(state))

    def _handle_delete(self, user: str) -> None:
        if self.server.registry.get(user) is None:
            self._send_json(404, {"error": "unknown user", "user": user})
            return
        flow = self._flow(user)
        if flow is not None:
            flow.cancel()
        self.server.reservations.release(user)
        self.server.registry.remove(user)
        with self.server.flow_lock:
            self.server.flows.pop(user, None)
        self._send_json(200, {"user": user, "removed": True})

    def _handle_update(self, user: str) -> None:
        entry = self.server.registry.get(user)
        if entry is None:
            self._send_json(404, {"error": "unknown user", "user": user})
            return
        try:
            fields = self._read_json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json(400, {"error": "invalid JSON body"})
            return
        if not isinstance(fields, dict):
            self._send_json(400, {"error": "update body must be an object"})
            return
        def deep_merge(base, patch):
            out = dict(base)
            for key, value in patch.items():
                if isinstance(value, dict) and isinstance(out.get(key), dict):
                    out[key] = deep_merge(out[key], value)
                else:
                    out[key] = value
            return out

        # Flat convenience names retained for the registration page and old
        # scripts; nested registry names remain the canonical transport.
        flat_map = {
            "root_default": ("root", "default"),
            "ssh_backend": ("ssh", "backend"),
            "ssh_control_master": ("ssh", "control_master"),
            "ssh_proxy": ("ssh", "default", "proxy"),
            "thread_pool_size": ("runtime", "thread_pool_size"),
            "channel_budget": ("runtime", "channel_budget"),
            "connect_timeout": ("runtime", "connect_timeout"),
            "log_level": ("cdslog", "log_level"),
            "log_max_bytes": ("cdslog", "log_max_bytes"),
            "daemon_python": ("roles", "daemon", "python"),
            "spectre_host": ("roles", "spectre", "host"),
            "spectre_bin": ("roles", "spectre", "bin"),
        }
        translated: dict = {}
        for key in list(fields):
            path = flat_map.get(key)
            if path is None:
                continue
            value = fields.pop(key)
            node = translated
            for part in path[:-1]:
                node = node.setdefault(part, {})
            node[path[-1]] = value
        fields = deep_merge(fields, translated)

        # ``GET /api/user/<user>`` returns a full entry, so the update endpoint
        # must accept that same shape back: ``token`` is read-only but valid
        # (a *changed* token is refused below) and ``registered_at`` is
        # server-managed, never user-writable.
        # spec 多用户与注册 §5: ssh.* / root.default / role.* / runtime.* /
        # cdslog.* / expected_* are the writable fields -- ``mode`` is fixed at
        # registration time.  ``token``/``registered_at`` are accepted so the
        # entry returned by GET can be posted back (read-only, validated).
        allowed = {"ssh", "root", "roles", "runtime", "cdslog",
                   "token", "registered_at"}
        unknown = set(fields) - allowed
        if unknown:
            self._send_json(
                400,
                {"error": "invalid update", "detail": f"unknown fields: {sorted(unknown)}"},
            )
            return

        if "token" in fields and fields.pop("token") != entry.token:
            self._send_json(400, {"error": "token is immutable; remove and re-register"})
            return
        fields.pop("registered_at", None)

        candidate_data = deep_merge(entry.model_dump(), fields)
        try:
            candidate = UserEntry.model_validate(candidate_data)
        except Exception as exc:  # noqa: BLE001
            self._send_json(400, {"error": "invalid update", "detail": str(exc)})
            return
        if candidate.token != entry.token:
            self._send_json(400, {"error": "token is immutable; remove and re-register"})
            return
        try:
            self.server.registry.register(user, candidate, overwrite=True)
        except Exception as exc:  # noqa: BLE001
            self._send_json(400, {"error": "invalid update", "detail": str(exc)})
            return
        self._send_json(200, {"user": user, "entry": candidate.model_dump()})

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
    request_queue_size = 64

    def __init__(self, server_address, registry: Registry) -> None:
        super().__init__(server_address, RegistrationHandler)
        self.registry = registry
        self.reservations = ReservationTable()
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
