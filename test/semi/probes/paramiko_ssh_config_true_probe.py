"""P-037 复验：真实 ``ssh -G`` 的 ``true``/``false`` 必须被 paramiko 后端接受。

缺陷背景：部分用户 ``~/.ssh/config`` 写 ``StrictHostKeyChecking true``（OpenSSH
接受），而 paramiko 后端此前只认 ``yes``/``ask``，于是同一个配置在 paramiko
后端下报 ``ValueError``。修复是在解析处把 ``true/false`` 归一化为 ``yes/no``。

本探针不依赖 Virtuoso：

* case ``ssh_g_raw``：报告本机 ``ssh -G <host>`` 的真实取值（``true``/``false``
  时才有意义，``ask`` 等默认值标记为 not-applicable）；
* case ``synthetic_true_config``：构造一份含 ``StrictHostKeyChecking true`` 与
  ``IdentitiesOnly true`` 的临时 ssh_config（HostName/User/Port 取自真实
  ``ssh -G``），断言 :meth:`ParamikoSessionBackend._endpoint` 不再报错；
* case ``connection``（``--connection`` 时）：用真实配置建 endpoint 并
  ``test_connection()``，验证 paramiko 后端对真机可用。

用法（Windows 或 wsl-gent 均可）::

    PYTHONPATH=src python test/semi/probes/paramiko_ssh_config_true_probe.py \
        --host wsl-gent --connection \
        --out test/artifacts/evidence/paramiko-ssh-config-true.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from common.paramiko_backend import ParamikoSessionBackend  # noqa: E402


def _ssh_g(host: str, config: Path | None = None) -> dict[str, str]:
    cmd = ["ssh"]
    if config is not None:
        cmd += ["-F", str(config)]
    cmd += ["-G", host]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ssh -G {host} failed: {proc.stderr.strip()}")
    values: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        key, _, value = line.partition(" ")
        values.setdefault(key.lower(), value.strip())
    return values


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="wsl-gent")
    parser.add_argument("--connection", action="store_true",
                        help="额外用真实配置连一次（需要网络/跳板可用）")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    cases: list[dict] = []

    real = _ssh_g(args.host)
    raw_value = real.get("stricthostkeychecking", "")
    cases.append({
        "case": "ssh_g_raw",
        "ok": raw_value in ("yes", "no", "ask", "true", "false"),
        "detail": {
            "stricthostkeychecking": raw_value,
            "identitiesonly": real.get("identitiesonly", ""),
            "note": (
                "true/false 出现时即为缺陷触发条件；ask 为 OpenSSH 默认值"
            ),
        },
    })

    #: 无论本机真实配置是 true/false/ask，都用合成配置复现触发条件
    cfg_path = None
    with tempfile.NamedTemporaryFile(
            "w", suffix=".sshconfig", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(
            f"Host {args.host}\n"
            f"  HostName {real.get('hostname', args.host)}\n"
            f"  User {real.get('user', '') or 'root'}\n"
            f"  Port {real.get('port', '22')}\n"
            "  StrictHostKeyChecking true\n"
            "  IdentitiesOnly true\n"
        )
        cfg_path = Path(fh.name)
    try:
        backend = ParamikoSessionBackend(
                host=args.host,
                user=None,
                jump_host=None,
                jump_user=None,
                ssh_key_path=None,
                ssh_config_path=cfg_path,
                connect_timeout=15,
                max_sessions=2,
        )
        try:
            endpoint = backend._endpoint(args.host, None)
            cases.append({
                "case": "synthetic_true_config",
                "ok": True,
                "detail": {
                    "hostname": endpoint.hostname,
                    "port": endpoint.port,
                    "user": endpoint.username,
                },
            })
        finally:
            backend.close()
    except Exception as exc:  # noqa: BLE001 - report, do not mask
        cases.append({
            "case": "synthetic_true_config",
            "ok": False,
            "detail": f"{type(exc).__name__}: {exc}",
        })
    finally:
        cfg_path.unlink(missing_ok=True)

    if args.connection:
        backend = ParamikoSessionBackend(
            host=args.host,
            user=None,
            jump_host=None,
            jump_user=None,
            ssh_key_path=None,
            ssh_config_path=None,
            connect_timeout=20,
            max_sessions=2,
        )
        try:
            cases.append({
                "case": "connection",
                "ok": bool(backend.test_connection(20)),
                "detail": "real ssh config + paramiko test_connection",
            })
        finally:
            backend.close()

    payload = {
        "probe": "paramiko_ssh_config_true",
        "host": args.host,
        "cases": cases,
        "passed": sum(1 for case in cases if case["ok"]),
        "total": len(cases),
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if all(case["ok"] for case in cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
