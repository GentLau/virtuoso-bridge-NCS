"""Calibre 包的纯工具层（stdlib only）：deck 改写、启动器、报告解析。

不含任何中层调用，便于单测；口径见 ``spec/design-concepts/上层/12-calibre.md``。
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

#: 白名单占位符改写（只改这些字面量；DRC / LVS / RCX deck 实测用到）
_PLACEHOLDER_KEYS = (
    ("GDSFILENAME", "gds"),
    ("TOPCELLNAME", "top"),
    ("lvs_top.gds", "gds"),
    ("lvs_top.cdl", "cdl"),
    ("lvs_top", "top"),
)


def deck_rewrite(text: str, *, gds: str, top: str, cdl: str | None = None) -> tuple[str, list[str]]:
    """把 deck 里的占位符替换成本次输入；返回 (新文本, 改动清单)。"""
    values = {"gds": gds, "top": top, "cdl": cdl}
    changes: list[str] = []
    output = text
    for literal, key in _PLACEHOLDER_KEYS:
        replacement = values.get(key)
        if not replacement:
            continue
        quoted = f'"{literal}"'
        if quoted in output:
            output = output.replace(quoted, f'"{replacement}"')
            changes.append(f"{literal} -> {replacement}")
    return output, changes


def deck_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def build_launcher(
    *,
    kind: str,
    run_dir: str,
    argv: Iterable[str] | None = None,
    log_name: str | None = None,
    timeout: int | None = None,
    stages: list[list[str]] | None = None,
    job_meta: dict[str, Any] | None = None,
) -> str:
    """生成 bash 启动器：ulimit → 后台跑 calibre（单段/多阶段）→ 写 job.pid / job.json。

    * 工具跑在**后台子 shell**（launcher 立即返回；状态靠 job.pid + 日志 + 产物判断）；
    * ``stages`` 给多阶段（PEX）：顺序执行，任一段失败即停止并写 ``stageN_failed``；
    * 单段写 ``<kind>.log``；多阶段各写 ``<kind>.stageN.log``，进度标记写 ``<kind>.log``。
    """
    if not argv and not stages:
        raise ValueError("build_launcher needs argv or stages")
    log_name = log_name or f"{kind}.log"
    quoted_run = _shq(run_dir)
    timeout_prefix = f"timeout {int(timeout)} " if timeout else ""
    body_lines: list[str] = ["("]
    if stages:
        for index, stage_argv in enumerate(stages, 1):
            quoted_argv = " ".join(_shq(part) for part in stage_argv)
            body_lines.append(
                f"  {timeout_prefix}{quoted_argv} >> {kind}.stage{index}.log 2>&1"
                f" || {{ echo stage{index}_failed >> {log_name}; exit 1; }}"
            )
        body_lines.append(f"  echo COMPLETED >> {log_name}")
    else:
        quoted_argv = " ".join(_shq(part) for part in (argv or ()))
        body_lines.append(f"  {timeout_prefix}{quoted_argv} > {log_name} 2>&1")
    meta = json.dumps(job_meta or {}, ensure_ascii=False)
    script = "\n".join(
        [
            "#!/bin/bash",
            "ulimit -n 65536 2>/dev/null || true",
            f"cd {quoted_run} || exit 3",
            "cat > job.json <<'VB_JOB_EOF'",
            meta,
            "VB_JOB_EOF",
            *body_lines,
            ") < /dev/null > /dev/null 2>&1 &",
            "echo $! > job.pid",
            "exit 0",
        ]
    )
    return script + "\n"


def _shq(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


# ------------------------------------------------------------------ 状态/解析 --
_DONE_MARKERS = {
    "drc": ("CALIBRE::DRC-H COMPLETED", "TOTAL RESULTS GENERATED"),
    "lvs": ("LVS completed",),
    "pex": ("COMPLETED",),
}
_FAIL_MARKERS = (
    "FATAL ERROR",
    "ERROR:",
    "Can not open",
    "FAILED",
    "ERROR (OSSHNL-",
    "Error while loading",
    "Netlist did not complete",
    "stage1_failed",
    "stage2_failed",
    "stage3_failed",
)
_LICENSE_HINTS = ("license", "licensing", "cannot checkout", "mgcld", "check out")


@dataclass
class JobState:
    status: str  # running / completed / failed / unknown
    failure_kind: str | None = None  # license / input / unknown
    detail: str = ""


def classify_log(log_tail: str) -> str | None:
    """从日志尾判断失败类别；无失败迹象返回 None。"""
    lowered = log_tail.lower()
    if any(marker.lower() in lowered for marker in _FAIL_MARKERS):
        if any(hint in lowered for hint in _LICENSE_HINTS):
            return "license"
        return "input"
    return None


def job_state(kind: str, *, process_alive: bool, log_tail: str, artifacts: list[str]) -> JobState:
    """按 spec §3.4 的三重判据给状态。"""
    markers = _DONE_MARKERS.get(kind, ())
    if any(marker in log_tail for marker in markers):
        return JobState("completed", None, "completion marker found")
    failure = classify_log(log_tail)
    if failure:
        return JobState("failed", failure, "failure marker found in log tail")
    if process_alive:
        return JobState("running", None, "process alive")
    if artifacts:
        return JobState("unknown", None, "process gone but artifacts exist without completion marker")
    return JobState("unknown", None, "process gone, no artifacts")


_DRC_RULES = re.compile(
    r"^TOTAL (?:RULECHECKS EXECUTED\s*=\s*|DRC RuleChecks Executed:\s*)(\d+)", re.M)
_DRC_RESULTS = re.compile(
    r"^TOTAL (?:RESULTS GENERATED\s*=\s*|DRC Results Generated:\s*)(\d+)", re.M)
_DRC_RULECHECK = re.compile(r"^RULECHECK\s+(\S+)\s.*?TOTAL Result Count\s*=\s*(\d+)", re.M)
_DRC_LEGACY_RULE = re.compile(r"^(?:RESULT|CHECK)\s+(\S+)\s+(\d+)", re.M)
_LVS_STATUS = re.compile(r"LVS completed\.\s*([A-Za-z ]+?)(?:\.|\s*$)", re.I)
_LVS_TABLE = re.compile(r"^\s*([A-Za-z][A-Za-z ]*?)\s*:\s+(\d+)\s+(\d+)\s*\*?\s*$", re.M)
_LVS_COUNT = re.compile(r"^\s*(\w[\w ]*?)\s*=\s*(\d+)\s*$", re.M)
_LVS_VERDICTS = {
    "NOT COMPARED": "not_compared",
    "INCORRECT": "incorrect",
    "CORRECT": "correct",
}
_PEX_WARN = re.compile(r"xRC Warnings\s*=\s*(\d+)")
_PEX_ERR = re.compile(r"xRC Errors\s*=\s*(\d+)")
_PEX_NETLIST = re.compile(r"PEX NETLIST FILE\s*=\s*(\S+)")
_LOG_RULES = re.compile(r"TOTAL (?:RULECHECKS EXECUTED\s*=\s*|DRC RuleChecks Executed:\s*)(\d+)")
_LOG_RESULTS = re.compile(r"TOTAL (?:RESULTS GENERATED\s*=\s*|DRC Results Generated:\s*)(\d+)")
_LOG_LVS = re.compile(r"LVS completed\.\s*([A-Za-z ]+?)(?:\.|\s*$)", re.I)
_LOG_PEX_ERR = re.compile(r"xRC Errors\s*=\s*(\d+)")
_LOG_PEX_WARN = re.compile(r"xRC Warnings\s*=\s*(\d+)")


def _normalize_lvs_verdict(raw: str) -> str:
    return _LVS_VERDICTS.get(raw.strip().upper(), "unknown")


def parse_log_counters(text: str) -> dict[str, Any]:
    """从工具日志里抠出稳定计数（DRC/LVS/PEX 三者通用）。"""
    counters: dict[str, Any] = {}
    if match := _LOG_RULES.search(text):
        counters["rules_checked"] = int(match.group(1))
    if match := _LOG_RESULTS.search(text):
        counters["total_results"] = int(match.group(1))
    if match := _LOG_LVS.search(text):
        counters["lvs_status"] = _normalize_lvs_verdict(match.group(1))
    if match := _LOG_PEX_ERR.search(text):
        counters["pex_errors"] = int(match.group(1))
    if match := _LOG_PEX_WARN.search(text):
        counters["pex_warnings"] = int(match.group(1))
    return counters


def parse_drc_report(text: str, *, limit: int = 20) -> dict[str, Any]:
    rules = _DRC_RULES.search(text)
    results = _DRC_RESULTS.search(text)
    by_rule: dict[str, int] = {}
    for match in _DRC_RULECHECK.finditer(text):
        count = int(match.group(2))
        if count:
            by_rule[match.group(1)] = count
    for match in _DRC_LEGACY_RULE.finditer(text):
        by_rule.setdefault(match.group(1), int(match.group(2)))
    return {
        "rules_checked": int(rules.group(1)) if rules else None,
        "total_results": int(results.group(1)) if results else None,
        "by_rule": by_rule,
        # 坐标级明细在 DRC_RES.db（ASCII），由 parse_drc_results_db 解析；
        # .rep 只有统计表，这里不臆造条目。
        "first_offenders": [],
        "report_bytes": len(text),
    }


def parse_drc_results_db(text: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """Parse the ASCII ``DRC_RES.db`` detail file into first offenders.

    结构：首行 `<top cell> <scale>`；每个违规块 = 规则名行（无空格）→
    可选 `N X 3 <date>` 头与 `{ ... }` 规则文本 → 若干 `p <idx> <n>` +
    ``n`` 个坐标点。只取坐标多边形，不解析 layer（db 不携带）。
    """
    lines = text.splitlines()
    cell: str | None = None
    for line in lines:
        if line.strip():
            cell = line.split()[0]
            break

    offenders: list[dict[str, Any]] = []
    index = 0
    while index < len(lines) and len(offenders) < limit:
        rule = lines[index].strip()
        index += 1
        if not rule or " " in rule or not re.fullmatch(r"[A-Za-z0-9_.\-]+", rule):
            continue
        polygons: list[list[tuple[float, float]]] = []
        while index < len(lines):
            stripped = lines[index].strip()
            if not stripped:
                index += 1
                continue
            if re.fullmatch(r"[A-Za-z0-9_.\-]+", stripped):  # 下一个规则名
                break
            if stripped.startswith("p "):
                parts = stripped.split()
                point_count = int(parts[2]) if len(parts) >= 3 else 0
                points: list[tuple[float, float]] = []
                index += 1
                while index < len(lines) and len(points) < point_count:
                    tokens = lines[index].split()
                    index += 1
                    if len(tokens) >= 2:
                        try:
                            points.append((float(tokens[0]), float(tokens[1])))
                        except ValueError:
                            pass
                if points:
                    polygons.append(points)
            else:
                index += 1
        if not polygons:
            continue
        first = polygons[0]
        xs = [point[0] for point in first]
        ys = [point[1] for point in first]
        offenders.append({
            "rule": rule,
            "cell": cell,
            "bbox": [min(xs), min(ys), max(xs), max(ys)],
            "count": len(polygons),
        })
    return offenders


def parse_lvs_report(text: str, *, limit: int = 20) -> dict[str, Any]:
    status_match = _LVS_STATUS.search(text)
    raw_status = (status_match.group(1).strip().upper()
                  if status_match else "")
    if not raw_status:
        for candidate in ("NOT COMPARED", "INCORRECT", "CORRECT"):
            if candidate in text.upper():
                raw_status = candidate
                break
    status = _normalize_lvs_verdict(raw_status)
    counts: dict[str, int] = {}
    for name, layout, source in _LVS_TABLE.findall(text):
        key = name.strip().lower().replace(" ", "_")
        counts[key] = int(layout)
        counts[f"{key}_source"] = int(source)
        if len(counts) >= 40:
            break
    for name, value in _LVS_COUNT.findall(text):
        key = name.strip().lower().replace(" ", "_")
        counts.setdefault(key, int(value))
    differences = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith(("INCORRECT", "Mismatch", "*Mismatch", "Different"))
    ][:limit]
    return {"status": status, "counts": counts, "differences": differences,
            "report_bytes": len(text)}


def parse_pex_log(text: str) -> dict[str, Any]:
    warnings = _PEX_WARN.search(text)
    errors = _PEX_ERR.search(text)
    netlists = _PEX_NETLIST.findall(text)
    return {
        "errors": int(errors.group(1)) if errors else None,
        "warnings": int(warnings.group(1)) if warnings else None,
        "netlist_files": netlists,
        "log_bytes": len(text),
    }


def parse_job_json(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


@dataclass
class StatusSnapshot:
    """`calibre.status` 的一次采样（由包用一条 C 命令采集后解析）。"""

    job_json: dict[str, Any] = field(default_factory=dict)
    pid: int | None = None
    process_alive: bool = False
    log_tail: str = ""
    artifacts: list[str] = field(default_factory=list)


__all__ = [
    "JobState",
    "StatusSnapshot",
    "build_launcher",
    "classify_log",
    "deck_rewrite",
    "deck_sha256",
    "job_state",
    "parse_drc_report",
    "parse_drc_results_db",
    "parse_job_json",
    "parse_lvs_report",
    "parse_pex_log",
    "parse_log_counters",
]
