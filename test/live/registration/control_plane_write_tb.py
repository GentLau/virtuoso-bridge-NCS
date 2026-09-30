# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-30 21:40
# 依赖: test/artifacts/admin-token.txt（gitignored）
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
# ① 环境检查：admin token 文件存在；`python -m register.server` 可用（打包契约另有离线 TB）；
# ② 构建：**独立** work-dir（`test/artifacts/env/cp-write-<stamp>`）+ 自带一个 fixture 用户，
#    在**独立端口**起一个一次性控制面（不碰常驻 8124/8127，不污染常驻注册表）；
# ③ 最终检查：`/api/users` 能看到 fixture 用户；
# ④ 只做被测动作：`POST /api/user/<u>/update`、`PUT /api/config`、`DELETE /api/user/<u>`；
# ⑤ 读回比对（值级）：更新后的 runtime 字段必须能读回、config 必须落盘且 GET 一致、
#    删除后用户必须从 `/api/users` 消失；负例（未知用户 404 / body 带 token 400 /
#    未知字段 400 / 非法 pool size 400 / 无 admin 401）全部结构化；
# ⑥ 收尾：停掉一次性控制面进程（work-dir 留在 artifacts 供审计）。
"""控制面**写通道**真机 TB（在独立实例上做，保护常驻注册表）。

覆盖动机：`/api/user/<u>/update`、`DELETE /api/user/<u>`、`PUT /api/config` 会改注册表/配置，
常驻控制面上做真机破坏性操作会打断其他人 → 之前只有离线 handler 测试。
本 TB 用**一次性控制面 + 独立 work-dir + 自带 fixture 用户**把它们端到端跑通，
判据全部是值级读回（不是只看 200）。

用法::

    PYTHONPATH=src python test/live/registration/control_plane_write_tb.py \
        --out test/artifacts/evidence/round9/control-plane-write-tb.json
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from common.paths import init_work_dir, registry_path  # noqa: E402
from common.registry import UserEntry, load_registry  # noqa: E402
from register.candidate import validate_entry_shape  # noqa: E402

USER = "cpw_user"
STAMP = time.strftime("%m%d%H%M%S")

# fixture 条目：**remote 形状**（与真实注册流程落盘的结构一致 —— 显式凭据 +
# expected_fingerprint + daemon.python），但主机/凭据全是假值：update 通道只在
# role 组发生变化时才探测 host-key，本 TB 只改 runtime/config，因此不会去连它。
FIXTURE_FINGERPRINT = "SHA256:cpwFixtureFingerprintNotProbed"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class Http:
    def __init__(self, base: str, admin_token: str) -> None:
        self.base = base.rstrip("/")
        self.admin_token = admin_token
        self.last_headers: dict[str, str] = {}

    def call(self, method: str, path: str, body: Any = None, *, admin: bool = True,
             timeout: float = 30.0) -> tuple[int, dict[str, Any]]:
        headers = {"Content-Type": "application/json"}
        headers["Authorization"] = (f"Bearer {self.admin_token}" if admin
                                    else "Bearer not-the-admin-token")
        payload = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(f"{self.base}{path}", data=payload,
                                         headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                self.last_headers = {k: v for k, v in response.headers.items()}
                raw = response.read().decode("utf-8", "replace")
                return response.status, json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as error:
            self.last_headers = {k: v for k, v in error.headers.items()}
            raw = error.read().decode("utf-8", "replace")
            try:
                return error.code, json.loads(raw)
            except ValueError:
                return error.code, {"raw": raw[:200]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-token-file",
                        default=str(ROOT / "test" / "artifacts" / "admin-token.txt"))
    parser.add_argument("--work-dir",
                        default=str(ROOT / "test" / "artifacts" / "env" / f"cp-write-{STAMP}"))
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    admin_token = Path(args.admin_token_file).read_text(encoding="utf-8").strip() \
        if Path(args.admin_token_file).is_file() else ""
    work_dir = Path(args.work_dir)
    port = _free_port()
    http = Http(f"http://127.0.0.1:{port}", admin_token)
    results: list[tuple[str, str]] = []
    evidence: dict[str, Any] = {"work_dir": str(work_dir), "port": port, "cases": {}}
    server: subprocess.Popen | None = None
    user_token = f"cpw-token-{STAMP}"

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

    def case_build() -> None:
        nonlocal server
        assert admin_token, f"缺少 admin token：{args.admin_token_file}"
        work_dir.mkdir(parents=True, exist_ok=True)
        init_work_dir(str(work_dir))
        registry = load_registry(registry_path())
        # update 通道按多用户与注册 §5 做**整体形状校验**；手写的空壳条目会被判
        # `invalid update`（2026-09-30 实测 400）。这里自造一条通过同一校验器的
        # remote 形状 fixture（不抄常驻注册表，避免把别人的历史状态当基线）。
        base_root = "/home/cpw-fixture/.virtuoso-bridge"
        entry = UserEntry.model_validate({
            "token": user_token,
            "mode": {"default": "remote"},
            "ssh": {"default": {"host": "cpw-fixture-host", "user": "cpwfixture",
                                "key_dir": "/home/cpw-fixture/.ssh",
                                "key": "cpw_fixture_key"}},
            "root": {"default": None},
            "roles": {
                "gui": {"root": f"{base_root}/gui",
                        "expected_fingerprint": FIXTURE_FINGERPRINT},
                "daemon": {"root": f"{base_root}/daemon",
                           "expected_fingerprint": FIXTURE_FINGERPRINT,
                           "daemon_port": 65510, "local_port": 65511,
                           "python": "python3"},
                "command": {"root": f"{base_root}/command",
                            "expected_fingerprint": FIXTURE_FINGERPRINT},
                "file": {"root": f"{base_root}/file",
                         "expected_fingerprint": FIXTURE_FINGERPRINT},
                "spectre": {"root": f"{base_root}/spectre"},
            },
            "runtime": {"thread_pool_size": 2},
        })
        shape_errors = validate_entry_shape(entry, USER, require_root_default_null=False)
        assert not shape_errors, f"fixture 未通过 runtime 形状校验: {shape_errors}"
        registry.register(USER, entry)
        assert registry_path().is_file(), f"fixture registry 未落盘: {registry_path()}"

        env = dict(os.environ, PYTHONPATH=str(SRC))
        server = subprocess.Popen(
            [sys.executable, "-m", "register.server", "--host", "127.0.0.1",
             "--port", str(port), "--work-dir", str(work_dir)],
            cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                status, body = http.call("GET", "/health", admin=False, timeout=3)
                if status == 200 and body.get("status") == "ok":
                    break
            except Exception:  # noqa: BLE001 - 启动期拒连属正常
                pass
            time.sleep(0.5)
        else:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
            child_out = (server.stdout.read().decode("utf-8", "replace")
                         if server.stdout is not None else "")
            raise AssertionError(
                f"一次性控制面 30s 未就绪（子进程 rc={server.returncode}）："
                f"{child_out[-400:]}")
        status, users = http.call("GET", "/api/users")
        names = sorted(
            str(item.get("user")) if isinstance(item, dict) else str(item)
            for item in (users.get("users") or []))
        assert status == 200 and USER in names, f"fixture 用户未就绪: {status} {names}"
        evidence["cases"]["build"] = {"users": names}

    def case_update_user() -> None:
        status, body = http.call("POST", f"/api/user/{USER}/update",
                                 {"runtime": {"thread_pool_size": 3}})
        assert status == 200, f"update 应 200: {status} {body}"
        status, detail = http.call("GET", f"/api/user/{USER}")
        assert status == 200, f"update 后读回失败: {status} {detail}"
        blob = json.dumps(detail, ensure_ascii=False)
        assert '"thread_pool_size": 3' in blob, f"update 未生效（值级）: {blob[:200]}"
        assert user_token not in blob, "用户详情不得回显 token"
        evidence["cases"]["update_user"] = {"detail": blob[:200]}

    def case_put_config() -> None:
        marker = f"cpw-{STAMP}"
        status, body = http.call("PUT", "/api/config",
                                 {"business_thread_pool_size": 6, "cp_write_marker": marker})
        assert status == 200, f"PUT /api/config 应 200: {status} {body}"
        status, config = http.call("GET", "/api/config")
        assert status == 200 and config.get("business_thread_pool_size") == 6, \
            f"config 未生效: {status} {config}"
        assert config.get("cp_write_marker") == marker, f"marker 未生效: {config}"
        on_disk = json.loads((work_dir / "config.json").read_text(encoding="utf-8"))
        assert on_disk.get("cp_write_marker") == marker and \
            on_disk.get("business_thread_pool_size") == 6, f"config 未落盘: {on_disk}"
        evidence["cases"]["put_config"] = {"config": config}

    def case_update_roles() -> None:
        # 日常档：只改 role.root（不触发 host-key 重探测）→ 值级读回 + 落盘一致。
        new_root = "/home/cpw-fixture/.virtuoso-bridge/spectre-relocated"
        status, body = http.call("POST", f"/api/user/{USER}/update",
                                 {"roles": {"spectre": {"root": new_root}}})
        assert status == 200, f"roles update 应 200: {status} {body}"
        status, detail = http.call("GET", f"/api/user/{USER}")
        entry = detail.get("entry") or {}
        spectre = (entry.get("roles") or {}).get("spectre") or {}
        assert spectre.get("root") == new_root, f"role.root 未按值生效: {spectre}"
        on_disk = json.loads(registry_path().read_text(encoding="utf-8"))
        assert on_disk[USER]["roles"]["spectre"]["root"] == new_root, \
            "role.root 未落盘（值级）"
        evidence["cases"]["update_roles"] = {"spectre_root": spectre.get("root")}

    def case_endpoint_reenroll() -> None:
        # 边界档：连接身份变化 + 显式 expected_fingerprint（多用户与注册 §6.5
        # 「机器重装」确认路径）→ 不联网探测也能把新基准与新配置一起落盘。
        fp_new = "SHA256:cpwFixtureAfterReinstall"
        status, body = http.call("POST", f"/api/user/{USER}/update", {
            "ssh": {"default": {"host": "cpw-fixture-host-b"}},
            "roles": {
                "gui": {"expected_fingerprint": fp_new},
                "daemon": {"expected_fingerprint": fp_new},
                "command": {"expected_fingerprint": fp_new},
                "file": {"expected_fingerprint": fp_new},
            },
        })
        assert status == 200, f"显式指纹的迁移 update 应 200: {status} {body}"
        status, detail = http.call("GET", f"/api/user/{USER}")
        entry = detail.get("entry") or {}
        host = ((entry.get("ssh") or {}).get("default") or {}).get("host")
        assert host == "cpw-fixture-host-b", f"新 host 未生效: {host}"
        roles = entry.get("roles") or {}
        for name in ("gui", "daemon", "command", "file"):
            got = (roles.get(name) or {}).get("expected_fingerprint")
            assert got == fp_new, f"{name}.expected_fingerprint 未按值生效: {got}"
        evidence["cases"]["endpoint_reenroll"] = {"host": host, "fingerprint": fp_new}

    def case_endpoint_untrusted_rejected() -> None:
        # 非法档：换到没有 known_hosts 基准的 endpoint 且不给指纹 → 必须先探测，
        # 探测失败整体拒绝（400），**原条目一字不改**（注册表文件按字节比对）。
        before = registry_path().read_text(encoding="utf-8")
        status, body = http.call("POST", f"/api/user/{USER}/update", {
            "ssh": {"default": {"host": "cpw-unknown-host.invalid"}},
        })
        assert status == 400 and body.get("error") == "invalid update", \
            f"未知 endpoint 应 400 invalid update: {status} {body}"
        assert "host key fingerprint" in json.dumps(body, ensure_ascii=False), \
            f"拒绝原因应点明 host-key 基准缺失: {body}"
        after = registry_path().read_text(encoding="utf-8")
        assert after == before, "被拒绝的 update 不得改动注册表"
        status, detail = http.call("GET", f"/api/user/{USER}")
        host = (((detail.get("entry") or {}).get("ssh") or {}).get("default") or {}).get("host")
        assert host == "cpw-fixture-host-b", f"被拒绝的 update 不得改变 host: {host}"
        evidence["cases"]["endpoint_untrusted_rejected"] = {"detail": str(body)[:200]}

    def case_negative() -> None:
        status, body = http.call("POST", "/api/user/no_such_user/update", {"runtime": {}})
        assert status == 404 and body.get("error") == "unknown user", \
            f"未知用户 update 应 404: {status} {body}"
        status, body = http.call("DELETE", "/api/user/no_such_user")
        assert status == 404 and body.get("error") == "unknown user", \
            f"未知用户 delete 应 404: {status} {body}"
        status, body = http.call("POST", f"/api/user/{USER}/update",
                                 {"token": user_token})
        assert status == 400 and "token" in str(body.get("error")), \
            f"update body 带 token 应 400: {status} {body}"
        status, body = http.call("POST", f"/api/user/{USER}/update",
                                 {"not_a_field": 1})
        assert status == 400 and body.get("error") == "invalid update", \
            f"未知字段应 400 invalid update: {status} {body}"
        status, body = http.call("PUT", "/api/config", {"business_thread_pool_size": 0})
        assert status == 400 and "business_thread_pool_size" in \
            json.dumps(body, ensure_ascii=False), f"非法 pool size 应 400: {status} {body}"
        for method, path, payload in (("POST", f"/api/user/{USER}/update", {}),
                                      ("DELETE", f"/api/user/{USER}", None),
                                      ("PUT", "/api/config", {})):
            status, body = http.call(method, path, payload, admin=False)
            assert status == 401, f"{method} {path} 无 admin 应 401: {status} {body}"
        evidence["cases"]["negative"] = {"checked": 8}

    def case_delete_user() -> None:
        status, body = http.call("DELETE", f"/api/user/{USER}")
        assert status == 200 and body.get("removed") is True, \
            f"delete 应 200 removed=true: {status} {body}"
        status, users = http.call("GET", "/api/users")
        names = [str(item.get("user")) if isinstance(item, dict) else str(item)
                 for item in (users.get("users") or [])]
        assert USER not in names, f"删除后仍在 /api/users: {names}"
        status, detail = http.call("GET", f"/api/user/{USER}")
        assert status == 404, f"删除后详情应 404: {status} {detail}"
        evidence["cases"]["delete_user"] = {"remaining": names}

    run("CPW-BUILD 独立 work-dir + fixture 用户 + 一次性控制面就绪", case_build)
    run("CPW-01 update（runtime 值级读回 + 不回显 token）", case_update_user)
    run("CPW-02 update roles（root 值级读回 + 落盘一致）", case_update_roles)
    run("CPW-03 update 迁移（显式指纹路径值级读回）", case_endpoint_reenroll)
    run("CPW-04 update 拒绝（未知 endpoint 零落盘 + 原值保持）",
        case_endpoint_untrusted_rejected)
    run("CPW-05 PUT config（GET 一致 + 落盘一致）", case_put_config)
    run("CPW-06 负例（404/400×3/401×3）", case_negative)
    run("CPW-07 delete（removed=true + 列表消失 + 详情 404）", case_delete_user)

    if server is not None:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()

    failures = [name for name, status in results if status != "PASS"]
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        evidence["results"] = [{"case": name, "status": status} for name, status in results]
        out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        print(f"evidence: {out}")
    print(f"{len(results) - len(failures)}/{len(results)} 通过"
          + (f"；失败 {failures}" if failures else ""))
    return 0 if not failures and results else 1


if __name__ == "__main__":
    raise SystemExit(main())
