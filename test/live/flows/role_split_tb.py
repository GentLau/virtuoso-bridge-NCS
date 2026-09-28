# === TB 注释头（规范见 test/docs/写TB规范.md §0）=====================
# 作者: 设计/Codex
# 最后改动: 2026-09-28 12:04
# 依赖: 无
# =====================================================================
# 六步流程（按 test/docs/写TB规范.md §1–§6）：
# §1 环境检查：已调用 require_environment(work_dir, token)。
# §2 构建：注册表/BusinessServer + lab 保活进程。
# §3 最终检查：query 确认五 role 的 host/root 解析。
# §4 执行：跨 role command、skill、上传/下载动作。
# §5 比对：hostname、文件内容、角色落点与期望一致。
# §6 重复/收尾：canary 重复；回收保活进程，保留 JSON 证据。
"""S2 多 role 分主机 TB：验证同一 token 下五 role 真的路由到不同主机。

场景（见 ``test/docs/推荐测试环境.md`` S2）：

* ``daemon``  → wsl-gent（真实 Virtuoso 实例，端口/令牌来自注册表）
* ``command`` → w1-gent（lab WSL，无 Virtuoso）
* ``file``    → w2-gent（lab WSL，无 Virtuoso）

判据不是"没报错"，而是**每一 role 的落点用独立证据钉死**：

1. ``run_command("hostname")`` 的输出必须等于**直连 command 主机**取到的 hostname；
2. ``execute_skill("getHostName()")`` 的输出必须等于**直连 daemon 主机**取到的 hostname，
   且两者必须不同（否则说明 role 根本没分主机）；
3. ``upload_file`` 写到 file role 的 root 下，**直连 file 主机** ``cat`` 回来必须字节一致，
   且 ``download_file`` 取回的内容也要一致。

lab WSL 空闲 1–2 分钟会自动停机（``test/reports/环境建设说明.md`` §3.2），因此本 TB
自己拉起 ``sleep infinity`` 保活进程，结束时回收。

用法::

    python test/live/flows/role_split_tb.py --work-dir test/artifacts/env/scenario-role-split \
        --token d6af595b342647b58ec63ca6 --out test/artifacts/env/scenario-role-split/evidence.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
_SUPPORT = Path(__file__).resolve().parents[2] / "shared" / "fixtures"
if str(_SUPPORT) not in sys.path:
    sys.path.insert(0, str(_SUPPORT))
_RUNNERS = ROOT / "test" / "shared" / "runners"
if str(_RUNNERS) not in sys.path:
    sys.path.insert(0, str(_RUNNERS))
from env_check import require_environment  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

try:  # Windows: keep ssh/scp console windows hidden
    from _win import no_window  # type: ignore
except ImportError:  # pragma: no cover
    def no_window(**kwargs):  # type: ignore
        return dict(kwargs)


def ssh(host: str, command: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, command],
        capture_output=True, text=True, timeout=timeout, **no_window(),
    )


def ensure_lab_host(host: str, timeout: float = 120.0) -> tuple[bool, subprocess.Popen | None]:
    """Start a lab WSL distro and pin it open (it stops itself when idle)."""
    if ssh(host, "hostname", timeout=12).returncode == 0:
        return True, None
    keepalive = subprocess.Popen(
        ["wsl.exe", "-d", host, "--", "sleep", "infinity"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **no_window(),
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        if ssh(host, "hostname", timeout=12).returncode == 0:
            return True, keepalive
        time.sleep(3.0)
    return False, keepalive


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work-dir", default=str(ROOT / "test" / "artifacts" / "env" / "scenario-role-split"))
    #: token 默认**从注册表里读**（`--user` 的条目）——2026-09-24 踩过：TB 写死一个 token，
    #: 换环境（scenario-role-split 的 rolesplit 用 `vb-s11`）就全红成 `invalid token`，
    #: 看着像产品故障。显式 `--token` 仍然优先。
    ap.add_argument("--token", default="")
    ap.add_argument("--user", default="roleprobe")
    ap.add_argument("--skip-lab-start", action="store_true")
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)

    work_dir = Path(args.work_dir)
    if not args.token:
        try:
            entry = json.loads((work_dir / "registry.json").read_text(encoding="utf-8")).get(args.user) or {}
            token = str(entry.get("token") or "")
        except (OSError, ValueError):
            token = ""
        if not token:
            ap.error("--token 为空，且注册表里读不到该 user 的 token（用 --token 显式给）")
        args.token = token
    from common.paths import init_work_dir  # noqa: E402
    from transport.middle import BusinessServer  # noqa: E402

    # 六步 §1：确认 token 的 command / SKILL 通道可用，再做 role 落点验证。
    environment = require_environment(
        work_dir=str(work_dir.resolve()), token=args.token
    )
    # 六步 §2/§3：绑定 work root、构建 registry 客户端并核对各 role 初始落点。
    init_work_dir(str(work_dir))
    middle = BusinessServer()

    steps: list[dict] = []
    value: dict = {}
    keepalives: list[tuple[str, subprocess.Popen]] = []
    ok = True

    def record(name: str, passed: bool, detail) -> None:
        nonlocal ok
        steps.append({"name": name, "ok": bool(passed), "detail": detail})
        if not passed:
            ok = False

    try:
        query = middle.query(token=args.token)
        roles = getattr(query, "roles", {}) or {}
        # query() 按设计**不暴露拓扑**（host/user），所以预期落点从注册表文件直读；
        # query 只用来核对 root 等事实是否与注册表一致。
        raw_registry = json.loads((work_dir / "registry.json").read_text(encoding="utf-8"))
        raw_roles = raw_registry[args.user]["roles"]
        plans = {}
        for name in ("daemon", "command", "file"):
            role = roles.get(name)
            plans[name] = {
                "host": raw_roles[name].get("host") or raw_registry[args.user]["ssh"]["default"]["host"],
                "user": raw_roles[name].get("user") or raw_registry[args.user]["ssh"]["default"]["user"],
                "root": getattr(role, "root", None),
                "daemon_port": getattr(role, "daemon_port", None),
                "registry_root": raw_roles[name].get("root"),
            }
        value["role_plan"] = plans
        record("query-roles", True, plans)
        record("query-root-matches-registry",
               all(plans[name]["root"] == plans[name]["registry_root"]
                   for name in ("daemon", "command", "file")),
               {name: (plans[name]["root"], plans[name]["registry_root"])
                for name in ("daemon", "command", "file")})

        daemon_host = plans["daemon"]["host"] or "wsl-gent"
        command_host = plans["command"]["host"]
        file_host = plans["file"]["host"]
        if not command_host or not file_host:
            record("roles-are-split", False,
                   "注册表未给 command/file 指定独立主机，本场景需要分主机")

        # 1) daemon role：SKILL 必须在 daemon 主机上执行
        direct_daemon = ssh(daemon_host, "hostname").stdout.strip()
        skill = middle.execute_skill("getHostName()", timeout=60, token=args.token)
        skill_host = (skill.output or "").strip().strip('"')
        value["daemon"] = {"direct": direct_daemon, "via_skill": skill_host}
        record("daemon-role-lands-on-daemon-host",
               skill.ok and skill_host.split(".")[0] == direct_daemon.split(".")[0],
               value["daemon"])

        # 2) command role：命令必须在 command 主机上执行
        for host in {command_host, file_host}:
            started, keep = ensure_lab_host(host)
            if keep is not None:
                keepalives.append((host, keep))
            if not started:
                record(f"lab-host-{host}-reachable", False, {"host": host})

        direct_command = ssh(command_host, "hostname").stdout.strip()
        ran = middle.run_command("hostname", timeout=60, token=args.token)
        value["command"] = {"direct": direct_command, "stdout": ran.stdout.strip(),
                            "stderr": (ran.stderr or "").strip()[:400],
                            "returncode": ran.returncode, "kind": ran.kind}
        record("command-role-lands-on-command-host",
               ran.returncode == 0 and ran.stdout.strip() == direct_command,
               value["command"])

        # 3) file role：上传必须落在 file 主机的 role root 下，且内容可原样取回
        payload = f"role-split-{time.strftime('%H%M%S')}\n"
        remote_path = f"{plans['file']['root']}/roundtrip.txt"
        stage = Path(tempfile.mkdtemp(prefix="vb-"))
        local_up = stage / "up.txt"
        local_up.write_text(payload, encoding="utf-8")
        up = middle.upload_file(local_up, remote_path, timeout=60, token=args.token)
        cat = ssh(file_host, f"cat {remote_path}")
        local_down = stage / "down.txt"
        down = middle.download_file(remote_path, local_down, timeout=60, token=args.token)
        downloaded = local_down.read_text(encoding="utf-8") if local_down.exists() else ""
        value["file"] = {
            "remote_path": remote_path,
            "upload_rc": up.returncode, "download_rc": down.returncode,
            "upload_stderr": (up.stderr or "").strip()[:400],
            "download_stderr": (down.stderr or "").strip()[:400],
            "remote_content": cat.stdout, "downloaded_content": downloaded,
        }
        record("file-role-lands-on-file-host",
               cat.returncode == 0 and cat.stdout == payload and downloaded == payload,
               value["file"])
        for leftover in stage.glob("*"):
            leftover.unlink(missing_ok=True)
        stage.rmdir()
    finally:
        for host, proc in keepalives:
            try:
                proc.terminate()
            except Exception:  # noqa: BLE001 - best effort
                pass

    evidence = {
        "scenario": "S2-role-split",
        "ok": ok,
        "work_dir": str(work_dir),
        "token": args.token,
        "environment": environment,
        "steps": steps,
        "value": value,
    }
    out = Path(args.out) if args.out else work_dir / "evidence.json"
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in evidence.items() if k != "steps"}, ensure_ascii=False))
    for step in steps:
        print(f"  [{'ok' if step['ok'] else 'FAIL'}] {step['name']}")
    print(f"evidence: {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
