"""Front-end-only testbench for the six-step registration page.

This module deliberately does not import the real registration flow or
registry. It serves the production HTML and emulates its HTTP contract entirely
in memory, so it never opens SSH connections, talks to Virtuoso, deploys files,
or writes registry.json.

Run with:

    python -m server.registration_mock_server --port 8125
"""

from __future__ import annotations

import argparse
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from typing import Any
from urllib.parse import unquote, urlparse


_PAGE = files("server").joinpath("registration_page.html").read_text(encoding="utf-8")
_PANEL = files("server").joinpath("registration_mock_panel.html").read_text(encoding="utf-8")

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


@dataclass
class MockRegistrationState:
    """One in-memory mock registration session."""

    user: str
    token: str
    scenario: str
    mode: str = "local"
    stage: str = "applied"
    step: int = 1
    setup_path: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    report: dict[str, Any] | None = None
    attempts: dict[str, int] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "user": self.user,
            "stage": self.stage,
            "step": self.step,
            "token": self.token,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }
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
        mode = "local" if request.get("local") or not request.get("host") else "remote"
        flow = MockRegistrationState(
            user=user,
            token=token,
            scenario=self.mock_server.scenario,
            mode=mode,
        )
        with self.mock_server.flow_lock:
            self.mock_server.flows[user] = flow
        return flow

    def _flow(self, user: str) -> MockRegistrationState | None:
        with self.mock_server.flow_lock:
            return self.mock_server.flows.get(user)

    def _setup_path(self, user: str) -> str:
        return f"/mock/virtuoso-bridge/{user}/setup/virtuoso_setup.il"

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
            if flow.stage != "applied":
                return 409, {"error": f"validate requires applied stage, got {flow.stage}"}
            flow.step = 2
            if scenario == "validate_fail":
                flow.stage = "failed"
                flow.errors = [f"user '{flow.user}' is already registered"]
            else:
                flow.stage = "validated"
                flow.errors = []

        elif action == "probe":
            if flow.stage != "validated":
                return 409, {"error": f"probe requires validated stage, got {flow.stage}"}
            flow.step = 3
            if scenario == "probe_fail":
                flow.stage = "failed"
                flow.errors = ["ssh unreachable: mock-eda-host"]
            else:
                flow.stage = "probed"
                flow.errors = []

        elif action == "deploy":
            if flow.stage != "probed":
                return 409, {"error": f"deploy requires probed stage, got {flow.stage}"}
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
                return 409, {"error": f"verify requires deployed stage, got {flow.stage}"}
            flow.step = 5
            attempt = flow.mark_attempt(action)
            if scenario == "verify_fail_once" and attempt == 1:
                flow.stage = "failed"
                flow.report = _failed_report()
                flow.errors = [flow.report["detail"]]
                return 200, flow.payload()

            flow.report = _success_report()
            flow.errors = []
            if scenario == "commit_fail":
                flow.stage = "failed"
                flow.step = 6
                flow.errors = ["mock registry is read-only"]
            else:
                flow.stage = "committed"
                flow.step = 6
                if scenario == "warning_success":
                    warning = "daemon banner host 'mock-compute' differs from expected 'mock-gui'"
                    flow.warnings = [warning]
                    flow.report = _success_report(warnings=[warning])

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
            flow = MockRegistrationState(
                user=user,
                token=f"mock-preview-token-{sequence:02d}",
                scenario=self.mock_server.scenario,
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
        if path.startswith("/api/register/"):
            self._delay()
            user = unquote(path[len("/api/register/"):].rstrip("/"))
            flow = self._flow(user)
            if flow is None:
                self._send_json(404, {"error": "no registration in progress", "user": user})
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

        if path in {"/api/register/apply", "/api/register"}:
            self._delay()
            try:
                flow = self._new_flow(body)
            except ValueError as exc:
                self._send_json(400, {"error": "invalid request", "detail": [str(exc)]})
                return
            if path == "/api/register":
                status = 200
                payload = flow.payload()
                for action in ("validate", "probe", "deploy"):
                    status, payload = self._transition(flow, action)
                    if status != 200 or payload.get("stage") == "failed":
                        break
                self._send_json(status, payload)
            else:
                self._send_json(200, flow.payload())
            return

        if path.startswith("/api/register/"):
            self._delay()
            rest = path[len("/api/register/"):].rstrip("/")
            for action in ("validate", "probe", "deploy", "verify"):
                suffix = "/" + action
                if rest.endswith(suffix):
                    user = unquote(rest[:-len(suffix)])
                    flow = self._flow(user)
                    if flow is None:
                        self._send_json(404, {"error": "no registration in progress", "user": user})
                        return
                    status, payload = self._transition(flow, action)
                    self._send_json(status, payload)
                    return

        self._send_json(404, {"error": "not found"})

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
