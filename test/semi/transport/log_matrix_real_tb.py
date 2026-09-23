"""Real-machine CDS.log matrix TB (Windows client -> real Virtuoso daemon).

Covers the machine-facing half of ``test/plans/日志返回.md``: byte identity with
``CDS.log``, the ``off`` source cut (including the 内容嗅探 regression), level
filtering on real ``\\e`` / ``\\w`` lines, and the no-injection guarantee.

Run with::

    PYTHONPATH=src python test/semi/transport/log_matrix_real_tb.py \
        --work-dir test/artifacts/env/log-vblog --token vb-vblog

The registry must already contain the token (see test/README.md).
The live CIW log path is discovered from the daemon (``hiGetLogFileName()``);
``--cds-log`` is only needed to pin an explicit file.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
_SUPPORT = Path(__file__).resolve().parents[2] / "shared" / "fixtures"
if str(_SUPPORT) not in sys.path:
    sys.path.insert(0, str(_SUPPORT))

from transport.middle import BusinessServer  # noqa: E402
from common.registry import UserEntry, load_registry  # noqa: E402
from common.paths import registry_path, override_work_dir_for_tests  # noqa: E402

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
        override_work_dir_for_tests(self.work_dir)
        registry = load_registry(registry_path())
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
        self.cds_log = args.cds_log or self._discover_log_path()

    def _discover_log_path(self) -> str:
        """Ask the live CIW which file it actually logs to.

        Virtuoso may be started with ``-log FILE`` or from any cwd, so the
        on-disk file is authoritative.  A hardcoded default silently goes
        stale (the old default pointed at a CDS.log frozen by a 2026-09-21
        crash, which was misread as a bridge log-capture defect).
        """
        result = self.skill("hiGetLogFileName()", level="off")
        if not result.ok:
            raise ProbeFailure(
                "cannot discover the live CIW log file (hiGetLogFileName): "
                f"{result.model_dump()}"
            )
        path = (result.output or "").strip().strip('"')
        if not path:
            raise ProbeFailure("hiGetLogFileName() returned an empty path")
        return path

    def skill(self, code: str, *, level: str | None = None, max_bytes: int | None = None):
        """Run one Skill call with an explicit log level for this request."""
        return self.server.execute_skill(
            code,
            timeout=60,
            token=self.token,
            log_level=level,
            log_max_bytes=max_bytes,
        )

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
        if not attempts[-1]["window_identical"]:
            # a contiguous sub-slice is not the contract: the delta must be
            # exactly the file interval produced by this request.  Retry while
            # the CIW's asynchronous log flush catches up.
            continue
        return {
            "bytes": len(returned),
            "file_offset": offset,
            "window_identical": True,
            "attempts": attempts,
        }
    raise ProbeFailure(
        "CDS.log delta window did not match byte-for-byte within 4 attempts "
        f"(attempts: {attempts}); daemon_log_protocol_tb.py only covers the "
        "daemon side. If every attempt has contiguous_slice=true but "
        "file_growth > returned_bytes, another client wrote to the same CIW "
        "during the window: this case requires exclusive daemon access."
    )


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


def case_il_log_flag_prefix_guard() -> dict:
    """静态源码护栏（**不是行为红灯**）：IL 只能从指令前缀读日志开关。

    为什么是静态的：`log_level=off` 时 IL 若被用户文本误导，只会多做一次
    CIW 侧 flush/fileLength 并多发一帧；该帧被 daemon 丢弃，客户端不可观察
    （见 `off-sentinel-payload` 用例）。因此“off = 不做任何日志动作”这条
    设计不变量用源码护栏固定，报告中必须标明其性质。
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
    return {
        "guard": "prefix-compare",
        "banned_pattern": "absent",
        "kind": "static-source-guard",
        "note": "not a behavioural red case; see off-sentinel-payload",
    }


def case_no_bridge_injection(env: Env) -> dict:
    """桥不得往 CDS.log 注入任何自己的行（旧实现写 VB-BEGIN/VB-END）。"""
    result = env.ssh(
        f"grep -c -E 'VB-BEGIN|VB-END|RBDLogDelta' {env.cds_log} || true"
    )
    if result.returncode != 0:
        raise ProbeFailure(
            f"cannot inspect CDS.log for injected markers: {result.stderr!r}"
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
    "il-log-flag-prefix-guard": case_il_log_flag_prefix_guard,
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
    parser.add_argument(
        "--cds-log",
        default="",
        help="CIW log file to compare against; default: ask the live CIW "
        "(hiGetLogFileName())",
    )
    parser.add_argument("--log-level", default="all")
    parser.add_argument("--log-max-bytes", type=int, default=65536)
    parser.add_argument("--case", choices=sorted(CASES), action="append", default=[])
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    env = Env(args)
    selected = args.case or sorted(CASES)
    results = {}
    failed = 0
    try:
        for name in selected:
            started = time.monotonic()
            try:
                case = CASES[name]
                detail = case() if name == "il-log-flag-prefix-guard" else case(env)
                results[name] = {"status": "pass", "detail": detail}
            except Exception as exc:  # noqa: BLE001
                failed += 1
                results[name] = {"status": "fail", "error": f"{type(exc).__name__}: {exc}"}
            results[name]["elapsed_s"] = time.monotonic() - started
    finally:
        env.close()
    payload = {
        "ok": failed == 0,
        "failed": failed,
        "cds_log": env.cds_log,
        "work_dir": str(env.work_dir),
        "token": args.token,
        "results": results,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
