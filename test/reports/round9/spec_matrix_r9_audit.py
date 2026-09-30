"""round9 · spec 条款矩阵复核（只读输入，产物写 round9）。

两件事：
 1. **新鲜度**：round8 矩阵 297 条里，每条引用的离线证据在本轮（round9）JUnit 里
    跑过没有、绿不绿 → 给每行一个 `r9_status`；
 2. **变更影响**：本轮代码/口径变更（C1/C2/C4、P-070/083/084/089/091/092/093/094/098/102/103/104/105）
    可能让哪些条款的旧结论失效 → 按关键词命中列出，供人工改判。

用法：`python test/reports/round9/spec_matrix_r9_audit.py`
"""
from __future__ import annotations

import collections
import json
import pathlib
import re
import sys
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = pathlib.Path(__file__).resolve().parent
MATRIX = ROOT / "test/reports/round8/round8-spec覆盖矩阵.json"
JUNIT = ROOT / "test/artifacts/evidence/round9/offline-windows-r9.xml"
CORE = ROOT / "test/artifacts/evidence/round9/core-multi-r9.json"

#: 本轮变更 → 关键词（命中即"旧结论可能失效，需人工改判"）
CHANGES = {
    "C1 响应契约（成功默认省略 steps / 失败壳 / CDSlog / 删 metadata / execution_time）":
        [r"\bsteps?\b", r"step_details", r"CDSlog", r"metadata", r"execution_time", r"data 壳", r"响应体"],
    "C2 log_level / log_max_bytes（56 skill op）":
        [r"log_level", r"log_max_bytes", r"日志级别", r"降级", r"截断"],
    "C4 CommandResult 命名字段": [r"CommandResult", r"returncode", r"命令结果"],
    "P-070 Monte Carlo 驱动": [r"monte", r"蒙特卡洛", r"mcnumpoints", r"yield"],
    "P-083 spectre precision=有效数字": [r"precision", r"有效数字"],
    "P-084 删 include_results": [r"include_results"],
    "P-089 open_waveform result 删除": [r"open_waveform", r"waveform"],
    "P-091 截图远端暂存口径": [r"screenshot", r"截图", r"远端暂存"],
    "P-092 删 calibre power/ground": [r"\bpower\b", r"\bground\b"],
    "P-093/094 flat DRC 不带 -turbo / 秒退判定": [r"turbo", r"\bflat\b", r"秒退", r"进程消失"],
    "P-098 blocking 超时 status=timeout": [r"blocking", r"status\s*=?\s*timeout", r"超时后.*状态"],
    "P-102/103 PEX 本版不提供": [r"\bpex\b"],
    "P-104 maeOpenSetup 读路径 mode=r": [r"maeOpenSetup", r"read_config", r"读路径"],
    "P-105 screenshot view_type 校验": [r"view_type", r"截图"],
}


def junit_state(path: pathlib.Path) -> dict[str, dict]:
    """{点号模块名: {"total","red","skipped"}}（classname 去掉类名后缀）。"""
    state: dict[str, dict] = {}
    if not path.is_file():
        return state
    tree = ET.parse(path)
    for case in tree.iter("testcase"):
        raw = case.get("classname") or ""
        parts = raw.split(".")
        if parts and parts[-1][:1].isupper():
            parts = parts[:-1]  # 去掉类名
        module = ".".join(parts)
        entry = state.setdefault(module, {"total": 0, "red": 0, "skipped": 0})
        entry["total"] += 1
        if case.find("failure") is not None or case.find("error") is not None:
            entry["red"] += 1
        if case.find("skipped") is not None:
            entry["skipped"] += 1
    return state


def match_state(ev_path: str, junit: dict[str, dict]) -> dict | None:
    module = ev_path[:-3].replace("/", ".") if ev_path.endswith(".py") else ev_path
    if module in junit:
        return junit[module]
    for key, value in junit.items():  # 兜底：按文件名匹配
        if key.split(".")[-1] == module.split(".")[-1]:
            return value
    return None


def main() -> int:
    rows = json.loads(MATRIX.read_text(encoding="utf-8"))
    junit = junit_state(JUNIT)
    core_ok = False
    core_cases = 0
    if CORE.is_file():
        core = json.loads(CORE.read_text(encoding="utf-8"))
        core_ok = bool(core.get("ok"))
        core_cases = len(core.get("results") or {})
    out_rows = []
    counts = collections.Counter()
    for row in rows:
        evidence = row.get("evidence") or []
        if isinstance(evidence, str):
            evidence = [evidence]
        # `path::test_name` 形式：按 matrix 工具口径忽略 `::` 后缀
        evidence = [str(e).split("::")[0] for e in evidence]
        offline = [e for e in evidence if e.startswith("test/offline/")]
        others = [e for e in evidence if not e.startswith("test/offline/")]
        status, detail = "NO-OFFLINE-EVIDENCE", {}
        if row.get("verdict") == "na" and not offline:
            status, detail = "NA-NO-EVIDENCE-NEEDED", {}   # na 行本就不要求证据
        if offline:
            greens, reds, missing = [], [], []
            for ev in offline:
                st = match_state(str(ev), junit)
                if st is None and core_ok and "/core/" in ev:
                    st = {"total": core_cases, "red": 0, "skipped": 0}
                    greens.append({"file": ev, "source": "core-multi-r9", **st})
                    continue
                if st is None:
                    note = "" if (ROOT / ev).is_file() else "（文件不存在）"
                    missing.append(f"{ev}{note}")
                elif st["red"]:
                    reds.append({"file": ev, **st})
                else:
                    greens.append({"file": ev, **st})
            if reds:
                status, detail = "R9-RED", {"red": reds, "green": greens}
            elif greens:
                status, detail = "R9-GREEN", {"green": greens, "missing": missing}
            else:
                status, detail = "R9-NOT-IN-XML", {"missing": missing}
        counts[status] += 1
        out_rows.append({
            "id": row.get("id"), "doc": row.get("doc"), "section": row.get("section"),
            "verdict": row.get("verdict"), "r9_status": status,
            "text": (row.get("text") or "")[:220], "evidence": evidence, "detail": detail,
        })

    matched = []
    for row in rows:
        blob = " ".join([str(row.get("text") or ""), str(row.get("section") or ""),
                         str(row.get("doc") or "")])
        hits = [name for name, pats in CHANGES.items()
                if any(re.search(p, blob, re.I) for p in pats)]
        if hits:
            matched.append({"id": row.get("id"), "verdict": row.get("verdict"),
                            "doc": row.get("doc"), "section": row.get("section"),
                            "changes": hits, "text": (row.get("text") or "")[:200]})

    doc = {
        "generated_from": str(MATRIX.relative_to(ROOT)),
        "junit": str(JUNIT.relative_to(ROOT)),
        "rows_total": len(rows),
        "verdict_counts": dict(collections.Counter(r.get("verdict") for r in rows)),
        "r9_status_counts": dict(counts),
        "rows": out_rows,
        "change_impact_candidates": matched,
    }
    (OUT / "spec-matrix-r9-b.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    lines = ["# round9 · spec 条款矩阵复核（B 线代跑 A 线；机器结论）", "",
             f"- 输入矩阵：`{MATRIX.relative_to(ROOT).as_posix()}`（297 条）",
             f"- 本轮 JUnit：`{JUNIT.relative_to(ROOT).as_posix()}`（{len(junit)} 个测试文件）",
             f"- 旧结论分布：{doc['verdict_counts']}",
             f"- **本轮离线证据状态**：{doc['r9_status_counts']}"
             f"（脚本式 core TB 由 `{CORE.name}` 覆盖，ok={core_ok}，{core_cases} 用例）",
             f"- 变更影响候选：**{len(matched)}** 条（需逐条改判）", "",
             "| 状态 | 条数 | 含义 |", "|---|---|---|",
             "| R9-GREEN | %d | 引用的离线证据文件本轮跑过且无红 |" % counts["R9-GREEN"],
             "| NA-NO-EVIDENCE-NEEDED | %d | 条款本身标 na（不要求证据） |" % counts["NA-NO-EVIDENCE-NEEDED"],
             "| R9-RED | %d | 本轮有红 → 该条款结论依赖已立案缺陷 |" % counts["R9-RED"],
             "| R9-NOT-IN-XML | %d | 有离线证据文件但本轮 JUnit 里没有 |" % counts["R9-NOT-IN-XML"],
             "| NO-OFFLINE-EVIDENCE | %d | 只引用了 semi/live/产物类证据（需另核） |" % counts["NO-OFFLINE-EVIDENCE"],
             ]
    (OUT / "spec-matrix-r9-b.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("旧结论:", doc["verdict_counts"])
    print("本轮状态:", doc["r9_status_counts"])
    print("变更影响候选:", len(matched))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
