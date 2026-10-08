"""生成「op × 输出字段」矩阵（《全量测试准则》表 C 的第一版工具）。

为什么需要它：C06（`print` 的返回值没人断言）与 P-107（失败 run 的 `status/errors` 没人断言）
都是「输出字段没有被逐项比对」造成的。本工具把"**每个 op 可能返回哪些字段**"抽出来，
再扫 TB 里有没有对这些字段的断言，产出"未比对字段"清单。

方法（**静态近似**，口径写在输出里，不冒充真机判据）：

1. 从 `src/pyapi/packages/*.py` 的 `OPERATIONS = (...)` 表拿到 `op → 处理函数`；
2. 用 AST 扫该处理函数（含它调用的同模块 helper 一层）里的**字典字面量字符串键**，
   作为"这个 op 可能返回的业务字段"；
3. 永远附加通用信封字段：`ok / error / value / result / steps / CDSlog / warnings / errors`；
4. 在 `test/`（排除 `reports/ artifacts/ plans/ docs/ shared/archive/`）里搜每个字段名：
   * 出现在 `assert` / `self.assert*` / `_check(` / `ev.check` 行 → `asserted`
   * 只出现、不在断言行 → `read_only`
   * 完全没出现 → `absent`
5. 同时统计每个 op 在 **live/semi**（真机/半真机）里的调用点数量 —— 0 表示"没有实际执行证据"。

用法::

    PYTHONPATH=src python test/shared/runners/build_output_field_matrix.py \
        --out test/reports/round9/output-field-matrix.json \
        --md test/reports/round9/output-field-matrix.md

已知局限（下一版要补）：
* 处理函数里的字典键可能包含"请求回显"而非"输出字段"（会多报）；
* helper 只跟一层，跨模块构造的字段可能漏；
* "出现在断言行"不等于"断言成立"，最终仍需人工/真机确认（本工具只负责把清单缩小）。
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "pyapi" / "packages"
TEST = ROOT / "test"
EXCLUDE_DIRS = ("reports", "artifacts", "plans", "docs", "shared/archive", "shared")
ENVELOPE = ("ok", "error", "value", "result", "steps", "CDSlog", "warnings", "errors")
ASSERT_HINT = re.compile(r"assert|_check\(|check_true|check\(|_expect|fail\(", re.IGNORECASE)

#: 已知"非行内断言"形态：(op, field) → 人工核对过的证据指针。
#: 这些字段的**判据真实存在**，但写法（多行 assert / checks 字典 + for 循环）扫描器
#: 认不出来。每条都必须写清 file:行，便于复核；不要再往这里塞"没把握"的条目。
KNOWN_ASSERTED: dict[tuple[str, str], str] = {
    ("virtuoso.maestro.read_history", "points_done"):
        "test/live/packages/maestro_mc_e2e_tests.py:561-576 checks 字典逐字段断言（=points_total）",
    ("virtuoso.maestro.read_history", "points_total"):
        "test/live/packages/maestro_mc_e2e_tests.py:553-557 + 561-576",
    ("virtuoso.maestro.read_history", "tests_done"):
        "test/live/packages/maestro_mc_e2e_tests.py:564 同 checks 循环（=tests_total）",
    ("virtuoso.maestro.read_history", "tests_total"):
        "test/live/packages/maestro_mc_e2e_tests.py:561-576 checks 循环",
    ("virtuoso.maestro.read_history", "corners_done"):
        "test/live/packages/maestro_mc_e2e_tests.py:565 同 checks 循环（=corners_total）",
    ("virtuoso.maestro.read_history", "corners_total"):
        "test/live/packages/maestro_mc_e2e_tests.py:561-576 checks 循环",
    ("virtuoso.maestro.read_history", "overwrite_target"):
        "test/live/packages/maestro_mc_e2e_tests.py:567 同 checks 循环（==history）",
    ("virtuoso.maestro.read_config", "models"):
        "test/live/packages/maestro_nested_keys_e2e_tests.py::NKM-03 多行 assert any(model.file/section)",
    ("virtuoso.maestro.read_config", "job_policy"):
        "test/live/packages/maestro_nested_keys_e2e_tests.py::NKM-05/NKM-09 断言 policy['simulation']/['netlisting']",
    ("virtuoso.maestro.read_config", "netlisting"):
        "test/live/packages/maestro_nested_keys_e2e_tests.py::NKM-09（P-118 红钉）显式读并断言 netlisting",
}


def iter_test_files() -> list[Path]:
    files: list[Path] = []
    for path in TEST.rglob("*.py"):
        rel = path.relative_to(TEST).as_posix()
        if any(rel.startswith(prefix + "/") for prefix in EXCLUDE_DIRS):
            continue
        files.append(path)
    return files


def operations(pkg: Path) -> list[tuple[str, str]]:
    """抽出 `OPERATIONS` 里的 (op 名, 处理函数名)。"""
    try:
        tree = ast.parse(pkg.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    found: list[tuple[str, str]] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "OPERATIONS" not in names or not isinstance(node.value, (ast.Tuple, ast.List)):
            continue
        for element in node.value.elts:
            if isinstance(element, ast.Tuple) and len(element.elts) >= 2:
                first, second = element.elts[0], element.elts[1]
                if isinstance(first, ast.Constant) and isinstance(first.value, str) \
                        and isinstance(second, ast.Constant) and isinstance(second.value, str):
                    found.append((first.value, second.value))
    return found


def dict_keys_in_function(pkg: Path, func_name: str) -> tuple[set[str], set[str]]:
    """返回 (该函数里的字典键, 它调用的同模块 helper 名)。"""
    tree = ast.parse(pkg.read_text(encoding="utf-8"))
    keys: set[str] = set()
    calls: set[str] = set()
    targets = [n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == func_name]
    for target in targets:
        for node in ast.walk(target):
            if isinstance(node, ast.Dict):
                for key in node.keys:
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        keys.add(key.value)
                    elif isinstance(key, ast.Name):
                        keys.add(f"<{key.id}>")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                calls.add(node.func.id)
    return keys, calls


def helper_keys(pkg: Path, helper: str) -> set[str]:
    keys, _ = dict_keys_in_function(pkg, helper)
    return keys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "test/reports/round9/output-field-matrix.json"))
    parser.add_argument("--md", default=str(ROOT / "test/reports/round9/output-field-matrix.md"))
    parser.add_argument("--evidence-dir", default=str(ROOT / "test/artifacts/evidence/round9"),
                        help="本轮证据目录（扫其中 JSON 判断字段是否真的出现在返回体里，用于把"
                             "「真缺口」与「内部键/错误码」分开）")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    test_files = iter_test_files()
    contents = {p: p.read_text(encoding="utf-8", errors="replace") for p in test_files}
    live_files = [p for p in test_files
                  if p.as_posix().find("/live/") >= 0 or p.as_posix().find("/semi/") >= 0]
    evidence_dir = Path(args.evidence_dir)
    evidence_text = ""
    evidence_files = 0
    if evidence_dir.is_dir():
        for path in sorted(evidence_dir.rglob("*.json")):
            try:
                evidence_text += path.read_text(encoding="utf-8", errors="replace")
                evidence_files += 1
            except OSError:
                continue

    rows: list[dict] = []
    ops_total = 0
    for pkg in sorted(SRC.glob("*.py")):
        for op, handler in operations(pkg):
            ops_total += 1
            keys, calls = dict_keys_in_function(pkg, handler)
            for helper in sorted(calls)[:8]:   # 排序后取前 8 个：保证多次运行结果稳定
                keys |= helper_keys(pkg, helper)
            fields = sorted(set(keys) - {"op", "name", "kind"} | set(ENVELOPE))
            # TB 里 op 常常是「包前缀常量 + 短名」拼出来的（例如 cellview TB 的 `OP + "lib.rename"`），
            # 所以除了全名，还要按短名统计（取最后两段，如 `lib.rename`）。
            short = ".".join(op.split(".")[-2:])
            def count_sites(text: str) -> int:
                return (text.count(f'"{op}"') + text.count(f"'{op}'")
                        + text.count(f'"{short}"') + text.count(f"'{short}'"))
            op_sites = sum(count_sites(text) for text in contents.values())
            live_sites = sum(count_sites(text)
                             for path, text in contents.items() if path in live_files)
            for field in fields:
                literal = f'"{field}"'
                hits = [p for p, t in contents.items() if literal in t or f"'{field}'" in t]
                asserted = []
                read_only = []
                for path in hits:
                    for line in contents[path].splitlines():
                        if field not in line:
                            continue
                        (asserted if ASSERT_HINT.search(line) else read_only).append(
                            f"{path.relative_to(ROOT).as_posix()}:{line.strip()[:80]}")
                status = "asserted" if asserted else ("read_only" if read_only else "absent")
                known = KNOWN_ASSERTED.get((op, field))
                if known and status != "asserted":
                    status = "asserted"
                    asserted = [f"<known-non-inline> {known}"]
                in_evidence = bool(evidence_text) and (literal in evidence_text
                                                       or f"'{field}'" in evidence_text)
                rows.append({
                    "op": op,
                    "module": pkg.name,
                    "handler": handler,
                    "field": field,
                    "status": status,
                    "in_round_evidence": in_evidence,
                    "asserted_examples": asserted[:3],
                    "read_only_examples": read_only[:2],
                    "op_call_sites": op_sites,
                    "op_live_semi_call_sites": live_sites,
                })

    by_status: dict[str, int] = {}
    for row in rows:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
    absent_by_op: dict[str, list[str]] = {}
    real_gaps: dict[str, list[str]] = {}
    for row in rows:
        if row["status"] != "asserted":
            absent_by_op.setdefault(row["op"], []).append(row["field"])
            if row["in_round_evidence"]:
                real_gaps.setdefault(row["op"], []).append(row["field"])
    no_live = sorted({row["op"] for row in rows if row["op_live_semi_call_sites"] == 0})

    doc = {
        "method": "AST 抽 op 处理函数的字典键 + 扫 test/ 断言行（静态近似；口径见脚本 docstring）",
        "ops_total": ops_total,
        "fields_total": len(rows),
        "by_status": by_status,
        "evidence_files_scanned": evidence_files,
        "real_gap_candidates": {k: sorted(set(v)) for k, v in sorted(real_gaps.items())},
        "ops_without_live_semi_call_site": no_live,
        "fields_not_asserted_by_op": {k: sorted(set(v)) for k, v in sorted(absent_by_op.items())},
        "rows": rows,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    top = sorted(absent_by_op.items(), key=lambda kv: -len(set(kv[1])))[:15]
    lines = [
        "# op × 输出字段矩阵（表 C 第一版 · 静态近似）",
        "",
        f"> 工具：`test/shared/runners/build_output_field_matrix.py`｜op **{ops_total}** 个 / 字段行 **{len(rows)}** 条",
        f"> 状态分布：`{json.dumps(by_status, ensure_ascii=False)}`"
        "（asserted=有断言行命中；read_only=只在读取/证据里出现；absent=测试树里没出现）",
        "",
        "## 1. 未断言字段最多的 op（Top 15）",
        "",
        "| op | 未断言字段数 | 字段 |",
        "|---|---|---|",
    ]
    for op, fields in top:
        lines.append(f"| `{op}` | {len(set(fields))} | {', '.join(sorted(set(fields))[:12])} |")
    lines += [
        "",
        "## 1b. 真缺口候选（本轮证据里**真的出现过**该字段、但 TB 没断言）",
        "",
        f"> 扫描证据：`{evidence_dir.relative_to(ROOT).as_posix()}`（{evidence_files} 个 JSON）",
        "",
        "| op | 字段 |",
        "|---|---|",
    ]
    for op, fields in sorted(real_gaps.items()):
        lines.append(f"| `{op}` | {', '.join(sorted(set(fields)))} |")
    if not real_gaps:
        lines.append("| — | （无） |")
    lines += [
        "",
        "## 2. live/semi 无调用点的 op（没有真机/半真机执行证据）",
        "",
        (", ".join(f"`{op}`" for op in no_live) if no_live else "（无）"),
        "",
        "## 3. 口径与局限",
        "",
        "* 本表是**静态近似**：`asserted` 只表示「断言行里出现了该字段名」，不等于判据强度达标；",
        "  `read_only` 与 `absent` 都算「**未逐项比对**」，需要补 TB 断言或立「读回面/参数裁决」卡；",
        "* 字典键会包含「请求回显」字段（多报），helper 只跟一层（可能漏报）；下一版按 op 逐个复核；",
        "* 真机行为证据仍以各 TB 的证据 JSON 为准；本表只负责把「待比对字段」缩到可人工复核的规模。",
    ]
    md = Path(args.md)
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"op {ops_total} 个 / 字段行 {len(rows)} 条 / 状态 {by_status}")
    print(f"live-semi 无调用点 op：{len(no_live)}")
    print(f"json: {out}\nmd:   {md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
