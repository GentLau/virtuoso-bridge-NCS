"""按 role 分离凭据的半真机 TB（用测试环境已有的双钥，不改任何远端文件）。

环境事实见 ``test/docs/环境说明.md`` §3.1（测试工程师整理，2026-09-23）：

* ``~/.ssh/id_ed25519``（comment ``openclaw-workspace``）授权到 wsl-gent 的
  ``Gent`` / ``vbuser1`` / ``vbuser2``；
* ``C:\\wsl\\shared\\keys\\vbuser2_ed25519``（comment ``vbuser2``）是 vbuser2 的
  独立钥；两把钥都能以 **vbuser2** 登录同一台 wsl-gent。

因此本 TB 直接构造"同 endpoint、不同凭据"：
command role 用 vbuser2 自己的钥、file role 用 `~/.ssh/id_ed25519`，
断言两条连接不共用、且各自真的用对应的私钥认证成功；同时用
``ssh-keygen -lf`` 交叉校验我们的公钥指纹算法。

用法（在**客户端**一侧运行，默认就是本机 Windows）::

    PYTHONPATH=src python test/semi/transport/role_credential_isolation_tb.py \
        --out test/artifacts/evidence/role-credential-isolation.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from common.registry import UserEntry  # noqa: E402
from common.ssh_credentials import public_key_fingerprint  # noqa: E402
from transport.remote_roles import resolve  # noqa: E402
from transport.tunnel import RemoteClient  # noqa: E402


def _ssh_keygen_fingerprint(key_dir: str, key: str) -> str | None:
    pub = Path(key_dir).expanduser() / f"{key}.pub"
    if not pub.is_file():
        return None
    proc = subprocess.run(
        ["ssh-keygen", "-lf", str(pub)], capture_output=True, text=True
    )
    if proc.returncode != 0:
        return None
    parts = proc.stdout.split()
    return parts[1] if len(parts) >= 2 else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="wsl-gent")
    parser.add_argument("--ssh-user", default="vbuser2")
    parser.add_argument("--key-a-dir", default="~/.ssh")
    parser.add_argument("--key-a", default="id_ed25519")
    parser.add_argument("--key-b-dir", default=r"C:\wsl\shared\keys")
    parser.add_argument("--key-b", default="vbuser2_ed25519")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    key_a = (args.key_a_dir, args.key_a)
    key_b = (args.key_b_dir, args.key_b)
    cases: list[dict] = []
    client = None

    def case(name: str, ok: bool, detail) -> None:
        cases.append({"case": name, "ok": bool(ok), "detail": detail})

    def key_path(key: tuple[str, str]) -> Path:
        return Path(key[0]).expanduser() / key[1]

    try:
        case("environment_keys_present",
             all((key_path(k).is_file() and key_path(k).with_name(k[1] + ".pub").is_file())
                 for k in (key_a, key_b)),
             {"a": str(key_path(key_a)), "b": str(key_path(key_b))})

        fp_a = public_key_fingerprint(*key_a)
        fp_b = public_key_fingerprint(*key_b)
        case("fingerprint_matches_ssh_keygen",
             fp_a == _ssh_keygen_fingerprint(*key_a)
             and fp_b == _ssh_keygen_fingerprint(*key_b),
             {"ours_a": fp_a, "ssh_keygen_a": _ssh_keygen_fingerprint(*key_a),
              "ours_b": fp_b, "ssh_keygen_b": _ssh_keygen_fingerprint(*key_b)})
        case("fingerprints_are_distinct", bool(fp_a and fp_b and fp_a != fp_b),
             {"a": fp_a, "b": fp_b})

        entry = UserEntry(token="tok-cred-semi", mode="remote")
        entry.ssh.backend = "openssh"
        entry.ssh.default.host = args.host
        entry.ssh.default.user = args.ssh_user
        entry.ssh.default.key_dir, entry.ssh.default.key = key_a  # file role
        entry.roles.command.host = args.host
        entry.roles.command.user = args.ssh_user
        entry.roles.command.key_dir, entry.roles.command.key = key_b  # command role
        entry.roles.file.host = args.host
        entry.roles.file.user = args.ssh_user
        entry.roles.daemon.host = args.host
        entry.roles.daemon.user = args.ssh_user
        entry.roles.daemon.daemon_port = 65081
        entry.roles.daemon.local_port = 65082

        client = RemoteClient(entry, resolve(entry, "cred-semi"), "cred-semi")
        command_runner = client.command_runner
        file_runner = client._runner(client.targets.file)
        case("same_endpoint_two_runners", command_runner is not file_runner,
             "same (host,user) with different credentials must not share a connection")
        case("command_runner_uses_key_b",
             str(getattr(command_runner, "_ssh_key_path", "")) == str(key_path(key_b)),
             str(getattr(command_runner, "_ssh_key_path", None)))
        case("file_runner_uses_key_a",
             str(getattr(file_runner, "_ssh_key_path", "")) == str(key_path(key_a)),
             str(getattr(file_runner, "_ssh_key_path", None)))

        first = command_runner.run_command("id -un", timeout=25)
        case("command_role_authenticated_as_user",
             first.returncode == 0 and first.stdout.strip() == args.ssh_user,
             {"rc": first.returncode, "stdout": first.stdout.strip(),
              "stderr": first.stderr.strip()[:200]})
        second = file_runner.run_command("id -un", timeout=25)
        case("file_role_authenticated_as_user",
             second.returncode == 0 and second.stdout.strip() == args.ssh_user,
             {"rc": second.returncode, "stdout": second.stdout.strip(),
              "stderr": second.stderr.strip()[:200]})
    except Exception as exc:  # noqa: BLE001 - evidence, not control flow
        case("exception", False, f"{type(exc).__name__}: {exc}")
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:  # noqa: BLE001 - best effort
                pass

    payload = {
        "tb": "role_credential_isolation",
        "host": args.host,
        "user": args.ssh_user,
        "keys": {"a": str(key_path(key_a)), "b": str(key_path(key_b))},
        "cases": cases,
        "passed": sum(1 for item in cases if item["ok"]),
        "total": len(cases),
        "finished": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if all(item["ok"] for item in cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
