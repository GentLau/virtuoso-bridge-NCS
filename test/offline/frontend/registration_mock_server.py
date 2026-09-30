"""Front-end-only testbench for the six-step registration page.

This module deliberately does not import the real registration flow or
registry. It serves the production HTML and emulates its HTTP contract entirely
in memory, so it never opens SSH connections, talks to Virtuoso, deploys files,
or writes registry.json.

Run with:

    .venv/Scripts/python.exe test/offline/frontend/registration_mock_server.py --port 8125
"""

from __future__ import annotations

import argparse
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_PAGE = (_PROJECT_ROOT / "src" / "register" / "registration_page.html").read_text(encoding="utf-8")
_PANEL = (Path(__file__).resolve().parent / "registration_mock_panel.html").read_text(encoding="utf-8")

SCENARIOS: dict[str, str] = {
    "happy": "全流程成功",
    "warning_success": "成功，但返回主机告警",
    "validate_fail": "第 2 步本地校验失败",
    "probe_fail": "第 3 步环境探测失败",
    "deploy_fail": "第 4 步部署失败",
    "verify_fail_once": "第 5 步首次失败，重试成功",
    "commit_fail": "第 6 步注册表写入失败",
    "session_lost": "第 2 步返回会话失效（404）",
    "transient_500": "第 3 步首次返回临时错误（500）",
}

PREVIEW_STATES = {
    "form",
    "applied",
    "validated",
    "probed",
    "deployed",
    "committed",
    "failed_validate",
    "failed_probe",
    "failed_deploy",
    "failed_verify",
    "failed_commit",
}


def _testbench_page() -> str:
    """Inject the mock controller without changing the production page asset."""
    head, body = _PANEL.split("<!-- MOCK_BODY -->", 1)
    page = _PAGE.replace("<title>", "<title>[Mock TB] ", 1)
    page = page.replace("</head>", head + "\n</head>", 1)
    return page.replace("</body>", body + "\n</body>", 1)


_MOCK_PAGE = _testbench_page()


def _success_report(*, warnings: list[str] | None = None) -> dict[str, Any]:
    return {
        "command_ok": True,
        "skill_ok": True,
        "token_ok": True,
        "banner_hostname": "mock-daemon-01",
        "expected_hostname": "mock-daemon-01",
        "detail": "mock command and SKILL checks passed",
        "warnings": list(warnings or []),
    }


def _failed_report(*, token_ok: bool = True) -> dict[str, Any]:
    return {
        "command_ok": True,
        "skill_ok": False,
        "token_ok": token_ok,
        "banner_hostname": "mock-daemon-01",
        "expected_hostname": "mock-daemon-01",
        "detail": "skill=ExecutionStatus.ERROR:['Connection refused by mock daemon']",
        "warnings": [],
    }


def _normalize_mock_request(request: dict[str, Any]) -> dict[str, Any]:
    """Flatten the production page payload for the mock-only view fields."""
    out = dict(request)
    # 加强凭据只在 apply 时校验：不落盘、不回显（spec r22），mock 同样不保留。
    out.pop("enhanced_token", None)
    mode = request.get("mode")
    if isinstance(mode, dict):
        out["mode"] = mode.get("default")

    def nested(mapping: Any, key: str) -> Any:
        return mapping.get(key) if isinstance(mapping, dict) else None

    ssh_default = nested(nested(request, "ssh"), "default") or {}
    for source, target in (
        ("host", "ssh_default_host"),
        ("user", "ssh_default_user"),
        ("jump_host", "jump_host"),
        ("jump_user", "jump_user"),
        ("proxy", "ssh_proxy"),
    ):
        value = nested(ssh_default, source)
        if value is not None:
            out[target] = value

    root = nested(request, "root") or {}
    if nested(root, "default") is not None:
        out["scratch_root"] = nested(root, "default")

    roles = request.get("roles") or {}
    gui = nested(roles, "gui") or {}
    daemon = nested(roles, "daemon") or {}
    command = nested(roles, "command") or {}
    file_role = nested(roles, "file") or {}
    spectre = nested(roles, "spectre") or {}
    for source, target in (
        ("host", "daemon_host"),
        ("user", "daemon_user"),
        ("daemon_port", "daemon_port"),
        ("local_port", "local_port"),
        ("python", "remote_python"),
        ("expected_hostname", "daemon_endpoint_hostname"),
        ("expected_user", "daemon_expected_user"),
        ("expected_fingerprint", "ssh_host_key_fingerprint"),
    ):
        value = nested(daemon, source)
        if value is not None:
            out[target] = value
    for source, target in (("host", "gui_host"), ("user", "gui_user")):
        value = nested(gui, source)
        if value is not None:
            out[target] = value
    for source, target in (("host", "command_host"), ("user", "command_user")):
        value = nested(command, source)
        if value is not None:
            out[target] = value
    for source, target in (("host", "file_host"), ("root", "file_root")):
        value = nested(file_role, source)
        if value is not None:
            out[target] = value
    for source, target in (
        ("host", "spectre_host"),
        ("bin", "spectre_bin"),
        ("root", "spectre_root"),
    ):
        value = nested(spectre, source)
        if value is not None:
            out[target] = value
    return out


@dataclass
class MockRegistrationState:
    """One in-memory mock registration session."""

    user: str
    token: str
    scenario: str
    mode: str = "local"
    request: dict[str, Any] = field(default_factory=dict)
    stage: str = "applied"
    step: int = 1
    setup_path: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    report: dict[str, Any] | None = None
    attempts: dict[str, int] = field(default_factory=dict)

    def resolved_payload(self) -> dict[str, Any]:
        request = self.request
        remote = self.mode == "remote"
        default_host = str(request.get("ssh_default_host") or request.get("host") or
                           ("mock-eda-host" if remote else "localhost"))
        default_user = str(request.get("ssh_default_user") or request.get("ssh_user") or
                           ("designer1" if remote else "local-user"))
        gui_host = str(request.get("gui_host") or default_host)
        gui_user = str(request.get("gui_user") or default_user)
        command_host = str(request.get("command_host") or request.get("host") or default_host)
        command_user = str(request.get("command_user") or request.get("ssh_user") or default_user)
        daemon_host = str(request.get("daemon_host") or default_host)
        daemon_user = str(request.get("daemon_user") or default_user)
        file_host = str(request.get("file_host") or default_host)
        spectre_host = request.get("spectre_host") or default_host
        daemon_port = int(request.get("daemon_port") or (65128 if remote else 65432))
        local_port = int(request.get("local_port") or daemon_port)
        scratch = str(request.get("scratch_root") or (
            f"/home/designer1/.virtuoso-bridge/{self.user}" if remote
            else f"C:/mock/virtuoso-bridge/{self.user}"
        ))
        # 5-role route shape (mock-only panel view)
        return {
            "mode": self.mode,
            "ssh_default_host": default_host,
            "ssh_default_user": default_user,
            "gui_host": gui_host,
            "gui_user": gui_user,
            "command_host": command_host,
            "command_user": command_user,
            "daemon_host": daemon_host,
            "daemon_user": daemon_user,
            "daemon_port": daemon_port,
            "local_port": local_port,
            "file_host": file_host,
            "deploy_root": scratch,
            "file_root": f"{scratch.rstrip('/')}/file",
            "remote_python": request.get("remote_python") or ("python3.11" if remote else "python3.12"),
            "ssh_host_key_fingerprint": (
                request.get("ssh_host_key_fingerprint")
                or ("SHA256:MOCK-FINGERPRINT-7vQp2K" if remote else None)
            ),
            "daemon_endpoint_hostname": (
                request.get("daemon_endpoint_hostname")
                or ("mock-compute-01" if remote else "mock-localhost")
            ),
            "jump_host": request.get("jump_host"),
            "jump_user": request.get("jump_user"),
            "spectre_host": spectre_host,
            "spectre_bin": request.get("spectre_bin"),
            "ssh_backend": request.get("ssh_backend") or "openssh",
            "ssh_max_sessions": int(request.get("ssh_max_sessions") or 10),
            "ssh_control_master": request.get("ssh_control_master") or "auto",
            "thread_pool_size": int(request.get("thread_pool_size") or 32),
            "channel_budget": int(request.get("channel_budget") or 10),
            "connect_timeout": float(request.get("connect_timeout") or 15.0),
            "log_level": request.get("log_level") or "all",
            "log_max_bytes": int(request.get("log_max_bytes") or 65536),
        }

    def entry_payload(self) -> dict[str, Any]:
        resolved = self.resolved_payload()
        root = str(resolved["deploy_root"]).rstrip("/")
        remote = self.mode == "remote"
        global_host = resolved["ssh_default_host"] if remote else None
        global_user = resolved["ssh_default_user"] if remote else None
        gui_host = resolved["gui_host"] if remote else None
        gui_user = resolved["gui_user"] if remote else None
        command_host = resolved["command_host"] if remote else None
        command_user = resolved["command_user"] if remote else None

        def role(name: str, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
            data: dict[str, Any] = {
                "root": f"{root}/{name}",
            }
            if extra:
                data.update(extra)
            return data

        return {
            "mode": {"default": resolved["mode"]},
            "ssh": {
                "default": {
                    "host": global_host,
                    "user": global_user,
                    "jump_host": resolved["jump_host"],
                    "jump_user": resolved["jump_user"],
                    "proxy": self.request.get("ssh_proxy"),
                },
                "backend": resolved["ssh_backend"],
                "control_master": resolved["ssh_control_master"],
                "tool_override": {},
            },
            "root": {"default": root},
            "roles": {
                "gui": role("gui", extra={"host": gui_host, "user": gui_user}),
                "daemon": role("daemon", extra={
                    "host": resolved["daemon_host"] if remote else None,
                    "user": resolved["daemon_user"] if remote else None,
                    "daemon_port": resolved["daemon_port"],
                    "local_port": resolved["local_port"],
                    "python": resolved["remote_python"],
                    "expected_hostname": resolved["daemon_endpoint_hostname"],
                    "expected_user": resolved["daemon_user"],
                }),
                "command": role("command", extra={"host": command_host, "user": command_user}),
                "file": role("file", extra={
                    "host": resolved["file_host"] if remote else None,
                    "root": resolved["file_root"],
                }),
                "spectre": role("spectre", extra={
                    "host": resolved["spectre_host"] if remote else None,
                    "bin": resolved["spectre_bin"],
                }),
            },
            "runtime": {
                "thread_pool_size": resolved["thread_pool_size"],
                "channel_budget": resolved["channel_budget"],
                "connect_timeout": resolved["connect_timeout"],
            },
            "cdslog": {
                "log_level": resolved["log_level"],
                "log_max_bytes": resolved["log_max_bytes"],
            },
            "registered_at": None,
        }

    def payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "user": self.user,
            "stage": self.stage,
            "step": self.step,
            "token": self.token,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "requested": dict(self.request),
        }
        probe_completed = self.step > 3 or (self.step == 3 and self.stage != "failed")
        if probe_completed:
            payload["entry"] = self.entry_payload()
        if self.setup_path:
            payload["setup_path"] = self.setup_path
        if self.report is not None:
            payload["report"] = dict(self.report)
        return payload

    def mark_attempt(self, action: str) -> int:
        count = self.attempts.get(action, 0) + 1
        self.attempts[action] = count
        return count


class RegistrationMockServer(ThreadingHTTPServer):
    """Threaded in-memory server implementing the registration page contract."""

    daemon_threads = True

    def __init__(
        self,
        server_address,
        *,
        scenario: str = "happy",
        delay_ms: int = 350,
    ) -> None:
        if scenario not in SCENARIOS:
            raise ValueError(f"unknown mock scenario: {scenario}")
        super().__init__(server_address, RegistrationMockHandler)
        self.scenario = scenario
        self.delay_ms = max(0, min(int(delay_ms), 5000))
        self.flows: dict[str, MockRegistrationState] = {}
        self.flow_lock = threading.RLock()
        self.preview_counter = 0
        self.mock_registry: dict[str, dict[str, Any]] = {}
        self.config: dict[str, Any] = {"business_thread_pool_size": 64}
        self.process_status = "ready"
        self.reset_registry()

    @staticmethod
    def _demo_entry() -> dict[str, Any]:
        return {
            "mode": {"default": "remote"},
            "ssh": {
                "default": {
                    "host": "mock-server-a",
                    "user": "designer1",
                    "jump_host": None,
                    "jump_user": None,
                    "proxy": None,
                    "key_dir": "~/.ssh",
                    "key": "id_ed25519",
                },
                "backend": "paramiko",
                "control_master": "auto",
                "tool_override": {},
            },
            "root": {"default": None},
            "roles": {
                "gui": {
                    "mode": None, "host": None, "user": None,
                    "jump_host": None, "jump_user": None, "proxy": None,
                    "key_dir": None, "key": None,
                    "root": "/home/designer1/.virtuoso-bridge/demo/gui",
                    "expected_fingerprint": "SHA256:mock-gui",
                    "max_sessions": 10, "display": ":11",
                },
                "daemon": {
                    "mode": None, "host": None, "user": None,
                    "jump_host": None, "jump_user": None, "proxy": None,
                    "key_dir": None, "key": None,
                    "root": "/home/designer1/.virtuoso-bridge/demo/daemon",
                    "expected_fingerprint": "SHA256:mock-daemon",
                    "max_sessions": 10, "daemon_port": 65081,
                    "local_port": 65082, "python": "/usr/bin/python3",
                    "expected_hostname": "mock-server-a",
                    "expected_user": "designer1",
                },
                "command": {
                    "mode": None, "host": None, "user": None,
                    "jump_host": None, "jump_user": None, "proxy": None,
                    "key_dir": None, "key": None,
                    "root": "/home/designer1/.virtuoso-bridge/demo/command",
                    "expected_fingerprint": "SHA256:mock-command",
                    "max_sessions": 10,
                    "calibre": {"bin": "/opt/eda/calibre/bin/calibre"},
                },
                "file": {
                    "mode": None, "host": None, "user": None,
                    "jump_host": None, "jump_user": None, "proxy": None,
                    "key_dir": None, "key": None,
                    "root": "/home/designer1/.virtuoso-bridge/demo/file",
                    "expected_fingerprint": "SHA256:mock-file",
                    "max_sessions": 10,
                },
                "spectre": {
                    "mode": None, "host": None, "user": None,
                    "jump_host": None, "jump_user": None, "proxy": None,
                    "key_dir": None, "key": None,
                    "root": "/home/designer1/.virtuoso-bridge/demo/spectre",
                    "expected_fingerprint": None,
                    "max_sessions": 10,
                    "bin": "/opt/cadence/spectre/bin/spectre",
                },
            },
            "runtime": {"thread_pool_size": 32, "channel_budget": 10, "connect_timeout": 15.0},
            "cdslog": {"log_level": "all", "log_max_bytes": 65536},
            "registered_at": 1780000000,
        }

    def reset_registry(self) -> None:
        with self.flow_lock:
            self.mock_registry = {"demo": self._demo_entry()}
            self.config = {"business_thread_pool_size": 64}
            self.process_status = "ready"

    def config_payload(self) -> dict[str, Any]:
        with self.flow_lock:
            return {
                "scenario": self.scenario,
                "scenario_label": SCENARIOS[self.scenario],
                "delay_ms": self.delay_ms,
                "active_sessions": len(self.flows),
                "safe": True,
            }

    def reset(self) -> None:
        with self.flow_lock:
            self.flows.clear()
        self.reset_registry()


class RegistrationMockHandler(BaseHTTPRequestHandler):
    """Serve the production UI and emulate all registration endpoints."""

    server_version = "vb-registration-mock/1.0"

    @property
    def mock_server(self) -> RegistrationMockServer:
        return self.server  # type: ignore[return-value]

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        if not raw:
            return {}
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("JSON body must be an object")
        return value

    def _delay(self) -> None:
        delay = self.mock_server.delay_ms
        if delay:
            time.sleep(delay / 1000.0)

    def _new_flow(self, request: dict[str, Any]) -> MockRegistrationState:
        user = str(request.get("user") or "").strip()
        if not user:
            raise ValueError("user is required")
        token = str(request.get("token") or "").strip() or f"mock-{uuid.uuid4().hex[:16]}"
        normalized = _normalize_mock_request(request)
        mode_value = normalized.get("mode")
        if isinstance(mode_value, dict):
            mode_value = mode_value.get("default")
        mode = str(mode_value or "").strip()
        if mode not in ("local", "remote"):
            raise ValueError("mode is required and must be local or remote")
        with self.mock_server.flow_lock:
            previous = self.mock_server.flows.get(user)
            if previous is not None and previous.stage != "cancelled":
                raise ValueError("step order violation: registration already in progress")
            self.mock_server.flows.pop(user, None)
        flow = MockRegistrationState(
            user=user,
            token=token,
            scenario=self.mock_server.scenario,
            mode=mode,
            request=normalized,
        )
        with self.mock_server.flow_lock:
            self.mock_server.flows[user] = flow
        return flow

    def _flow(self, user: str) -> MockRegistrationState | None:
        with self.mock_server.flow_lock:
            return self.mock_server.flows.get(user)

    def _setup_path(self, user: str) -> str:
        return f"/mock/virtuoso-bridge/{user}/setup/virtuoso_setup.il"

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization", "")
        token = header.removeprefix("Bearer ").strip()
        return token in ("mock-admin", "demo-token")

    @staticmethod
    def _merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        output = dict(base)
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(output.get(key), dict):
                output[key] = RegistrationMockHandler._merge(output[key], value)
            else:
                output[key] = value
        return output

    def _entry_payload(self, user: str) -> dict[str, Any] | None:
        with self.mock_server.flow_lock:
            entry = self.mock_server.mock_registry.get(user)
            return None if entry is None else json.loads(json.dumps(entry))

    def _system_status(self) -> dict[str, Any]:
        return {
            "status": self.mock_server.process_status,
            "pid": 4242,
            "port": self.server.server_address[1],
            "work_dir": "/mock/work-dir",
            "startup_args": ["--host", "127.0.0.1", "--port", str(self.server.server_address[1])],
        }

    def _transition(
        self,
        flow: MockRegistrationState,
        action: str,
    ) -> tuple[int, dict[str, Any]]:
        scenario = flow.scenario

        if scenario == "session_lost" and action == "validate":
            with self.mock_server.flow_lock:
                self.mock_server.flows.pop(flow.user, None)
            return 404, {"error": "no registration in progress", "user": flow.user}

        if scenario == "transient_500" and action == "probe" and flow.mark_attempt(action) == 1:
            return 500, {
                "error": "mock upstream temporarily unavailable",
                "detail": ["这是 TB 注入的一次性 500；会话仍停留在第 2 步，可查询后继续。"],
            }

        if action == "validate":
            retrying = flow.stage == "failed" and flow.step == 2
            if flow.stage != "applied" and not retrying:
                return 400, {"error": f"validate requires applied stage, got {flow.stage}"}
            flow.step = 2
            if scenario == "validate_fail":
                flow.stage = "failed"
                flow.errors = [f"user '{flow.user}' is already registered"]
            else:
                flow.stage = "validated"
                flow.errors = []

        elif action == "probe":
            retrying = flow.stage == "failed" and flow.step == 3
            if flow.stage != "validated" and not retrying:
                return 400, {"error": f"probe requires validated stage, got {flow.stage}"}
            flow.step = 3
            if scenario == "probe_fail":
                flow.stage = "failed"
                flow.errors = ["ssh unreachable: mock-eda-host"]
            else:
                flow.stage = "probed"
                flow.errors = []

        elif action == "deploy":
            retrying = flow.stage == "failed" and flow.step == 4
            if flow.stage != "probed" and not retrying:
                return 400, {"error": f"deploy requires probed stage, got {flow.stage}"}
            flow.step = 4
            if scenario == "deploy_fail":
                flow.stage = "failed"
                flow.errors = ["deploy failed: mock upload rejected: permission denied"]
            else:
                flow.stage = "deployed"
                flow.setup_path = self._setup_path(flow.user)
                flow.errors = []

        elif action == "verify":
            retrying = flow.stage == "failed" and flow.step == 5
            if flow.stage != "deployed" and not retrying:
                return 400, {"error": f"verify requires deployed stage, got {flow.stage}"}
            flow.step = 5
            attempt = flow.mark_attempt(action)
            if scenario == "verify_fail_once" and attempt == 1:
                flow.stage = "failed"
                flow.report = _failed_report()
                flow.errors = [flow.report["detail"]]
                return 200, flow.payload()

            flow.report = _success_report()
            flow.errors = []
            flow.stage = "verified"
            if scenario == "warning_success":
                warning = "daemon banner host 'mock-compute' differs from expected 'mock-gui'"
                flow.warnings = [warning]
                flow.report = _success_report(warnings=[warning])

        elif action == "commit":
            retrying = flow.stage == "failed" and flow.step == 6
            if flow.stage != "verified" and not retrying:
                return 400, {"error": f"commit requires verified stage, got {flow.stage}"}
            flow.step = 6
            if scenario == "commit_fail":
                flow.stage = "failed"
                flow.errors = ["mock registry is read-only"]
            else:
                flow.stage = "committed"
                flow.errors = []

        elif action == "cancel":
            if flow.stage == "cancelled":
                return 200, flow.payload()
            if flow.stage == "committed":
                return 400, {
                    "error": f"cancel requires a non-committed stage, got {flow.stage}"
                }
            flow.stage = "cancelled"
            flow.errors = []

        else:
            return 404, {"error": "unknown registration action"}

        return 200, flow.payload()

    def _seed(self, preview: str) -> dict[str, Any]:
        if preview not in PREVIEW_STATES:
            raise ValueError(f"unknown preview state: {preview}")
        with self.mock_server.flow_lock:
            self.mock_server.flows.clear()
            if preview == "form":
                return {"state": preview, "user": None}
            self.mock_server.preview_counter += 1
            sequence = self.mock_server.preview_counter
            user = f"mock-preview-{sequence:02d}"
            request = {
                "user": user,
                "host": "mock-eda-host",
                "ssh_user": "designer1",
                "daemon_host": "mock-compute-01",
                "daemon_user": "designer1",
                "scratch_root": "/home/designer1/.virtuoso-bridge",
                "ssh_backend": "openssh",
                "thread_pool_size": 32,
                "channel_budget": 10,
                "connect_timeout": 15.0,
                "log_level": "all",
                "log_max_bytes": 65536,
            }
            flow = MockRegistrationState(
                user=user,
                token=f"mock-preview-token-{sequence:02d}",
                scenario=self.mock_server.scenario,
                mode="remote",
                request=request,
            )
            stage_map = {
                "applied": ("applied", 1),
                "validated": ("validated", 2),
                "probed": ("probed", 3),
                "deployed": ("deployed", 4),
                "committed": ("committed", 6),
                "failed_validate": ("failed", 2),
                "failed_probe": ("failed", 3),
                "failed_deploy": ("failed", 4),
                "failed_verify": ("failed", 5),
                "failed_commit": ("failed", 6),
            }
            flow.stage, flow.step = stage_map[preview]
            if flow.step >= 4:
                flow.setup_path = self._setup_path(user)
            if preview == "committed":
                flow.report = _success_report()
            elif preview == "failed_validate":
                flow.errors = [f"user '{user}' is already registered"]
            elif preview == "failed_probe":
                flow.errors = ["ssh unreachable: mock-eda-host"]
            elif preview == "failed_deploy":
                flow.errors = ["deploy failed: mock upload rejected: permission denied"]
            elif preview == "failed_verify":
                flow.report = _failed_report()
                flow.errors = [flow.report["detail"]]
            elif preview == "failed_commit":
                flow.report = _success_report()
                flow.errors = ["mock registry is read-only"]
            self.mock_server.flows[user] = flow
            return {"state": preview, "user": user, "payload": flow.payload()}

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/":
            self._send_html(_MOCK_PAGE)
            return
        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if path == "/__mock__/config":
            self._send_json(200, self.mock_server.config_payload())
            return
        if path == "/__mock__/health":
            self._send_json(200, {"ok": True, "safe": True})
            return
        if path == "/api/config":
            if not self._authorized():
                self._send_json(401, {"error": "unauthorized"})
            else:
                self._send_json(200, self.mock_server.config)
            return
        if path == "/api/process/status":
            if not self._authorized():
                self._send_json(401, {"error": "unauthorized"})
            else:
                self._send_json(200, self._system_status())
            return
        if path == "/api/users":
            if not self._authorized():
                self._send_json(401, {"error": "unauthorized"})
            else:
                with self.mock_server.flow_lock:
                    users = [
                        {"user": name, "entry": json.loads(json.dumps(entry))}
                        for name, entry in self.mock_server.mock_registry.items()
                    ]
                self._send_json(200, {"users": users})
            return
        if path.startswith("/api/user/"):
            if not self._authorized():
                self._send_json(401, {"error": "unauthorized"})
                return
            user = unquote(path[len("/api/user/"):].rstrip("/"))
            entry = self._entry_payload(user)
            if entry is None:
                self._send_json(404, {"error": "unknown user", "user": user})
            else:
                self._send_json(200, {"user": user, "entry": entry})
            return
        if path.startswith("/api/register/"):
            self._delay()
            user = unquote(path[len("/api/register/"):].rstrip("/"))
            flow = self._flow(user)
            if flow is None or flow.stage == "cancelled":
                self._send_json(404, {"error": "no registration in progress", "user": user})
            else:
                session_token = parse_qs(urlparse(self.path).query).get("token", [""])[0]
                if session_token != flow.token:
                    self._send_json(400, {"error": "invalid token"})
                else:
                    self._send_json(200, flow.payload())
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            body = self._read_json()
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            self._send_json(400, {"error": "invalid JSON body", "detail": [str(exc)]})
            return

        if path == "/__mock__/config":
            scenario = str(body.get("scenario", self.mock_server.scenario))
            if scenario not in SCENARIOS:
                self._send_json(400, {"error": f"unknown mock scenario: {scenario}"})
                return
            try:
                delay_ms = int(body.get("delay_ms", self.mock_server.delay_ms))
            except (TypeError, ValueError):
                self._send_json(400, {"error": "delay_ms must be an integer"})
                return
            with self.mock_server.flow_lock:
                self.mock_server.scenario = scenario
                self.mock_server.delay_ms = max(0, min(delay_ms, 5000))
                if body.get("reset", False):
                    self.mock_server.flows.clear()
            self._send_json(200, self.mock_server.config_payload())
            return

        if path == "/__mock__/reset":
            self.mock_server.reset()
            self._send_json(200, self.mock_server.config_payload())
            return

        if path == "/__mock__/seed":
            try:
                result = self._seed(str(body.get("state", "form")))
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
                return
            self._send_json(200, result)
            return

        if path.startswith("/api/user/") and path.endswith("/update"):
            if not self._authorized():
                self._send_json(401, {"error": "unauthorized"})
                return
            user = unquote(path[len("/api/user/"):-len("/update")])
            patch = dict(body)
            patch.pop("enhanced_token", None)
            with self.mock_server.flow_lock:
                current = self.mock_server.mock_registry.get(user)
                if current is None:
                    self._send_json(404, {"error": "unknown user", "user": user})
                    return
                self.mock_server.mock_registry[user] = self._merge(current, patch)
                updated = json.loads(json.dumps(self.mock_server.mock_registry[user]))
            self._send_json(200, {"user": user, "entry": updated})
            return

        if path in ("/api/process/reload", "/api/process/restart"):
            if not self._authorized():
                self._send_json(401, {"error": "unauthorized"})
                return
            if body.get("target", "business") != "business":
                self._send_json(400, {"error": "invalid target"})
                return
            with self.mock_server.flow_lock:
                self.mock_server.process_status = "ready"
            action = "restart" if path.endswith("/restart") else "reload"
            self._send_json(200, {"ok": True, "action": action, "status": self._system_status()})
            return

        if path == "/api/register":
            self._delay()
            action = body.get("action")
            user = body.get("user")
            if action == "apply":
                try:
                    flow = self._new_flow(body)
                except ValueError as exc:
                    if "step order violation" in str(exc):
                        self._send_json(400, {
                            "error": "step order violation",
                            "current_stage": "in-progress",
                            "expected": "no registration in progress",
                        })
                        return
                    self._send_json(400, {"error": "invalid request", "detail": [str(exc)]})
                    return
                self._send_json(200, flow.payload())
                return
            if action not in ("validate", "probe", "deploy", "verify", "commit", "cancel"):
                self._send_json(400, {"error": "invalid action", "action": action})
                return
            if set(body) - {"user", "action", "token"}:
                self._send_json(400, {
                    "error": "parameter changes require cancel and re-apply"
                })
                return
            if not isinstance(user, str) or not user:
                self._send_json(400, {"error": "invalid request: user is required"})
                return
            flow = self._flow(user)
            if flow is None:
                self._send_json(404, {"error": "no registration in progress", "user": user})
                return
            session_token = body.get("token")
            if not isinstance(session_token, str) or session_token != flow.token:
                self._send_json(400, {"error": "invalid token"})
                return
            try:
                with self.mock_server.flow_lock:
                    status, payload = self._transition(flow, action)
                self._send_json(status, payload)
                return
            except (AttributeError, ValueError) as exc:
                self._send_json(400, {"error": str(exc)})
                return

        self._send_json(404, {"error": "not found"})

    def do_PUT(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path != "/api/config":
            self._send_json(404, {"error": "not found"})
            return
        if not self._authorized():
            self._send_json(401, {"error": "unauthorized"})
            return
        try:
            body = self._read_json()
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            self._send_json(400, {"error": "invalid JSON body", "detail": [str(exc)]})
            return
        pool_size = body.get("business_thread_pool_size")
        if pool_size is not None and (isinstance(pool_size, bool) or not isinstance(pool_size, int) or pool_size < 1):
            self._send_json(400, {"error": "business_thread_pool_size must be a positive integer or null"})
            return
        with self.mock_server.flow_lock:
            self.mock_server.config.update(body)
            payload = dict(self.mock_server.config)
        self._send_json(200, payload)

    def do_DELETE(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if not path.startswith("/api/user/"):
            self._send_json(404, {"error": "not found"})
            return
        if not self._authorized():
            self._send_json(401, {"error": "unauthorized"})
            return
        user = unquote(path[len("/api/user/"):].rstrip("/"))
        with self.mock_server.flow_lock:
            removed = self.mock_server.mock_registry.pop(user, None)
        if removed is None:
            self._send_json(404, {"error": "unknown user", "user": user})
            return
        self._send_json(200, {
            "user": user,
            "removed": True,
            "credentials": [{
                "role": "daemon",
                "key_dir": "~/.ssh",
                "key": "id_ed25519",
                "fingerprint": "SHA256:mock-daemon",
                "still_used_by": [],
            }],
        })

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        print(f"[registration-mock] {self.address_string()} - {format % args}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Front-end-only mock testbench for the registration page"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8125)
    parser.add_argument("--scenario", choices=tuple(SCENARIOS), default="happy")
    parser.add_argument("--delay-ms", type=int, default=350)
    args = parser.parse_args(argv)

    server = RegistrationMockServer(
        (args.host, args.port),
        scenario=args.scenario,
        delay_ms=args.delay_ms,
    )
    print("=" * 68)
    print("Virtuoso Bridge registration UI — MOCK TESTBENCH")
    print("SAFE MODE: no SSH, no Virtuoso, no deployment, no registry write")
    print(f"page:     http://{args.host}:{args.port}/")
    print(f"scenario: {SCENARIOS[args.scenario]} ({args.scenario})")
    print(f"delay:    {server.delay_ms} ms per registration request")
    print("Press Ctrl+C to stop.")
    print("=" * 68)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()


__all__ = [
    "PREVIEW_STATES",
    "SCENARIOS",
    "MockRegistrationState",
    "RegistrationMockHandler",
    "RegistrationMockServer",
    "main",
]
