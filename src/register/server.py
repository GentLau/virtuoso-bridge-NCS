"""Registration and management HTTP server (the registration page).

Stdlib-only ``ThreadingHTTPServer`` guiding a user through the six-step manual
registration flow:

* ``POST /api/register`` with ``{user, action, ...}`` executes one action per
  request (``apply / validate / probe / deploy / verify / commit / cancel``);
* ``GET /api/register/<user>`` reads the in-memory session state.

The module owns both ``registry.json`` and the control-plane ``config.json``.
Registration states are kept in memory only.  The sixth action (``commit``) is
the single durable registry write; ``verify`` only observes and reports
connectivity.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import tempfile
from importlib.resources import files
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from pydantic import ValidationError

from register import RegistrationFlow, RegistrationRequest
from register.reservation import ReservationTable
from common.registry import Registry, UserEntry, load_registry
from common.paths import (  # noqa: E402 - 进程级路径基座（common 层）
    init_work_dir,
    registry_path,
)

_PAGE = files("register").joinpath("registration_page.html").read_text(encoding="utf-8")

# 内置单管理员 token 的 SHA-256 哈希写死在代码中；原文离线保管。
_ADMIN_TOKEN_HASH = "db84f807b2bc4af3c4aa7ee220862433438a3d1ee22be3705568a9e7a26b7771"


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
            payload["entry"] = self._redacted(state.entry)
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

    def _require_admin(self) -> bool:
        """单管理员 token 校验：只比对代码内 SHA-256 哈希，凭据不进日志。"""
        header = self.headers.get("Authorization", "")
        presented = header.removeprefix("Bearer ").strip() if header else ""
        digest = hashlib.sha256(presented.encode("utf-8")).hexdigest() if presented else ""
        ok = bool(presented) and hmac.compare_digest(digest, _ADMIN_TOKEN_HASH)
        if not ok:
            self._send_json(401, {"error": "unauthorized"})
            return False
        self.log_message("admin authorized")
        return True

    @staticmethod
    def _redacted(entry) -> dict:
        data = entry.model_dump()
        data.pop("token", None)
        return data

    # -- routing --------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/":
            self._send_html(200, _PAGE)
            return
        if path == "/health":
            self._send_json(200, {"status": "ok"})
            return
        if path == "/help":
            self._send_json(200, {"endpoints": [
                "GET /", "GET /health", "GET /help",
                "POST /api/register", "GET /api/register/<user>",
                "GET /api/users", "GET /api/user/<user>",
                "POST /api/user/<user>/update", "DELETE /api/user/<user>",
                "GET /api/config", "PUT /api/config",
            ]})
            return
        if path == "/api/config":
            if not self._require_admin():
                return
            self._send_json(200, self.server.config)
            return
        if path == "/api/users":
            if not self._require_admin():
                return
            self._send_json(200, {
                "users": [
                    {"user": name, "entry": self._redacted(entry)}
                    for name, entry in self.server.registry.entries()
                ]
            })
            return
        if path.startswith("/api/user/"):
            if not self._require_admin():
                return
            user = unquote(path[len("/api/user/"):].rstrip("/"))
            entry = self.server.registry.get(user)
            if entry is None:
                self._send_json(404, {"error": "unknown user", "user": user})
            else:
                self._send_json(200, {"user": user, "entry": self._redacted(entry)})
            return
        if path.startswith("/api/register/"):
            user = unquote(path[len("/api/register/"):].rstrip("/"))
            flow = self._flow(user)
            if flow is None or flow.state is None:
                self._send_json(404, {"error": "no registration in progress", "user": user})
                return
            if flow.state.stage == "cancelled":
                self._send_json(404, {"error": "no registration in progress", "user": user})
                return
            session_token = parse_qs(urlparse(self.path).query).get("token", [""])[0]
            if flow.state.token is not None and session_token != flow.state.token:
                self._send_json(400, {"error": "invalid token"})
                return
            self._send_json(200, self._state_payload(flow.state))
            return
        self._send_json(404, {"error": "not found"})

    def do_DELETE(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path.startswith("/api/user/"):
            if not self._require_admin():
                return
            user = unquote(path[len("/api/user/"):].rstrip("/"))
            self._handle_delete(user)
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path.startswith("/api/user/") and path.endswith("/update"):
            if not self._require_admin():
                return
            user = unquote(path[len("/api/user/"):-len("/update")])
            self._handle_update(user)
            return
        if path == "/api/register":
            self._handle_register_command()
            return
        self._send_json(404, {"error": "not found"})

    _REGISTER_ACTIONS = (
        "apply", "validate", "probe", "deploy", "verify", "commit", "cancel",
    )
    _TERMINAL_STAGES = ("cancelled", "failed", "committed")
    _ACTION_REQUIRED_STAGE = {
        "validate": ("applied",),
        "probe": ("validated",),
        "deploy": ("probed",),
        "verify": ("deployed", "failed"),
        "commit": ("verified",),
    }

    def _handle_register_command(self) -> None:
        """POST /api/register: `{user, action, token?, 参数}` (顶层补充 §3).

        顺序错误与 token 不匹配都返回 4xx、**不改变会话状态**。
        """
        try:
            raw = self._read_json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json(400, {"error": "invalid JSON body"})
            return
        if not isinstance(raw, dict):
            self._send_json(400, {"error": "request body must be an object"})
            return

        user = raw.get("user")
        action = raw.get("action")
        if not isinstance(user, str) or not user:
            self._send_json(400, {"error": "invalid request: user is required"})
            return
        if action not in self._REGISTER_ACTIONS:
            self._send_json(400, {"error": "invalid action", "action": action})
            return

        if action == "apply":
            with self.server.flow_lock:
                previous = self.server.flows.get(user)
            if (
                previous is not None
                and getattr(previous.state, "stage", None) not in self._TERMINAL_STAGES
            ):
                current = previous.state.stage if previous.state else None
                self._send_json(400, {
                    "error": "step order violation",
                    "current_stage": current,
                    "expected": "no registration in progress",
                })
                return
            if previous is not None:
                previous.cancel()
                with self.server.flow_lock:
                    self.server.flows.pop(user, None)
            payload = {key: value for key, value in raw.items()
                       if key not in ("action", "user")}
            try:
                request = RegistrationRequest(user=user, **payload)
            except ValidationError as exc:
                self._send_json(400, {"error": "invalid request",
                                      "detail": [str(e) for e in exc.errors()]})
                return
            flow = RegistrationFlow(self.server.registry, self.server.reservations)
            state = flow.start(request)
            self._store(flow, user)
            self._send_json(200, self._state_payload(state))
            return

        flow = self._flow(user)
        if flow is None or flow.state is None:
            self._send_json(404, {"error": "no registration in progress", "user": user})
            return
        state = flow.state
        session_token = raw.get("token")
        if not isinstance(session_token, str) or not session_token:
            self._send_json(400, {"error": "invalid token"})
            return
        if state.token is not None and session_token != state.token:
            self._send_json(400, {"error": "invalid token"})
            return

        if action == "cancel":
            if state.stage == "cancelled":
                self._send_json(200, self._state_payload(state))
                return
            if state.stage == "committed":
                self._send_json(400, {
                    "error": "step order violation",
                    "current_stage": state.stage,
                    "expected": "non-committed",
                })
                return
            state = flow.cancel()
            self._send_json(200, self._state_payload(state))
            return

        expected = self._ACTION_REQUIRED_STAGE[action]
        current = state.stage
        allowed = current in expected
        if action == "verify" and current == "failed":
            allowed = state.step == 5
        if not allowed:
            self._send_json(400, {
                "error": "step order violation",
                "current_stage": current,
                "expected": "deployed" if action == "verify" else expected[0],
            })
            return

        state = getattr(flow, action)()
        # v27: ordinary step failures discard the candidate immediately;
        # verify failures stay retryable in place per the HTTP action table.
        if state.stage == "failed" and action != "verify":
            with self.server.flow_lock:
                self.server.flows.pop(user, None)
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
                   "registered_at"}
        if "token" in fields:
            self._send_json(400, {"error": "token must not be provided in update body"})
            return
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
        self._send_json(200, {"user": user, "entry": self._redacted(candidate)})

    def do_PUT(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/config":
            if not self._require_admin():
                return
            body = self._read_json()
            if not isinstance(body, dict):
                self._send_json(400, {"error": "invalid config body"})
                return
            unknown = set(body) - set(self.server.config)
            if unknown:
                self._send_json(400, {"error": "unknown config keys", "detail": sorted(unknown)})
                return
            self.server.config.update(body)
            self.server.save_config()
            self._send_json(200, self.server.config)
            return
        self._send_json(404, {"error": "not found"})

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
        self.config_path = registry_path().parent / "config.json"
        self.config: dict = self.load_config()

    def load_config(self) -> dict:
        """启动时导入一次到内存快照；运行期不再读文件。"""
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"business_thread_pool_size": None}
        return {"business_thread_pool_size": data.get("business_thread_pool_size")}

    def save_config(self) -> None:
        """配置变更的手动写回：临时文件 + 原子替换，不频繁 IO。"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=str(self.config_path.parent),
            prefix="config-",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self.config, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            os.replace(tmp, self.config_path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Virtuoso Bridge registration page")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8124)
    parser.add_argument("--work-dir", default=None, help="local working directory holding registry.json")
    args = parser.parse_args(argv)

    init_work_dir(args.work_dir)
    from common.ssh import configure_command_log

    from common.paths import command_log_file

    configure_command_log(command_log_file())
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
