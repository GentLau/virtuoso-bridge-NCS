# -*- coding: utf-8 -*-
"""**原子级**覆盖核账（离线 ≠ 覆盖）：把每个写原子在 离线/半真机/真机 三层的引用面摊开。

为什么需要它（2026-09-27 独立审计 C0 卡的教训）：`test/docs/测试架构.md §3` 的覆盖度模型是
**能力域级**（"上层业务包 schematic 有没有测"），粒度太粗 —— 一个包里 17 个原子，
只要测过 `place_*` 就容易被记成"包已覆盖"，于是 delete/rename/set 类原子被系统性漏掉。
本脚本把粒度下沉到**原子**，并明确区分：

* `refs`：原子名在该层测试文件里出现几次（**只代表引用面**，不代表真机执行过）；
* `gap`：semi/live 两层**零引用** → 这是"从未在真机跑过"的强信号（离线文本断言不算）；
* `weak`：写了却没有读回/比对的候选（启发式，需人工分类，见 `KNOWN_FALSE_POSITIVES`）。

用法::

    $env:PYTHONPATH='src'
    python test/shared/runners/audit_atom_coverage.py                 # 打印 + 写 JSON
    python test/shared/runners/audit_atom_coverage.py --md            # 额外输出 Markdown 表
    python test/shared/runners/audit_atom_coverage.py --fail-on-gap   # 有 gap 时 rc=1（将来可入门禁）

证据：默认 `test/artifacts/evidence/atom-coverage-<date>.json`。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LAYERS = {"offline": "test/offline", "semi": "test/semi", "live": "test/live"}
DEFAULT_PKGS = ("schematic", "layout", "symbol")

# 注意 `(?<![\w.])`：`prop in (...)`、`cmd.get('x') == ...` 这类写法里也含 "op"，
# 不加前置断言会把变量名里的 op 当原子（第一版就把 `prop in (("justify", ...))` 误抓成原子 justify）。
ATOM_EQ_RE = re.compile(r'(?<![\w.])op\s*==\s*"([a-z_0-9]+)"')
OP_IN_NAME_RE = re.compile(r"(?<![\w.])op\s+(?:in|not in)\s+(_[A-Z_]+)")
INLINE_IN_RE = re.compile(r"(?<![\w.])op\s+(?:in|not in)\s+\(([^)]*)\)")
TUPLE_RE = re.compile(r"^(_[A-Z_]+)\s*=\s*\(([^)]*)\)", re.M)

#: 人工复核过的"写了不读回"误报（每条都要写清理由，别默默加进来）
KNOWN_FALSE_POSITIVES = {
    ("test/live/packages/layout_e2e_tests.py", "layout.gds"):
        "同文件大量 `virtuoso.layout.read` + `_check`；GDS 用「导出成功 + 后续 read」判定",
    ("test/live/flows/s11_inprocess_lvs_tb.py", "basic.file.upload"):
        "上传件被下游 LVS 消费，判据是 `lvs.rep` 里 grep CORRECT/INCONCLUSIVE",
    ("test/live/stress/layout_multiuser_lock_tb.py", "layout.write"):
        "并发锁语义 TB，判据就是各次 write 的成败与结构化拒绝",
    ("test/live/flows/layout_suite_p044_workaround_tb.py", "layout.gds"):
        "GDS-01 是 export+import round-trip 用例，判据在 round-trip 结果",
    ("test/semi/probes/layout_lock_ownership_probe.py", "layout.write"):
        "判据是 append-open 结果 + write 错误串是否含 locked（R7-TB-14 改造后）",
    ("test/semi/probes/layout_p044_second_write_probe.py", "layout.write"):
        "判据是第二次 write 的成败（P-044 本身）",
    ("test/semi/probes/symbol_regen_handle_probe.py", "symbol.generate"):
        "判据是 SKILL 查询的视图打开状态（dbFindOpenCellViewByName），非 DB 读回",
    ("test/semi/probes/symbol_generate_hierarchy_handle_probe.py", "symbol.generate"):
        "同上：判据是子单元 symbol 打开状态",
    ("test/semi/probes/symbol_http_400_repro.py", "symbol.generate"):
        "负控制 TB：判据是 HTTP 400 与错误串",
    ("test/semi/probes/calibre_env_probe.py", "calibre.lvs"):
        "命中的是 docstring/命令模板里的字面量，该探针只报环境事实",
    ("test/semi/probes/calibre_env_probe.py", "calibre.drc"):
        "同上",
    ("test/live/packages/calibre_e2e_tests.py", "basic.file.upload"):
        "上传的 runset 立刻被 `calibre.lvs` 消费，随后 `_check(mode/run_dir)` 断言（下游判据）",
    ("test/live/flows/layout_suite_p044_workaround_tb.py", "layout.write"):
        "并发锁套件：判据是各 case 的 verdict（含 write 成败/结构化拒绝）",
    ("test/semi/probes/symbol_regen_handle_probe.py", "schematic.write"):
        "探针自己造前置用的 write；判据在后续 3 次 `symbol.generate` 的句柄态"
        "（每次必须 ok 且 `dbFindOpenCellViewByName` 为 CLOSED）",
    ("test/semi/probes/calibre_flat_turbo_probe.py", "basic.file.upload"):
        "round9 补记：上传的 deck 由下游 `calibre.drc` 消费，判据是 flat 模式不带 -turbo"
        "（argv/日志）且 DRC.rep 产出（P-093）；上传本身另有 `ok is True` 断言",
    ("test/semi/probes/calibre_timeout_probe.py", "basic.file.upload"):
        "round9 补记：上传的坏 deck 由下游 `calibre.drc` 消费，判据是 `status=timeout`"
        "（P-098）；上传本身另有 `ok is True` 断言",
}

#: **间接验证**：写操作本身没读回，但它的产物被后一步消费且那一步有断言
#: 2026-09-28 B3：ADC / 多用户 SerDes 已补 `symbol.read` 端口直接比对，表清空。
INDIRECT_JUDGEMENTS = {}

#: 已知"判据偏弱"（接口 ok 即算过，不看结果内容）——不是缺口，但报告里要点名
#: 2026-09-28 B3：serdes 的 calibre 段已补 read_results 断言、S11 gds 已补 stat+sha256，表清空。
WEAK_JUDGEMENTS = {}

#: 写操作 → 期望的读回/比对动作（弱判据检测用）
WRITE_VERIFIERS = [
    ("schematic.write", ("schematic.read", "schCheck", "check_and_save")),
    ("layout.write", ("layout.read",)),
    ("layout.gds", ("layout.read", "stat ", "sha256sum", "ls -l", "round")),
    ("symbol.generate", ("symbol.read",)),
    ("calibre.lvs", ("read_results", "calibre.status", "lvs.rep")),
    ("calibre.drc", ("read_results", "calibre.status", "DRC.rep")),
    ("spectre.run", ("measure", "data", "run_dir")),
    ("basic.file.upload", ("download", "sha256", "cmp ")),
]


def atoms_of(pkg: str) -> set[str]:
    src = ROOT / "src" / "pyapi" / "packages" / f"{pkg}.py"
    text = src.read_text(encoding="utf-8")
    atoms = set(ATOM_EQ_RE.findall(text))
    tuples = {name: re.findall(r'"([a-z_0-9]+)"', body)
              for name, body in TUPLE_RE.findall(text)}
    for name in set(OP_IN_NAME_RE.findall(text)) & set(tuples):
        atoms.update(tuples[name])
    for body in INLINE_IN_RE.findall(text):
        atoms.update(re.findall(r'"([a-z_0-9]+)"', body))
    return atoms


def evidence_hits(atoms: set[str]) -> dict[str, int]:
    """第二来源：原子是否**真的被执行过**——扫 `test/artifacts/evidence/**/*.json` 的请求痕迹。

    判据形态（实测）：
    * `"op": "<原子>"`（write 请求体，见 `evidence/s11-round3/s11-layout.json`）；
    * `"name": "command:<原子>"`（步骤名，见 `evidence/round4-scenario/serdes/*.json`）。

    排除本核账脚本自己的产物（否则会自我命中）。只扫 <=4MB 的 JSON，避免把整个证据树读进内存
    （实测证据树 ~430MB，JSON 部分 ~57MB）。
    """
    patterns = {atom: (re.compile(r'"op"\s*:\s*"' + re.escape(atom) + r'"'),
                       re.compile(r'"name"\s*:\s*"command:' + re.escape(atom) + r'"'))
                for atom in atoms}
    hits = {atom: 0 for atom in atoms}
    root = ROOT / "test" / "artifacts" / "evidence"
    for path in root.rglob("*.json"):
        name = path.name
        if name.startswith("atom-coverage-"):
            continue
        try:
            if path.stat().st_size > 4 * 1024 * 1024:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for atom, (op_re, step_re) in patterns.items():
            if op_re.search(text) or step_re.search(text):
                hits[atom] += 1
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pkg", action="append", default=[])
    parser.add_argument("--md", action="store_true")
    parser.add_argument("--fail-on-gap", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    pkgs = args.pkg or list(DEFAULT_PKGS)

    corpus: dict[str, dict[str, str]] = {}
    for layer, rel in LAYERS.items():
        corpus[layer] = {p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8", errors="replace")
                         for p in (ROOT / rel).rglob("*.py") if p.is_file()}

    all_atoms: set[str] = set()
    per_pkg: dict[str, set[str]] = {}
    for pkg in pkgs:
        per_pkg[pkg] = atoms_of(pkg)
        all_atoms |= per_pkg[pkg]
    ev_hits = evidence_hits(all_atoms)

    rows: list[dict] = []
    for pkg in pkgs:
        for atom in sorted(per_pkg[pkg]):
            refs = {layer: sum(1 for text in corpus[layer].values() if atom in text)
                    for layer in LAYERS}
            rows.append({"pkg": pkg, "atom": atom, "refs": refs,
                         "evidence_files": ev_hits.get(atom, 0),
                         "gap": refs["semi"] == 0 and refs["live"] == 0})

    weak: list[dict] = []
    for layer in ("semi", "live"):
        for rel, text in sorted(corpus[layer].items()):
            for write_op, verifiers in WRITE_VERIFIERS:
                if write_op not in text or any(v in text for v in verifiers):
                    continue
                key = (rel, write_op)
                kind = ("false-positive" if key in KNOWN_FALSE_POSITIVES
                        else "indirect" if key in INDIRECT_JUDGEMENTS
                        else "weak" if key in WEAK_JUDGEMENTS else "needs-triage")
                weak.append({"file": rel, "write_op": write_op, "kind": kind,
                             "note": KNOWN_FALSE_POSITIVES.get(key)
                                     or INDIRECT_JUDGEMENTS.get(key)
                                     or WEAK_JUDGEMENTS.get(key) or ""})

    gaps = [row for row in rows if row["gap"]]
    payload = {
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "packages": pkgs,
        "atoms_total": len(rows),
        "gap_atoms": [f"{r['pkg']}.{r['atom']}" for r in gaps],
        "gap_atoms_never_in_evidence": [f"{r['pkg']}.{r['atom']}" for r in gaps
                                        if r["evidence_files"] == 0],
        "control_place_rect_evidence_files": ev_hits.get("place_rect", 0),
        "gap_count": len(gaps),
        "rows": rows,
        "write_without_readback": weak,
        "needs_triage": [w for w in weak if w["kind"] == "needs-triage"],
    }
    out = Path(args.out) if args.out else (
        ROOT / "test" / "artifacts" / "evidence"
        / f"atom-coverage-{dt.date.today().isoformat()}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"原子总数 {len(rows)}；semi/live 零引用 {len(gaps)}"
          f"（其中证据树里也查不到的 {payload['gap_atoms_never_in_evidence'].__len__()} 个）；"
          f"阳性对照 place_rect 出现在 {payload['control_place_rect_evidence_files']} 个证据文件里")
    for name in payload["gap_atoms"]:
        print("  -", name)
    triage = payload["needs_triage"]
    print(f"\n写了不读回：需人工分类 {len(triage)} 条，"
          f"已知误报 {sum(1 for w in weak if w['kind'] == 'false-positive')} 条，"
          f"已知弱判据 {sum(1 for w in weak if w['kind'] == 'weak')} 条")
    for item in triage:
        print(f"  - {item['file']} ← {item['write_op']}")
    print(f"\nevidence: {out}")

    if args.md:
        print("\n| 原子 | offline | semi | live | 证据文件 | 判定 |")
        print("|---|---:|---:|---:|---:|---|")
        for row in rows:
            mark = ("**GAP（真机未跑 + 证据树无痕）**"
                    if row["gap"] and row["evidence_files"] == 0
                    else "**GAP（真机未跑）**" if row["gap"] else "有引用")
            print(f"| `{row['pkg']}.{row['atom']}` | {row['refs']['offline']} | "
                  f"{row['refs']['semi']} | {row['refs']['live']} | "
                  f"{row['evidence_files']} | {mark} |")

    return 1 if (args.fail_on_gap and gaps) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
