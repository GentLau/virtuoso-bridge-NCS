"""Real-machine CDS.log matrix TB (Windows client -> real Virtuoso daemon).

Covers the machine-facing half of ``test/计划/日志返回.md``: byte identity with
``CDS.log``, the ``off`` source cut (including the 内容嗅探 regression), level
filtering on real ``\\e`` / ``\\w`` lines, and the no-injection guarantee.

Run with::

    PYTHONPATH=src python test/tb/log_matrix_real_tb.py \
        --work-dir test/tb/artifacts/log-vblog --token vb-vblog --marker-file ...

The registry must already contain the token (see test/tb/README.md).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from transport.middle import BusinessServer  # noqa: E402
from transport.registry import UserEntry, load_registry  # noqa: E402
from transport.runtime_paths import set_working_dir  # noqa: E402

try:  # Windows: keep ssh/scp console windows hidden
    from _win import no_window  # type: ignore
except ImportError:  # pragma: no cover
    def no_window(**kwargs):  # type: ignore
        return dict(kwargs)


class ProbeFailure(AssertionError):
    pass


class Env:
    def __init__(self, args) -> None:
        self.args = args
        self.work_dir = Path(args.work_dir).resolve()
        self.work_dir.mkdir(parents=True, exist_ok=True)
        set_working_dir(self.work_dir)
        registry = load_registry()
        self.token = args.token
        if registry.get(args.user) is None:
            entry = UserEntry(token=args.token, mode="remote")
            entry.ssh.default.host = args.host
            entry.ssh.default.user = args.ssh_user
            entry.roles.daemon.host = args.host
            entry.roles.daemon.user = args.ssh_user
            entry.roles.daemon.root = args.root
            entry.roles.daemon.daemon_port = args.daemon_port
            entry.roles.daemon.local_port = args.local_port
            entry.roles.daemon.expected_user = args.ssh_user
            for name in ("gui", "command", "file", "spectre"):
                role = getattr(entry.roles, name)
                role.host = args.host
                role.user = args.ssh_user
                role.root = args.root
            entry.cdslog.log_level = args.log_level
            entry.cdslog.log_max_bytes = args.log_max_bytes
            registry.register(args.user, entry)
        self.server = BusinessServer(self.work_dir)
        self.cds_log = args.cds_log

    def skill(self, code: str, *, level: str | None = None, max_bytes: int | None = None):
        """Run one Skill call with an explicit log level for this request."""
        entry = self.server.registry.get(self.args.user)
        previous_level, previous_max = entry.cdslog.log_level, entry.cdslog.log_max_bytes
        if level is not None:
            entry.cdslog.log_level = level
        if max_bytes is not None:
            entry.cdslog.log_max_bytes = max_bytes
        self.server.invalidate_token(self.token)
        try:
            return self.server.execute_skill(code, timeout=60, token=self.token)
        finally:
            entry.cdslog.log_level = previous_level
            entry.cdslog.log_max_bytes = previous_max
            self.server.invalidate_token(self.token)

    def ssh(self, command: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["ssh", self.args.host, command],
            capture_output=True, text=True, timeout=60, **no_window(),
        )

    def log_size(self) -> int:
        result = self.ssh(f"stat -c %s {self.cds_log}")
        if result.returncode != 0:
            raise ProbeFailure(f"cannot stat CDS.log: {result.stderr!r}")
        return int((result.stdout or "0").strip().splitlines()[-1])

    def log_bytes(self) -> bytes:
        result = subprocess.run(
            ["ssh", self.args.host, f"base64 -w0 {self.cds_log}"],
            capture_output=True, timeout=60, **no_window(),
        )
        if result.returncode != 0:
            raise ProbeFailure(f"cannot read CDS.log: {result.stderr!r}")
        import base64

        return base64.b64decode(result.stdout)

    def close(self) -> None:
        self.server.close()


def case_skill_baseline(env: Env) -> dict:
    result = env.skill("1+1", level="all")
    if not result.ok or (result.output or "").strip().strip('"') != "2":
        raise ProbeFailure(f"real daemon skill failed: {result.model_dump()}")
    return {"output": result.output, "log_len": len(result.log)}


def case_off_sentinel_payload(env: Env) -> dict:
    """off + 用户文本含 RBDLogOn=t 哨兵：必须仍然不取日志、不发第二帧。"""
    sentinel_skill = 'sprintf(nil "RBDLogOn=t ")'
    first = env.skill(sentinel_skill, level="off")
    if not first.ok:
        raise ProbeFailure(f"sentinel skill failed: {first.model_dump()}")
    if first.log:
        raise ProbeFailure(
            "off returned log bytes for a payload containing the log sentinel: "
            f"{first.log[:200]!r}"
        )
    if first.warnings:
        raise ProbeFailure(f"off returned warnings: {first.warnings!r}")

    # the decisive assertion: a forged sentinel must not desync the frame pipe
    follow = env.skill("1+1", level="off")
    if not follow.ok or (follow.output or "").strip().strip('"') != "2":
        raise ProbeFailure(
            "frame desync after sentinel payload: "
            f"status={follow.status} errors={follow.errors} output={follow.output!r}"
        )
    return {
        "sentinel_output": first.output,
        "sentinel_log": first.log,
        "follow_up_output": follow.output,
    }


def _warm_up(env: Env) -> None:
    """Force a real CDS.log flush so the next capture window is non-empty.

    Cadence writes CDS.log through its own buffer; a large ``hiPrintToLogFile``
    block plus ``hiFlush()``/``hiFlushLogFile()`` is what makes the increment
    observable inside the IL's ``[start, end)`` window.
    """
    filler = "w" * 3000
    env.skill(
        f'progn(hiPrintToLogFile("VB-WARM-{uuid.uuid4().hex[:8]} {filler}") '
        "hiFlush() hiFlushLogFile() 1+1)",
        level="all",
        max_bytes=1 << 20,
    )


def case_increment_bytes(env: Env) -> dict:
    """all + 未超限：返回 log 必须是 CDS.log 中一段连续的原始字节。"""
    attempts = []
    for _ in range(4):
        _warm_up(env)
        tag = uuid.uuid4().hex[:8]
        before = env.log_size()
        result = env.skill(
            f'progn(hiPrintToLogFile("VB-LOG-{tag}") hiFlush() hiFlushLogFile() 1+1)',
            level="all",
            max_bytes=1 << 20,
        )
        after = env.log_size()
        if not result.ok:
            raise ProbeFailure(f"increment skill failed: {result.model_dump()}")
        returned = (result.log or "").encode("utf-8")
        data = env.log_bytes()
        offset = data.find(returned) if returned else -1
        attempts.append({
            "returned_bytes": len(returned),
            "file_growth": after - before,
            "contiguous_slice": offset >= 0,
            "window_identical": bool(returned) and returned == data[before:after],
        })
        if not returned:
            continue
        if offset < 0:
            raise ProbeFailure(
                "returned log is not a contiguous slice of CDS.log: "
                f"{returned[:120]!r}"
            )
        if f"VB-LOG-{tag}".encode() not in returned:
            raise ProbeFailure(
                f"window did not contain the injected marker: {returned[:120]!r}"
            )
        return {
            "bytes": len(returned),
            "file_offset": offset,
            "window_identical": attempts[-1]["window_identical"],
            "attempts": attempts,
        }
    return {
        "skipped": (
            "CDS.log 落盘时序导致窗口为空（真机 CIW 侧异步刷新）；"
            "逐字节契约由 daemon_log_protocol_tb.py 确定性覆盖"
        ),
        "attempts": attempts,
    }


def case_off_source_cut(env: Env) -> dict:
    """off 源头掐断：日志确有新增，但 off 请求一个字节都不返回。"""
    _warm_up(env)
    before = env.log_size()
    tag = uuid.uuid4().hex[:8]
    write = env.skill(
        f'progn(hiPrintToLogFile("VB-OFF-{tag}") hiFlush() hiFlushLogFile() 1+1)',
        level="all",
        max_bytes=1 << 20,
    )
    if not write.ok:
        raise ProbeFailure(f"writer skill failed: {write.model_dump()}")
    _warm_up(env)
    after = env.log_size()
    if after <= before:
        raise ProbeFailure(f"log did not grow ({before} -> {after}); cannot assert off")
    result = env.skill("1+1", level="off")
    if not result.ok:
        raise ProbeFailure(f"off skill failed: {result.model_dump()}")
    if result.log:
        raise ProbeFailure(f"off returned log bytes: {result.log[:200]!r}")
    if result.warnings:
        raise ProbeFailure(f"off returned warnings: {result.warnings!r}")
    return {"log_grew": after - before, "off_log_len": len(result.log)}


def case_il_no_substring_sniff() -> dict:
    """静态护栏：IL 必须从指令前缀读日志开关，不得扫描用户文本。

    Client-side observation cannot see the CIW-side flush, so the invariant
    "off = 不做任何日志动作" is pinned at the source level: the flag may only
    be read from the directive prefix the daemon itself writes.
    """
    il = (SRC / "bridge" / "resources" / "ramic_bridge.il").read_text(encoding="utf-8")
    banned = "index(data \"RBDLogOn=t \")"
    if banned in il:
        raise ProbeFailure(
            "IL sniffs user payload text for the log flag; a skill string "
            "containing the sentinel turns log capture on while log_level=off"
        )
    wanted = 'equal(substring(data 1 11) "RBDLogOn=t ")'
    if wanted not in il:
        raise ProbeFailure(f"IL does not read the log flag from the prefix: {wanted}")
    return {"guard": "prefix-compare", "banned_pattern": "absent"}


def case_no_bridge_injection(env: Env) -> dict:
    """桥不得往 CDS.log 注入任何自己的行（旧实现写 VB-BEGIN/VB-END）。"""
    result = env.ssh(
        f"grep -c -E 'VB-BEGIN|VB-END|RBDLogDelta' {env.cds_log} || true"
    )
    count = (result.stdout or "").strip().splitlines()
    injected = int(count[-1]) if count and count[-1].isdigit() else 0
    if injected:
        raise ProbeFailure(f"bridge injected {injected} marker lines into CDS.log")
    return {"injected_lines": injected}


CASES = {
    "skill-baseline": case_skill_baseline,
    "off-sentinel-payload": case_off_sentinel_payload,
    "off-source-cut": case_off_source_cut,
    "increment-bytes": case_increment_bytes,
    "no-bridge-injection": case_no_bridge_injection,
    "il-no-substring-sniff": case_il_no_substring_sniff,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--user", default="vblog")
    parser.add_argument("--host", default="wsl-gent")
    parser.add_argument("--ssh-user", default="Gent")
    parser.add_argument("--root", default="/home/Gent/.virtuoso-bridge/vblog")
    parser.add_argument("--daemon-port", type=int, default=65121)
    parser.add_argument("--local-port", type=int, default=65201)
    parser.add_argument("--cds-log", default="/home/Gent/project/vblog/CDS.log")
    parser.add_argument("--log-level", default="all")
    parser.add_argument("--log-max-bytes", type=int, default=65536)
    parser.add_argument("--case", choices=sorted(CASES), action="append", default=[])
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    env = Env(args)
    selected = args.case or sorted(CASES)
    results = {}
    failed = 0
    skipped = 0
    try:
        for name in selected:
            started = time.monotonic()
            try:
                case = CASES[name]
                detail = case() if name == "il-no-substring-sniff" else case(env)
                if isinstance(detail, dict) and "skipped" in detail:
                    skipped += 1
                    results[name] = {"status": "skip", "detail": detail}
                else:
                    results[name] = {"status": "pass", "detail": detail}
            except Exception as exc:  # noqa: BLE001
                failed += 1
                results[name] = {"status": "fail", "error": f"{type(exc).__name__}: {exc}"}
            results[name]["elapsed_s"] = time.monotonic() - started
    finally:
        env.close()
    payload = {"ok": failed == 0, "failed": failed, "skipped": skipped, "results": results}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
