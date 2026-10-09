# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-30 16:35
# 依赖: test/artifacts/admin-token.txt（gitignored，管理员 token）
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
# ① 环境检查：控制面 8124 `/health` 200 + `/help` 列出 `/api/bug`；admin token 可用；
# ② 构建：记录 `log/bug_reports/` 现有文件集合作为基线（本 TB 只清理自己创建的文件）；
# ③ 最终检查：`GET /api/process/status` 处于 ready（不是别的进程/脏状态）；
# ④ 只做被测动作：控制面只读接口（status/users/user/config）+ `POST /api/bug` 正/负例
#    （正例 body 里故意塞 `authorization` 与 token 明文；负例：无 token / 无效 token）；
# ⑤ 读回比对（值级）：状态字段、用户清单、配置键、
#    **bug 报告落盘文件**的 id/user/raw_body（凭据必须被打码、marker 必须在）/status/logs 有界；
#    负例必须 400 且**零落盘**；
# ⑥ 收尾：按 report id 精确删除本 TB 创建的 bug 报告文件（不动他人报告）。
"""控制面（8124）常规通道 + bug 报告通道的真机 TB。

覆盖动机（2026-09-30）：bug 报告通道（`POST /api/bug`）此前**只有离线 handler 测试**
（`test/offline/unit/test_registration_server_edges.py`），没有任何真机 TB；
而它是"源码缺陷上报"的唯一入口 —— 通道本身不可用，会把缺陷反馈链一起打断。

判据来源：`src/register/server.py::_handle_bug_report` 与 spec `注册与管理` §3：
* 无 token / 无效 token → **4xx 且不落任何文件**；
* 合法 token → 200 + 落盘 `log/bug_reports/bug-<UTC>-<user>-<8hex>.json`；
* 落盘前**先剥离凭据**（`token`/`authorization` 等 → `"***"`），
  并附：提交 user、时间、状态摘要（`status`）、有界近期日志（`logs`，字节/行数双向截断）；
* 文件权限 0600、目录 0700（本 TB 在 Windows 侧只断言"文件存在 + 字段正确"，
  权限断言留给离线/半真机层）。

**本 TB 不覆盖的写通道（有意为之，附理由）**：`POST /api/user/<u>/update`、
`DELETE /api/user/<u>`、`PUT /api/config` 会**改动常驻注册表**（影响其他人正在用的
token/配置），因此不在常驻控制面上做真机破坏性操作；它们的契约由离线单测
（`test/offline/unit/test_registration_server_edges.py`）与**注册六步 TB**（该 TB 自建
并清理自己的用户）承担。异步进程管理只有 `reload` 在只读语义下被真机验证（`restart`
会中断他人会话，留给排障/环境恢复流程）。

用法::

    PYTHONPATH=src python test/live/registration/control_plane_tb.py \
        --out test/artifacts/evidence/round9/control-plane-tb.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8124"
WORK_DIR = ROOT / "test" / "artifacts" / "env" / "log-vblog"
USER = "vblog"
MARKER = f"BUGCH_{time.strftime('%H%M%S')}"


class Http:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.last_headers: dict[str, str] = {}

    def call(self, method: str, path: str, body: dict[str, Any] | None = None,
             admin: bool = False, admin_token: str | None = None,
             user_token: str | None = None, timeout: float = 30.0) -> tuple[int, dict[str, Any]]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if admin and admin_token:
            headers["Authorization"] = f"Bearer {admin_token}"
        else:
            headers["Authorization"] = "Bearer wrong-admin-token"
        payload = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(f"{self.base}{path}", data=payload,
                                         headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                self.last_headers = {k: v for k, v in response.headers.items()}
                raw = response.read().decode("utf-8", "replace")
                return response.status, (json.loads(raw) if raw.strip().startswith(("{", "[")) else {"raw": raw})
        except urllib.error.HTTPError as error:
            self.last_headers = {k: v for k, v in error.headers.items()}
            raw = error.read().decode("utf-8", "replace")
            try:
                return error.code, json.loads(raw)
            except ValueError:
                return error.code, {"raw": raw[:200]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=BASE)
    parser.add_argument("--work-dir", default=str(WORK_DIR))
    parser.add_argument("--user", default=USER)
    parser.add_argument("--admin-token-file", default=str(ROOT / "test" / "artifacts" / "admin-token.txt"))
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    http = Http(args.base)
    work_dir = Path(args.work_dir)
    reports_dir = work_dir / "log" / "bug_reports"
    admin_token = Path(args.admin_token_file).read_text(encoding="utf-8").strip() \
        if Path(args.admin_token_file).is_file() else ""

    registry = json.loads((work_dir / "registry.json").read_text(encoding="utf-8"))
    user_token = str((registry.get(args.user) or {}).get("token") or "")

    results: list[tuple[str, str]] = []
    evidence: dict[str, Any] = {"marker": MARKER, "base": args.base, "cases": {}}
    created: list[Path] = []

    def run(name: str, func) -> Any:
        try:
            value = func()
        except Exception as exc:  # noqa: BLE001
            results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
            print(f"FAIL    {name}: {type(exc).__name__}: {exc}", flush=True)
            return None
        results.append((name, "PASS"))
        print(f"PASS    {name}", flush=True)
        return value

    def case_env() -> None:
        # 控制面在业务面 restart/reload 后可能有一瞬间不接新连接 → 环境检查给 3 次有界重试。
        last: tuple[int, dict[str, Any]] | None = None
        for _ in range(3):
            try:
                status, body = http.call("GET", "/health", timeout=10.0)
                last = (status, body)
                if status == 200 and body.get("status") == "ok":
                    break
            except Exception as exc:  # noqa: BLE001 - 连接被拒不等于判据失败
                last = (0, {"error": f"{type(exc).__name__}: {exc}"})
            time.sleep(2)
        assert last and last[0] == 200 and last[1].get("status") == "ok", \
            f"/health 异常（3 次重试后）: {last}"
        status, body = http.call("GET", "/help")
        assert status == 200 and body.get("ok") is True, \
            f"/help 异常: {status} {body}"
        guide = body.get("data")
        assert isinstance(guide, str) and guide.strip(), \
            f"/help 应返回注册流程指导文本: {body}"
        assert admin_token, f"缺少 admin token（{args.admin_token_file}）"
        assert user_token, f"注册表里 {args.user} 没有 token"

    def case_admin_readonly() -> None:
        status, body = http.call("GET", "/api/process/status", admin=True, admin_token=admin_token)
        assert status == 200, f"/api/process/status {status}: {body}"
        assert body.get("state") == "ready", f"业务面不是 ready: {body.get('state')!r}"
        assert isinstance(body.get("pid"), int) and body["pid"] > 0, f"pid 异常: {body}"
        assert str(body.get("port")) == "8127", f"业务面端口异常: {body.get('port')!r}"
        assert Path(str(body.get("work_dir", ""))).resolve() == work_dir.resolve(), \
            f"work_dir 异常: {body.get('work_dir')!r}"

        status, users = http.call("GET", "/api/users", admin=True, admin_token=admin_token)
        assert status == 200, f"/api/users {status}: {users}"
        names = {str(item.get("user")) if isinstance(item, dict) else str(item)
                 for item in (users.get("users") or users if isinstance(users, list) else users.get("users") or [])}
        assert args.user in names, f"/api/users 缺少 {args.user}: {sorted(names)[:8]}"

        status, detail = http.call("GET", f"/api/user/{args.user}", admin=True, admin_token=admin_token)
        assert status == 200, f"/api/user/{args.user} {status}: {detail}"
        assert "token" not in json.dumps(detail, ensure_ascii=False), \
            f"用户详情不得回显 token: {str(detail)[:160]}"

        status, config = http.call("GET", "/api/config", admin=True, admin_token=admin_token)
        assert status == 200 and isinstance(config, dict) and config, f"/api/config 异常: {status} {config}"

        status, reloaded = http.call("POST", "/api/process/reload", admin=True,
                                     admin_token=admin_token)
        assert status == 200 and reloaded.get("state") == "ready", f"reload 异常: {status} {reloaded}"
        evidence["cases"]["admin_readonly"] = {"users": sorted(names)[:8], "config_keys": sorted(config)[:8]}

    def case_admin_denied() -> None:
        for path, method in (("/api/process/status", "GET"), ("/api/users", "GET"),
                             ("/api/config", "GET")):
            status, body = http.call(method, path, admin=False)
            assert status == 401 and body.get("error") == "unauthorized", \
                f"{path} 无 admin token 应 401: {status} {body}"

    def case_page_and_help() -> None:
        """管理页与 `/help` 自描述契约（非业务面也要有判据）。"""
        status, body = http.call("GET", "/")
        html = str(body.get("raw") or "")
        assert status == 200 and len(html) > 500, f"GET / 应返回管理页 HTML: {status} len={len(html)}"
        assert "text/html" in http.last_headers.get("Content-Type", "").lower(), \
            f"GET / Content-Type 应为 text/html: {http.last_headers.get('Content-Type')!r}"

        status, help_body = http.call("GET", "/help")
        assert status == 200 and help_body.get("ok") is True, \
            f"/help 异常: {status} {help_body}"
        guide = help_body.get("data")
        assert isinstance(guide, str) and "注册" in guide, \
            f"/help 应返回注册流程指导文本: {help_body}"
        evidence["cases"]["page_and_help"] = {
            "html_bytes": len(html), "guide_chars": len(guide),
        }

    def case_register_read_and_methods() -> None:
        """`GET /api/register/<user>` 的只读语义 + 方法不允许（405 + Allow）。"""
        status, body = http.call("GET", f"/api/register/{args.user}")
        assert status == 404 and body.get("error") == "no registration in progress", \
            f"无进行中注册时应 404 结构化: {status} {body}"
        status, body = http.call("GET", "/api/register/no_such_user_qq")
        assert status == 404 and body.get("error") == "no registration in progress", \
            f"未知用户也应 404 同形: {status} {body}"

        status, body = http.call("HEAD", "/health")
        assert status == 405, f"HEAD /health 应 405: {status} {body}"
        allow = http.last_headers.get("Allow", "")
        assert allow == "GET, POST, PUT, DELETE", f"/health Allow 头异常: {allow!r}"
        # `DELETE`/`PUT` 在非自身路径上的语义未在 spec 固化：只钉"结构化 4xx、不 2xx、不崩"。
        status, body = http.call("DELETE", "/health")
        assert status in (404, 405) and isinstance(body.get("error"), str), \
            f"DELETE /health 应为结构化 4xx: {status} {body}"
        status, body = http.call("PATCH", "/health")
        assert status == 405 and body.get("error") == "method not allowed", \
            f"PATCH /health 应 405: {status} {body}"
        assert http.last_headers.get("Allow") == "GET, POST, PUT, DELETE", \
            f"405 必须带 Allow 头（实测 {http.last_headers.get('Allow')!r}）"
        status, body = http.call("GET", "/api/no_such_path_qq")
        assert status == 404, f"未知路径应 404: {status} {body}"
        evidence["cases"]["register_read_and_methods"] = {"allow": allow}

    def case_bug_positive() -> None:
        reports_dir.mkdir(parents=True, exist_ok=True)
        before = {p.name for p in reports_dir.glob("bug-*.json")}
        payload = {
            "token": user_token,
            "summary": f"{MARKER} 控制面 bug 通道真机自检",
            "authorization": "Bearer SECRET-SHOULD-BE-MASKED",
            "details": {"where": "control_plane_tb", "marker": MARKER},
        }
        status, body = http.call("POST", "/api/bug", body=payload)
        assert status == 200 and body.get("ok") is True, f"bug 提交失败: {status} {body}"
        report_id = str(body.get("id") or "")
        assert report_id.startswith("bug-"), f"返回 id 异常: {body}"
        path = reports_dir / f"{report_id}.json"
        created.append(path)
        assert path.is_file(), f"报告未落盘: {path}"
        assert str(body.get("path", "")).replace("\\", "/").endswith(f"bug_reports/{report_id}.json"), \
            f"返回 path 异常: {body.get('path')!r}"
        after = {p.name for p in reports_dir.glob("bug-*.json")}
        assert after - before == {path.name}, f"应恰好新增 1 份报告: {sorted(after - before)}"

        entry = json.loads(path.read_text(encoding="utf-8"))
        assert entry.get("id") == report_id and entry.get("user") == args.user, \
            f"报告 id/user 异常: {entry.get('id')!r} {entry.get('user')!r}"
        raw_body = str(entry.get("raw_body") or "")
        assert MARKER in raw_body, "raw_body 必须保留原始请求体（除凭据外）"
        assert user_token not in raw_body, "raw_body 不得包含 token 明文"
        assert "SECRET-SHOULD-BE-MASKED" not in raw_body, "raw_body 不得包含 authorization 明文"
        assert entry.get("token_masked") is True and entry.get("credentials_stripped") is True, \
            f"凭据打码标志异常: token_masked={entry.get('token_masked')!r} " \
            f"credentials_stripped={entry.get('credentials_stripped')!r}"
        assert "***" in raw_body, "被打码的凭据应替换为 ***"

        summary = entry.get("status") or {}
        assert int(summary.get("users") or 0) >= 1, f"状态摘要 users 异常: {summary}"
        assert isinstance(summary.get("registrations_in_progress"), list), f"status 摘要异常: {summary}"
        plane = summary.get("control_plane") or {}
        assert str(plane.get("work_dir", "")).replace("\\", "/").endswith("log-vblog"), \
            f"control_plane.work_dir 异常: {plane.get('work_dir')!r}"
        logs = entry.get("logs") or []
        assert logs, "报告必须附带近期日志"
        for item in logs:
            assert {"name", "size", "truncated", "tail"} <= set(item), f"日志条目字段缺失: {item}"
            assert len(str(item.get("tail") or "").splitlines()) <= 500, \
                f"日志 tail 行数超上限: {item.get('name')} -> {len(item['tail'].splitlines())}"
        evidence["cases"]["bug_positive"] = {
            "id": report_id, "raw_body_bytes": entry.get("raw_body_bytes"),
            "logs": [item.get("name") for item in logs][:6],
            "status_users": summary.get("users"),
        }

    def case_bug_negative() -> None:
        reports_dir.mkdir(parents=True, exist_ok=True)
        before = {p.name for p in reports_dir.glob("bug-*.json")}
        for label, payload in (
            ("无 token", {"summary": f"{MARKER} no-token"}),
            ("无效 token", {"token": "definitely-not-a-registered-token",
                            "summary": f"{MARKER} bad-token"}),
        ):
            status, body = http.call("POST", "/api/bug", body=payload)
            assert status == 400 and body.get("error") == "invalid token", \
                f"{label} 应 400 invalid token: {status} {body}"
        after = {p.name for p in reports_dir.glob("bug-*.json")}
        assert after == before, f"负例不得落盘（新增 {sorted(after - before)}）"
        evidence["cases"]["bug_negative"] = {"before": len(before), "after": len(after)}

    run("CP-ENV 控制面可达 + bug 通道在 /help 中 + token 就绪", case_env)
    run("CP-ADMIN 只读通道（status/users/user/config/reload）", case_admin_readonly)
    run("CP-AUTH-NEG 无 admin token 必须 401", case_admin_denied)
    run("CP-PAGE-HELP 管理页 200 + /help 自描述完整", case_page_and_help)
    run("CP-REGISTER-READ 注册态只读 + 405/Allow 方法语义", case_register_read_and_methods)
    run("BUG-01 正例：200 + 落盘 + 凭据打码 + status/logs 有界", case_bug_positive)
    run("BUG-02 负例：无 token / 无效 token → 400 且零落盘", case_bug_negative)

    for path in created:
        try:
            path.unlink()
        except OSError:
            pass
    evidence["cleanup"] = [p.name for p in created]

    failures = [name for name, status in results if status != "PASS"]
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        evidence["results"] = [{"case": name, "status": status} for name, status in results]
        out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"evidence: {out}")
    print(f"{len(results) - len(failures)}/{len(results)} 通过"
          + (f"；失败 {failures}" if failures else ""))
    return 0 if not failures and results else 1


if __name__ == "__main__":
    raise SystemExit(main())
