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
button{margin:8px 0;padding:10px 18px;font-size:15px;cursor:pointer}
#steps{margin:16px 0;font-size:13px;color:#555}
#steps b{color:#000}
#out{white-space:pre-wrap;background:#f5f5f5;border:1px solid #ddd;padding:12px;margin-top:12px;font-size:13px}
pre{white-space:pre-wrap}
</style>
</head>
<body>
<h1>Virtuoso Bridge 用户注册</h1>
<p>六步：①申请 → ②本地校验 → ③探测 → ④部署 → ⑤连通性测试 → ⑥写入注册表。前五步任何一步失败都不会写入注册表。</p>
<div id="steps"></div>
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
<details>
<summary>高级策略配置（可选，缺省用注册表默认）</summary>
<div class="row">
  <div><label>SSH 后端</label>
    <select name="ssh_backend"><option value="">默认 openssh</option><option value="openssh">openssh</option><option value="paramiko">paramiko</option></select></div>
  <div><label>SSH 并发会话上限</label><input name="ssh_max_sessions" type="number" min="1"></div>
</div>
<label>SOCKS5 代理（如 socks5://127.0.0.1:1080，可选）</label>
<input name="ssh_proxy">
<div class="row">
  <div><label>ControlMaster 策略</label>
    <select name="ssh_control_master"><option value="">默认 auto</option><option value="auto">auto</option><option value="force">force</option><option value="disable">disable</option></select></div>
  <div><label>连接建立超时（秒）</label><input name="connect_timeout" type="number" min="0.1" step="0.1"></div>
</div>
<div class="row">
  <div><label>线程池大小</label><input name="thread_pool_size" type="number" min="1"></div>
  <div><label>channel 预算</label><input name="channel_budget" type="number" min="1"></div>
</div>
<div class="row">
  <div><label>CDS.log 返回级别</label>
    <select name="log_level"><option value="">默认 all</option><option value="off">off</option><option value="all">all</option><option value="warn">warn</option><option value="error">error</option></select></div>
  <div><label>CDS.log 单次上限（字节）</label><input name="log_max_bytes" type="number" min="1"></div>
</div>
<div class="row">
  <div><label>Spectre 主机（缺省同 command 主机）</label><input name="spectre_host"></div>
  <div><label>Spectre 可执行文件路径（可选固化）</label><input name="spectre_bin"></div>
</div>
</details>
<button type="button" id="applyBtn">第 1 步：提交申请</button>
</form>
<div id="out"></div>
<script>
var STEPS = ['申请','本地校验','探测','部署','连通性测试','写入注册表'];
var CURRENT_USER = null;

function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function collectPayload() {
  var fd = new FormData(document.getElementById('f'));
  var payload = {};
  fd.forEach(function (v, k) { if (v !== '') payload[k] = v; });
  var nums = ['daemon_port','local_port','ssh_max_sessions','connect_timeout','thread_pool_size','channel_budget','log_max_bytes'];
  for (var i = 0; i < nums.length; i++) {
    var k = nums[i];
    if (payload[k] !== undefined && payload[k] !== '') payload[k] = Number(payload[k]);
  }
  payload.local = payload.mode === 'local';
  delete payload.mode;
  return payload;
}
function show(text, html) {
  var el = document.getElementById('out');
  if (html) el.innerHTML = text; else el.textContent = text;
}
function showSteps(step, stage) {
  var okStep = (stage === 'committed') ? 6 : step;
  var html = '';
  for (var i = 0; i < 6; i++) {
    var cls = i < okStep ? '✔' : (i + 1 === okStep ? '▶' : '○');
    html += cls + ' ' + (i + 1) + '.' + STEPS[i] + (i < 5 ? ' → ' : '');
  }
  document.getElementById('steps').innerHTML = '<b>当前进度：</b>' + html;
}
function post(path, body, ok) {
  show('正在处理……');
  fetch(path, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: body === undefined ? '' : JSON.stringify(body)
  }).then(function (r) {
    return r.json().then(function (data) { return { status: r.status, data: data }; });
  }).then(function (res) {
    if (res.status === 404) {
      // in-memory session lost (server restarted) -> guide back to step 1
      render({
        user: (res.data && res.data.user) || '',
        stage: 'failed',
        step: 0,
        token: null,
        errors: ['注册会话不存在（服务可能已重启或过期）。请返回修改参数后重新从第 1 步提交。']
      });
      return;
    }
    ok(res.data);
  }).catch(function (err) { show('请求失败: ' + err); });
}
function applyStep() {
  post('/api/register/apply', collectPayload(), render);
}
function step(user, action, label) {
  show(label);
  post('/api/register/' + encodeURIComponent(user) + '/' + action, undefined, render);
}
function render(data) {
  CURRENT_USER = data.user;
  showSteps(data.step || 0, data.stage);
  var errors = (data.errors && data.errors.length) ? data.errors.join('\\n') : '';
  if (data.stage === 'applied') {
    show('第 1 步完成，token=' + (data.token || '') + '\\n\\n下一步：本地校验（user/端口查重，纯本地）。');
    outButtons('<button onclick="step(\\'' + esc(data.user) + '\\',\\'validate\\',\\'第 2 步：本地校验\\')">第 2 步：本地校验</button>');
  } else if (data.stage === 'validated') {
    show('第 2 步通过（user/端口与注册表无冲突）。\\n\\n下一步：探测远端环境。');
    outButtons('<button onclick="step(\\'' + esc(data.user) + '\\',\\'probe\\',\\'第 3 步：探测\\')">第 3 步：探测</button>');
  } else if (data.stage === 'probed') {
    show('第 3 步通过（SSH/指纹/python/端口/部署根）。\\n\\n下一步：上传 daemon/il/setup 到远端。');
    outButtons('<button onclick="step(\\'' + esc(data.user) + '\\',\\'deploy\\',\\'第 4 步：部署\\')">第 4 步：部署</button>');
  } else if (data.stage === 'deployed') {
    show('<b>第 4 步完成。请在 CIW 中执行（每次 load 都会打印 token，请目视确认与下面一致）：</b><br>' +
      '<pre>' + esc('load("' + data.setup_path + '")') + '</pre>' +
      '<b>token：</b>' + esc(data.token || ''), true);
    outButtons('<button onclick="step(\\'' + esc(data.user) + '\\',\\'verify\\',\\'第 5 步：连通性测试\\')">我已 load，开始第 5 步连通性测试</button>');
  } else if (data.stage === 'committed') {
    show('注册完成。配置已写入 registry.json，此后按 token 路由使用。', false);
    outButtons('');
  } else {
    show('失败于第 ' + (data.step || 0) + ' 步：\\n' + errors + '\\n\\n可修改参数后重新提交，或对同一用户重试当前步骤。');
    var stepNo = data.step || 0;
    var action = stepNo === 2 ? 'validate' : stepNo === 3 ? 'probe' : stepNo === 4 ? 'deploy' : stepNo === 5 ? 'verify' : null;
    var html = '<button onclick="location.reload()">返回修改</button>';
    if (action) html += '<button onclick="step(\\'' + esc(data.user) + '\\',\\'' + action + '\\',\\'重试第 ' + stepNo + ' 步\\')">重试第 ' + stepNo + ' 步</button>';
    outButtons(html);
  }
}
function outButtons(html) {
  var extra = document.getElementById('action');
  if (!extra) { extra = document.createElement('div'); extra.id = 'action'; document.getElementById('out').appendChild(extra); }
  extra.innerHTML = html;
}
document.getElementById('applyBtn').addEventListener('click', applyStep);
</script>
</body>
</html>
"""


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
