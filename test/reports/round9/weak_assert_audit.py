"""round9 断言强度审计（只读静态分析）。

两套 TB 风格都要覆盖：

* unittest 风格（offline）：`self.assertEqual/assertIn/assertTrue/...`；
* 脚本风格（live/semi）：`_check(cond, msg)`、`_expect(...)`、`if not cond: raise AssertionError(...)`。

强度分级（保守，宁可判弱）：

* ``strong``：条件里出现"具体期望值"的比较（字面量 ==/!=、数值区间、`in ("a",...)` 字面量集合、
  startswith/endswith 字面量、正则）或 `assertRaises`/错误码断言；
* ``weak``：只验真值/存在/`ok`/`isinstance`/`len>0`/`!= None`；
* ``medium``：其余（如与变量比较、集合比较但无法判定字面量）。

用法：``python test/reports/round9/weak_assert_audit.py``
"""
from __future__ import annotations

import ast
import json
import pathlib
import re
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = pathlib.Path(__file__).resolve().parent
DIRS = ("test/offline", "test/semi", "test/live")

CHECK_HELPERS = re.compile(r"^_{0,2}(check|expect|assert|require|verify|ensure)_?\w*$")
CASE_NAME = re.compile(r"(^|_)(case|stage|probe|test)\w*|^test_|^main$")
STRONG_CALLS = {
    "assertEqual", "assertNotEqual", "assertIn", "assertNotIn", "assertAlmostEqual",
    "assertGreater", "assertGreaterEqual", "assertLess", "assertLessEqual",
    "assertRaises", "assertRaisesRegex", "assertRegex", "assertCountEqual",
    "assertListEqual", "assertDictEqual", "assertSetEqual", "assertTupleEqual",
    "assertSequenceEqual", "assertMultiLineEqual", "assertLogs",
}
WEAK_CALLS = {"assertTrue", "assertFalse", "assertIsNone", "assertIsNotNone", "assertIs",
              "assertIsNot", "assertIsInstance", "assertNotIsInstance", "fail"}
LITERAL = r"""(?:["'][^"']*["']|\d+(?:\.\d+)?|True|False|None|\[|\{|\()"""


def _txt(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return re.sub(r"\s+", " ", ast.unparse(node))
    except Exception:  # noqa: BLE001
        return ""


def classify_condition(text: str) -> str:
    if not text:
        return "weak"
    # 明确的字面量比较 / 区间 / 取值集合 → strong
    if re.search(rf"(==|!=)\s*{LITERAL}", text):
        return "strong"
    if re.search(rf"{LITERAL}\s*(==|!=)", text):
        return "strong"
    if re.search(r"(>=|<=|>|<)\s*[\w.\"']", text):
        return "strong"
    if re.search(r"\b(startswith|endswith|fullmatch|match)\([" "']", text):
        return "strong"
    if re.search(r"\bin\s*[\(\[]\s*[\"']", text):
        return "strong"
    if re.search(r"\bin\s+\w*_?(CODES|SET|VALID|ALLOWED)\w*", text):
        return "strong"
    # 只验真值/存在/类型/长度 → weak
    if re.fullmatch(r"[\w.\[\]\"'()]+", text) or text.endswith(".ok"):
        return "weak"
    if re.search(r"\b(isinstance|len)\(|!= None|is not None|is None\b", text) and not re.search(r"(==|!=)\s*[\"'\d]", text):
        return "weak"
    if re.search(r"\.get\([\"']ok[\"']\)|\bok\b\s*$", text):
        return "weak"
    return "medium"


class CaseCollector(ast.NodeVisitor):
    """收集一个文件里每个用例函数内的断言点。"""

    def __init__(self, src: str):
        self.src = src
        self.cases: dict[str, list[dict]] = defaultdict(list)
        self.stack: list[str] = []
        self.strong_helpers: set[str] = set()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self.stack.append(node.name)
        for child in node.body:
            self.visit(child)
        self.stack.pop()

    def _record(self, strength: str, text: str, lineno: int, kind: str) -> None:
        case = self.stack[-1] if self.stack else "<module>"
        self.cases[case].append({"strength": strength, "kind": kind,
                                 "text": text[:160], "line": lineno})

    def visit_Assert(self, node: ast.Assert) -> None:  # noqa: N802
        self._record(classify_condition(_txt(node.test)), _txt(node.test), node.lineno, "assert")
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> None:  # noqa: N802
        exc = node.exc
        name = _txt(exc.func if isinstance(exc, ast.Call) else exc)
        if "AssertionError" in name:
            # 常见形态：if not cond: raise AssertionError → 用外层 if 条件判强度
            cond = ""
            parent_if = getattr(node, "_parent_if", None)
            if parent_if is not None:
                cond = _txt(parent_if.test)
                if cond.startswith("not "):
                    pass
            self._record(classify_condition(cond), cond or _txt(node), node.lineno, "raise")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        func = node.func
        recv = func.value.id if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) else ""
        name = func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else "")
        # Evidence.check(case, name, expected, actual) / check_true(case, name, cond, actual)
        if name == "check" and len(node.args) >= 4:
            text = f"expected={_txt(node.args[2])} actual={_txt(node.args[3])}"
            self._record("strong", text, node.lineno, f"evidence:{recv}.check")
            self.generic_visit(node)
            return
        if name == "check_true" and len(node.args) >= 3:
            self._record(classify_condition(_txt(node.args[2])), _txt(node.args[2]),
                         node.lineno, f"evidence:{recv}.check_true")
            self.generic_visit(node)
            return
        # 形状：require(results, label, condition, **detail) —— 条件在 index 2
        if name in ("require", "expect", "verify") and len(node.args) >= 3:
            self._record(classify_condition(_txt(node.args[2])), _txt(node.args[2]),
                         node.lineno, f"helper:{name}")
            self.generic_visit(node)
            return
        # 断言藏在本地/实例 helper 里（如 _check_png / Stage.ok）：由 helper 强断言表补记
        if name in self.strong_helpers:
            self._record("strong", f"via helper {name}()", node.lineno, "helper-body")
            self.generic_visit(node)
            return
        if name == "check" and len(node.args) >= 2 and node.args[1:]:
            # offline 形状：check(expr, *needles) —— needles 是期望子串
            text = f"{_txt(node.args[0])} contains {[_txt(a) for a in node.args[1:]]}"
            self._record("strong", text, node.lineno, "helper:check")
            self.generic_visit(node)
            return
        short = name.split("assert")[-1] if name.startswith("assert") else name
        if name.startswith("assert") and short:
            if short in STRONG_CALLS or name in STRONG_CALLS:
                text = ", ".join(_txt(a) for a in node.args[:2])
                self._record("strong", text, node.lineno, "unittest:" + name)
            elif short in WEAK_CALLS or name in WEAK_CALLS:
                text = ", ".join(_txt(a) for a in node.args[:2])
                strength = classify_condition(_txt(node.args[0]) if node.args else "")
                self._record(strength, text, node.lineno, "unittest:" + name)
        elif CHECK_HELPERS.match(name) and node.args:
            self._record(classify_condition(_txt(node.args[0])), _txt(node.args[0]),
                         node.lineno, "helper:" + name)
        self.generic_visit(node)


def annotate_parents(tree: ast.AST) -> None:
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            child._parent = parent  # type: ignore[attr-defined]


def main() -> int:
    files: dict[str, dict] = {}
    for rel in DIRS:
        for path in (ROOT / rel).rglob("*.py"):
            src = path.read_text(encoding="utf-8", errors="replace")
            try:
                tree = ast.parse(src)
            except SyntaxError:
                files[path.relative_to(ROOT).as_posix()] = {"error": "syntax"}
                continue
            annotate_parents(tree)
            # 把 raise 挂到外层 if
            for parent in ast.walk(tree):
                if isinstance(parent, ast.If):
                    for stmt in parent.body:
                        stmt._parent_if = parent  # type: ignore[attr-defined]
            # 第一遍：找出"体内含强断言"的 helper（断言藏在 helper 里的情况）
            probe = CaseCollector(src)
            probe.visit(tree)
            strong_helpers = {name for name, items in probe.cases.items()
                              if any(i["strength"] == "strong" for i in items)}
            # 第二遍：正式收集（带上 helper 强断言表）
            collector = CaseCollector(src)
            collector.strong_helpers = strong_helpers
            collector.visit(tree)
            cases = {name: items for name, items in collector.cases.items() if items}
            # 日志读取但未被断言的用例：看用例源码段落里是否读了 log/CDSlog，而断言文本里没提日志
            segments: dict[str, str] = {}
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.end_lineno:
                    segments[node.name] = "\n".join(src.splitlines()[node.lineno - 1:node.end_lineno])
            log_cases = []
            for name, items in cases.items():
                body = segments.get(name, "")
                reads_log = bool(re.search(r'CDSlog|\[["\']log["\']\]|\.get\(["\']log["\']\)', body))
                asserts_log = any(re.search(r"log", i["text"], re.I) for i in items)
                if reads_log and not asserts_log:
                    log_cases.append(name)
            files[path.relative_to(ROOT).as_posix()] = {"cases": cases, "log_unasserted": log_cases}
    totals = Counter()
    weak_only = []
    log_unasserted = []
    for rel, info in sorted(files.items()):
        if "cases" not in info:
            continue
        for case, items in info["cases"].items():
            if not CASE_NAME.search(case):
                continue  # 只看用例/探针/阶段函数，跳过 helper 与基础设施
            strengths = Counter(i["strength"] for i in items)
            totals.update(strengths)
            if strengths["strong"] == 0 and strengths["medium"] == 0 and strengths["weak"] > 0:
                weak_only.append({"file": rel, "case": case, "weak": strengths["weak"],
                                  "sample": items[0]["text"]})
            if case in info.get("log_unasserted", []):
                log_unasserted.append(f"{rel}:{case}")
    doc = {
        "method": "AST：断言点=assert / raise AssertionError（挂外层 if）/ self.assert* / _check|_expect|... helper 首参",
        "caveat": "强度是静态启发式；medium/weak 需人工复核，报告只把弱断言当线索",
        "totals": dict(totals),
        "weak_only_cases": sorted(weak_only, key=lambda x: -x["weak"]),
        "log_read_but_unasserted": log_unasserted,
        # 只留每文件的计数与弱断言明细，避免artifact 体积过大（全量明细可由脚本随时重算）
        "files": {
            k: {
                "counts": dict(Counter(i["strength"] for items in i["cases"].values() for i in items)),
                "weak_only": sorted(c for c, items in i["cases"].items()
                                    if CASE_NAME.search(c)
                                    and not any(x["strength"] in ("strong", "medium") for x in items)),
                "log_unasserted": i.get("log_unasserted", []),
            }
            for k, i in files.items() if "cases" in i
        },
    }
    (OUT / "weak-assert-audit.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"断言点 {sum(totals.values())}：strong {totals['strong']} / medium {totals['medium']} "
          f"/ weak {totals['weak']}；仅弱断言用例 {len(weak_only)}；日志未断言 {len(log_unasserted)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
