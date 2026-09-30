"""生成"多跳（jump / SOCKS5 proxy）专项环境"的注册表。

为什么需要它：spec 的路由合同里 endpoint 身份 = `(host, user, jump_host, jump_user, proxy)`，
第五轮 spec 覆盖矩阵把"多跳跳板 / 代理"记为缺口 X1（当时认为环境只有单跳）。
实际上本机 SSH config 里已经有真实的两跳链路：

    Windows ──ssh──► w3-gent (172.20.170.23, dev) ──ssh──► w1-gent (172.20.170.21, dev)

本脚本据此造一个**独立 work-dir + 独立注册表**，不碰常驻环境（`log-vblog` / 8127）：

| 用户 | token | 路由 | 说明 |
|---|---|---|---|
| `hop-jump` | `vb-hopjump` | host=w1-gent, jump_host=w3-gent | 真实两跳（paramiko direct-tcpip） |
| `hop-socks` | `vb-hopsocks` | host=w1-gent, proxy=socks5://127.0.0.1:11080 | 真实 SOCKS5（配套 TB 会自己拉起该隧道） |
| `hop-fake` | `vb-hopfake` | host=w1-gent, jump_host=w3-gent, daemon=65203 | 两跳 + lab fake daemon（skill 通道） |

用法::

    python test/shared/runners/make_multihop_env.py

随后起独立业务面（改动注册表后必须重启，否则不生效）::

    python -m server.api_server --port 8131 --work-dir test/artifacts/env/multihop
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TARGET_DIR = ROOT / "test" / "artifacts" / "env" / "multihop"

KEY_DIR = r"C:\wsl\shared\keys"
KEY_W1 = "lab_w1_ed25519"
W1_HOST = "w1-gent"
W1_USER = "dev"
W3_HOST = "w3-gent"
W3_USER = "dev"
SOCKS_URL = "socks5://127.0.0.1:11080"
ROOT_W1 = "/home/dev/hop-root"


def _role(
    *,
    host: str | None = None,
    user: str | None = None,
    root: str | None = None,
    jump_host: str | None = None,
    jump_user: str | None = None,
    proxy: str | None = None,
    use_key: bool = True,
    **extra,
) -> dict:
    """按 registry 的 role schema 造一条 role（未给的字段显式 null，便于人工核对）。"""
    return {
        "mode": None,
        "host": host,
        "user": user,
        "jump_host": jump_host,
        "jump_user": jump_user,
        "proxy": proxy,
        "key_dir": KEY_DIR if (use_key and host) else None,
        "key": KEY_W1 if (use_key and host) else None,
        "root": root,
        "expected_fingerprint": None,
        "max_sessions": 32 if host else 10,
        **extra,
    }


def _entry(token: str, *, jump: bool = False, proxy: bool = False, fake_daemon: bool = False) -> dict:
    roles = {
        "gui": _role(host=W1_HOST, user=W1_USER, root=ROOT_W1,
                     jump_host=W3_HOST if jump else None, jump_user=W3_USER if jump else None,
                     proxy=SOCKS_URL if proxy else None, display=None),
        "daemon": _role(
            host=W1_HOST, user=W1_USER, root=ROOT_W1,
            jump_host=W3_HOST if jump else None, jump_user=W3_USER if jump else None,
            proxy=SOCKS_URL if proxy else None,
            daemon_port=65203 if fake_daemon else None,
            local_port=64590 if fake_daemon else None,
            python=None, expected_hostname=None, expected_user=W1_USER,
        ),
        "command": _role(host=W1_HOST, user=W1_USER, root=ROOT_W1,
                         jump_host=W3_HOST if jump else None, jump_user=W3_USER if jump else None,
                         proxy=SOCKS_URL if proxy else None),
        "file": _role(host=W1_HOST, user=W1_USER, root=ROOT_W1,
                      jump_host=W3_HOST if jump else None, jump_user=W3_USER if jump else None,
                      proxy=SOCKS_URL if proxy else None),
        "spectre": _role(host=W1_HOST, user=W1_USER, root=ROOT_W1,
                         jump_host=W3_HOST if jump else None, jump_user=W3_USER if jump else None,
                         proxy=SOCKS_URL if proxy else None, bin=None),
    }
    return {
        "token": token,
        "mode": {"default": "remote"},
        "ssh": {
            "default": {
                "host": W1_HOST, "user": W1_USER,
                "jump_host": W3_HOST if jump else None,
                "jump_user": W3_USER if jump else None,
                "proxy": SOCKS_URL if proxy else None,
                "key_dir": KEY_DIR, "key": KEY_W1,
            },
            "backend": "paramiko",       # jump/proxy 只走 paramiko 后端（openssh 后端另有 -J 路径）
            "control_master": "auto",
            "tool_override": {},
        },
        "root": {"default": None},
        "roles": roles,
        "runtime": {"thread_pool_size": 16, "channel_budget": 8, "connect_timeout": 15.0},
        "cdslog": {"log_level": "all", "log_max_bytes": 65536},
        "registered_at": 1790172000,
    }


def main() -> int:
    # 独立注册表只放本专项的三个用户，不复用 / 泄露常驻环境的其它 token。
    registry = {
        "hop-jump": _entry("vb-hopjump", jump=True),
        "hop-socks": _entry("vb-hopsocks", proxy=True),
        "hop-fake": _entry("vb-hopfake", jump=True, fake_daemon=True),
    }

    # 直连基线：TB 的负控制用 `vb-lab11`（常驻 w1 lab fake，65201）对比"无跳板"路径的
    # client IP，因此这个 token 必须也在本注册表里——否则基线取不到 IP，TB 会 8/10。
    # 条目从常驻注册表**原样复制**（并用生产 Registry.load 复验），不手写。
    resident = ROOT / "test" / "artifacts" / "env" / "log-vblog" / "registry.json"
    if resident.is_file():
        try:
            source = json.loads(resident.read_text(encoding="utf-8"))
        except ValueError:
            source = {}
        for user in ("vbfake1", "vbfake2"):
            entry = source.get(user)
            if isinstance(entry, dict):
                registry[user] = entry
        if "vbfake1" not in registry:
            print("  [warn] 常驻注册表里没有 vbfake1/vbfake2：直连基线将取不到 token（TB 会红）")
    else:
        print("  [warn] 常驻注册表不存在：跳过直连基线用户的复制")

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    out = TARGET_DIR / "registry.json"
    out.write_text(json.dumps(registry, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"written: {out}")
    for name in ("hop-jump", "hop-socks", "hop-fake", "vbfake1", "vbfake2"):
        if name not in registry:
            continue
        item = registry[name]
        cmd = item["roles"]["command"]
        print(f"  {name:10s} token={item['token']:12s} host={cmd['host']} "
              f"jump={cmd['jump_host']} proxy={cmd['proxy']}")
    print("\n起业务面： python -m server.api_server --port 8131 --work-dir test/artifacts/env/multihop")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
