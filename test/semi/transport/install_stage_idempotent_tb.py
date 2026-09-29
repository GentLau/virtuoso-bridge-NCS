# === TB 注释头（规范见 test/docs/写TB规范.md §0）=====================
# 作者: 设计/Codex
# 最后改动: 2026-09-29 10:30
# 依赖: 无
# =====================================================================
# 六步流程（按 test/docs/写TB规范.md §1–§6）：
# §1 环境检查：需要 wsl-gent SSH、sh、sha256sum；main 里显式检查。
# §2 构建：远端唯一临时目录 + stage 文件 + 本地 payload 摘要。
# §3 最终检查：确认 stage 存在且摘要正确，target 尚不存在。
# §4 执行：第一次 install 后，对同一命令做第二次执行（模拟已投递重试）。
# §5 比对：两次都必须 rc=0，且 target 内容正确；旧命令第二次必报 cannot stat。
# §6 重复/收尾：清理远端临时目录，红/绿 JSON 留证。
"""P-090 安装幂等性 TB：同一 install 命令重复执行不得因 stage 已移走而失败。

现场语义：第一次 mv 已经成功、但调用方收到可重试协议错误并重发同一条安装
命令；第二次执行时 stage 已不存在。正确实现必须识别 target 摘要一致并返回
成功，而不是报 `mv: cannot stat <stage>`。

用法::

    PYTHONPATH=src python test/semi/transport/install_stage_idempotent_tb.py \
        --host wsl-gent --out test/artifacts/evidence/p090-install-idempotent.json
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
_FIXTURES = ROOT / "test" / "shared" / "fixtures"
if str(_FIXTURES) not in sys.path:
    sys.path.insert(0, str(_FIXTURES))

from _win import no_window  # type: ignore  # noqa: E402
from transport.tunnel import _install_stage_command  # noqa: E402


def ssh(host: str, command: str, *, input_bytes: bytes | None = None,
        timeout: float = 60.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", host, command],
        input=input_bytes,
        capture_output=True,
        timeout=timeout,
        **no_window(),
    )


def run_script(host: str, script: str, timeout: float = 60.0) -> subprocess.CompletedProcess:
    return ssh(host, "sh -s", input_bytes=script.encode("utf-8"), timeout=timeout)


def text(data: bytes) -> str:
    return (data or b"").decode("utf-8", errors="replace").strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="wsl-gent")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    probe = ssh(args.host, "printf '%s' vb-ok", timeout=30)
    if probe.returncode != 0 or text(probe.stdout) != "vb-ok":
        print(f"[ENV-FAIL] ssh {args.host} unavailable: {text(probe.stderr)}")
        return 2
    tools = ssh(args.host, "command -v sh && command -v sha256sum", timeout=30)
    if tools.returncode != 0:
        print(f"[ENV-FAIL] remote sh/sha256sum unavailable: {text(tools.stderr)}")
        return 2

    tag = uuid.uuid4().hex[:8]
    home = text(ssh(args.host, 'printf "%s" "$HOME"', timeout=30).stdout)
    root = f"{home.rstrip('/')}/.virtuoso-bridge/.p090-tb-{tag}"
    stage = f"{root}/payload.txt.vbtmp-{uuid.uuid4().hex}"
    target = f"{root}/payload.txt"
    payload = b"p090-payload\n"

    source = root + "/payload-local.txt"
    setup = (
        f"rm -rf {shlex.quote(root)}; mkdir -p {shlex.quote(root)}; "
        f"printf 'p090-payload\\n' > {shlex.quote(source)}; "
        f"cp {shlex.quote(source)} {shlex.quote(stage)}"
    )
    made = ssh(args.host, setup, timeout=30)
    if made.returncode != 0:
        print(f"[ENV-FAIL] cannot prepare remote stage: {text(made.stderr)}")
        return 2

    digest_out = text(ssh(args.host, f"sha256sum -- {shlex.quote(stage)}", timeout=30).stdout)
    digest = digest_out.split()[0] if digest_out else ""
    if not digest:
        ssh(args.host, f"rm -rf {shlex.quote(root)}", timeout=30)
        print("[ENV-FAIL] cannot read stage digest")
        return 2

    command = _install_stage_command(stage, target, digest)
    first = run_script(args.host, command)
    first_content = ssh(args.host, f"cat {shlex.quote(target)}", timeout=30)
    second = run_script(args.host, command)
    second_content = ssh(args.host, f"cat {shlex.quote(target)}", timeout=30)
    ssh(args.host, f"rm -rf {shlex.quote(root)}", timeout=30)

    first_ok = (
        first.returncode == 0
        and first_content.returncode == 0
        and first_content.stdout == payload
    )
    second_ok = (
        second.returncode == 0
        and second_content.returncode == 0
        and second_content.stdout == payload
    )
    payload_out = {
        "tb": "install_stage_idempotent_tb",
        "status": "PASS" if first_ok and second_ok else "RED",
        "host": args.host,
        "stage": stage,
        "target": target,
        "digest": digest,
        "command": command,
        "first": {"rc": first.returncode, "stderr": text(first.stderr)},
        "second": {"rc": second.returncode, "stderr": text(second.stderr)},
        "first_ok": first_ok,
        "second_ok": second_ok,
    }
    out = Path(args.out) if args.out else (
        ROOT / "test" / "artifacts" / "evidence" / "p090-install-idempotent.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload_out, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(payload_out, ensure_ascii=False, indent=2))
    print(f"evidence: {out}")
    return 0 if first_ok and second_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
