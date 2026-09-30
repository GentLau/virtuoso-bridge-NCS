"""round9 嵌套键覆盖审计（只读静态分析）。

顶层 op×参数矩阵（build_op_param_matrix.py）只能看到 Request 的顶层字段；
但 `commands: list[dict]` / `tasks: list[dict]` / `metrics: list[dict]` 这类
**嵌套映射**才是大量用户可传输入的真正入口。本脚本：

1. 从实现里抽「命令字典的合法键空间」：dispatch 分支的 op 字面量 + 常量集合
   （如 layout 的 `_PLACE_ATOMS`），以及每个分支读到的 `command.get("f")` 字段；
2. 扫全部 TB，统计每个 (op, 字段) 字面量是否出现过；
3. 输出 JSON + Markdown 报告（报告由人写，本脚本只产出机器结论）。

用法：`python test/reports/round9/nested_key_audit.py`
"""
from __future__ import annotations

import ast
import json
import pathlib
import re
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = pathlib.Path(__file__).resolve().parent

#: 带嵌套映射参数的 (包文件, 方法名) —— 由 Request 模型的字段类型扫描得到
TARGETS = {
    "layout.py": {"write", "display"},
    "schematic.py": {"write"},
    "symbol.py": {"write"},
    "verilog.py": {"write"},
    "veriloga.py": {"write"},
    "maestro.py": {"write", "write_history"},
    "spectre.py": {"run", "measure"},
}

CMD_VARS = ("command", "cmd", "item", "entry", "task", "metric")


def module_const_sets(tree: ast.Module, cls_tree: ast.Module | None = None) -> dict[str, set[str]]:
    """收集 `NAME = ("a", "b")` / `NAME = {"a"}` 形式的常量集合。"""
    out: dict[str, set[str]] = {}

    def scan(body: list[ast.stmt]) -> None:
        for node in body:
            targets = []
            value = None
            if isinstance(node, ast.Assign):
                targets, value = node.targets, node.value
            elif isinstance(node, ast.AnnAssign):
                targets, value = [node.target], node.value
            if not targets or value is None:
                continue
            if isinstance(value, (ast.Tuple, ast.List, ast.Set)):
                vals = {
                    elt.value
                    for elt in value.elts
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                }
                if vals and len(vals) == len(value.elts):
                    for t in targets:
                        if isinstance(t, ast.Name):
                            out[t.id] = vals

    scan(tree.body)
    if cls_tree is not None:
        scan(cls_tree.body)
    return out


class CommandCollector:
    """按 op 守卫收集 `command.get("f")` 字段；守卫上下文向下继承。"""

    TRANSPARENT = (ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try)

    def __init__(self, const_sets: dict[str, set[str]], op_var: str, cmd_vars: set[str],
                 func_ops: set[str] | None = None):
        self.const_sets = const_sets
        self.op_var = op_var
        self.cmd_vars = cmd_vars
        self.func_ops = func_ops          # 该函数整体归属的 op（来自 dispatch 调用点）
        self.pairs: set[tuple[str, str]] = set()
        self.op_names: set[str] = set(self.func_ops or ())
        self.any_fields: set[str] = set()  # 未落在任何 op 守卫内的字段

    # -- guard helpers -----------------------------------------------------
    @staticmethod
    def guard_ops(test: ast.AST, op_var: str, const_sets: dict[str, set[str]]) -> set[str] | None:
        """把 `op == "x"` / `op in ("a","b")` / `op in _SET` 解析成 op 集合。"""
        if isinstance(test, ast.Compare) and len(test.ops) == 1:
            left = test.left
            if isinstance(left, ast.Name) and left.id == op_var:
                right = test.comparators[0]
                if isinstance(test.ops[0], (ast.Eq, ast.Is)) and isinstance(right, ast.Constant):
                    return {right.value} if isinstance(right.value, str) else None
                if isinstance(test.ops[0], ast.In):
                    if isinstance(right, (ast.Tuple, ast.List, ast.Set)):
                        vals = {
                            e.value for e in right.elts
                            if isinstance(e, ast.Constant) and isinstance(e.value, str)
                        }
                        return vals or None
                    if isinstance(right, ast.Name) and right.id in const_sets:
                        return set(const_sets[right.id])
        return None

    # -- field collection --------------------------------------------------
    def _record_fields(self, node: ast.AST, ops: set[str] | None) -> None:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                if sub.func.attr == "get" and isinstance(sub.func.value, ast.Name):
                    if sub.func.value.id in self.cmd_vars and sub.args:
                        key = sub.args[0]
                        if isinstance(key, ast.Constant) and isinstance(key.value, str):
                            self._record(ops, key.value)
            if isinstance(sub, ast.Subscript) and isinstance(sub.value, ast.Name):
                if sub.value.id in self.cmd_vars:
                    sl = sub.slice
                    if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                        self._record(ops, sl.value)

    def _record(self, ops: set[str] | None, field: str) -> None:
        effective = ops if ops is not None else self.func_ops
        if effective is None:
            self.any_fields.add(field)
            return
        self.op_names |= effective
        for op in effective:
            self.pairs.add((op, field))

    def finalize(self) -> None:
        """未落在守卫内的字段属于该函数覆盖到的全部 op。"""
        for op in self.op_names:
            for field in self.any_fields:
                self.pairs.add((op, field))

    # -- traversal ---------------------------------------------------------
    def walk(self, stmts: list[ast.stmt], ctx: set[str] | None) -> None:
        for stmt in stmts:
            if isinstance(stmt, ast.If):
                guard = self.guard_ops(stmt.test, self.op_var, self.const_sets)
                inner = guard if guard is not None else ctx
                self.walk(stmt.body, inner)
                self.walk(stmt.orelse, ctx)
                continue
            if isinstance(stmt, ast.Match):
                for case in stmt.cases:
                    ops: set[str] | None = None
                    if isinstance(case.pattern, ast.MatchValue) and isinstance(case.pattern.value, ast.Constant):
                        if isinstance(case.pattern.value.value, str):
                            ops = {case.pattern.value.value}
                    self.walk(case.body, ops if ops is not None else ctx)
                continue
            if isinstance(stmt, self.TRANSPARENT):
                for field_name in ("body", "orelse", "finalbody"):
                    sub = getattr(stmt, field_name, None)
                    if sub:
                        self.walk(sub, ctx)
                for handler in getattr(stmt, "handlers", []) or []:
                    self.walk(handler.body, ctx)
                continue
            # 普通语句：先收字段（按当前 ctx），再看内部是否还有 op 守卫
            self._record_fields(stmt, ctx)
        # 说明：字段收集用 ast.walk（含分支内部），守卫归属用 ctx 栈，够用且保守


def op_var_of(func: ast.FunctionDef, cmd_vars: set[str]) -> str | None:
    if any(a.arg == "op" for a in func.args.args):
        return "op"
    for node in ast.walk(func):
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        ok = False
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute):
            ok = (
                value.func.attr == "get"
                and isinstance(value.func.value, ast.Name)
                and value.func.value.id in cmd_vars
                and bool(value.args)
                and isinstance(value.args[0], ast.Constant)
                and value.args[0].value == "op"
            )
        elif isinstance(value, ast.Subscript) and isinstance(value.value, ast.Name):
            ok = (
                value.value.id in cmd_vars
                and isinstance(value.slice, ast.Constant)
                and value.slice.value == "op"
            )
        if ok:
            for t in node.targets:
                if isinstance(t, ast.Name):
                    return t.id
    return None


def declared_ops(func: ast.FunctionDef, cmd_vars: set[str]) -> set[str]:
    """`command.get("op") not in ("a","b")` 这类白名单也是实现的合法 op 空间。"""
    out: set[str] = set()
    for node in ast.walk(func):
        if not isinstance(node, ast.Compare) or len(node.ops) != 1:
            continue
        left = node.left
        if not (isinstance(left, ast.Call) and isinstance(left.func, ast.Attribute)):
            continue
        if left.func.attr != "get" or not isinstance(left.func.value, ast.Name):
            continue
        if left.func.value.id not in cmd_vars or not left.args:
            continue
        key = left.args[0]
        if not (isinstance(key, ast.Constant) and key.value == "op"):
            continue
        right = node.comparators[0]
        if isinstance(right, (ast.Tuple, ast.List, ast.Set)):
            out |= {
                e.value for e in right.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            }
    return out


def analyse_module(path: pathlib.Path) -> tuple[dict[str, set[str]], list[dict], dict[str, set[str]]]:
    """返回 (op -> 字段集合, 未归属 helper 列表, 常量集合)。"""
    src = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(src)
    const_sets = module_const_sets(tree)
    for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
        const_sets.update(module_const_sets(ast.Module(body=[], type_ignores=[]), cls))

    funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]

    # 1) dispatch 分支 → 被调用 handler 的 op 归属
    handler_ops: dict[str, set[str]] = {}
    for func in funcs:
        params = {a.arg for a in func.args.args}
        cmd_vars = params & set(CMD_VARS)
        # 命令字典常常来自循环变量（`for index, command in enumerate(request.commands)`）
        for node in ast.walk(func):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                if node.id in CMD_VARS:
                    cmd_vars.add(node.id)
        if not cmd_vars:
            continue
        op_var = op_var_of(func, cmd_vars)
        if op_var is None:
            continue
        declared = declared_ops(func, cmd_vars)
        guards_seen: set[str] = set()
        for node in ast.walk(func):
            if isinstance(node, ast.If):
                g = CommandCollector.guard_ops(node.test, op_var, const_sets)
                if g:
                    guards_seen |= g
        for node in ast.walk(func):
            if not isinstance(node, ast.If):
                continue
            guard = CommandCollector.guard_ops(node.test, op_var, const_sets)
            if not guard:
                continue
            for body, ops in ((node.body, guard), (node.orelse, declared - guards_seen)):
                if not ops:
                    continue
                for sub in ast.walk(ast.Module(body=body, type_ignores=[])):
                    if (
                        isinstance(sub, ast.Call)
                        and isinstance(sub.func, ast.Attribute)
                        and isinstance(sub.func.value, ast.Name)
                        and sub.func.value.id == "self"
                    ):
                        handler_ops.setdefault(sub.func.attr, set()).update(ops)

    # 2) 逐函数收集字段
    results: dict[str, set[str]] = defaultdict(set)
    helpers: list[dict] = []
    for func in funcs:
        params = {a.arg for a in func.args.args}
        cmd_vars = params & set(CMD_VARS)
        for node in ast.walk(func):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                if node.id in CMD_VARS:
                    cmd_vars.add(node.id)
        if not cmd_vars:
            continue
        op_var = op_var_of(func, cmd_vars)
        func_ops = set(handler_ops.get(func.name) or ()) | declared_ops(func, cmd_vars) or None
        if op_var is None and not func_ops:
            # 只认 spectre 的 `tasks[]` / `metrics[]` 这类真正的用户输入记录；
            # `item`/`entry` 多是实现内部的循环变量，易造成假面。
            record_vars = cmd_vars & {"task", "metric"}
            if record_vars:
                collector = CommandCollector(const_sets, "__none__", record_vars, None)
                collector.walk(func.body, None)
                fields = sorted({f for _op, f in collector.pairs} | collector.any_fields)
                for var in sorted(record_vars):
                    for field in fields:
                        results[f"<{var}[]>"].add(field)
                continue
            collector = CommandCollector(const_sets, "__none__", cmd_vars, None)
            collector.walk(func.body, None)
            fields = sorted({f for _op, f in collector.pairs} | collector.any_fields)
            if fields:
                helpers.append({"function": func.name, "fields": fields,
                                "note": "子判别/匹配 helper（按 kind 等二级键分支），未做 op 归属"})
            continue
        collector = CommandCollector(const_sets, op_var or "__none__", cmd_vars, func_ops)
        collector.walk(func.body, func_ops)
        collector.finalize()
        for op, field in collector.pairs:
            results[op].add(field)
    return results, helpers, const_sets


def tb_literals() -> dict[str, set[str]]:
    """每个 TB 文件里出现过的字符串字面量 / 关键字名（AST 精确，而非子串）。"""
    out: dict[str, set[str]] = {}
    for rel in ("test/offline", "test/semi", "test/live", "test/shared"):
        for p in (ROOT / rel).rglob("*.py"):
            text = p.read_text(encoding="utf-8", errors="replace")
            lits: set[str] = set()
            try:
                tree = ast.parse(text)
            except SyntaxError:
                out[p.relative_to(ROOT).as_posix()] = lits
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    lits.add(node.value)
                elif isinstance(node, ast.keyword) and node.arg:
                    lits.add(node.arg)
            out[p.relative_to(ROOT).as_posix()] = lits
    return out


ENUM_NAME_RE = re.compile(r"(KINDS|TYPES|ATOMS|MODES|OPERATIONS|SECTIONS|FOCUS|LAYERS)$")


def main() -> int:
    impl = ROOT / "src" / "pyapi" / "packages"
    parsed: dict[str, dict] = {}
    helpers_doc: dict[str, list] = {}
    enum_sets: dict[str, dict[str, set[str]]] = {}
    all_fields: set[str] = set()
    for fname in TARGETS:
        ops, helpers, const_sets = analyse_module(impl / fname)
        parsed[fname] = {op: sorted(fields) for op, fields in sorted(ops.items())}
        helpers_doc[fname] = helpers
        enums = {
            name: vals for name, vals in const_sets.items()
            if ENUM_NAME_RE.search(name) and len(vals) >= 2
        }
        if enums:
            enum_sets[fname] = enums
        for fields in ops.values():
            all_fields |= fields

    lits = tb_literals()
    hits: dict[str, list[str]] = defaultdict(list)
    for rel, values in lits.items():
        for field in all_fields & values:
            hits[field].append(rel)

    report = {}
    for fname, ops in parsed.items():
        entry = {}
        for op, fields in ops.items():
            rows = [{"field": f, "covered": bool(hits.get(f)),
                     "tb_files": sorted(hits.get(f, []))[:5]} for f in fields]
            entry[op] = {"fields": rows, "gaps": [r["field"] for r in rows if not r["covered"]]}
        report[fname] = entry

    enum_report = {
        fname: {
            name: [{"value": v, "covered": v in {x for vs in lits.values() for x in vs},
                    "tb_files": sorted(rel for rel, vs in lits.items() if v in vs)[:4]}
                   for v in sorted(vals)]
            for name, vals in enums.items()
        }
        for fname, enums in enum_sets.items()
    }

    all_ops = sum(len(entry) for entry in report.values())
    uncovered = sorted({r["field"] for entry in report.values()
                        for info in entry.values() for r in info["fields"] if not r["covered"]})
    enum_gaps = sorted({f"{fname}:{name}:{row['value']}" for fname, names in enum_report.items()
                        for name, rows in names.items() for row in rows if not row["covered"]})
    doc = {
        "method": "AST：dispatch 分支 op 字面量/常量集合 + 分支内 command.get() 字段（守卫上下文继承 + handler→op 归属）；TB 端用 AST 字符串字面量精确匹配",
        "caveat": "字面量出现≠断言语义；只用于找『从未被任何 TB 触碰过的嵌套键』",
        "totals": {"command_ops": all_ops, "fields": len(all_fields),
                   "uncovered_fields": len(uncovered),
                   "enum_values": sum(len(v) for names in enum_report.values() for v in names.values()),
                   "uncovered_enum_values": len(enum_gaps)},
        "uncovered_field_list": uncovered,
        "uncovered_enum_list": enum_gaps,
        "helpers_without_op_mapping": helpers_doc,
        "report": report,
        "enum_report": enum_report,
    }
    (OUT / "nested-key-audit.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    lines = ["# 嵌套键覆盖（机器结论，脚本生成）", "",
             f"- 目标包 {len(TARGETS)}；命令 op {all_ops} 个；字段 {len(all_fields)} 条；"
             f"**从未被任何 TB 触碰的字段 {len(uncovered)} 条**",
             f"- 二级枚举值（`*_KINDS`/`*_TYPES` 等）：未覆盖 {len(enum_gaps)} 个",
             "", "| 包 | 命令 op | 字段数 | 未被 TB 触碰 |", "|---|---|---|---|"]
    for fname, entry in report.items():
        for op, info in sorted(entry.items()):
            gaps = " ".join(f"`{g}`" for g in info["gaps"]) or "—"
            lines.append(f"| {fname} | `{op}` | {len(info['fields'])} | {gaps} |")
    if enum_gaps:
        lines += ["", "## 未覆盖的二级枚举值", ""]
        lines += [f"- `{x}`" for x in enum_gaps]
    if uncovered:
        lines += ["", "## 未被任何 TB 触碰的字段（全量）", ""]
        lines += [f"- `{x}`" for x in uncovered]
    (OUT / "nested-key-audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"命令 op {all_ops}；字段 {len(all_fields)}；未被触碰字段 {len(uncovered)}；"
          f"未覆盖枚举值 {len(enum_gaps)} -> nested-key-audit.md/json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
