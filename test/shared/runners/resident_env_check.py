"""常驻半真机环境自检：按注册表逐个 token 打通一次 `1+1`，并报告该实例怎么起。

用法（仓库根目录）::

    PYTHONPATH=src python test/shared/runners/resident_env_check.py
    PYTHONPATH=src python test/shared/runners/resident_env_check.py --verbose

口径：
* **remote** 用户（daemon 有 host）→ 必须 `1+1` 成功；
* **local** 用户（`mode=local`，没有远端 daemon）→ 记为 skip（它们由本地 TB 自己拉起）；
* 失败时打印"该实例怎么起"的提示（脚本都在 `test/shared/runners/`，配方见 `test/docs/推荐测试环境.md` §0）。
退出码：只要有一个 remote 用户不通就非 0。
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from common.paths import init_work_dir  # noqa: E402
from transport.middle import BusinessServer  # noqa: E402

HINTS = {
    "vblog": "bringup_user.sh（Gent 身份）/ 见 推荐测试环境 §0",
    "vbs11": "bringup_user.sh（Gent 身份）/ 见 推荐测试环境 §0",
    "vbuser1": "ssh -o User=vbuser1 wsl-gent 'bash ~/bringup_user.sh vbuser1 65401'",
    "vbuser2": "ssh -o User=vbuser2 wsl-gent 'bash ~/bringup_user.sh vbuser2 65402'",
    "vbfake1": "test/shared/runners/start_lab_fakes.sh（WSL 里先 sed -i 's/\\r$//'）",
    "vbfake2": "test/shared/runners/start_lab_fakes.sh（同上）",
    "vbtest": "wsl-gent 上 ~/.virtuoso-bridge/vbtest/fakevirt（见 推荐测试环境 §0）",
    "calprobe": "PDK/Calibre 专用实例（calprobe, 65122），见 推荐测试环境 S1",
}


def http_health(base: str) -> tuple[bool, str]:
    root = base.rstrip("/").removesuffix("/api/operation")
    try:
        with urllib.request.urlopen(f"{root}/health", timeout=10) as response:
            return response.status == 200, f"HTTP {response.status}"
    except urllib.error.HTTPError as error:
        return False, f"HTTP {error.code}"
    except OSError as error:
        return False, f"{type(error).__name__}: {error}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", default="test/artifacts/env/log-vblog")
    parser.add_argument("--base", default="http://127.0.0.1:8127")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    work_dir = Path(args.work_dir).resolve()
    registry = json.loads((work_dir / "registry.json").read_text(encoding="utf-8"))
    init_work_dir(str(work_dir))
    init_work_dir(work_dir)
    server = BusinessServer()
    healthy: list[tuple] = []
    failures: list[tuple] = []
    skipped: list[tuple] = []
    for user, entry in registry.items():
        if not isinstance(entry, dict):
            continue
        daemon = (entry.get("roles") or {}).get("daemon") or {}
        if not daemon.get("daemon_port"):
            continue
        default_host = ((entry.get("ssh") or {}).get("default") or {}).get("host")
        if (entry.get("mode") or {}).get("default") == "local" or not (daemon.get("host") or default_host):
            skipped.append((user, "local 模式（无远端 daemon，由本地 TB 自己起）"))
            continue
        result = server.execute_skill("1+1", token=entry.get("token"))
        if result.ok and (result.output or "").strip().strip('"') == "2":
            healthy.append((user, daemon.get("host") or default_host, daemon.get("daemon_port")))
        else:
            failures.append((user, daemon.get("host") or default_host,
                             daemon.get("daemon_port"), (result.errors or [result.output])[0]))

    print(f"常驻环境自检  work-dir={work_dir}")
    ok, detail = http_health(args.base)
    print(f"  业务面 {args.base}/health : {'OK' if ok else 'FAIL'} ({detail})")
    for user, host, port in healthy:
        print(f"  [OK]   {user:10s} {host}:{port}")
    for user, why in skipped:
        print(f"  [skip] {user:10s} {why}")
    for user, host, port, why in failures:
        print(f"  [FAIL] {user:10s} {host}:{port} -> {why}")
        if user in HINTS:
            print(f"         起法：{HINTS[user]}")
    print(f"  remote 实例 {len(healthy)}/{len(healthy) + len(failures)} 通；skip {len(skipped)}")
    if not ok:
        print("  提示：standalone 业务面用 `python -m server.api_server --port 8127 "
              "--work-dir test/artifacts/env/log-vblog` 起；改注册表后要重启它。")
    return 0 if (not failures and ok) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
