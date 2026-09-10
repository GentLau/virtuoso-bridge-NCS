"""Registration HTTP server (the future registration page).

Stdlib-only ``ThreadingHTTPServer`` guiding a user through the six-step manual
registration flow:

  POST /api/register             submit the application -> steps 2/3/4
  POST /api/register/<user>/verify   user has load()ed -> steps 5/6
  GET  /api/register/<user>           current in-progress state
  GET  /                                registration form page

Registration state is kept in memory only; the single durable write is the
step-6 registry commit performed by ``RegistrationFlow.verify()``.
"""

from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from pydantic import ValidationError

from transport.register import RegistrationFlow, RegistrationRequest
from transport.registry import Registry, load_registry
from transport.runtime_paths import registry_path, set_working_dir

_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>Virtuoso Bridge — 注册</title>
<style>
body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;max-width:760px;margin:40px auto;padding:0 16px;color:#222}
h1{font-size:22px}
label{display:block;margin:12px 0 4px;font-size:14px}
input,select{width:100%;box-sizing:border-box;padding:8px;font-size:14px}
.row{display:flex;gap:12px}
.row>div{flex:1}
button{margin:16px 0;padding:10px 18px;font-size:15px}
#out{white-space:pre-wrap;background:#f5f5f5;border:1px solid #ddd;padding:12px;margin-top:12px;font-size:13px}
pre{white-space:pre-wrap}
</style>
</head>
<body>
<h1>Virtuoso Bridge 用户注册</h1>
<p>六步流程：申请 → 本地校验 → 探测 → 部署 → 连通性测试 → 写入注册表。前五步任何一步失败都不会写入注册表。</p>
<form id="f">
<div class="row">
  <div><label>用户名（必填）</label><input name="user" required></div>
  <div><label>token（可选，缺省自动生成）</label><input name="token"></div>
</div>
<label>模式</label>
<select name="mode">
  <option value="auto">自动（无远程参数时按本地）</option>
  <option value="remote">remote</option>
  <option value="local">local</option>
</select>
<div class="row">
  <div><label>目标 SSH 主机（remote 必填）</label><input name="host"></div>
  <div><label>目标 SSH 用户</label><input name="ssh_user"></div>
</div>
<div class="row">
  <div><label>daemon 主机（缺省同 SSH 主机）</label><input name="daemon_host"></div>
  <div><label>daemon 用户（缺省同 SSH 用户）</label><input name="daemon_user"></div>
</div>
<div class="row">
  <div><label>daemon 端口（缺省自动分配）</label><input name="daemon_port" type="number"></div>
  <div><label>本地端口（仅 remote，缺省同 daemon 端口）</label><input name="local_port" type="number"></div>
</div>
<label>部署根 scratch root（缺省 ~/.virtuoso-bridge）</label>
<input name="scratch_root" placeholder="~/.virtuoso-bridge">
<div class="row">
  <div><label>跳板主机</label><input name="jump_host"></div>
  <div><label>跳板用户</label><input name="jump_user"></div>
</div>
<button type="submit">第一步：提交申请（含 2 本地校验 / 3 探测 / 4 部署）</button>
</form>
<div id="out"></div>
<script>
const out = document.getElementById('out');
document.getElementById('f').addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const payload = {};
  for (const [k, v] of fd.entries()) if (v !== '') payload[k] = v;
  for (const k of ['daemon_port','local_port']) if (payload[k] !== undefined) payload[k] = Number(payload[k]);
  payload.local = payload.mode === 'local';
  delete payload.mode;
  out.textContent = '正在处理……';
  try {
    const res = await fetch('/api/register', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
    const data = await res.json();
    render(data);
  } catch (err) { out.textContent = '请求失败: ' + err; }
});
async function verify(user) {
  out.textContent = '正在做第五步连通性测试……';
  try {
    const res = await fetch('/api/register/' + encodeURIComponent(user) + '/verify', {method:'POST'});
    render(await res.json());
  } catch (err) { out.textContent = '请求失败: ' + err; }
}
function render(data) {
  if (data.stage === 'deployed') {
    out.innerHTML = '<b>第四步完成，请在 CIW 中执行（每次 load 都会打印 token，请目视确认与下面一致）：</b><br>' +
      '<pre>' + html_escape('load("' + data.setup_path + '")') + '</pre>' +
      '<b>token：</b>' + html_escape(data.token || '') + '<br><br>' +
      '<button onclick="verify(' + JSON.stringify(data.user) + ')">我已 load，开始第五步连通性测试</button>';
  } else if (data.stage === 'committed') {
    out.innerHTML = '<b>注册完成。</b> 配置已写入 registry.json，此后按 token 路由使用。';
  } else {
    let text = (data.stage || 'failed') + '\n';
    if (data.errors && data.errors.length) text += data.errors.join('\n');
    else text += data.detail || '';
    out.textContent = text;
  }
}
function html_escape(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
</script>
</body>
</html>
"""


class RegistrationHandler(BaseHTTPRequestHandler):
    server_version = "vb-registration/0.1"

    # -- helpers -------------------------------------------------------------

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

    # -- routing ---------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/":
            self._send_html(200, _PAGE)
            return
        if path.startswith("/api/register/"):
            user = path[len("/api/register/"):].rstrip("/")
            flow = self._flow(user)
            if flow is None or flow.state is None:
                self._send_json(404, {"error": "no registration in progress", "user": user})
                return
            self._send_json(200, self._state_payload(flow.state))
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/register":
            self._handle_apply()
            return
        if path.startswith("/api/register/") and path.endswith("/verify"):
            user = path[len("/api/register/"):-len("/verify")]
            self._handle_verify(user)
            return
        self._send_json(404, {"error": "not found"})

    def _handle_apply(self) -> None:
        try:
            raw = self._read_json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json(400, {"error": "invalid JSON body"})
            return
        try:
            request = RegistrationRequest(**raw)
        except ValidationError as exc:
            detail = [str(e) for e in exc.errors()]
            self._send_json(400, {"error": "invalid request", "detail": detail})
            return

        flow = RegistrationFlow(self.server.registry)  # type: ignore[attr-defined]
        state = flow.apply(request)
        with self.server.flow_lock:  # type: ignore[attr-defined]
            self.server.flows[request.user] = flow  # type: ignore[attr-defined]
        self._send_json(200, self._state_payload(state))

    def _handle_verify(self, user: str) -> None:
        user = unquote(user)
        flow = self._flow(user)
        if flow is None:
            self._send_json(404, {"error": "no registration in progress", "user": user})
            return
        state = flow.verify()
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
