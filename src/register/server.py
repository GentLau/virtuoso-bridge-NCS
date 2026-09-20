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
import re
import tempfile
import time
import uuid
from datetime import datetime, timezone
from importlib.resources import files
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from pydantic import ValidationError

from register import RegistrationFlow, RegistrationRequest
from register.candidate import (
    fingerprint_conflicts_candidate,
    validate_entry_shape,
)
from register.reservation import ReservationTable
from common.registry import Registry, RegistryError, load_registry
from common.paths import (  # noqa: E402 - 进程级路径基座（common 层）
    init_work_dir,
    log_dir,
    registry_path,
    work_root,
)

_PAGE = files("register").joinpath("registration_page.html").read_text(encoding="utf-8")

#: POST /api/bug 报告条目中随附日志的有界上限
_BUG_LOG_TAIL_BYTES = 200_000
_BUG_LOG_TAIL_LINES = 500

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
                "POST /api/bug",
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
        if path == "/api/bug":
            self._handle_bug_report()
            return
        self._send_json(404, {"error": "not found"})

    _REGISTER_ACTIONS = (
        "apply", "validate", "probe", "deploy", "verify", "commit", "cancel",
    )
    _ACTION_REQUIRED_STAGE = {
        "validate": ("applied",),
        "probe": ("validated",),
        "deploy": ("probed",),
        "verify": ("deployed", "failed"),
        "commit": ("verified",),
    }
    _ACTION_STEP = {
        "validate": 2,
        "probe": 3,
        "deploy": 4,
        "verify": 5,
        "commit": 6,
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
        if action != "apply" and set(raw) - {"user", "action", "token"}:
            self._send_json(400, {
                "error": "parameter changes require cancel and re-apply",
            })
            return

        if action == "apply":
            payload = {key: value for key, value in raw.items()
                       if key not in ("action", "user")}
            try:
                request = RegistrationRequest(user=user, **payload)
            except ValidationError as exc:
                self._send_json(400, {"error": "invalid request",
                                      "detail": [str(e) for e in exc.errors()]})
                return
            # 检查“无同名进行中会话”与创建/登记必须是一个原子步骤，否则两个
            # 并发 apply 会各自看到空会话并互相覆盖（顶层补充 §3）。
            error_payload = None
            with self.server.flow_lock:
                previous = self.server.flows.get(user)
                current = getattr(previous.state, "stage", None) if previous else None
                if current == "committed":
                    error_payload = {"error": "user is already registered"}
                elif previous is not None and current != "cancelled":
                    error_payload = {
                        "error": "step order violation",
                        "current_stage": current,
                        "expected": "cancel",
                    }
                else:
                    if previous is not None:
                        previous.cancel()
                    flow = RegistrationFlow(
                        self.server.registry, self.server.reservations
                    )
                    state = flow.start(request)
                    self.server.flows[user] = flow
            if error_payload is not None:
                self._send_json(400, error_payload)
                return
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
        allowed = (
            current in expected
            or (current == "failed" and state.step == self._ACTION_STEP[action])
        )
        if not allowed:
            self._send_json(400, {
                "error": "step order violation",
                "current_stage": current,
                "expected": "deployed" if action == "verify" else expected[0],
            })
            return

        state = getattr(flow, action)()
        self._send_json(200, self._state_payload(state))

    # -- POST /api/bug（控制面 v22 §3） --------------------------------------
    @staticmethod
    def _mask_token(raw_text: str, token: str) -> tuple[str, bool]:
        """Return the raw body with the bearer token value masked.

        控制面 v22 要求“记录原始请求体”，但 token 是终生有效的凭据；原文
        落盘等于把用户凭据写进报告文件。除 token 值以外一个字符都不改。
        """
        if not token:
            return raw_text, False
        pattern = r'("token"\s*:\s*)"' + re.escape(token) + r'"'
        masked = re.sub(pattern, r'\1"***"', raw_text, count=1)
        return masked, masked != raw_text

    def _bug_status_summary(self) -> dict:
        with self.server.flow_lock:  # type: ignore[attr-defined]
            flows = list(self.server.flows.items())  # type: ignore[attr-defined]
        registrations = []
        for user, flow in flows:
            state = getattr(flow, "state", None)
            if state is None or state.stage == "cancelled":
                continue
            registrations.append({
                "user": user,
                "stage": state.stage,
                "step": state.step,
            })
        return {
            "users": len(self.server.registry.users()),  # type: ignore[attr-defined]
            "registrations_in_progress": registrations,
            "config": dict(self.server.config),  # type: ignore[attr-defined]
            "control_plane": {
                "pid": os.getpid(),
                "work_dir": str(work_root()),
            },
        }

    @staticmethod
    def _bug_recent_logs() -> list[dict]:
        """Bounded tail of the local operation/error logs in ``log/``."""
        entries: list[dict] = []
        try:
            candidates = sorted(log_dir().glob("*"))
        except OSError:
            return entries
        for path in candidates:
            if not path.is_file():
                continue
            try:
                size = path.stat().st_size
                with path.open("rb") as fh:
                    if size > _BUG_LOG_TAIL_BYTES:
                        fh.seek(-_BUG_LOG_TAIL_BYTES, os.SEEK_END)
                    data = fh.read()
            except OSError:
                continue
            text = data.decode("utf-8", errors="replace")
            lines = text.splitlines()
            truncated = size > _BUG_LOG_TAIL_BYTES or len(lines) > _BUG_LOG_TAIL_LINES
            if len(lines) > _BUG_LOG_TAIL_LINES:
                lines = lines[-_BUG_LOG_TAIL_LINES:]
            entries.append({
                "name": path.name,
                "size": size,
                "truncated": truncated,
                "tail": "\n".join(lines),
            })
        return entries

    def _handle_bug_report(self) -> None:
        """Record one bug report entry; invalid/missing token records nothing."""
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            length = 0
        raw_bytes = self.rfile.read(length) if length > 0 else b""
        raw_text = raw_bytes.decode("utf-8", errors="replace")

        token = ""
        try:
            parsed = json.loads(raw_text) if raw_text else None
        except (json.JSONDecodeError, UnicodeDecodeError):
            parsed = None
        if isinstance(parsed, dict) and isinstance(parsed.get("token"), str):
            token = parsed["token"]

        user = self.server.registry.user_of(token) if token else None  # type: ignore[attr-defined]
        if not user:
            # v22: 无 token / 无效 → 4xx，不记录（这里不落任何文件）
            self._send_json(400, {"error": "invalid token"})
            return

        now = datetime.now(timezone.utc)
        report_id = (
            f"bug-{now.strftime('%Y%m%dT%H%M%SZ')}-{user}-{uuid.uuid4().hex[:8]}"
        )
        raw_body, token_masked = self._mask_token(raw_text, token)
        entry = {
            "id": report_id,
            "received_at": now.isoformat(),
            "user": user,
            "remote_addr": self.client_address[0],
            "content_type": self.headers.get("Content-Type", ""),
            "raw_body": raw_body,
            "raw_body_bytes": len(raw_bytes),
            "token_masked": token_masked,
            "status": self._bug_status_summary(),
            "logs": self._bug_recent_logs(),
        }

        reports_dir = log_dir() / "bug_reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(reports_dir, 0o700)
        except OSError:
            pass
        path = reports_dir / f"{report_id}.json"
        fd, tmp = tempfile.mkstemp(dir=str(reports_dir), prefix="bug-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(entry, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            self._send_json(500, {"error": "failed to record bug report"})
            return
        self._send_json(200, {
            "ok": True,
            "id": report_id,
            "path": str(path.relative_to(work_root())),
        })

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
        # 多用户与注册 v31 / §5: 白名单字段为 ssh.* / root.default / role.* /
        # runtime.* / cdslog.* / expected_*；token、registered_at、未声明字段
        # 与扁平别名一律拒绝（扁平别名不属公共协议）。
        if "token" in fields:
            self._send_json(400, {"error": "token must not be provided in update body"})
            return
        allowed = {"ssh", "root", "roles", "runtime", "cdslog"}
        unknown = set(fields) - allowed
        if unknown:
            self._send_json(
                400,
                {"error": "invalid update", "detail": f"unknown fields: {sorted(unknown)}"},
            )
            return

        try:
            candidate = self.server.registry.update(
                user,
                fields,
                validator=lambda updated: (
                    validate_entry_shape(
                        updated, user, require_root_default_null=False
                    )
                    + fingerprint_conflicts_candidate(updated, user)
                ),
            )
        except KeyError:
            self._send_json(404, {"error": "unknown user", "user": user})
            return
        except (RegistryError, ValueError) as exc:
            self._send_json(400, {"error": "invalid update", "detail": str(exc)})
            return
        self._send_json(200, {"user": user, "entry": self._redacted(candidate)})

    def do_PUT(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/config":
            if not self._require_admin():
                return
            try:
                body = self._read_json()
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                self._send_json(400, {"error": "invalid JSON body"})
                return
            if not isinstance(body, dict):
                self._send_json(400, {"error": "invalid config body"})
                return
            unknown = set(body) - set(self.server.config)
            if unknown:
                self._send_json(400, {"error": "unknown config keys", "detail": sorted(unknown)})
                return
            candidate = dict(self.server.config)
            candidate.update(body)
            pool_size = candidate.get("business_thread_pool_size")
            if pool_size is not None and (
                isinstance(pool_size, bool)
                or not isinstance(pool_size, int)
                or pool_size < 1
            ):
                self._send_json(400, {
                    "error": "business_thread_pool_size must be a positive integer",
                })
                return
            # 先落盘成功、再替换内存快照：持久化失败时不得出现内外不一致。
            try:
                self.server.save_config(candidate)
            except OSError as exc:
                self._send_json(500, {
                    "error": "failed to persist config", "detail": str(exc),
                })
                return
            self.server.config = candidate
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

    def save_config(self, config: dict | None = None) -> None:
        """配置变更的手动写回：临时文件 + 原子替换，不频繁 IO。"""
        payload = self.config if config is None else config
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=str(self.config_path.parent),
            prefix="config-",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
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
