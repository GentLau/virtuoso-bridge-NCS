"""round10 · 检查"只引用 semi/live 证据"的 spec 行，其证据文件**本轮跑没跑**。

为什么需要：`spec_matrix_r10_audit.py` 只能核对离线证据（JUnit）；剩下的
`NO-OFFLINE-EVIDENCE` 行（23 条）引用的都是半真机/真机 TB —— 必须证明它们
出现在**本轮**的 runner 结果里，否则就是"只靠历史证据"。

输入：本轮四份 runner 结果 + 矩阵 JSON；输出：`live-evidence-currency-r10.md`。

用法：`python test/reports/round10/live_evidence_currency.py`
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
V = ROOT / "test" / "artifacts" / "evidence" / "round10"
MATRIX = ROOT / "test" / "reports" / "round8" / "round8-spec覆盖矩阵.json"
OUT = Path(__file__).resolve().parent / "live-evidence-currency-r10.md"


def _load(path: Path):
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    gate = _load(V / "http-gate-results.json") or {}
    flows = _load(V / "flows" / "summary.json") or {}
    reg = _load(V / "registration" / "summary.json") or {}
    semi = _load(V / "semi-probes-r10.json") or {}

    gate_map = {s["suite"]: s["ok"] for s in gate.get("suites", [])}

    def ran_this_round(name: str) -> str:
        file_part, _, case_part = name.partition("::")
        base = Path(file_part).name
        if base in gate_map:
            ok = gate_map[base]
            if ok:
                return "HTTP 门禁 PASS"
            # 套件整体红（可能是末位红钉）：若该行点名了用例，就从套件日志里核对
            # "这条用例自己 PASS"——避免把 NKM-09 的钉子算到 NKM-07a 头上。
            if case_part:
                log = V / f"{base}.log"
                if log.is_file():
                    text = log.read_text(encoding="utf-8", errors="replace")
                    if any(line.startswith("PASS") and case_part in line
                           for line in text.splitlines()):
                        return f"HTTP 门禁 FAIL(红钉)，但 `{case_part}` PASS"
            return "HTTP 门禁 FAIL"
        if base == "registration_http_six_step_tb.py":
            six = [c for c in reg.get("cases", []) if c["case"].startswith("six_")]
            if six:
                ok = all(c["rc"] == 0 for c in six)
                return f"registration six-step {'PASS' if ok else 'FAIL'}"
        for flow in flows.get("flows", []):
            if base.startswith(Path(flow["log"]).stem):
                return f"flows {'PASS' if flow['rc'] == 0 else 'FAIL'}"
        for case in reg.get("cases", []):
            if case["case"] in base:
                return f"registration {'PASS' if case['rc'] == 0 else 'FAIL'}"
        for probe in semi.get("results", []):
            if probe["probe"] == base:
                return f"semi {'PASS' if probe['status'] == 'ok' else 'FAIL'}"
        if name.startswith("test/semi/"):
            for probe in semi.get("results", []):
                if Path(probe["probe"]).stem in Path(name).stem:
                    return f"semi {'PASS' if probe['status'] == 'ok' else 'FAIL'}"
        return "—（静态/产物或本轮未跑）"

    rows = json.loads(MATRIX.read_text(encoding="utf-8"))
    live_rows = []
    for row in rows:
        ev = row.get("evidence") or []
        if isinstance(ev, str):
            ev = [ev]
        # 保留 `path::case` 形式：套件整体红（末位红钉）时要能点名核对"这条用例自己 PASS"。
        ev = [str(e) for e in ev]
        if any(e.startswith("test/offline/") for e in ev):
            continue
        if row.get("verdict") == "na":
            continue          # na 条款本就不要求证据
        live_rows.append((row, ev))

    lines = [
        "# round10 · 半真机/真机证据的本轮复跑核对（机器生成）",
        "",
        f"> 输入：`{MATRIX.relative_to(ROOT).as_posix()}` 里 **{len(live_rows)} 条没有离线证据** 的行；",
        "> 本轮 runner 结果：HTTP 门禁 25 套、flows 9 场景、registration 9 场景、semi 48 探针。",
        "> 判定：该行引用的 semi/live TB 在本轮跑过且绿 = ✅；否则如实标出。",
        "",
        "| 条款 | verdict | 引用证据 | 本轮状态 |",
        "|---|---|---|---|",
    ]
    unresolved = []
    for row, ev in live_rows:
        statuses = []
        for e in ev:
            file_part = e.split("::")[0]
            if file_part.startswith("src/") or file_part.startswith("test/artifacts/"):
                continue
            statuses.append(f"`{Path(file_part).name}`：{ran_this_round(e)}")
        if not statuses:
            statuses = ["—（只引用产物/源码锚点）"]
        if not any("PASS" in s for s in statuses):
            unresolved.append(row["id"])
        lines.append(f"| {row['id']} | {row.get('verdict')} | " +
                     "<br>".join(statuses) + " |")
    lines += ["", f"> **没有任何本轮 PASS 依据的行：{len(unresolved)}** → "
                  + (", ".join(unresolved) if unresolved else "无")]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(live_rows)} rows; unresolved={len(unresolved)}; -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
